const { app, BrowserWindow, clipboard, dialog, ipcMain, safeStorage, screen, session, shell, systemPreferences } = require('electron');
const { execFile, spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

app.setName('Open Knowledge Agent');

let mainWindow;
let projectPath = process.env.OPEN_KNOWLEDGE_AGENT_BACKEND || '';
let knowledgeParentPath = '';
let compactPosition = null;
let compact = true;
let chatgpt;
let chatgptUsageUrl = 'https://chatgpt.com/settings/usage';
let chatgptSession = { status: 'disconnected', sharing: false };
let chatgptModels = [];
let selectedModel = '';
let authBusy = false;
let githubState = { available: false, connected: false, busy: false };
let speechProcess;

const COMPACT_SIZE = { width: 210, height: 190 };
const EXPANDED_SIZE = { width: 900, height: 760 };

function configPath() {
  return path.join(app.getPath('userData'), 'config.json');
}

function loadConfig() {
  try {
    const config = JSON.parse(fs.readFileSync(configPath(), 'utf8'));
    if (config.projectPath) projectPath = config.projectPath;
    if (config.selectedModel) selectedModel = config.selectedModel;
    if (config.knowledgeParentPath) knowledgeParentPath = config.knowledgeParentPath;
    if (Array.isArray(config.compactPosition) && config.compactPosition.length === 2) compactPosition = config.compactPosition;
  } catch (_) {}
}

function saveConfig() {
  fs.mkdirSync(path.dirname(configPath()), { recursive: true });
  fs.writeFileSync(configPath(), JSON.stringify({ projectPath, selectedModel, knowledgeParentPath, compactPosition }, null, 2));
}

function configuredKnowledgeRoot() {
  return knowledgeParentPath ? path.join(knowledgeParentPath, 'Open Knowledge Agent Knowledge') : '';
}

function copyMissing(source, destination) {
  if (!fs.existsSync(source)) return;
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const from = path.join(source, entry.name);
    const to = path.join(destination, entry.name);
    if (entry.isDirectory()) copyMissing(from, to);
    else if (!fs.existsSync(to)) fs.copyFileSync(from, to);
  }
}

function githubCliPath() {
  const candidates = [
    path.join(process.resourcesPath, 'app', 'vendor', 'gh', 'gh'),
    path.join(__dirname, '..', 'vendor', 'gh', 'gh'),
    '/opt/homebrew/bin/gh',
    '/usr/local/bin/gh'
  ];
  return candidates.find(candidate => fs.existsSync(candidate));
}

function speechHelperPath() {
  const candidates = [
    path.join(process.resourcesPath, 'app', 'native', 'Open Knowledge Agent Voice.app', 'Contents', 'MacOS', 'SpeechHelper'),
    path.join(process.resourcesPath, 'app', 'native', 'SpeechHelper'),
    path.join(__dirname, '..', 'native', 'SpeechHelper')
  ];
  return candidates.find(candidate => fs.existsSync(candidate));
}

function imageTextHelperPath() {
  const candidates = [
    path.join(process.resourcesPath, 'app', 'native', 'Open Knowledge Agent Voice.app', 'Contents', 'MacOS', 'ImageTextHelper'),
    path.join(__dirname, '..', 'native', 'ImageTextHelper')
  ];
  return candidates.find(candidate => fs.existsSync(candidate));
}

function extractImageText(dataUrl) {
  return new Promise((resolve, reject) => {
    const match = /^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$/.exec(String(dataUrl));
    if (!match) return reject(new Error('Paste a PNG, JPEG, or WebP image.'));
    const bytes = Buffer.from(match[2], 'base64');
    if (!bytes.length || bytes.length > 10 * 1024 * 1024) {
      return reject(new Error('Pasted images must be smaller than 10 MB.'));
    }
    const helper = imageTextHelperPath();
    if (!helper) return reject(new Error('The local image text component is missing. Rebuild the app.'));
    const extension = match[1] === 'jpeg' ? 'jpg' : match[1];
    const imagePath = path.join(os.tmpdir(), `open-knowledge-image-${Date.now()}-${process.pid}.${extension}`);
    fs.writeFileSync(imagePath, bytes, { mode: 0o600 });
    execFile(helper, [imagePath], { maxBuffer: 4 * 1024 * 1024, timeout: 60_000 }, (error, stdout, stderr) => {
      try { fs.unlinkSync(imagePath); } catch (_) {}
      try {
        const payload = JSON.parse(stdout || '{}');
        if (payload.error) return reject(new Error(payload.error));
        if (error) return reject(new Error((stderr || error.message).trim()));
        resolve({ text: payload.text || '' });
      } catch (parseError) {
        reject(new Error((stderr || parseError.message || 'Could not read the pasted image.').trim()));
      }
    });
  });
}

