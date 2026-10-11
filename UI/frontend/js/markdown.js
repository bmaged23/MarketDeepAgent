// Safe chat Markdown subset: construct known DOM elements; never parse model HTML.
function appendMarkdownInline(parent, text) {
  const pattern = /(`[^`\n]+`|\*\*[^\n]+?\*\*|__[^\n]+?__|\*[^*\n]+\*|_[^_\n]+_|\[[^\]\n]+\]\([^\s)]+\))/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(cursor, match.index)));
    const token = match[0]; let node;
    if (token.startsWith('`')) {
      node = document.createElement('code'); node.textContent = token.slice(1,-1);
    } else if (token.startsWith('[')) {
      const parts = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (/^https?:\/\//i.test(parts[2])) {
        node = document.createElement('a'); node.href = parts[2]; node.target = '_blank'; node.rel = 'noopener noreferrer'; node.textContent = parts[1];
      } else { node = document.createTextNode(token); }
    } else {
      const strong = token.startsWith('**') || token.startsWith('__');
      node = document.createElement(strong ? 'strong' : 'em');
      appendMarkdownInline(node, token.slice(strong ? 2 : 1, strong ? -2 : -1));
    }
    parent.append(node); cursor = match.index + token.length;
  }
  parent.append(document.createTextNode(text.slice(cursor)));
}
function renderChatMarkdown(parent, source) {
  const lines = String(source).replace(/\r\n?/g,'\n').split('\n');
  let paragraph = [], list = null;
  const flush = () => {
    if (paragraph.length) { const p = document.createElement('p'); appendMarkdownInline(p,paragraph.join('\n')); parent.append(p); paragraph = []; }
  };
  for (let i=0; i<lines.length; i++) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      flush(); list = null; const codeLines = [];
      while (++i < lines.length && !/^\s*```/.test(lines[i])) codeLines.push(lines[i]);
      const pre = document.createElement('pre'), code = document.createElement('code');
      code.textContent = codeLines.join('\n'); pre.append(code); parent.append(pre); continue;
    }
    if (!line.trim()) { flush(); list = null; continue; }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) { flush(); list = null; const h = document.createElement('h'+heading[1].length); appendMarkdownInline(h,heading[2]); parent.append(h); continue; }
    const item = /^\s*(?:([-+*])\s+|(\d+)\.\s+)(.+)$/.exec(line);
    if (item) {
      flush(); const kind = item[2] ? 'ol' : 'ul';
      if (!list || list.tagName.toLowerCase() !== kind) { list = document.createElement(kind); if (item[2]) list.start = Number(item[2]); parent.append(list); }
      const li = document.createElement('li'); appendMarkdownInline(li,item[3]); list.append(li); continue;
    }
    const quote = /^>\s?(.*)$/.exec(line);
    if (quote) { flush(); list = null; const block = document.createElement('blockquote'); appendMarkdownInline(block,quote[1]); parent.append(block); continue; }
    list = null; paragraph.push(line);
  }
  flush();
}
function focusChatAnswer(container, answer) {
  // Scroll only the message pane, keeping the beginning of a long answer readable.
  const top = container.scrollTop + answer.getBoundingClientRect().top - container.getBoundingClientRect().top - 18;
  container.scrollTo({top:Math.max(0,top),behavior:'auto'});
}
