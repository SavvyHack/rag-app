import './styles.css';
import {renderMarkdown, escape} from './renderer.js';

const $ = id => document.getElementById(id);
const paths = {
  plus:'M12 5v14M5 12h14', search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  chats:'M21 11a8 8 0 0 1-8 8H5l-4 3V11a8 8 0 0 1 8-8h4a8 8 0 0 1 8 8Z M6 9h10M6 13h6',
  chat:'M20 4H4v13h4l4 4v-4h8Z', inbox:'M4 4h16l2 13v3H2v-3L4 4ZM2 15h6l2 3h4l2-3h6',
  folder:'M3 7V4h7l3 3h8v13H3Z', file:'M13 2H5v20h14V8ZM13 2v6h6M8 12h8M8 16h6',
  note:'M4 3h16v18H4ZM8 7h8M8 11h8M8 15h5', shield:'M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6ZM8 12l3 3 5-6',
  more:'M5 11v2M12 11v2M19 11v2', settings:'M4 7h16M4 17h16M8 4v6M16 14v6',
  attach:'m8 12 7-7a4 4 0 0 1 6 6L10 22a6 6 0 0 1-8-8L13 3M6 16 16 6',
  chevron:'m8 10 4 4 4-4', arrow:'M12 19V5m-6 6 6-6 6 6', close:'m6 6 12 12M6 18 18 6',
  copy:'M9 8h12v13H9ZM5 16H2V2h12v3', spark:'m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z',
  edit:'m15 3 6 6-11 11-7 1 1-7ZM12 6l6 6', download:'M12 3v12m-5-5 5 5 5-5M3 16v5h18v-5',
  trash:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7', code:'m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 20',
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.chat}"/></svg>`;
document.querySelectorAll('[data-icon]').forEach(el => el.outerHTML = icon(el.dataset.icon));

let state = null, pending = false, pollStarted = false, toastTimer, modalSubmit = null;
let sidebarSignature = '', chatId = null;
const messageNodes = new Map(), drafts = new Map();
const dialog = $('dialog');
const api = () => window.pywebview?.api;