function publishSpeech(event) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('voice:event', event);
  }
}

function startSystemSpeech(locale = 'zh-CN') {
  if (speechProcess) throw new Error('Voice recording is already active.');
  const helper = speechHelperPath();
  if (!helper) throw new Error('The macOS speech component is missing. Reinstall Open Knowledge Agent.');
  let stdoutBuffer = '';
  let stderr = '';
  let terminalEvent = false;
  const child = spawn(helper, [locale], { stdio: ['ignore', 'pipe', 'pipe'] });
  speechProcess = child;
  child.stdout.on('data', chunk => {
    stdoutBuffer += chunk.toString('utf8');
    const lines = stdoutBuffer.split('\n');
    stdoutBuffer = lines.pop() || '';
    lines.filter(Boolean).forEach(line => {
      try {
        const event = JSON.parse(line);
        if (event.type === 'final' || event.type === 'error') terminalEvent = true;
        publishSpeech(event);
      } catch (_) {}
    });
  });
  child.stderr.on('data', chunk => { stderr += chunk.toString('utf8'); });
  child.on('error', error => {
    terminalEvent = true;
    publishSpeech({ type: 'error', text: error.message || String(error) });
  });
  child.on('close', code => {
    if (speechProcess === child) speechProcess = undefined;
    if (!terminalEvent && code !== 0) {
      publishSpeech({ type: 'error', text: stderr.trim() || `Speech recognition stopped with code ${code}.` });
    }
  });
  return { active: true };
}

function stopSystemSpeech() {
  if (speechProcess) speechProcess.kill('SIGINT');
  return { active: Boolean(speechProcess) };
}

function runGitHub(args) {
  return new Promise((resolve, reject) => {
    const executable = githubCliPath();
    if (!executable) {
      reject(new Error('GitHub login component is not installed.'));
      return;
    }
    execFile(
      executable,
      args,
      { maxBuffer: 2 * 1024 * 1024, timeout: 10 * 60_000 },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error((stderr || stdout || error.message).trim()));
          return;
        }
        resolve(stdout.trim());
      }
    );
  });
}

function publishGitHubState() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('github:state', githubState);
  }
}

async function refreshGitHubState() {
  const available = Boolean(githubCliPath());
  if (!available) {
    githubState = { available: false, connected: false, busy: false };
    publishGitHubState();
    return githubState;
  }
  const wasBusy = githubState.busy;
  try {
    const user = JSON.parse(await runGitHub(['api', '--hostname', 'github.com', 'user']));
    githubState = {
      available: true,
      connected: true,
      busy: wasBusy,
      login: user.login,
      name: user.name || '',
      avatar: user.avatar_url || ''
    };
  } catch (_) {
    githubState = { available: true, connected: false, busy: wasBusy };
  }
  publishGitHubState();
  return githubState;
}

async function loginGitHub() {
  if (githubState.busy) throw new Error('A GitHub account action is already running.');
  githubState = { ...githubState, busy: true, error: undefined };
  publishGitHubState();
  try {
    await runGitHub([
      'auth', 'login', '--hostname', 'github.com', '--git-protocol', 'https',
      '--web', '--clipboard'
    ]);
    await runGitHub(['auth', 'setup-git', '--hostname', 'github.com']);
    await refreshGitHubState();
    return githubState;
  } catch (error) {
    githubState = { ...githubState, error: error.message || String(error) };
    throw error;
  } finally {
    githubState = { ...githubState, busy: false };
    publishGitHubState();
  }
}

async function logoutGitHub() {
  if (!githubState.connected || !githubState.login) return refreshGitHubState();
  if (githubState.busy) throw new Error('A GitHub account action is already running.');
  githubState = { ...githubState, busy: true, error: undefined };
  publishGitHubState();
  try {
    await runGitHub(['auth', 'logout', '--hostname', 'github.com', '--user', githubState.login]);
    return await refreshGitHubState();
  } finally {
    githubState = { ...githubState, busy: false };
    publishGitHubState();
  }
}

