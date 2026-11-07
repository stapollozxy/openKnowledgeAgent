const iconButton = document.getElementById('agentIcon');
const sidebar = document.getElementById('sidebar');
const topicList = document.getElementById('topicList');
const sessionList = document.getElementById('sessionList');
const messagesNode = document.getElementById('messages');
const input = document.getElementById('input');
const sendButton = document.getElementById('sendButton');
const typeButton = document.getElementById('typeButton');
const voiceButton = document.getElementById('voiceButton');
const statusNode = document.getElementById('status');
const statusText = document.getElementById('statusText');
const errorNode = document.getElementById('error');
const accountDot = document.getElementById('accountDot');
const accountTitle = document.getElementById('accountTitle');
const accountDetail = document.getElementById('accountDetail');
const signInButton = document.getElementById('signInButton');
const disconnectButton = document.getElementById('disconnectButton');
const usageButton = document.getElementById('usageButton');
const modelSelect = document.getElementById('modelSelect');
const githubDot = document.getElementById('githubDot');
const githubTitle = document.getElementById('githubTitle');
const githubDetail = document.getElementById('githubDetail');
const githubLoginButton = document.getElementById('githubLoginButton');
const githubLogoutButton = document.getElementById('githubLogoutButton');
const insightsNav = document.getElementById('insightsNav');
const insightsPanel = document.getElementById('insightsPanel');
const insightsEmpty = document.getElementById('insightsEmpty');
const insightsContent = document.getElementById('insightsContent');
const insightsUpdated = document.getElementById('insightsUpdated');
const refreshInsightsButton = document.getElementById('refreshInsights');
const openKnowledgeButton = document.getElementById('openKnowledge');
const setKnowledgeLocationButton = document.getElementById('setKnowledgeLocation');
const activeTopicLabel = document.getElementById('activeTopicLabel');
const exportDataButton = document.getElementById('exportData');
const importDataButton = document.getElementById('importData');
const imageTray = document.getElementById('imageTray');
const topicPicker = document.getElementById('topicPicker');
const topicDialog = document.getElementById('topicDialog');
const topicNameInput = document.getElementById('topicNameInput');
const confirmTopicButton = document.getElementById('confirmTopic');

let currentSessionID = null;
let currentTopicID = null;
let topicsCache = [];
let busy = false;
let mediaRecorder = null;
let mediaStream = null;
let audioChunks = [];
let recordingTimer = null;
let systemVoiceActive = false;
let compactMode = true;
let accountState = null;
let currentGitHubState = null;
let viewMode = 'chat';
let idleTimer = null;
let isComposing = false;
let topicNameComposing = false;
let pendingImages = [];
const IDLE_COMPACT_MS = 30_000;

function canAutoCompact() {
  const recording = systemVoiceActive || mediaRecorder?.state === 'recording';
  const signingIn = accountState?.session?.status === 'connecting' || accountState?.busy;
  const githubBusy = currentGitHubState?.busy;
  const topicDialogOpen = !topicDialog.classList.contains('hidden');
  return !compactMode && !busy && !recording && !signingIn && !githubBusy && !topicDialogOpen && !input.value.trim() && !pendingImages.length;
}

function resetIdleTimer() {
  clearTimeout(idleTimer);
  if (compactMode) return;
  idleTimer = setTimeout(async () => {
    if (!canAutoCompact()) {
      resetIdleTimer();
      return;
    }
    await window.studyAgent.compactWindow();
  }, IDLE_COMPACT_MS);
}

function showError(error) {
  errorNode.textContent = error?.message || String(error);
  errorNode.classList.remove('hidden');
}

function clearError() { errorNode.classList.add('hidden'); }

function setBusy(value, label = 'Agent is thinking…') {
  busy = value;
  statusText.textContent = label;
  statusNode.classList.toggle('hidden', !value);
  sendButton.disabled = value;
  resetIdleTimer();
}

