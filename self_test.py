"""Opt-in smoke test for source and frozen executables; never uses real chat data."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--output', required=True)
    parser.add_argument('--inference', action='store_true')
    parser.add_argument('--semantic', action='store_true')
    parser.add_argument('--ui', action='store_true')
    args = parser.parse_args()
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    report = {'passed': False, 'checks': [], 'frozen': bool(getattr(sys, 'frozen', False))}
    started = time.monotonic()
    try:
        from storage import Store
        from rag_engine import Engine, PromptBuilder
        from documents import extract_document
        with tempfile.TemporaryDirectory(prefix='offline-rag-test-') as directory:
            root = Path(directory)
            store = Store(root / 'data')
            chat = store.create_chat()
            fixture = root / 'project.md'
            fixture.write_text('# Aurora\nThe project launch code is ORCHID-728. The project budget is 420 dollars.', encoding='utf-8')
            digest, chunks = extract_document(fixture)
            store.add_document(chat, fixture.name, digest, chunks)
            store.add_message(chat, 'user', 'My name is Taylor.')
            store.add_message(chat, 'assistant', 'Hello Taylor.')
            store.update_chat(chat, notes='The user prefers short answers.')
            store.set_setting('active_chat', chat)
            store = Store(root / 'data')
            assert store.messages(chat)[0]['content'] == 'My name is Taylor.'
            assert len(store.chunks(chat)) == 1
            report['checks'].append('saved chat, notes, and documents reopen')
            engine = Engine(store)
            assert 'ORCHID-728' in engine.retrieve(chat, 'launch code', [])[0]['content']
            report['checks'].append('saved document retrieval')
            if args.semantic:
                engine.reindex(chat, lambda *_: None, threading.Event())
                assert store.chunks(chat)[0]['embedding']
                report['checks'].append('semantic model and persisted embeddings')
            if args.inference:
                engine.load('balanced', 8192, lambda *_: None)
                query = 'What is my name and the project launch code? Answer in one sentence.'
                store.add_message(chat, 'user', query)
                answer_id = store.add_message(chat, 'assistant', '', 'streaming')
                engine.answer(chat, query, answer_id, lambda *_: None, threading.Event())
                response = store.messages(chat)[-1]['content']
                report['response'] = response
                assert 'Taylor' in response, response
                assert 'ORCHID-728' in response, response
                assert '<think>' not in response, response
                assert store.messages(chat)[-1]['status'] == 'complete'
                builder = PromptBuilder(engine.llm, 8192)
                history = store.messages(chat) * 60
                _, _, tokens = builder.build('What is my name?', history, 'Use short answers.', engine.retrieve(chat, 'code', []), True)
                assert tokens + builder.reply_tokens + 64 <= 8192
                report['checks'].append('real CPU inference, history recall, document answer, token budget')
                engine.llm.close()
                engine.llm = None
            if args.ui:
                from app import StandaloneRAGApp
                app = StandaloneRAGApp(store, auto_load=False)
                app.withdraw()
                app.update_idletasks()
                assert 'Taylor' in app.chat_display.get('1.0', 'end')
                other = app.store.create_chat()
                app.select_chat(other)
                assert 'Taylor' not in app.chat_display.get('1.0', 'end')
                app.select_chat(chat)
                assert 'Taylor' in app.chat_display.get('1.0', 'end')
                app.assistant_id = app.store.add_message(chat, 'assistant', '', 'streaming')
                app.busy = True
                app.render_chat()
                app.show_stream('First line\nSecond line')
                app.show_stream('First line\nSecond line\nThird line')
                displayed = app.chat_display.get('1.0', 'end')
                assert displayed.count('First line') == 1
                assert 'Third line' in displayed
                app.busy = False
                app.destroy()
                report['checks'].append('desktop widgets, saved-chat switching, multiline streaming')
            if engine.embedder:
                # Release ONNX file handles before TemporaryDirectory cleanup on Windows.
                engine.embedder = None
                import gc
                gc.collect()
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    report['elapsed_seconds'] = round(time.monotonic() - started, 2)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    run()