function publicAuthState() {
  return {
    session: chatgptSession,
    models: chatgptModels,
    selectedModel,
    busy: authBusy,
    available: Boolean(chatgpt)
  };
}

function publishAuthState() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('auth:state', publicAuthState());
  }
}

function credentialEncryption() {
  const available = () => app.isReady() && safeStorage.isEncryptionAvailable();
  return {
    id: 'electron-safe-storage-v1',
    isAvailable: available,
    encrypt(plaintext) {
      if (!available()) throw new Error('macOS Keychain encryption is unavailable.');
      return safeStorage.encryptString(plaintext);
    },
    decrypt(ciphertext) {
      if (!available()) throw new Error('macOS Keychain encryption is unavailable.');
      return safeStorage.decryptString(Buffer.from(ciphertext));
    }
  };
}

async function initializeChatGPT() {
  const module = await import('@siwc/local');
  chatgptUsageUrl = module.CHATGPT_USAGE_URL;
  chatgpt = module.createChatGPT({
    appName: 'Open Knowledge Agent',
    appId: 'open-knowledge-agent',
    redirectPort: 0,
    storageDir: path.join(app.getPath('userData'), 'chatgpt'),
    credentialEncryption: credentialEncryption(),
    openBrowser: async url => {
      const target = new URL(url);
      if (target.origin !== 'https://auth.openai.com') {
        throw new Error('Unexpected sign-in destination.');
      }
      await shell.openExternal(target.href);
    }
  });
  chatgpt.subscribe(next => {
    chatgptSession = next;
    if (next.status !== 'connected' || !next.sharing) chatgptModels = [];
    publishAuthState();
  });
  chatgptSession = await chatgpt.getSession();
  await refreshChatGPTModels();
}

async function refreshChatGPTModels() {
  if (!chatgpt || chatgptSession.status !== 'connected' || !chatgptSession.sharing) {
    chatgptModels = [];
    publishAuthState();
    return;
  }
  chatgptModels = await chatgpt.listModels();
  if (!chatgptModels.some(model => model.slug === selectedModel)) {
    selectedModel = chatgptModels[0]?.slug || '';
    saveConfig();
  }
  publishAuthState();
}

async function changeChatGPTAccount(action) {
  if (!chatgpt) throw new Error('ChatGPT login is not available in this build.');
  if (authBusy) throw new Error('An account action is already in progress.');
  authBusy = true;
  publishAuthState();
  try {
    await action();
    chatgptSession = await chatgpt.getSession();
    await refreshChatGPTModels();
    return publicAuthState();
  } finally {
    authBusy = false;
    publishAuthState();
  }
}

function systemPythonPath() {
  return ['/usr/bin/python3', '/opt/homebrew/bin/python3', '/usr/local/bin/python3']
    .find(candidate => fs.existsSync(candidate));
}

function agentRuntime() {
  if (projectPath) {
    const virtualenvPython = path.join(projectPath, '.venv', 'bin', 'python');
    if (fs.existsSync(virtualenvPython)) {
      return { python: virtualenvPython, cwd: projectPath, environment: {} };
    }
    const source = path.join(projectPath, 'src');
    const python = systemPythonPath();
    if (python && fs.existsSync(path.join(source, 'study_agent', 'cli.py'))) {
      return { python, cwd: projectPath, environment: { PYTHONPATH: source } };
    }
  }

  const bundledSource = path.join(process.resourcesPath, 'app', 'backend', 'src');
  const python = systemPythonPath();
  if (python && fs.existsSync(path.join(bundledSource, 'study_agent', 'cli.py'))) {
    return {
      python,
      cwd: app.getPath('userData'),
      environment: {
        PYTHONPATH: bundledSource,
        STUDY_AGENT_HOME: path.join(app.getPath('userData'), 'data'),
        STUDY_AGENT_KNOWLEDGE_HOME: configuredKnowledgeRoot() || path.join(app.getPath('userData'), 'knowledge')
      }
    };
  }
  throw new Error('The bundled agent backend is unavailable. Reinstall the app or choose a backend folder in Settings.');
}