function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 3600);
}
async function action(name, payload = {}) {
  if (!api()) { toast('The desktop connection is not ready yet.'); return false; }
  try {
    const result = await api().dispatch(name, payload);
    if (!result.ok) throw new Error(result.error);
    if (result.state) render(result.state);
    return true;
  } catch (error) {
    if (dialog.open) { $('dialog-error').textContent = error.message; $('dialog-error').hidden = false; }
    else toast(error.message || 'Could not complete this action.');
    return false;
  }
}
function openDialog(title, body, submit, label = 'Save', danger = false) {
  $('dialog-title').textContent = title;
  $('dialog-body').innerHTML = body;
  $('dialog-error').hidden = true;
  modalSubmit = submit;
  $('dialog-actions').innerHTML = submit
    ? `<button type="button" class="secondary" id="cancel-dialog">Cancel</button><button type="submit" class="${danger ? 'danger' : 'primary'}">${escape(label)}</button>` : '';
  $('cancel-dialog')?.addEventListener('click', () => dialog.close());
  if (!dialog.open) dialog.showModal();
  const field = $('dialog-body').querySelector('input,textarea,select');
  if (field) {field.focus(); if (field.select) field.select();}
}
$('dialog-close').onclick = () => dialog.close();
$('dialog-form').onsubmit = async event => {
  event.preventDefault();
  if (!modalSubmit) return;
  const button = $('dialog-actions').querySelector('[type=submit]');
  if (button.disabled) return;
  button.disabled = true;
  try { if (await modalSubmit()) dialog.close(); }
  finally { if (button.isConnected) button.disabled = false; }
};
function nameDialog(title, value, submit, folder = false) {
  openDialog(title, `<label for="name-field">${folder ? 'Folder' : 'Chat'} name</label><input id="name-field" required maxlength="${folder ? 80 : 100}" value="${escape(value)}" autocomplete="off">`, () => submit($('name-field').value.trim()));
}
function folderOptions(folder) {
  openDialog(folder.name, `<div class="menu-items"><button type="button" id="rename-folder">${icon('edit')}Rename folder</button><button type="button" id="delete-folder" class="danger-text">${icon('trash')}Delete folder</button></div><p>Deleting a folder keeps its chats in Unfiled.</p>`);
  $('rename-folder').onclick = () => nameDialog('Rename folder', folder.name, name => action('rename_folder', {id:folder.id,name}), true);
  $('delete-folder').onclick = () => openDialog('Delete folder?', `<p>Remove <strong>${escape(folder.name)}</strong>? Its chats, files, and memory notes will be kept in Unfiled.</p>`, () => action('delete_folder', {id:folder.id}), 'Delete folder', true);
}
function moveDialog() {
  const options = [{id:'',name:'Unfiled'}, ...state.folders];
  openDialog('Move chat', `<p>Choose a home for <strong>${escape(state.chat.title)}</strong>.</p><label for="destination">Folder</label><select id="destination">${options.map(f => `<option value="${escape(f.id)}" ${f.id === (state.chat.folder_id || '') ? 'selected' : ''}>${escape(f.name)}</option>`).join('')}</select>`, async () => {
    const ok = await action('move_chat',{id:$('destination').value});
    if (ok) toast('Chat moved.'); return ok;
  }, 'Move chat');
}
function settingsDialog() {
  openDialog('Model settings', `<p>Models run on your CPU. The first download needs an internet connection.</p><label for="model-choice">Model</label><select id="model-choice">${state.models.map(m => `<option value="${m.id}" ${m.id === state.model ? 'selected' : ''}>${escape(m.label)}</option>`).join('')}</select><label for="context-choice">Context window</label><select id="context-choice">${[4096,8192,16384].map(n => `<option value="${n}" ${n === state.context ? 'selected' : ''}>${n.toLocaleString()} tokens</option>`).join('')}</select><div class="field-note">Larger windows use more memory. Start with Light on a slower computer.</div>`, () => action('load',{model:$('model-choice').value, context:Number($('context-choice').value)}), 'Load / retry');
}
function filesDialog() {
  openDialog('Attached files', `<p>Extracted text is saved with this chat, even if the original file moves.</p><div>${state.documents.length ? state.documents.map(d => `<div class="document-row">${icon('file')}<div>${escape(d.name)}<small>${d.chunk_count} sections saved</small></div><button type="button" data-remove="${escape(d.id)}" class="quiet">Remove</button></div>`).join('') : '<p>No files attached yet.</p>'}</div><div class="menu-items"><button type="button" id="attach-more">${icon('plus')}Attach files</button><button type="button" id="semantic">${icon('search')}${state.semantic ? 'Update' : 'Enable'} semantic search</button></div><div class="field-note">PDF, text, Markdown, HTML, JSON, CSV, YAML, XML, and logs.<br>Semantic search downloads a small model on first use.</div>`);
  $('dialog-body').querySelectorAll('[data-remove]').forEach(button => button.onclick = async () => {
    if (await action('remove_document', {id:button.dataset.remove})) filesDialog();
  });
  $('attach-more').onclick = async () => { dialog.close(); await action('attach'); };
  $('semantic').onclick = async () => { dialog.close(); await action('semantic'); };
}
function chatOptions() {
  openDialog('Chat options', `<div class="menu-items"><button type="button" id="rename-chat">${icon('edit')}Rename chat</button><button type="button" id="move-menu">${icon('folder')}Move to folder</button><button type="button" id="export-md">${icon('download')}Export as Markdown</button><button type="button" id="export-json">${icon('code')}Export as JSON</button><hr><button type="button" id="delete-chat" class="danger-text">${icon('trash')}Delete chat</button></div>`);
  $('rename-chat').onclick = () => nameDialog('Rename chat',state.chat.title,name => action('rename_chat',{name}));
  $('move-menu').onclick = moveDialog;
  for (const format of ['md','json']) $(`export-${format}`).onclick = async () => {dialog.close(); await action('export',{format});};
  $('delete-chat').onclick = () => openDialog('Delete this chat?', `<p>Permanently delete <strong>${escape(state.chat.title)}</strong>, its messages, memory notes, and attached text? This cannot be undone.</p>`, () => action('delete_chat'), 'Delete chat', true);
}

