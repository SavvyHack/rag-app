import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock

from controller import ChatController
from storage import Store


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)

    def test_existing_v1_database_migrates_without_losing_any_content(self):
        old = self.root / 'old'
        old.mkdir()
        with closing(sqlite3.connect(old / 'chats.sqlite3')) as db:
            db.executescript("""CREATE TABLE chats(id TEXT PRIMARY KEY,title TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
                INSERT INTO chats VALUES ('old','Invoice chat','Keep this note','yesterday','today');
                PRAGMA user_version=1;""")
        migrated = Store(old)
        self.assertEqual(migrated.chat('old')['notes'], 'Keep this note')
        self.assertIsNone(migrated.chat('old')['folder_id'])
        migrated.add_message('old','assistant','**Invoice** $40.50')
        folder = migrated.create_folder('Finance')
        migrated.move_chat('old',folder)
        self.assertEqual(Store(old).messages('old')[0]['content'],'**Invoice** $40.50')
        self.assertEqual(Store(old).chat('old')['folder_id'],folder)

    def test_folder_lifecycle_preserves_chat_messages_notes_and_documents(self):
        folder = self.store.create_folder(' Work ')
        chat = self.store.create_chat(folder)
        self.store.add_message(chat,'user','Question')
        self.store.add_document(chat,'source.txt','digest',[('text','Saved facts')])
        self.store.update_chat(chat, notes='A note')
        self.store.rename_folder(folder,'Finance')
        self.assertEqual(self.store.folders()[0]['chat_count'],1)
        self.assertEqual(Store(self.root).folders()[0]['name'],'Finance')
        self.store.delete_folder(folder)
        reopened = Store(self.root)
        self.assertIsNone(reopened.chat(chat)['folder_id'])
        self.assertEqual(reopened.chat(chat)['notes'],'A note')
        self.assertEqual(len(reopened.messages(chat)),1)
        self.assertEqual(reopened.chunks(chat)[0]['content'],'Saved facts')

    def test_moves_are_validated_and_do_not_change_recency(self):
        first, second = self.store.create_folder('A'), self.store.create_folder('B')
        chat = self.store.create_chat(first)
        before = self.store.chat(chat)['updated']
        self.store.move_chat(chat,second)
        self.assertEqual(self.store.chat(chat)['updated'],before)
        with self.assertRaises(ValueError): self.store.move_chat(chat,'missing')
        self.assertEqual(self.store.chat(chat)['folder_id'],second)
        self.store.move_chat(chat)
        self.assertIsNone(self.store.chat(chat)['folder_id'])
        for name in ('', '   ', 'x'*81):
            with self.assertRaises(ValueError): self.store.create_folder(name)

    def test_controller_persists_selection_and_new_chat_in_folder(self):
        ui = ChatController(self.store)
        self.assertTrue(ui.dispatch('create_folder',{'name':'Invoices'})['ok'])
        folder = ui.folder
        ui.dispatch('new_chat')
        chat = ui.chat_id
        self.assertEqual(self.store.chat(chat)['folder_id'],folder)
        reopened = ChatController(Store(self.root))
        self.assertEqual(reopened.folder,folder)
        self.assertEqual(reopened.chat_id,chat)
        reopened.dispatch('move_chat',{'id':None})
        self.assertEqual(ChatController(Store(self.root)).folder,'unfiled')
        self.assertFalse(reopened.dispatch('select_folder',{'id':'missing'})['ok'])

    def test_controller_stream_stop_and_close_preserve_partial_response(self):
        entered, release = threading.Event(), threading.Event()
        engine = Mock(llm=True, embedder=None, profile='balanced',context_size=8192)
        def answer(chat, query, assistant, emit, cancel):
            emit('stream','**Partial**\nSecond line')
            entered.set()
            release.wait(3)
            self.store.update_message(assistant,'**Partial**\nSecond line','stopped')
            return {'status':'stopped'}
        engine.answer = answer
        ui = ChatController(self.store,engine)
        ui.window = Mock()
        self.assertTrue(ui.dispatch('send',{'text':'Test'})['ok'])
        self.assertTrue(entered.wait(3))
        snapshot = ui.poll()
        self.assertEqual(snapshot['messages'][-1]['content'],'**Partial**\nSecond line')
        self.assertFalse(ui.dispatch('new_chat')['ok'])
        self.assertFalse(ui.on_closing())
        self.assertTrue(ui.cancel.is_set())
        release.set(); ui.worker.join(3)
        self.assertFalse(ui.busy)
        self.assertEqual(self.store.messages(ui.chat_id)[-1]['status'],'stopped')
        ui.window.destroy.assert_called_once()

    def test_export_uses_original_markdown_and_json(self):
        ui = ChatController(self.store)
        content = '**Invoice** $40.50\n\n$$x^2$$'
        self.store.add_message(ui.chat_id,'assistant',content)
        for format in ('md','json'):
            path = self.root / ('chat.' + format)
            ui.window = Mock()
            ui.window.create_file_dialog.return_value = (str(path),)
            self.assertTrue(ui.dispatch('export',{'format':format})['ok'])
            saved = path.read_text(encoding='utf-8')
            if format == 'json': self.assertEqual(json.loads(saved)['messages'][0]['content'],content)
            else: self.assertIn(content,saved)