function runAgent(args) {
  return new Promise((resolve, reject) => {
    let runtime;
    try { runtime = agentRuntime(); }
    catch (error) { reject(error); return; }
    execFile(
      runtime.python,
      ['-m', 'study_agent.cli', ...args],
      {
        cwd: runtime.cwd,
        maxBuffer: 8 * 1024 * 1024,
        env: {
          ...process.env,
          ...runtime.environment,
          ...(githubCliPath() ? { STUDY_AGENT_GH_PATH: githubCliPath() } : {}),
          ...(!runtime.environment.STUDY_AGENT_KNOWLEDGE_HOME && configuredKnowledgeRoot()
            ? { STUDY_AGENT_KNOWLEDGE_HOME: configuredKnowledgeRoot() }
            : {})
        }
      },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error((stderr || error.message).trim()));
          return;
        }
        resolve(stdout.trim());
      }
    );
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: COMPACT_SIZE.width,
    height: COMPACT_SIZE.height,
    minWidth: COMPACT_SIZE.width,
    minHeight: COMPACT_SIZE.height,
    title: 'Open Knowledge Agent',
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0b1022',
    icon: path.join(__dirname, '..', 'assets', 'AppIconSource.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  mainWindow.setAlwaysOnTop(true, 'floating');
  mainWindow.setMovable(true);
  mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  mainWindow.setWindowButtonVisibility(false);
  const [x, y] = compactWindowPosition();
  mainWindow.setPosition(x, y);
  mainWindow.on('moved', () => {
    if (!compact || !mainWindow || mainWindow.isDestroyed()) return;
    compactPosition = mainWindow.getPosition();
    saveConfig();
  });
  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.send('window:state', { compact });
    publishAuthState();
    publishGitHubState();
  });
}

async function sendChatMessage(message, sessionId, topicId) {
  if (chatgptSession.status === 'connected' && chatgptSession.sharing) {
    if (!chatgptModels.length) await refreshChatGPTModels();
    if (!selectedModel) throw new Error('No ChatGPT model is available for this account.');
    const contextArgs = ['chat-context', message];
    if (sessionId) contextArgs.push('--session', String(sessionId));
    else if (topicId) contextArgs.push('--topic', String(topicId));
    const payload = JSON.parse(await runAgent(contextArgs));
    const result = await chatgpt.streamResponse({
      model: selectedModel,
      instructions: payload.instructions,
      input: payload.input
    });
    await runAgent([
      'chat-save', '--session', String(payload.session_id),
      '--user', message, '--assistant', result.text
    ]);
    return { session_id: payload.session_id, message: result.text, auth: 'chatgpt' };
  }

  const args = ['chat', message, '--json'];
  if (sessionId) args.push('--session', String(sessionId));
  else if (topicId) args.push('--topic', String(topicId));
  return { ...JSON.parse(await runAgent(args)), auth: 'api_key' };
}

function parseJsonObject(text) {
  const trimmed = String(text).trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  const start = trimmed.indexOf('{');
  const end = trimmed.lastIndexOf('}');
  if (start < 0 || end <= start) throw new Error('The insight model did not return valid JSON. Try Refresh again.');
  const payload = JSON.parse(trimmed.slice(start, end + 1));
  if (!payload || Array.isArray(payload) || typeof payload !== 'object') {
    throw new Error('The insight model returned an unexpected format.');
  }
  return payload;
}

async function generateInsights() {
  let output;
  if (chatgptSession.status === 'connected' && chatgptSession.sharing) {
    if (!chatgptModels.length) await refreshChatGPTModels();
    if (!selectedModel) throw new Error('No ChatGPT model is available for Insights.');
    const payload = JSON.parse(await runAgent(['insights-context']));
    const result = await chatgpt.streamResponse({
      model: selectedModel,
      instructions: payload.instructions,
      input: payload.input
    });
    output = result.text;
  } else {
    output = await runAgent(['insights-generate']);
  }

  const insight = parseJsonObject(output);
  const insightPath = path.join(os.tmpdir(), `study-agent-insights-${Date.now()}.json`);
  fs.writeFileSync(insightPath, JSON.stringify(insight), { encoding: 'utf8', mode: 0o600 });
  try {
    await runAgent(['insights-save', '--file', insightPath]);
  } finally {
    try { fs.unlinkSync(insightPath); } catch (_) {}
  }
  return JSON.parse(await runAgent(['insights-current']));
}

