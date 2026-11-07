(function exposeMarkdownRenderer(globalScope) {
  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function renderInline(value) {
    return String(value).split(/(`[^`\n]+`)/g).map(part => {
      if (part.startsWith('`') && part.endsWith('`')) {
        return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
      }
      return escapeHtml(part)
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    }).join('');
  }

  function tableCells(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '')
      .split('|').map(cell => cell.trim());
  }

  function isTableSeparator(line) {
    const cells = tableCells(line);
    return cells.length > 1 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
  }

  function renderMarkdown(value) {
    const lines = String(value ?? '').replace(/\r\n?/g, '\n').split('\n');
    const output = [];
    let paragraph = [];
    let listType = '';
    let listItems = [];
    let codeLanguage = '';
    let codeLines = null;

    const flushParagraph = () => {
      if (!paragraph.length) return;
      output.push(`<p>${paragraph.map(renderInline).join('<br>')}</p>`);
      paragraph = [];
    };
    const flushList = () => {
      if (!listItems.length) return;
      output.push(`<${listType}>${listItems.map(item => `<li>${renderInline(item)}</li>`).join('')}</${listType}>`);
      listType = '';
      listItems = [];
    };
    const flushBlocks = () => {
      flushParagraph();
      flushList();
    };

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      if (codeLines !== null) {
        if (/^```\s*$/.test(line)) {
          const className = codeLanguage ? ` class="language-${codeLanguage}"` : '';
          output.push(`<pre><code${className}>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
          codeLines = null;
          codeLanguage = '';
        } else {
          codeLines.push(line);
        }
        continue;
      }

      const fence = line.match(/^```\s*([A-Za-z0-9_+-]{0,32})\s*$/);
      if (fence) {
        flushBlocks();
        codeLanguage = fence[1] || '';
        codeLines = [];
        continue;
      }
      if (!line.trim()) {
        flushBlocks();
        continue;
      }

      if (line.includes('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
        flushBlocks();
        const headers = tableCells(line);
        const rows = [];
        index += 2;
        while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
          rows.push(tableCells(lines[index]));
          index += 1;
        }
        index -= 1;
        const head = headers.map(cell => `<th>${renderInline(cell)}</th>`).join('');
        const body = rows.map(row => (
          `<tr>${headers.map((_, cellIndex) => `<td>${renderInline(row[cellIndex] || '')}</td>`).join('')}</tr>`
        )).join('');
        output.push(`<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
        continue;
      }
      if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
        flushBlocks();
        output.push('<hr>');
        continue;
      }
      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        flushBlocks();
        const level = heading[1].length;
        output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        continue;
      }
      const unordered = line.match(/^\s*[-+*]\s+(.+)$/);
      const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (unordered || ordered) {
        flushParagraph();
        const nextType = unordered ? 'ul' : 'ol';
        if (listType && listType !== nextType) flushList();
        listType = nextType;
        listItems.push((unordered || ordered)[1]);
        continue;
      }
      const quote = line.match(/^>\s?(.*)$/);
      if (quote) {
        flushBlocks();
        output.push(`<blockquote>${renderInline(quote[1])}</blockquote>`);
        continue;
      }
      flushList();
      paragraph.push(line);
    }

    if (codeLines !== null) {
      const className = codeLanguage ? ` class="language-${codeLanguage}"` : '';
      output.push(`<pre><code${className}>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
    }
    flushBlocks();
    return output.join('');
  }

  const api = { renderMarkdown };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (globalScope) globalScope.OpenKnowledgeMarkdown = api;
})(typeof window !== 'undefined' ? window : null);