function addMessage(role, content) {
  document.getElementById('emptyState')?.remove();
  const row = document.createElement('div');
  row.className = `message-row ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = window.OpenKnowledgeMarkdown.renderMarkdown(content);
  row.appendChild(bubble);
  messagesNode.appendChild(row);
  messagesNode.scrollTop = messagesNode.scrollHeight;
}

const PROFILE_FIELD_LABELS = {
  course: 'Course',
  course_progress: 'Course progress',
  goal: 'Goal'
};

function addProfileUpdateProposal(proposal, sessionId) {
  if (!proposal?.changes || typeof proposal.changes !== 'object') return;
  const entries = Object.entries(proposal.changes)
    .filter(([key, value]) => PROFILE_FIELD_LABELS[key] && typeof value === 'string' && value.trim());
  if (!entries.length) return;

  const card = document.createElement('div');
  card.className = 'profile-update-card';
  const heading = document.createElement('strong');
  heading.textContent = 'Save to long-term profile?';
  const note = document.createElement('p');
  note.textContent = 'Nothing changes until you confirm.';
  const changes = document.createElement('div');
  changes.className = 'profile-change-list';
  entries.forEach(([key, value]) => {
    const row = document.createElement('div');
    const label = document.createElement('span');
    label.textContent = PROFILE_FIELD_LABELS[key];
    const comparison = document.createElement('p');
    const previous = proposal.current?.[key] || 'Not set';
    comparison.textContent = `${previous}  →  ${value.trim()}`;
    row.append(label, comparison);
    changes.appendChild(row);
  });
  const actions = document.createElement('div');
  actions.className = 'profile-update-actions';
  const dismiss = document.createElement('button');
  dismiss.textContent = 'Not now';
  const confirm = document.createElement('button');
  confirm.className = 'confirm';
  confirm.textContent = 'Confirm & save';
  dismiss.addEventListener('click', () => {
    actions.remove();
    note.textContent = 'Not saved.';
    card.classList.add('resolved');
  });
  confirm.addEventListener('click', async () => {
    confirm.disabled = true;
    dismiss.disabled = true;
    clearError();
    try {
      const result = await window.studyAgent.updateProfile(
        Object.fromEntries(entries), sessionId
      );
      actions.remove();
      note.textContent = 'Saved locally.';
      card.classList.add('saved', 'resolved');
      addMessage('assistant', result.message);
    } catch (error) {
      confirm.disabled = false;
      dismiss.disabled = false;
      showError(error);
    }
  });
  actions.append(dismiss, confirm);
  card.append(heading, note, changes, actions);
  messagesNode.appendChild(card);
  messagesNode.scrollTop = messagesNode.scrollHeight;
}

function renderAuth(state) {
  accountState = state;
  const session = state?.session || { status: 'disconnected', sharing: false };
  const connected = session.status === 'connected' && session.sharing;
  const connecting = session.status === 'connecting' || state?.busy;
  accountDot.classList.toggle('connected', connected);
  accountDot.classList.toggle('connecting', connecting);
  signInButton.classList.toggle('hidden', connected);
  disconnectButton.classList.toggle('hidden', !connected);
  usageButton.classList.toggle('hidden', !connected);
  modelSelect.classList.toggle('hidden', !connected || !(state.models || []).length);

  if (connected) {
    accountTitle.textContent = session.identity?.name || session.identity?.email || 'ChatGPT connected';
    accountDetail.textContent = 'Text chat uses your ChatGPT plan';
    modelSelect.innerHTML = '';
    state.models.forEach(model => {
      const option = document.createElement('option');
      option.value = model.slug;
      option.textContent = model.displayName;
      option.selected = model.slug === state.selectedModel;
      modelSelect.appendChild(option);
    });
  } else if (connecting) {
    accountTitle.textContent = 'Waiting for ChatGPT authorization…';
    accountDetail.textContent = 'Finish sign-in in your browser';
    signInButton.textContent = 'Cancel';
  } else {
    accountTitle.textContent = session.status === 'reauth_required' ? 'Reconnect ChatGPT' : 'ChatGPT not connected';
    accountDetail.textContent = session.error?.message || 'Connect your account or use an API key fallback';
    signInButton.textContent = session.status === 'reauth_required' ? 'Reconnect ChatGPT' : 'Continue with ChatGPT';
  }
  signInButton.disabled = !state?.available && !connecting;
  resetIdleTimer();
}

function renderGitHub(state) {
  currentGitHubState = state;
  githubDot.classList.toggle('connected', Boolean(state?.connected));
  githubDot.classList.toggle('connecting', Boolean(state?.busy));
  githubLoginButton.classList.toggle('hidden', Boolean(state?.connected));
  githubLogoutButton.classList.toggle('hidden', !state?.connected);
  githubLoginButton.disabled = !state?.available || Boolean(state?.busy);
  githubLogoutButton.disabled = Boolean(state?.busy);

  if (state?.busy) {
    githubTitle.textContent = state.connected ? 'Disconnecting GitHub…' : 'Waiting for GitHub authorization…';
    githubDetail.textContent = 'The one-time code is copied; finish in your browser';
  } else if (state?.connected) {
    githubTitle.textContent = state.name || `@${state.login}`;
    githubDetail.textContent = `Connected as @${state.login} · read-only Agent access`;
  } else if (!state?.available) {
    githubTitle.textContent = 'GitHub login unavailable';
    githubDetail.textContent = 'The bundled GitHub component could not be found';
  } else {
    githubTitle.textContent = 'GitHub not connected';
    githubDetail.textContent = state.error || 'Connect to read repositories, commits, PRs, and issues';
  }
  resetIdleTimer();
}

function resetMessages() {
  messagesNode.innerHTML = '<div id="emptyState" class="empty-state"><div class="sparkle">✦</div><h2>Start a chat</h2><p>Learn a course, explore a topic, plan your day, or build a project.</p></div>';
}

function renderTypeButton() {
  if (compactMode) {
    typeButton.innerHTML = '<span>⌨</span> Type';
    typeButton.title = 'Expand and type';
  } else {
    typeButton.innerHTML = '<span>−</span> Compact';
    typeButton.title = 'Return to the floating compact window';
  }
}

function showChatView() {
  viewMode = 'chat';
  document.body.classList.remove('insights-mode');
  insightsPanel.classList.add('hidden');
  insightsNav.classList.remove('active');
  if (!compactMode) sidebar.classList.remove('hidden');
}

function showInsightsView() {
  viewMode = 'insights';
  document.body.classList.add('insights-mode');
  insightsPanel.classList.remove('hidden');
  insightsNav.classList.add('active');
  sidebar.classList.add('hidden');
  resetIdleTimer();
}

function detail(parent, text, className = 'item-detail') {
  if (!text) return;
  const node = document.createElement('p');
  node.className = className;
  node.textContent = text;
  parent.appendChild(node);
}

function renderSimpleList(container, items, value) {
  container.innerHTML = '';
  (items || []).forEach(item => {
    const row = document.createElement('div');
    row.className = 'insight-item';
    const title = document.createElement('strong');
    title.textContent = value(item);
    row.appendChild(title);
    container.appendChild(row);
  });
  if (!container.children.length) container.textContent = '尚无足够证据';
}

function renderInsights(snapshot) {
  if (!snapshot?.payload) {
    insightsEmpty.classList.remove('hidden');
    insightsContent.classList.add('hidden');
    insightsUpdated.textContent = 'Built from your chats, tasks, evidence, and GitHub activity.';
    return;
  }
  const data = snapshot.payload;
  insightsEmpty.classList.add('hidden');
  insightsContent.classList.remove('hidden');
  insightsUpdated.textContent = `Last refreshed ${new Date(snapshot.created_at).toLocaleString()}`;
  document.getElementById('insightOverview').textContent = data.overview || '尚无总体判断';
  renderSimpleList(document.getElementById('strengthsList'), data.strengths, item => String(item));

  const gaps = document.getElementById('gapsList');
  gaps.innerHTML = '';
  (data.gaps || []).forEach(item => {
    const row = document.createElement('div');
    row.className = 'insight-item';
    const title = document.createElement('strong');
    title.textContent = item.topic || 'Knowledge gap';
    row.appendChild(title);
    detail(row, [item.why, item.evidence].filter(Boolean).join(' · '));
    gaps.appendChild(row);
  });
  if (!gaps.children.length) gaps.textContent = '尚无足够证据';

  const questions = document.getElementById('questionsList');
  questions.innerHTML = '';
  (data.meaningful_questions || []).forEach(item => {
    const row = document.createElement('div');
    row.className = 'question-item';
    const title = document.createElement('strong');
    title.textContent = item.question || 'Untitled question';
    row.appendChild(title);
    detail(row, item.why_it_matters);
    detail(row, item.missing_concept ? `缺少的概念：${item.missing_concept}` : '');
    detail(row, item.review_prompt, 'review-prompt');
    questions.appendChild(row);
  });
  if (!questions.children.length) questions.textContent = '多聊几个技术问题后，这里会形成你的问题本。';

  const learning = document.getElementById('learningList');
  learning.innerHTML = '';
  (data.next_learning || []).forEach((item, index) => {
    const row = document.createElement('div');
    row.className = 'learning-item';
    const title = document.createElement('strong');
    const badge = document.createElement('span');
    badge.className = 'priority-badge';
    badge.textContent = `P${item.priority || index + 1}`;
    title.appendChild(badge);
    title.append(document.createTextNode(item.topic || 'Next topic'));
    row.appendChild(title);
    detail(row, item.why);
    detail(row, item.next_action ? `下一步：${item.next_action}` : '');
    detail(row, item.done_when ? `完成标准：${item.done_when}` : '');
    learning.appendChild(row);
  });
  if (!learning.children.length) learning.textContent = '刷新后生成学习顺序。';

  const projects = document.getElementById('projectsList');
  projects.innerHTML = '';
  (data.industry_projects || []).forEach(item => {
    const row = document.createElement('div');
    row.className = 'project-item';
    const title = document.createElement('strong');
    title.textContent = item.name || 'Industry project';
    row.appendChild(title);
    detail(row, item.industrial_use);
    const meta = document.createElement('div');
    meta.className = 'project-meta';
    [['Architecture', item.architecture], ['Milestones', item.milestones], ['Metrics', item.metrics]].forEach(([label, values]) => {
      const box = document.createElement('div');
      const heading = document.createElement('b');
      heading.textContent = label;
      box.appendChild(heading);
      const list = document.createElement('ul');
      (values || []).forEach(value => {
        const li = document.createElement('li');
        li.textContent = value;
        list.appendChild(li);
      });
      box.appendChild(list);
      meta.appendChild(box);
    });
    row.appendChild(meta);
    detail(row, item.resume_evidence, 'resume-evidence');
    projects.appendChild(row);
  });
  if (!projects.children.length) projects.textContent = '刷新后生成适合当前阶段的工业项目。';
}

async function loadInsights() {
  const snapshot = await window.studyAgent.currentInsights();
  renderInsights(snapshot);
}

async function refreshInsights() {
  clearError();
  refreshInsightsButton.disabled = true;
  setBusy(true, 'Analyzing your learning history…');
  try {
    renderInsights(await window.studyAgent.generateInsights());
  } catch (error) {
    showError(error);
  } finally {
    refreshInsightsButton.disabled = false;
    setBusy(false);
  }
}

async function run(args) {
  return window.studyAgent.run(args);
}

async function ensureInitialized() {
  try {
    return JSON.parse(await run(['sessions']));
  } catch (error) {
    if (String(error).includes('init')) {
      await run(['init']);
      return JSON.parse(await run(['sessions']));
    }
    throw error;
  }
}

function renderTopics() {
  topicList.innerHTML = '';
  topicPicker.innerHTML = '';
  topicsCache.forEach(topic => {
    const option = document.createElement('option');
    option.value = String(topic.id);
    option.textContent = `${topic.name} (${topic.session_count})`;
    option.selected = topic.id === currentTopicID;
    topicPicker.appendChild(option);

    const row = document.createElement('div');
    row.className = 'topic-row';
    const button = document.createElement('button');
    button.className = `topic-button ${topic.id === currentTopicID ? 'active' : ''}`;
    const name = document.createElement('span');
    name.className = 'topic-name';
    name.textContent = topic.name;
    const count = document.createElement('span');
    count.className = 'topic-count';
    count.textContent = `${topic.session_count} sessions`;
    button.append(name, count);
    button.addEventListener('click', () => selectTopic(topic.id));

    const more = document.createElement('button');
    more.className = 'topic-more';
    more.textContent = '•••';
    more.title = 'Topic actions';
    const menu = document.createElement('div');
    menu.className = 'topic-menu hidden';
    const rename = document.createElement('button');
    rename.textContent = 'Rename';
    rename.addEventListener('click', event => {
      event.stopPropagation();
      menu.classList.add('hidden');
      renameTopic(topic);
    });
    menu.appendChild(rename);
    if (topic.name !== 'General') {
      const remove = document.createElement('button');
      remove.className = 'danger';
      remove.textContent = 'Delete topic';
      remove.addEventListener('click', event => {
        event.stopPropagation();
        menu.classList.add('hidden');
        deleteTopic(topic);
      });
      menu.appendChild(remove);
    }
    more.addEventListener('click', event => {
      event.stopPropagation();
      document.querySelectorAll('.topic-menu,.session-menu').forEach(other => {
        if (other !== menu) other.classList.add('hidden');
      });
      menu.classList.toggle('hidden');
    });
    row.appendChild(button);
    if (topic.name !== 'General') row.append(more, menu);
    topicList.appendChild(row);
  });
}

async function loadTopics(preferredTopicID = currentTopicID) {
  topicsCache = JSON.parse(await run(['topics']));
  const preferred = topicsCache.find(topic => topic.id === preferredTopicID);
  const general = topicsCache.find(topic => topic.name === 'General');
  currentTopicID = (preferred || general || topicsCache[0])?.id || null;
  const active = topicsCache.find(topic => topic.id === currentTopicID);
  activeTopicLabel.textContent = active?.name || 'General Learning · Projects · Knowledge';
  renderTopics();
}

async function selectTopic(id) {
  currentTopicID = id;
  currentSessionID = null;
  resetMessages();
  renderTopics();
  const active = topicsCache.find(topic => topic.id === id);
  activeTopicLabel.textContent = active?.name || 'General';
  topicPicker.value = String(id);
  await loadSessions();
}

function openTopicDialog() {
  clearError();
  topicNameInput.value = '';
  topicDialog.classList.remove('hidden');
  resetIdleTimer();
  setTimeout(() => topicNameInput.focus(), 0);
}

function closeTopicDialog() {
  topicDialog.classList.add('hidden');
  topicNameInput.value = '';
  resetIdleTimer();
}

async function createTopic(name = topicNameInput.value) {
  const trimmedName = name?.trim();
  if (!trimmedName) {
    topicNameInput.focus();
    return;
  }
  clearError();
  confirmTopicButton.disabled = true;
  try {
    const result = JSON.parse(await run(['topic-new', '--name', trimmedName]));
    await loadTopics(result.topic_id);
    await selectTopic(result.topic_id);
    closeTopicDialog();
  } catch (error) {
    showError(error);
    topicNameInput.focus();
  } finally {
    confirmTopicButton.disabled = false;
  }
}

async function renameTopic(topic) {
  const name = window.prompt('Rename topic', topic.name);
  if (!name?.trim() || name.trim() === topic.name) return;
  clearError();
  try {
    await run(['topic-rename', '--topic', String(topic.id), '--name', name.trim()]);
    await loadTopics(currentTopicID);
  } catch (error) { showError(error); }
}

async function deleteTopic(topic) {
  if (!window.confirm(`Delete topic “${topic.name}”? Its sessions will move to General.`)) return;
  clearError();
  try {
    await run(['topic-delete', '--topic', String(topic.id)]);
    if (currentTopicID === topic.id) currentTopicID = null;
    await loadTopics(currentTopicID);
    currentSessionID = null;
    resetMessages();
    await loadSessions();
  } catch (error) { showError(error); }
}

async function loadSessions() {
  clearError();
  try {
    await ensureInitialized();
    const args = ['sessions'];
    if (currentTopicID) args.push('--topic', String(currentTopicID));
    const sessions = JSON.parse(await run(args));
    sessionList.innerHTML = '';
    if (!sessions.length) {
      sessionList.innerHTML = '<p class="session-meta">No chats yet</p>';
      return;
    }
    sessions.forEach(session => {
      const row = document.createElement('div');
      row.className = 'session-row';
      const button = document.createElement('button');
      button.className = `session ${session.id === currentSessionID ? 'active' : ''}`;
      button.innerHTML = `<span class="session-title"></span><span class="session-meta">${session.message_count} messages</span>`;
      button.querySelector('.session-title').textContent = session.title;
      button.addEventListener('click', () => selectSession(session.id));
      const more = document.createElement('button');
      more.className = 'session-more';
      more.textContent = '•••';
      more.title = 'Session actions';
      const menu = document.createElement('div');
      menu.className = 'session-menu hidden';
      [['Fork session', () => forkSession(session.id)], ['Copy Markdown', () => copySession(session)], ['Delete', () => deleteSession(session)]].forEach(([label, action]) => {
        const item = document.createElement('button');
        item.textContent = label;
        if (label === 'Delete') item.className = 'danger';
        item.addEventListener('click', event => {
          event.stopPropagation();
          menu.classList.add('hidden');
          action();
        });
        menu.appendChild(item);
      });
      more.addEventListener('click', event => {
        event.stopPropagation();
        document.querySelectorAll('.session-menu').forEach(other => {
          if (other !== menu) other.classList.add('hidden');
        });
        menu.classList.toggle('hidden');
      });
      row.append(button, more, menu);
      sessionList.appendChild(row);
    });
  } catch (error) { showError(error); }
}

async function forkSession(id) {
  clearError();
  try {
    const result = JSON.parse(await run(['session-fork', '--session', String(id)]));
    await selectSession(result.session_id);
    await loadTopics(currentTopicID);
  } catch (error) { showError(error); }
}

async function copySession(session) {
  clearError();
  try {
    const history = JSON.parse(await run(['history', '--session', String(session.id)]));
    const markdown = [`# ${session.title}`, '', ...history.flatMap(message => [
      `## ${message.role === 'user' ? 'User' : 'Open Knowledge Agent'}`,
      '', message.content, ''
    ])].join('\n');
    await window.studyAgent.copyText(markdown);
    statusText.textContent = 'Session copied as Markdown';
    statusNode.classList.remove('hidden');
    setTimeout(() => { if (!busy) statusNode.classList.add('hidden'); }, 1800);
  } catch (error) { showError(error); }
}