function setCompact(nextCompact) {
  if (!mainWindow) return;
  if (compact && !nextCompact) compactPosition = mainWindow.getPosition();
  compact = nextCompact;
  if (compact) {
    mainWindow.setResizable(false);
    mainWindow.setAlwaysOnTop(true, 'floating');
    mainWindow.setWindowButtonVisibility(false);
    mainWindow.setSize(COMPACT_SIZE.width, COMPACT_SIZE.height, true);
    const [x, y] = compactWindowPosition();
    mainWindow.setPosition(x, y, true);
  } else {
    mainWindow.setResizable(true);
    mainWindow.setAlwaysOnTop(false);
    mainWindow.setWindowButtonVisibility(true);
    mainWindow.setSize(EXPANDED_SIZE.width, EXPANDED_SIZE.height, true);
    mainWindow.center();
  }
  mainWindow.webContents.send('window:state', { compact });
}

function compactWindowPosition() {
  if (compactPosition) {
    const display = screen.getDisplayNearestPoint({ x: compactPosition[0], y: compactPosition[1] });
    const area = display.workArea;
    return [
      Math.max(area.x, Math.min(compactPosition[0], area.x + area.width - COMPACT_SIZE.width)),
      Math.max(area.y, Math.min(compactPosition[1], area.y + area.height - COMPACT_SIZE.height))
    ];
  }
  const area = screen.getPrimaryDisplay().workArea;
  return [
    Math.round(area.x + area.width - COMPACT_SIZE.width - 22),
    Math.round(area.y + 46)
  ];
}

app.whenReady().then(async () => {
  loadConfig();
  if (!projectPath) {
    const developmentBackend = path.resolve(__dirname, '..', '..', 'study-agent');
    if (fs.existsSync(path.join(developmentBackend, 'pyproject.toml'))) projectPath = developmentBackend;
  }
  session.defaultSession.setPermissionCheckHandler((_webContents, permission) => {
    return permission === 'media';
  });
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    callback(permission === 'media');
  });
  createWindow();
  await refreshGitHubState();
  try {
    await initializeChatGPT();
  } catch (error) {
    chatgptSession = {
      status: 'disconnected', sharing: false,
      error: { message: error.message || String(error), retryable: true }
    };
    publishAuthState();
  }
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => app.quit());

ipcMain.handle('agent:run', async (_event, args) => runAgent(args));
ipcMain.handle('clipboard:write', async (_event, text) => clipboard.writeText(String(text)));
ipcMain.handle('chat:send', async (_event, message, sessionId, topicId) => sendChatMessage(message, sessionId, topicId));
ipcMain.handle('auth:state', async () => publicAuthState());
ipcMain.handle('auth:sign-in', async () => changeChatGPTAccount(() => chatgpt.signIn()));
ipcMain.handle('auth:cancel', () => chatgpt?.cancelSignIn());
ipcMain.handle('auth:disconnect', async () => changeChatGPTAccount(() => chatgpt.disconnect()));
ipcMain.handle('auth:usage', async () => shell.openExternal(chatgptUsageUrl));
ipcMain.handle('auth:model', async (_event, model) => {
  if (!chatgptModels.some(item => item.slug === model)) throw new Error('Unknown model.');
  selectedModel = model;
  saveConfig();
  publishAuthState();
  return publicAuthState();
});
ipcMain.handle('github:state', async () => refreshGitHubState());
ipcMain.handle('github:login', async () => loginGitHub());
ipcMain.handle('github:logout', async () => logoutGitHub());
ipcMain.handle('insights:current', async () => JSON.parse(await runAgent(['insights-current'])));
ipcMain.handle('insights:generate', async () => generateInsights());
ipcMain.handle('knowledge:open', async () => {
  const directory = JSON.parse(await runAgent(['knowledge-path'])).path;
  fs.mkdirSync(directory, { recursive: true });
  const error = await shell.openPath(directory);
  if (error) throw new Error(error);
});
ipcMain.handle('knowledge:state', async () => {
  const root = JSON.parse(await runAgent(['knowledge-path'])).path;
  return { parentPath: knowledgeParentPath, rootPath: root };
});
ipcMain.handle('knowledge:choose', async () => {
  const currentRoot = JSON.parse(await runAgent(['knowledge-path'])).path;
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Choose the top folder for Open Knowledge Agent knowledge',
    message: 'The app will create an “Open Knowledge Agent Knowledge” subfolder here.',
    defaultPath: knowledgeParentPath || app.getPath('documents'),
    properties: ['openDirectory', 'createDirectory']
  });
  if (result.canceled || !result.filePaths[0]) {
    return { parentPath: knowledgeParentPath, rootPath: currentRoot };
  }
  const selectedParent = path.resolve(result.filePaths[0]);
  const newRoot = path.join(selectedParent, 'Open Knowledge Agent Knowledge');
  if (path.resolve(currentRoot) !== path.resolve(newRoot)) copyMissing(currentRoot, newRoot);
  else fs.mkdirSync(newRoot, { recursive: true });
  knowledgeParentPath = selectedParent;
  saveConfig();
  return { parentPath: knowledgeParentPath, rootPath: newRoot };
});
ipcMain.handle('window:toggle', () => {
  setCompact(!compact);
  return { compact };
});
ipcMain.handle('window:expand', () => {
  setCompact(false);
  return { compact };
});
ipcMain.handle('window:compact', () => {
  setCompact(true);
  return { compact };
});

