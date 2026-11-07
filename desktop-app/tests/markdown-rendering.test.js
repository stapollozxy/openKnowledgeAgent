const assert = require('node:assert/strict');
const test = require('node:test');

const { renderMarkdown } = require('../src/markdown.js');

test('session messages render readable markdown instead of raw marker strings', () => {
  const output = renderMarkdown([
    '## Today',
    '',
    'Learn **continuous batching**:',
    '',
    '- Read the design',
    '- Run `pytest`',
    '',
    '```python',
    'print("done")',
    '```',
  ].join('\n'));

  assert.match(output, /<h2>Today<\/h2>/);
  assert.match(output, /<strong>continuous batching<\/strong>/);
  assert.match(output, /<ul>[\s\S]*<li>Read the design<\/li>/);
  assert.match(output, /<code>pytest<\/code>/);
  assert.match(output, /<pre><code class="language-python">print\(&quot;done&quot;\)<\/code><\/pre>/);
});

test('markdown rendering escapes model-supplied HTML', () => {
  const output = renderMarkdown('<script>alert("unsafe")</script>');

  assert.doesNotMatch(output, /<script>/);
  assert.match(output, /&lt;script&gt;/);
});

test('session messages render markdown tables and horizontal rules', () => {
  const output = renderMarkdown([
    '| Model | P95 latency |',
    '|---|---:|',
    '| Small | 42 ms |',
    '',
    '---',
  ].join('\n'));

  assert.match(output, /<table>/);
  assert.match(output, /<th>Model<\/th>/);
  assert.match(output, /<td>42 ms<\/td>/);
  assert.match(output, /<hr>/);
});