async function deleteSession(session) {
  if (!window.confirm(`Delete “${session.title}” and all of its messages?`)) return;
  clearError();
  try {
    await run(['session-delete', '--session', String(session.id)]);
    if (currentSessionID === session.id) {
      currentSessionID = null;
      resetMessages();
    }
    await loadSessions();
    await loadTopics(currentTopicID);
  } catch (error) { showError(error); }
}

async function selectSession(id) {
  clearError();
  try {
    showChatView();
    const history = JSON.parse(await run(['history', '--session', String(id)]));
    currentSessionID = id;
    pendingImages = [];
    renderImageTray();
    messagesNode.innerHTML = '';
    history.forEach(message => addMessage(message.role, message.content));
    if (!history.length) resetMessages();
    await loadSessions();
  } catch (error) { showError(error); }
}

async function newChat() {
  clearError();
  try {
    showChatView();
    const args = ['session-new', '--title', 'New Chat'];
    if (currentTopicID) args.push('--topic', String(currentTopicID));
    const result = JSON.parse(await run(args));
    currentSessionID = result.session_id;
    resetMessages();
    input.value = '';
    pendingImages = [];
    renderImageTray();
    await loadSessions();
    await loadTopics(currentTopicID);
    input.focus();
  } catch (error) { showError(error); }
}