ipcMain.handle('project:choose', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    defaultPath: projectPath || app.getPath('documents'),
    message: 'Optional: choose a study-agent folder for API-key mode. ChatGPT sign-in uses the bundled backend.'
  });
  if (!result.canceled && result.filePaths[0]) {
    projectPath = result.filePaths[0];
    saveConfig();
  }
  return projectPath;
});

ipcMain.handle('data:export', async () => {
  const sourceResult = await dialog.showOpenDialog(mainWindow, {
    title: 'Choose an existing agent folder to export',
    message: 'Select the folder that contains .study-agent/agent.db.',
    properties: ['openDirectory']
  });
  if (sourceResult.canceled || !sourceResult.filePaths[0]) return { canceled: true };
  const date = new Date().toISOString().slice(0, 10);
  const outputResult = await dialog.showSaveDialog(mainWindow, {
    title: 'Save portable agent data bundle',
    defaultPath: path.join(app.getPath('documents'), `OpenKnowledgeAgent-${date}.okagent`),
    filters: [{ name: 'Open Knowledge Agent Data', extensions: ['okagent'] }]
  });
  if (outputResult.canceled || !outputResult.filePath) return { canceled: true };
  return JSON.parse(await runAgent([
    'data-export', '--source', sourceResult.filePaths[0], '--output', outputResult.filePath
  ]));
});

ipcMain.handle('data:import', async () => {
  const fileResult = await dialog.showOpenDialog(mainWindow, {
    title: 'Import portable agent data bundle',
    properties: ['openFile'],
    filters: [{ name: 'Open Knowledge Agent Data', extensions: ['okagent'] }]
  });
  if (fileResult.canceled || !fileResult.filePaths[0]) return { canceled: true };
  const confirmation = await dialog.showMessageBox(mainWindow, {
    type: 'warning',
    buttons: ['Cancel', 'Import and replace'],
    defaultId: 0,
    cancelId: 0,
    title: 'Replace current local agent data?',
    message: 'Importing replaces the current topics, sessions, messages, tasks, evidence, and insights.',
    detail: 'A local backup of the current database and knowledge folder is created automatically before replacement.'
  });
  if (confirmation.response !== 1) return { canceled: true };
  return JSON.parse(await runAgent(['data-import', '--file', fileResult.filePaths[0]]));
});

ipcMain.handle('image:extract-text', async (_event, dataUrl) => extractImageText(dataUrl));

ipcMain.handle('voice:permission', async () => {
  if (process.platform !== 'darwin') return true;
  const current = systemPreferences.getMediaAccessStatus('microphone');
  if (current === 'granted') return true;
  return systemPreferences.askForMediaAccess('microphone');
});
ipcMain.handle('voice:system-start', async (_event, locale) => startSystemSpeech(locale));
ipcMain.handle('voice:system-stop', async () => stopSystemSpeech());

ipcMain.handle('voice:transcribe', async (_event, audioBytes) => {
  const audioPath = path.join(os.tmpdir(), `study-agent-${Date.now()}.webm`);
  fs.writeFileSync(audioPath, Buffer.from(audioBytes));
  try {
    return await runAgent(['transcribe', '--file', audioPath]);
  } finally {
    try { fs.unlinkSync(audioPath); } catch (_) {}
  }
});

app.on('before-quit', () => {
  if (speechProcess) speechProcess.kill('SIGTERM');
});

