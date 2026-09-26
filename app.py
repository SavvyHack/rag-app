"""Offline desktop shell. Only the bundled interface can access the Python bridge."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from controller import ChatController
from storage import Store


def create_app(store=None, auto_load=True, hidden=False):
    import webview
    controller = ChatController(store or Store())
    window = webview.create_window(
        'Offline Local RAG', str(Path(__file__).resolve().parent / 'web' / 'index.html'),
        width=1280, height=860, min_size=(860, 620), background_color='#111418',
        text_select=True, hidden=hidden,
    )
    controller.window = window
    window.expose(controller.poll, controller.dispatch)
    window.events.closing += controller.on_closing
    if auto_load:
        window.events.loaded += controller.auto_load
    return window, controller


def main():
    import webview
    for stream in ('stdout', 'stderr'):
        if getattr(sys, stream) is None:
            setattr(sys, stream, open(os.devnull, 'w'))
    store = Store()
    handler = RotatingFileHandler(store.directory / 'app.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    create_app(store)
    webview.start(gui='edgechromium' if sys.platform == 'win32' else None, private_mode=True)


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        from self_test import run
        run()
    else:
        main()