function renderImageTray() {
  imageTray.innerHTML = '';
  pendingImages.forEach((attachment, index) => {
    const preview = document.createElement('div');
    preview.className = `image-preview${attachment.loading ? ' loading' : ''}`;
    const image = document.createElement('img');
    image.src = attachment.dataUrl;
    image.alt = attachment.name || 'Pasted image';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = '×';
    remove.title = 'Remove image';
    remove.addEventListener('click', () => {
      pendingImages.splice(index, 1);
      renderImageTray();
    });
    preview.append(image, remove);
    imageTray.appendChild(preview);
  });
  imageTray.classList.toggle('hidden', !pendingImages.length);
  resetIdleTimer();
}

function fileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error('Could not read pasted image.'));
    reader.readAsDataURL(file);
  });
}

async function addPastedImage(file) {
  if (pendingImages.length >= 4) throw new Error('Attach at most four images per message.');
  const dataUrl = await fileAsDataUrl(file);
  const attachment = { name: file.name || 'clipboard-image', dataUrl, text: '', loading: true };
  pendingImages.push(attachment);
  renderImageTray();
  try {
    const result = await window.studyAgent.extractImageText(dataUrl);
    attachment.text = result.text || '';
  } finally {
    attachment.loading = false;
    renderImageTray();
  }
}