function renderSidebar() {
  const signature = JSON.stringify([state.chats, state.folders, state.folder, state.chat.id, state.busy, $('search').value]);
  if (signature === sidebarSignature) return;
  sidebarSignature = signature;
  $('all-count').textContent = state.chats.length;
  $('unfiled-count').textContent = state.chats.filter(c => !c.folder_id).length;
  $('all-chats').classList.toggle('active',state.folder === 'all');
  $('unfiled').classList.toggle('active',state.folder === 'unfiled');
  $('folders').innerHTML = state.folders.length ? state.folders.map(f => `<div class="folder-row ${state.folder === f.id ? 'active' : ''}"><button class="nav-row" data-folder="${escape(f.id)}" title="${escape(f.name)}" ${state.busy ? 'disabled' : ''}>${icon('folder')}<span class="folder-name">${escape(f.name)}</span><span class="count">${f.chat_count}</span></button><button class="icon-button folder-menu" data-folder-menu="${escape(f.id)}" aria-label="Manage ${escape(f.name)}" ${state.busy ? 'disabled' : ''}>${icon('more')}</button></div>`).join('') : '<div class="folder-empty">A little order goes a long way.<br>Create a folder to group your chats.</div>';
  $('folders').querySelectorAll('[data-folder]').forEach(el => el.onclick = () => action('select_folder',{id:el.dataset.folder}));
  $('folders').querySelectorAll('[data-folder-menu]').forEach(el => el.onclick = () => folderOptions(state.folders.find(f => f.id === el.dataset.folderMenu)));
  const query = $('search').value.trim().toLowerCase();
  const chats = state.chats.filter(c => (state.folder === 'all' || (state.folder === 'unfiled' ? !c.folder_id : c.folder_id === state.folder)) && c.title.toLowerCase().includes(query));
  $('chats-label').textContent = state.folder === 'all' ? 'All chats' : state.folder === 'unfiled' ? 'Unfiled chats' : state.folders.find(f => f.id === state.folder)?.name || 'Chats';
  $('filtered-count').textContent = chats.length;
  $('chats').innerHTML = chats.length ? chats.map(c => `<button class="chat-item ${c.id === state.chat.id ? 'active' : ''}" data-chat="${escape(c.id)}" title="${escape(c.title)}" ${state.busy ? 'disabled' : ''}>${icon('chat')}<span class="chat-meta"><span class="chat-name">${escape(c.title)}</span><small>${escape(new Date(c.updated).toLocaleDateString(undefined,{month:'short',day:'numeric'}))}</small></span></button>`).join('') : `<div class="empty-list">${query ? 'No matching chats in this section.' : 'No chats here yet.<br>Start a new chat, or move one here.'}</div>`;
  $('chats').querySelectorAll('[data-chat]').forEach(el => el.onclick = () => action('select_chat',{id:el.dataset.chat}));
}

