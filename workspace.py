"""Local file tools. File operations stay within the chosen project; commands need review."""
import base64
import difflib
import hashlib
import os
from pathlib import Path, PureWindowsPath
import queue
import subprocess
import sys
import tempfile
import threading
import time

from documents import decode_text, extract_document, SUPPORTED

SKIP = {'.git', '.hg', '.svn', 'node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build'}
PRIVATE = {'.env', '.ssh', '.aws', '.azure', '.gnupg'}
MAX_EDIT = 120_000


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('The project folder is unavailable. Choose it again.')

    def path(self, relative):
        if not isinstance(relative, str) or not relative or len(relative) > 500:
            raise ValueError('Use a relative project path.')
        win = PureWindowsPath(relative)
        parts = relative.replace('\\', '/').split('/')
        if Path(relative).is_absolute() or win.drive or win.root or ':' in relative or '..' in parts:
            raise ValueError('Paths must stay inside the project folder.')
        if any(p.lower() in SKIP | PRIVATE or p.lower().startswith('.env.') for p in parts):
            raise ValueError('That private or generated folder is excluded from file tools.')
        reserved = getattr(os.path, 'isreserved', lambda value: PureWindowsPath(value).is_reserved())
        if any(p.rstrip(' .') != p or reserved(p) for p in parts if p not in {'', '.'}):
            raise ValueError('Use an ordinary file name.')
        candidate = self.root / relative
        for parent in [candidate, *candidate.parents]:
            if parent == self.root:
                break
            if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
                raise ValueError('Linked paths are excluded from project tools.')
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError('Paths must stay inside the project folder.')
        return resolved

    def files(self, limit=500):
        result = []
        for folder, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in SKIP
                             and not (Path(folder) / d).is_symlink()
                             and not ((Path(folder) / d).is_junction() if hasattr(Path, 'is_junction') else False))
            for name in sorted(names):
                if name.startswith('.'):
                    continue
                relative = (Path(folder) / name).relative_to(self.root).as_posix()
                try:
                    self.path(relative)
                except ValueError:
                    continue
                result.append(relative)
                if len(result) >= limit:
                    return result
        return result

    def read(self, relative, start=1):
        path = self.path(relative)
        if not path.is_file() or path.stat().st_size > 2_000_000:
            raise ValueError('Choose a text file smaller than 2 MB, or attach the document.')
        text = decode_text(path.read_bytes())
        lines = text.splitlines()
        start = max(1, int(start))
        output = '\n'.join(f'{n}: {line}' for n, line in enumerate(lines[start-1:start+199], start))
        return {'path': relative, 'start': start, 'total_lines': len(lines), 'text': output[:14000],
                'truncated': len(output) > 14000 or start + 199 < len(lines)}

    def search(self, query):
        if not isinstance(query, str) or not query or len(query) > 200:
            raise ValueError('Search for 1–200 characters.')
        hits, files = [], self.files(2000)
        for relative in files:
            path = self.path(relative)
            if path.stat().st_size > 1_000_000:
                continue
            try:
                text = decode_text(path.read_bytes())
            except (ValueError, OSError, UnicodeError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if query.casefold() in line.casefold():
                    hits.append({'path': relative, 'line': number, 'text': line[:400]})
                    if len(hits) >= 60:
                        return {'matches': hits, 'truncated': True}
        return {'matches': hits, 'truncated': len(files) == 2000}

    def proposal(self, relative, content):
        path = self.path(relative)
        if path == self.root or path.is_dir() or not isinstance(content, str) or len(content.encode('utf-8')) > MAX_EDIT:
            raise ValueError('Edits must target a text file and stay under 120 KB.')
        before = path.read_bytes() if path.exists() and path.stat().st_size <= MAX_EDIT else None
        if path.exists() and before is None:
            raise ValueError('This file is too large for an inline edit.')
        old = decode_text(before) if before is not None else ''
        after = content.encode('utf-8')
        diff = ''.join(difflib.unified_diff(old.splitlines(keepends=True), content.splitlines(keepends=True),
                                           fromfile=relative + ' (before)', tofile=relative + ' (after)'))
        return {'path': relative, 'workspace': str(self.root), 'before_hash': fingerprint(before),
                'after_hash': fingerprint(after), 'before': base64.b64encode(before).decode() if before is not None else None,
                'after': content, 'preview': diff or '(No changes)', 'summary': f'Write {relative}'}

    def apply(self, detail, undo=False):
        if str(self.root) != detail['workspace']:
            raise ValueError('The project folder changed. Propose the edit again.')
        path = self.path(detail['path'])
        current = path.read_bytes() if path.is_file() else None
        expected = detail['after_hash'] if undo else detail['before_hash']
        if fingerprint(current) != expected:
            raise ValueError('This file changed since the proposal. Read it and propose a fresh edit.')
        raw = (base64.b64decode(detail['before']) if detail['before'] is not None else None) if undo else detail['after'].encode('utf-8')
        if raw is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.path(detail['path'])
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                os.replace(temporary, path)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
        return {'path': detail['path'], 'result': 'Restored original file' if undo else 'Saved file'}

    def extract(self, relative, emit, cancel):
        path = self.path(relative)
        if path.suffix.lower() not in SUPPORTED:
            return self.read(relative)
        _, chunks = extract_document(path, lambda text: emit('status', text), cancel)
        return {'path': relative, 'sections': [{'location': loc, 'text': text} for loc, text in chunks[:8]], 'truncated': len(chunks) > 8}

    def command(self, command, cancel, timeout=60):
        if not isinstance(command, str) or not command.strip() or len(command) > 8000:
            raise ValueError('Commands must contain 1–8,000 characters.')
        if sys.platform == 'win32':
            shell = str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
            args = [shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(command.encode('utf-16le')).decode()]
            options = {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            args, options = ['/bin/sh', '-c', command], {'start_new_session': True}
        process = subprocess.Popen(args, cwd=self.root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, **options)
        chunks, total = [], 0
        def read():
            nonlocal total
            while data := process.stdout.read(4096):
                if total < 32000:
                    chunks.append(data[:32000-total])
                total += len(data)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        deadline, stopped = time.monotonic() + timeout, False
        try:
            while process.poll() is None:
                if cancel.wait(.1) or time.monotonic() > deadline:
                    stopped = True
                    break
        finally:
            if stopped or process.poll() is None:
                if sys.platform == 'win32':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            reader.join(timeout=3)
            if not reader.is_alive():
                process.stdout.close()
        return {'exit_code': process.returncode, 'output': b''.join(chunks).decode('utf-8', errors='replace'),
                'truncated': total > 32000, 'stopped': stopped}