async function sendMessage(text = input.value, speak = false) {
  text = text.trim();
  if ((!text && !pendingImages.length) || busy) return;
  if (pendingImages.some(item => item.loading)) {
    showError(new Error('Wait for pasted image text extraction to finish.'));
    return;
  }
  const images = pendingImages;
  const imageContext = images.map((item, index) => (
    `Pasted image ${index + 1} (${item.name}):\n${item.text || '[No readable text was detected locally.]'}`
  )).join('\n\n');
  const outboundText = [text, imageContext].filter(Boolean).join('\n\n');
  const visibleText = [text, images.length ? `[${images.length} pasted image${images.length === 1 ? '' : 's'}]` : ''].filter(Boolean).join('\n');
  clearError();
  input.value = '';
  pendingImages = [];
  renderImageTray();
  addMessage('user', visibleText);
  setBusy(true);
  try {
    const result = await window.studyAgent.sendChat(outboundText, currentSessionID, currentTopicID);
    currentSessionID = result.session_id;
    addMessage('assistant', result.message);
    addProfileUpdateProposal(result.profile_update, result.session_id);
    await loadSessions();
    await loadTopics(currentTopicID);
    if (speak) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(result.message);
      utterance.lang = 'zh-CN';
      window.speechSynthesis.speak(utterance);
    }
  } catch (error) { showError(error); }
  finally { setBusy(false); }
}

