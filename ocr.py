"""On-device Windows OCR. No network, model download, or user-side conversion."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


class ImportCancelled(Exception):
    pass


def recognize(path, pages=None, progress=None, cancel=None):
    if sys.platform != 'win32':
        raise RuntimeError('Automatic OCR currently requires Windows 10 or 11.')
    if cancel and cancel.is_set():
        raise ImportCancelled()
    pages = list(pages or [1])
    helper = Path(__file__).resolve().parent / 'scripts' / 'windows-ocr.ps1'
    shell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = [str(shell), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
               '-File', str(helper), '-InputPath', str(Path(path).resolve()), '-Pages', ','.join(map(str, pages))]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    lines = queue.Queue()
    def read():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    result, diagnostics = {}, []
    deadline = time.monotonic() + 90
    try:
        if progress:
            progress(f'Reading scanned page {pages[0]} with on-device OCR…')
        while True:
            if cancel and cancel.is_set():
                raise ImportCancelled()
            if time.monotonic() > deadline:
                raise RuntimeError('OCR timed out on a page. Try a smaller or clearer scan.')
            try:
                line = lines.get(timeout=.1)
            except queue.Empty:
                continue
            if line is None:
                break
            try:
                item = json.loads(line)
            except (ValueError, TypeError):
                diagnostics.append(line.strip())
                continue
            if 'error' in item:
                raise RuntimeError('On-device OCR: ' + item['error'])
            number = int(item['page'])
            result[number] = item.get('text') or ''
            deadline = time.monotonic() + 90
            if progress:
                progress(f'OCR complete for page {number} · {len(result)}/{len(pages)} scanned pages')
        process.wait(timeout=5)
        if process.returncode or set(result) != set(pages):
            raise RuntimeError('On-device OCR could not finish. ' + ' '.join(diagnostics)[-1200:])
        return result
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=5)
        process.stdout.close()
