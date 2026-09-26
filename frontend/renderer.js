import MarkdownIt from 'markdown-it';
import texmath from 'markdown-it-texmath';
import katex from 'katex';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';

export const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const md = new MarkdownIt({html: false, linkify: true, breaks: true, typographer: false});
md.use(texmath, {
  engine: katex, delimiters: ['dollars', 'brackets', 'beg_end'],
  katexOptions: {throwOnError: false, trust: false, strict: 'ignore', maxExpand: 200, maxSize: 12, output: 'htmlAndMathml'},
});
// Each expression gets fresh macros; one answer cannot redefine math in another.
texmath.render = (tex, displayMode, options) => katex.renderToString(tex, {...options, displayMode, macros: {}});
md.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index];
  const language = token.info.trim().split(/\s+/)[0].toLowerCase();
  if (['math', 'latex', 'tex'].includes(language)) {
    return `<div class="math-block">${texmath.render(token.content, true, {throwOnError:false, trust:false, maxExpand:200, maxSize:12, strict:'ignore'})}</div>`;
  }
  const highlighted = language && hljs.getLanguage(language)
    ? hljs.highlight(token.content, {language, ignoreIllegals:true}).value : escape(token.content);
  return `<div class="code-block"><div class="code-heading"><span>${escape(language || 'text')}</span><button class="copy-code" type="button">Copy code</button></div><pre><code class="hljs">${highlighted}</code></pre></div>`;
};
// A response may describe an image; never fetch remote images or local files automatically.
md.renderer.rules.image = (tokens, index) => `<span class="image-description">[Image: ${escape(tokens[index].content || 'image')}]</span>`;
const baseLink = md.renderer.rules.link_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('rel', 'noopener noreferrer');
  return baseLink(tokens, idx, options, env, self);
};
// Task list marks remain inert and selectable, with no form controls in model output.
md.core.ruler.after('inline', 'task_lists', state => {
  for (let i = 2; i < state.tokens.length; i++) {
    const token = state.tokens[i];
    if (token.type === 'inline' && state.tokens[i-1].type === 'paragraph_open' && state.tokens[i-2].type === 'list_item_open') {
      const first = token.children?.[0];
      if (first?.type === 'text') first.content = first.content.replace(/^\[([ xX])\] /, (_, mark) => mark === ' ' ? '☐ ' : '☑ ');
    }
  }
});

export function renderMarkdown(source) {
  try {
    return DOMPurify.sanitize(md.render(source || ''), {
      USE_PROFILES: {html:true, mathMl:true, svg:true},
      ADD_TAGS: ['eq', 'eqn'],
      FORBID_TAGS: ['script','style','iframe','object','embed','form','input','textarea','select','foreignObject'],
      FORBID_ATTR: ['id','name'],
    });
  } catch {
    // Incomplete streamed markup or unsupported syntax must never hide the answer.
    return `<p class="plain-fallback">${escape(source)}</p>`;
  }
}