async function startVoice() {
  resetIdleTimer();
  clearError();
  systemVoiceActive = true;
  try {
    await window.studyAgent.startSystemSpeech('zh-CN');
  } catch (error) {
    systemVoiceActive = false;
    throw error;
  }
  voiceButton.classList.add('recording');
  voiceButton.innerHTML = '<span>■</span> Stop & Send';
  statusText.textContent = 'Starting macOS speech recognition…';
  statusNode.classList.remove('hidden');
}

async function stopVoice() {
  if (!systemVoiceActive) return;
  statusText.textContent = 'Finishing transcription…';
  await window.studyAgent.stopSystemSpeech();
  resetIdleTimer();
}

iconButton.addEventListener('click', async () => {
  const state = await window.studyAgent.toggleWindow();
  compactMode = state.compact;
  document.body.classList.toggle('compact', compactMode);
  if (!compactMode) {
    sidebar.classList.remove('hidden');
    await loadSessions();
  } else {
    sidebar.classList.add('hidden');
  }
});
typeButton.addEventListener('click', async () => {
  if (!compactMode) {
    await window.studyAgent.compactWindow();
    compactMode = true;
    document.body.classList.add('compact');
    sidebar.classList.add('hidden');
    renderTypeButton();
    return;
  }
  showChatView();
  await window.studyAgent.expandWindow();
  compactMode = false;
  document.body.classList.remove('compact');
  renderTypeButton();
  sidebar.classList.remove('hidden');
  await loadSessions();
  input.focus();
});
voiceButton.addEventListener('click', async () => {
  try {
    if (systemVoiceActive) await stopVoice();
    else await startVoice();
  } catch (error) { showError(error); }
});
sendButton.addEventListener('click', () => sendMessage());
input.addEventListener('compositionstart', () => { isComposing = true; });
input.addEventListener('compositionend', () => { isComposing = false; });
input.addEventListener('keydown', event => {
  if (event.isComposing || isComposing || event.keyCode === 229) return;
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
input.addEventListener('paste', async event => {
  const imageItems = Array.from(event.clipboardData?.items || []).filter(item => item.type.startsWith('image/'));
  if (!imageItems.length) return;
  event.preventDefault();
  clearError();
  try {
    for (const item of imageItems) {
      const file = item.getAsFile();
      if (file) await addPastedImage(file);
    }
  } catch (error) { showError(error); }
});
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
  resetIdleTimer();
});
document.getElementById('newChat').addEventListener('click', newChat);
document.getElementById('newChatSide').addEventListener('click', newChat);
document.getElementById('newTopic').addEventListener('click', openTopicDialog);
document.getElementById('newTopicMain').addEventListener('click', openTopicDialog);
topicPicker.addEventListener('change', () => selectTopic(Number(topicPicker.value)));
document.getElementById('cancelTopic').addEventListener('click', closeTopicDialog);
confirmTopicButton.addEventListener('click', () => createTopic());
topicNameInput.addEventListener('compositionstart', () => { topicNameComposing = true; });
topicNameInput.addEventListener('compositionend', () => { topicNameComposing = false; });
topicNameInput.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    event.preventDefault();
    closeTopicDialog();
    return;
  }
  if (event.key === 'Enter' && !(event.isComposing || topicNameComposing || event.keyCode === 229)) {
    event.preventDefault();
    createTopic();
  }
});
topicDialog.addEventListener('click', event => {
  if (event.target === topicDialog) closeTopicDialog();
});
document.getElementById('settings').addEventListener('click', async () => {
  await window.studyAgent.chooseProject();
  currentSessionID = null;
  currentTopicID = null;
  resetMessages();
  await loadTopics();
  await loadSessions();
});
insightsNav.addEventListener('click', async () => {
  showInsightsView();
  try { await loadInsights(); }
  catch (error) { showError(error); }
});
refreshInsightsButton.addEventListener('click', refreshInsights);
openKnowledgeButton.addEventListener('click', async () => {
  try { await window.studyAgent.openKnowledge(); }
  catch (error) { showError(error); }
});
setKnowledgeLocationButton.addEventListener('click', async () => {
  clearError();
  try {
    const state = await window.studyAgent.chooseKnowledge();
    setKnowledgeLocationButton.title = state.rootPath;
    insightsUpdated.textContent = `Knowledge folder: ${state.rootPath}`;
  } catch (error) { showError(error); }
});
exportDataButton.addEventListener('click', async () => {
  clearError();
  try {
    const result = await window.studyAgent.exportData();
    if (!result?.canceled) {
      insightsUpdated.textContent = `Data exported to ${result.path}`;
    }
  } catch (error) { showError(error); }
});
importDataButton.addEventListener('click', async () => {
  clearError();
  try {
    const result = await window.studyAgent.importData();
    if (!result?.canceled) {
      currentSessionID = null;
      currentTopicID = null;
      resetMessages();
      await loadTopics();
      await loadSessions();
      await loadInsights();
      insightsUpdated.textContent = `Imported data · backup: ${result.backup_path}`;
    }
  } catch (error) { showError(error); }
});

