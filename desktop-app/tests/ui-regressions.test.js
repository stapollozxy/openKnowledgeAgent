const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const renderer = fs.readFileSync(path.join(root, 'src', 'renderer.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'src', 'index.html'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'src', 'styles.css'), 'utf8');
const preload = fs.readFileSync(path.join(root, 'src', 'preload.js'), 'utf8');
const main = fs.readFileSync(path.join(root, 'src', 'main.js'), 'utf8');
const build = fs.readFileSync(path.join(root, 'build_app.sh'), 'utf8');

test('chat input protects IME composition from premature submit', () => {
  assert.match(renderer, /compositionstart/);
  assert.match(renderer, /compositionend/);
  assert.match(renderer, /isComposing/);
  assert.match(renderer, /keyCode\s*===\s*229/);
});

test('chat input accepts pasted image clipboard items', () => {
  assert.match(renderer, /addEventListener\(['"]paste['"]/);
  assert.match(renderer, /clipboardData/);
  assert.match(renderer, /image\//);
  assert.match(renderer, /readAsDataURL/);
});

test('compact window exposes a dedicated draggable handle', () => {
  assert.match(html, /id="dragHandle"/);
  assert.match(styles, /\.drag-handle[\s\S]*-webkit-app-region:\s*drag/);
  assert.match(styles, /body\.compact[\s\S]*\.drag-handle/);
  assert.match(styles, /body\.compact\.insights-mode \.actions[\s\S]*display:\s*grid/);
});

test('portable data export and import are wired through isolated IPC', () => {
  assert.match(html, /id="exportData"/);
  assert.match(html, /id="importData"/);
  assert.match(preload, /ipcRenderer\.invoke\('data:export'\)/);
  assert.match(preload, /ipcRenderer\.invoke\('data:import'\)/);
  assert.match(main, /ipcMain\.handle\('data:export'/);
  assert.match(main, /ipcMain\.handle\('data:import'/);
});

test('packaged app includes a backend for sign-in-first use', () => {
  assert.match(main, /function agentRuntime\(/);
  assert.match(main, /backend', 'src/);
  assert.match(build, /study-agent\/src/);
});
