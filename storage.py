"""Durable, per-user chat storage, independent of the executable's location."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid


def data_directory():
    if os.environ.get("OFFLINE_RAG_DATA_DIR"):
        return Path(os.environ["OFFLINE_RAG_DATA_DIR"]).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "OfflineRAG"


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "chats.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                    created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'complete', created TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id, id);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, digest TEXT NOT NULL, created TEXT NOT NULL,
                    UNIQUE(chat_id, digest));
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL, location TEXT NOT NULL, content TEXT NOT NULL,
                    embedding BLOB, embedding_model TEXT);
                CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            # Additive migration: existing transcripts, documents and notes stay in place.
            columns = {row['name'] for row in db.execute('PRAGMA table_info(chats)')}
            if 'folder_id' not in columns:
                db.execute('ALTER TABLE chats ADD COLUMN folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL')
            db.execute('CREATE INDEX IF NOT EXISTS chats_folder ON chats(folder_id)')
            db.execute('PRAGMA user_version=2')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))

    def create_chat(self, folder_id=None):
        chat_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO chats(id,title,notes,created,updated,folder_id) VALUES (?, ?, '', ?, ?, ?)",
                       (chat_id, "New chat", now(), now(), folder_id))
        return chat_id

    def folders(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('''
                SELECT f.*, count(c.id) AS chat_count FROM folders f
                LEFT JOIN chats c ON c.folder_id=f.id GROUP BY f.id
                ORDER BY f.name COLLATE NOCASE, f.id''')]

    @staticmethod
    def _folder_name(name):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            raise ValueError('Folder names must be between 1 and 80 characters.')
        return name.strip()

    def create_folder(self, name):
        name = self._folder_name(name)
        folder_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO folders VALUES (?, ?, ?)', (folder_id, name, now()))
        return folder_id

    def rename_folder(self, folder_id, name):
        name = self._folder_name(name)
        with self.connect() as db:
            if not db.execute('UPDATE folders SET name=? WHERE id=?', (name, folder_id)).rowcount:
                raise ValueError('This folder no longer exists.')

    def delete_folder(self, folder_id):
        """Removing an organisational folder never deletes its conversations."""
        with self.connect() as db:
            db.execute('DELETE FROM folders WHERE id=?', (folder_id,))

    def move_chat(self, chat_id, folder_id=None):
        with self.connect() as db:
            if folder_id and not db.execute('SELECT 1 FROM folders WHERE id=?', (folder_id,)).fetchone():
                raise ValueError('This folder no longer exists.')
            if not db.execute('UPDATE chats SET folder_id=? WHERE id=?', (folder_id, chat_id)).rowcount:
                raise ValueError('This chat no longer exists.')

    def chats(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM chats ORDER BY updated DESC, id")]

    def chat(self, chat_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        return dict(row) if row else None

    def update_chat(self, chat_id, *, title=None, notes=None):
        with self.connect() as db:
            if title is not None:
                db.execute("UPDATE chats SET title=?, updated=? WHERE id=?", (title[:100], now(), chat_id))
            if notes is not None:
                db.execute("UPDATE chats SET notes=?, updated=? WHERE id=?", (notes, now(), chat_id))

    def delete_chat(self, chat_id):
        with self.connect() as db:
            db.execute("DELETE FROM chats WHERE id=?", (chat_id,))

    def messages(self, chat_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY id", (chat_id,))]

    def add_message(self, chat_id, role, content, status="complete"):
        with self.connect() as db:
            cursor = db.execute("INSERT INTO messages(chat_id,role,content,status,created) VALUES (?,?,?,?,?)",
                                (chat_id, role, content, status, now()))
            db.execute("UPDATE chats SET updated=? WHERE id=?", (now(), chat_id))
            if role == "user":
                count = db.execute("SELECT count(*) FROM messages WHERE chat_id=? AND role='user'", (chat_id,)).fetchone()[0]
                if count == 1:
                    db.execute("UPDATE chats SET title=? WHERE id=?", (" ".join(content.split())[:60], chat_id))
            return cursor.lastrowid

    def update_message(self, message_id, content, status="streaming"):
        with self.connect() as db:
            db.execute("UPDATE messages SET content=?, status=? WHERE id=?", (content, status, message_id))

    def begin_turn(self, chat_id, query):
        """Save the question and reply placeholder in one transaction."""
        with self.connect() as db:
            count = db.execute("SELECT count(*) FROM messages WHERE chat_id=? AND role='user'", (chat_id,)).fetchone()[0]
            db.execute("INSERT INTO messages(chat_id,role,content,status,created) VALUES (?,'user',?,'complete',?)",
                       (chat_id, query, now()))
            cursor = db.execute("INSERT INTO messages(chat_id,role,content,status,created) VALUES (?,'assistant','','streaming',?)",
                                (chat_id, now()))
            db.execute("UPDATE chats SET updated=? WHERE id=?", (now(), chat_id))
            if count == 0:
                db.execute("UPDATE chats SET title=? WHERE id=?", (" ".join(query.split())[:60], chat_id))
            return cursor.lastrowid

    def has_document(self, chat_id, digest):
        with self.connect() as db:
            return bool(db.execute("SELECT 1 FROM documents WHERE chat_id=? AND digest=?", (chat_id, digest)).fetchone())

    def add_document(self, chat_id, name, digest, chunks, embeddings=None, embedding_model=None):
        """Commit source metadata and every chunk together, never a half-indexed file."""
        doc_id = uuid.uuid4().hex
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM chunks c JOIN documents d ON c.document_id=d.id WHERE d.chat_id=?", (chat_id,)).fetchone()[0]
            if total + len(chunks) > 10000:
                raise ValueError("This chat has reached its document limit. Start a new chat for more files.")
            db.execute("INSERT INTO documents VALUES (?,?,?,?,?)", (doc_id, chat_id, name, digest, now()))
            db.executemany("INSERT INTO chunks(document_id,position,location,content,embedding,embedding_model) VALUES (?,?,?,?,?,?)",
                           [(doc_id, i, location, text, embeddings[i] if embeddings else None,
                             embedding_model if embeddings else None) for i, (location, text) in enumerate(chunks)])
            db.execute("UPDATE chats SET updated=? WHERE id=?", (now(), chat_id))
        return doc_id

    def documents(self, chat_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT d.*, count(c.id) AS chunk_count FROM documents d LEFT JOIN chunks c ON c.document_id=d.id WHERE d.chat_id=? GROUP BY d.id ORDER BY d.created", (chat_id,))]

    def chunks(self, chat_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT c.*, d.name FROM chunks c JOIN documents d ON c.document_id=d.id WHERE d.chat_id=? ORDER BY d.created,c.position", (chat_id,))]

    def delete_document(self, chat_id, doc_id):
        with self.connect() as db:
            db.execute("DELETE FROM documents WHERE id=? AND chat_id=?", (doc_id, chat_id))