signInButton.addEventListener('click', async () => {
  clearError();
  try {
    if (accountState?.session?.status === 'connecting' || accountState?.busy) {
      await window.studyAgent.cancelSignIn();
    } else {
      await window.studyAgent.signIn();
    }
  } catch (error) { showError(error); }
});
disconnectButton.addEventListener('click', async () => {
  clearError();
  try { await window.studyAgent.disconnect(); }
  catch (error) { showError(error); }
});
usageButton.addEventListener('click', () => window.studyAgent.openUsage());
modelSelect.addEventListener('change', async () => {
  try { await window.studyAgent.selectModel(modelSelect.value); }
  catch (error) { showError(error); }
});
githubLoginButton.addEventListener('click', async () => {
  clearError();
  try { await window.studyAgent.githubLogin(); }
  catch (error) { showError(error); }
});
githubLogoutButton.addEventListener('click', async () => {
  clearError();
  try { await window.studyAgent.githubLogout(); }
  catch (error) { showError(error); }
});

window.studyAgent.onWindowState(state => {
  compactMode = state.compact;
  document.body.classList.toggle('compact', compactMode);
  if (compactMode) sidebar.classList.add('hidden');
  renderTypeButton();
  resetIdleTimer();
});

['pointerdown', 'mousemove', 'keydown', 'wheel', 'touchstart'].forEach(eventName => {
  window.addEventListener(eventName, resetIdleTimer, { passive: true });
});
window.addEventListener('click', () => {
  document.querySelectorAll('.session-menu,.topic-menu').forEach(menu => menu.classList.add('hidden'));
});

