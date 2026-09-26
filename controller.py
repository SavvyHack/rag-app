"""Thread-safe desktop actions, shared by the local web UI and integration tests."""
import json
import logging
from pathlib import Path
import threading

from documents import SUPPORTED
from rag_engine import Engine, MODELS


class ChatController:
    def __init__(self, store, engine=None):
        self.store = store
        self.engine = engine or Engine(store)
        self.window = None
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.worker = None
        self.busy = self.closing = False
        self.job = None
        self.error = self.status = ''
        self.revision = 0
        self.assistant_id = None
        self.stream = None
        chats = store.chats()
        saved = store.setting('active_chat')
        self.chat_id = saved if saved and store.chat(saved) else (chats[0]['id'] if chats else store.create_chat())
        self.folder = store.setting('active_folder', 'all')
        if self.folder not in {'all', 'unfiled'} and not any(f['id'] == self.folder for f in store.folders()):
            self.folder = 'all'

    def _touch(self):
        self.revision += 1

    def _select(self, chat_id):
        if not self.store.chat(chat_id):
            raise ValueError('This chat no longer exists.')
        self.chat_id = chat_id
        self.store.set_setting('active_chat', chat_id)
        self.error = self.status = ''

    def _profile(self):
        saved = self.store.setting('model', 'balanced')
        return saved if saved in MODELS else 'balanced'

    def poll(self, since=-1):
        with self.lock:
            if since == self.revision:
                return None
            messages = self.store.messages(self.chat_id)
            if self.busy and self.stream is not None:
                for message in messages:
                    if message['id'] == self.assistant_id:
                        message['content'] = self.stream
            ready = bool(self.engine.llm)
            context = self.store.setting('context', 8192)
            return {
                'revision': self.revision, 'chat': self.store.chat(self.chat_id),
                'chats': self.store.chats(), 'folders': self.store.folders(), 'folder': self.folder,
                'messages': messages, 'documents': self.store.documents(self.chat_id),
                'busy': self.busy, 'job': self.job, 'ready': ready,
                'status': self.status or ('Ready when you are' if ready else 'Load a model to start chatting'),
                'error': self.error, 'semantic': bool(self.engine.embedder),
                'model': self.engine.profile if ready else self._profile(),
                'context': self.engine.context_size if ready else (context if context in (4096, 8192, 16384) else 8192),
                'models': [{'id': key, 'label': spec.label} for key, spec in MODELS.items()],
            }

    def _emit(self, kind, value):
        with self.lock:
            if kind == 'stream':
                self.stream = value
            elif kind == 'status':
                self.status = value
            self._touch()

    def _start(self, kind, function):
        self.busy, self.job = True, kind
        self.error = ''
        self.status = {'answer': 'Thinking…', 'load': 'Preparing model…',
                       'import': 'Reading files…', 'semantic': 'Preparing semantic search…'}[kind]
        self.cancel.clear()
        def work():
            try:
                result = function()
                with self.lock:
                    self.status = ''
                    if kind == 'load':
                        self.store.set_setting('model', result['profile'])
                        self.store.set_setting('context', result['context_size'])
                    elif kind == 'import':
                        self.status = f"Import {'stopped' if result['cancelled'] else 'finished'} · {len(result['successes'])} files · {len(result['errors'])} errors"
                        self.error = '\n'.join(result['errors'])
                    elif kind == 'answer' and result['status'] == 'stopped':
                        self.status = 'Stopped. Your partial response is saved.'
                    elif kind == 'semantic' and result['cancelled']:
                        self.status = 'Indexing stopped. Completed sections are saved.'
            except Exception as error:
                logging.exception('%s failed', kind)
                with self.lock:
                    self.error = str(error)
                    self.status = 'Could not finish. See details or try again.'
            finally:
                with self.lock:
                    self.busy, self.job, self.stream = False, None, None
                    self._touch()
                    closing = self.closing
                if closing and self.window:
                    self.window.destroy()
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def auto_load(self):
        self.dispatch('load', {})

    def on_closing(self):
        with self.lock:
            if self.busy:
                self.closing = True
                self.cancel.set()
                self.status = 'Saving before closing…'
                self._touch()
                return False
        return True

    def dispatch(self, action, payload=None):
        """Explicit action allowlist; no arbitrary file paths, code, or SQL from the UI."""
        payload = payload or {}
        with self.lock:
            try:
                if action == 'stop':
                    self.cancel.set()
                    self.status = 'Stopping after the current processing step…'
                elif action == 'open_link':
                    from urllib.parse import urlsplit
                    import webbrowser
                    url = str(payload['url'])
                    if urlsplit(url).scheme not in {'https', 'http', 'mailto'}:
                        raise ValueError('Only web and email links can be opened.')
                    webbrowser.open(url)
                elif self.busy:
                    raise ValueError('Wait for the current operation to finish, or press Stop.')
                elif action == 'select_chat':
                    self._select(payload['id'])
                elif action == 'select_folder':
                    folder = payload['id']
                    if folder not in {'all', 'unfiled'} and not any(f['id'] == folder for f in self.store.folders()):
                        raise ValueError('This folder no longer exists.')
                    self.folder = folder
                    self.store.set_setting('active_folder', folder)
                elif action == 'new_chat':
                    self._select(self.store.create_chat(None if self.folder in {'all', 'unfiled'} else self.folder))
                elif action == 'rename_chat':
                    title = str(payload['name']).strip()
                    if not title or len(title) > 100:
                        raise ValueError('Chat names must be between 1 and 100 characters.')
                    self.store.update_chat(self.chat_id, title=title)
                elif action == 'delete_chat':
                    self.store.delete_chat(self.chat_id)
                    chats = self.store.chats()
                    self._select(chats[0]['id'] if chats else self.store.create_chat())
                    self.folder = 'all'
                    self.store.set_setting('active_folder', self.folder)
                elif action == 'create_folder':
                    self.folder = self.store.create_folder(payload['name'])
                    self.store.set_setting('active_folder', self.folder)
                elif action == 'rename_folder':
                    self.store.rename_folder(payload['id'], payload['name'])
                elif action == 'delete_folder':
                    self.store.delete_folder(payload['id'])
                    if self.folder == payload['id']:
                        self.folder = 'unfiled'
                        self.store.set_setting('active_folder', self.folder)
                elif action == 'move_chat':
                    self.store.move_chat(self.chat_id, payload.get('id') or None)
                    self.folder = payload.get('id') or 'unfiled'
                    self.store.set_setting('active_folder', self.folder)
                elif action == 'notes':
                    notes = str(payload['text']).strip()
                    if len(notes) > 1000:
                        raise ValueError('Keep memory notes under 1,000 characters.')
                    self.store.update_chat(self.chat_id, notes=notes)
                elif action == 'remove_document':
                    self.store.delete_document(self.chat_id, payload['id'])
                elif action == 'load':
                    profile = payload.get('model', self._profile())
                    context = int(payload.get('context', self.store.setting('context', 8192)))
                    if profile not in MODELS or context not in (4096, 8192, 16384):
                        raise ValueError('Choose a supported model and context size.')
                    self._start('load', lambda: self.engine.load(profile, context, self._emit))
                elif action == 'send':
                    if not self.engine.llm:
                        raise ValueError('Load a model before sending a message.')
                    query = str(payload['text']).strip()
                    if not query:
                        raise ValueError('Write a message first.')
                    self.assistant_id = self.store.begin_turn(self.chat_id, query)
                    chat_id, assistant_id = self.chat_id, self.assistant_id
                    self.stream = ''
                    self._start('answer', lambda: self.engine.answer(chat_id, query, assistant_id, self._emit, self.cancel))
                elif action == 'semantic':
                    chat_id = self.chat_id
                    self._start('semantic', lambda: self.engine.reindex(chat_id, self._emit, self.cancel))
                elif action == 'attach':
                    import webview
                    paths = self.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                        file_types=('Supported documents (' + ';'.join('*' + ext for ext in sorted(SUPPORTED)) + ')', 'All files (*.*)'))
                    if paths:
                        chat_id = self.chat_id
                        self._start('import', lambda: self.engine.import_files(chat_id, paths, self._emit, self.cancel))
                elif action == 'export':
                    self._export(payload.get('format', 'md'))
                else:
                    raise ValueError('Unknown action.')
                self._touch()
                return {'ok': True, 'state': self.poll()}
            except Exception as error:
                logging.exception('Desktop action %s failed', action)
                return {'ok': False, 'error': str(error)}

    def _export(self, format):
        import webview
        if format not in {'md', 'json'}:
            raise ValueError('Choose Markdown or JSON.')
        paths = self.window.create_file_dialog(webview.FileDialog.SAVE, save_filename='chat.' + format,
            file_types=(f'{"Markdown" if format == "md" else "JSON"} (*.{format})',))
        if not paths:
            return
        path = Path(paths if isinstance(paths, str) else paths[0])
        chat, messages = self.store.chat(self.chat_id), self.store.messages(self.chat_id)
        if format == 'json':
            content = json.dumps({'chat': chat, 'messages': messages, 'documents': self.store.documents(self.chat_id)}, ensure_ascii=False, indent=2)
        else:
            content = f"# {chat['title']}\n\n"
            if chat['notes']:
                content += f"## Memory notes\n\n{chat['notes']}\n\n"
            content += '\n\n'.join(f"## {m['role'].title()} ({m['status']})\n\n{m['content']}" for m in messages)
        path.write_text(content, encoding='utf-8')
        self.status = 'Chat exported.'