function welcome() {
  $('messages').innerHTML = `<div class="welcome"><div class="welcome-symbol">${icon('spark')}</div><h2>Make room for a good question.</h2><p>Think things through, explore an idea, or find answers in your documents. All on your own device.</p><div class="suggestions"><button class="suggestion" id="welcome-attach">${icon('file')}<span>Explore a document<small>Attach a file and ask a question</small></span></button><button class="suggestion" id="welcome-prompt">${icon('spark')}<span>Think it through<small>A fresh perspective on an idea</small></span></button></div></div>`;
  $('welcome-attach').onclick = () => action('attach');
  $('welcome-prompt').onclick = () => {$('prompt').value = 'Help me think through '; $('prompt').focus(); updateSend();};
}
function nearBottom() {const el = $('conversation'); return el.scrollHeight - el.scrollTop - el.clientHeight < 100;}
function bottom() {$('conversation').scrollTop = $('conversation').scrollHeight; $('jump-latest').hidden = true;}
function renderMessages(switched) {
  const follow = switched || nearBottom();
  if (!state.messages.length) {
    if (!$('messages').querySelector('.welcome')) {messageNodes.clear(); welcome();}
    return;
  }
  $('messages').querySelector('.welcome')?.remove();
  const ids = new Set(state.messages.map(m => m.id));
  for (const [id, saved] of messageNodes) if (!ids.has(id)) {saved.el.remove();messageNodes.delete(id);}
  for (const message of state.messages) {
    const streaming = state.busy && state.job === 'answer' && message.status === 'streaming';
    const signature = JSON.stringify([message.content, message.status, streaming]);
    let saved = messageNodes.get(message.id);
    if (saved?.signature === signature) continue;
    if (!saved) {
      const el = document.createElement('article');
      $('messages').append(el); saved = {el}; messageNodes.set(message.id,saved);
    }
    saved.signature = signature;
    const user = message.role === 'user';
    const status = streaming ? 'Writing…' : message.status === 'streaming' ? 'Unfinished' : message.status === 'complete' ? '' : message.status === 'error' ? 'Interrupted · saved' : 'Stopped · saved';
    // The engine appends source metadata after generation. Keep it separate visually.
    const sourceMatch = !user && message.content.match(/\n\nSources supplied:\n((?:\[\d+\] [^\n]+(?:\n|$))+)$/);
    const parts = sourceMatch ? [message.content.slice(0,sourceMatch.index),sourceMatch[1]] : [message.content];
    let rendered = message.content ? renderMarkdown(parts[0]) : `<div class="thinking">${streaming ? 'Thinking…' : 'No response saved.'}</div>`;
    if (parts.length > 1) rendered += `<div class="sources"><div class="sources-label">${icon('file')}Sources supplied</div>${escape(parts.slice(1).join('\n\nSources supplied:\n')).replace(/\n/g,'<br>')}</div>`;
    saved.el.className = `message ${user ? 'user' : 'assistant'} ${streaming ? 'streaming' : ''}`;
    saved.el.dataset.messageId = message.id;
    saved.el.innerHTML = `<div class="message-heading"><span class="avatar">${user ? 'Y' : icon('spark')}</span><span>${user ? 'You' : 'Local RAG'}</span><span class="message-status">${escape(status)}</span></div><div class="message-content">${rendered}</div><div class="message-actions"><button class="copy-message" title="Copy original message">${icon('copy')}Copy</button></div>`;
    saved.el.querySelectorAll('table').forEach(table => {const wrap = document.createElement('div');wrap.className = 'table-wrap';table.replaceWith(wrap);wrap.append(table);});
    saved.el.querySelector('.copy-message').onclick = () => copy(message.content);
    saved.el.querySelectorAll('.copy-code').forEach(button => button.onclick = () => copy(button.closest('.code-block').querySelector('code').textContent));
    saved.el.querySelectorAll('a').forEach(link => link.onclick = event => {event.preventDefault();action('open_link',{url:link.getAttribute('href')});});
  }
  if (follow) bottom(); else $('jump-latest').hidden = false;
}
function render(next) {
  if (!next || (state && next.revision < state.revision)) return;
  const switched = chatId !== next.chat.id;
  if (switched) {
    if (chatId) drafts.set(chatId,$('prompt').value);
    chatId = next.chat.id;
    $('prompt').value = drafts.get(chatId) || '';
    messageNodes.clear(); $('messages').replaceChildren(); autoSize();
  }
  state = next;
  $('chat-title').textContent = state.chat.title;
  $('chat-title').title = state.chat.title;
  $('breadcrumb').textContent = state.chat.folder_id ? 'Folders / ' + (state.folders.find(f => f.id === state.chat.folder_id)?.name || 'Unfiled') : 'Your library / Unfiled';
  $('file-count').textContent = state.documents.length ? `Files · ${state.documents.length}` : 'Files';
  $('memory-dot').hidden = !state.chat.notes;
  $('model-label').textContent = state.models.find(m => m.id === state.model)?.label.split(' · ')[1] || 'Choose a model';
  $('model-dot').style.background = state.ready ? '' : '#88949e';
  $('status').textContent = state.status;
  $('error-banner').hidden = !state.error;
  $('error-summary').textContent = state.error.split('\n')[0];
  for (const id of ['new-chat','new-folder','all-chats','unfiled','move-chat','chat-options','settings','files','memory','attach','model-button']) $(id).disabled = state.busy;
  $('stop').hidden = !state.busy || !['answer','import','semantic'].includes(state.job);
  $('stop').disabled = state.status.startsWith('Stopping');
  $('send').hidden = !$('stop').hidden;
  renderSidebar(); renderMessages(switched); updateSend();
  $('welcome-attach')?.toggleAttribute('disabled',state.busy);
}
function updateSend() {$('send').disabled = pending || !state?.ready || state.busy || !$('prompt').value.trim();}
function autoSize() {$('prompt').style.height = 'auto'; $('prompt').style.height = Math.min($('prompt').scrollHeight,190) + 'px';}
async function send() {
  if ($('send').disabled || pending) return;
  const text = $('prompt').value;
  pending = true; updateSend();
  try {
    if (await action('send',{text})) {
      // Preserve any new text typed while the bridge was accepting this message.
      if ($('prompt').value === text) {$('prompt').value = ''; drafts.delete(chatId); autoSize();}
      bottom();
    }
  } finally {pending = false; updateSend(); $('prompt').focus();}
}
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text); toast('Copied to clipboard.');
  } catch {
    const field = document.createElement('textarea'); field.value = text; field.style.position = 'fixed';field.style.opacity = '0';
    document.body.append(field);field.select();const ok = document.execCommand('copy');field.remove();toast(ok ? 'Copied to clipboard.' : 'Select the text and press Ctrl+C to copy.');
  }
}
$('new-chat').onclick = () => action('new_chat');
$('new-folder').onclick = () => nameDialog('New folder','',name => action('create_folder',{name}),true);
$('all-chats').onclick = () => action('select_folder',{id:'all'});
$('unfiled').onclick = () => action('select_folder',{id:'unfiled'});
$('search').oninput = () => {if (state) renderSidebar();};
$('move-chat').onclick = moveDialog;
$('chat-options').onclick = chatOptions;
$('settings').onclick = $('model-button').onclick = () => state && settingsDialog();
$('files').onclick = filesDialog;
$('memory').onclick = () => openDialog('Memory notes', `<p>Keep names, preferences, and project facts available in this chat. These notes are included in future questions.</p><label for="notes">Notes · up to 1,000 characters</label><textarea id="notes" maxlength="1000">${escape(state.chat.notes)}</textarea>`, () => action('notes',{text:$('notes').value}), 'Save notes');
$('attach').onclick = () => action('attach');
$('send').onclick = send;
$('stop').onclick = () => action('stop');
$('prompt').oninput = () => {autoSize();updateSend();};
$('prompt').onkeydown = event => {if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault();send();}};
$('jump-latest').onclick = bottom;
$('conversation').onscroll = () => {$('jump-latest').hidden = nearBottom();};
$('error-details').onclick = () => openDialog('Error details',`<p class="error-detail">${escape(state.error)}</p>`);
document.addEventListener('keydown',event => {if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'n' && !dialog.open) {event.preventDefault(); if (!state?.busy) action('new_chat');}});
async function poll() {
  if (pollStarted) return;
  pollStarted = true;
  while (api()) {
    try {render(await api().poll(state?.revision ?? -1));}
    catch { $('status').textContent = 'Reconnecting to your local workspace…'; }
    await new Promise(resolve => setTimeout(resolve,180));
  }
  pollStarted = false;
}
window.addEventListener('pywebviewready',poll);
for (const id of ['new-chat','new-folder','all-chats','unfiled','move-chat','chat-options','settings','files','memory','attach','model-button']) $(id).disabled = true;
if (api()) poll();
// Read-only entry point for renderer/desktop smoke checks, with the same production UI.
window.LocalRAG = {renderMarkdown, render};