window.studyAgent.onAuthState(renderAuth);
window.studyAgent.authState().then(renderAuth).catch(showError);
window.studyAgent.onGitHubState(renderGitHub);
window.studyAgent.githubState().then(renderGitHub).catch(showError);
window.studyAgent.knowledgeState().then(state => {
  setKnowledgeLocationButton.title = state.rootPath;
}).catch(showError);
window.studyAgent.onSpeechEvent(async event => {
  if (event.type === 'ready') {
    statusText.textContent = 'Listening… click Stop & Send when finished';
    statusNode.classList.remove('hidden');
  } else if (event.type === 'partial') {
    input.value = event.text || '';
    input.dispatchEvent(new Event('input'));
  } else if (event.type === 'final') {
    systemVoiceActive = false;
    voiceButton.classList.remove('recording');
    voiceButton.innerHTML = '<span>●</span> Voice';
    statusNode.classList.add('hidden');
    const text = (event.text || '').trim();
    if (text) {
      input.value = text;
      await sendMessage(text, true);
    }
  } else if (event.type === 'error') {
    systemVoiceActive = false;
    voiceButton.classList.remove('recording');
    voiceButton.innerHTML = '<span>●</span> Voice';
    statusNode.classList.add('hidden');
    showError(event.text || 'Speech recognition failed.');
  }
  resetIdleTimer();
});
async function initializeNavigation() {
  try {
    await ensureInitialized();
    await loadTopics();
    await loadSessions();
  } catch (error) { showError(error); }
}
initializeNavigation();

