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
    parser.add_argument('--ocr', action='store_true')
    parser.add_argument('--agent', action='store_true')
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
            if args.ocr:
                from PIL import Image, ImageDraw, ImageFont
                scan = Image.new('RGB', (1600, 800), 'white')
                ImageDraw.Draw(scan).text((100, 150), 'Invoice total 238.50\nReference ORCHID 728',
                    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 56), fill='black', spacing=30)
                scan_path = root / 'scan.pdf'
                scan.save(scan_path)
                _, scanned_chunks = extract_document(scan_path)
                assert '238.50' in scanned_chunks[0][1], scanned_chunks
                assert 'OCR' in scanned_chunks[0][0]
                report['checks'].append('native offline scanned PDF OCR, numeric text and page citations')
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
            if args.agent:
                from agent import LocalAgent
                if not engine.llm:
                    engine.load('balanced', 8192, lambda *_: None)
                agent_chat = store.create_chat()
                project = root / 'project'
                project.mkdir()
                store.set_workspace(agent_chat, project)
                store.set_mode(agent_chat, 'agent')
                request = 'Create greeting.md containing exactly Hello ORCHID-728. Use write_file to create it, read_file to verify, then finish. No commands are needed.'
                assistant = store.begin_turn(agent_chat, request)
                def review(kind, value):
                    if kind == 'status' and 'Review the proposed' in value:
                        event = store.activity(agent_chat)['events'][0]
                        # Only authorize this synthetic fixture, never arbitrary model commands.
                        detail = store.event(event['id'], agent_chat)['detail']
                        allowed = event['name'] == 'write_file' and detail.get('path') == 'greeting.md'
                        store.update_event(event['id'], 'approved' if allowed else 'rejected')
                result = LocalAgent(store, engine).answer(agent_chat, request, assistant, review, threading.Event())
                report['agent_status'] = result['status']
                report['agent_activity'] = store.activity(agent_chat)
                assert result['status'] == 'complete', result
                assert 'Hello ORCHID-728' in (project / 'greeting.md').read_text(), store.activity(agent_chat)
                report['checks'].append('real local model proposes reviewed file edit, verifies file and finishes')
            if args.inference or args.agent:
                builder = PromptBuilder(engine.llm, 8192)
                history = store.messages(chat) * 60
                _, _, tokens = builder.build('What is my name?', history, 'Use short answers.', engine.retrieve(chat, 'code', []), True)
                assert tokens + builder.reply_tokens + 64 <= 8192
                report['checks'].append('real CPU inference, history recall, document answer, token budget')
                engine.llm.close()
                engine.llm = None
            if args.ui:
                check_desktop_ui(store, chat, report)
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


def check_desktop_ui(store, chat, report):
    """Exercise the actual WebView2 window and JS/Python bridge with synthetic data."""
    import webview
    from app import create_app
    store.add_message(chat, 'assistant', '**Invoice** $40.50\n\n' + r'\[\frac{1}{2}\]')
    window, controller = create_app(store, auto_load=False, hidden=True)
    failures = []

    def check():
        def wait_for(expression, timeout=20):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if window.evaluate_js(expression):
                    return
                time.sleep(.15)
            raise AssertionError('Desktop UI timed out: ' + expression)
        try:
            wait_for("Boolean(window.LocalRAG && document.querySelector('.assistant .katex'))")
            assert window.evaluate_js("document.querySelector('.assistant:last-child strong').textContent") == 'Invoice'
            assert window.evaluate_js("document.getElementById('messages').textContent.includes('Taylor')")
            # Trigger bridge calls from the real DOM, then check persisted results.
            window.evaluate_js("document.getElementById('new-folder').click(); document.getElementById('name-field').value='Smoke folder'; document.getElementById('dialog-form').requestSubmit(); true")
            wait_for("document.getElementById('folders').textContent.includes('Smoke folder') && !document.getElementById('dialog').open")
            assert store.folders()[0]['name'] == 'Smoke folder'
            window.evaluate_js("document.getElementById('new-chat').click(); true")
            wait_for("Boolean(document.querySelector('.welcome'))")
            assert store.chat(controller.chat_id)['folder_id'] == store.folders()[0]['id']
            controller.dispatch('select_folder', {'id':'all'})
            controller.dispatch('select_chat', {'id':chat})
            wait_for("document.getElementById('messages').textContent.includes('Taylor')")
            with controller.lock:
                controller.assistant_id = store.add_message(chat, 'assistant', '', 'streaming')
                controller.busy, controller.job = True, 'answer'
                controller._emit('stream', '**First line**\nSecond line')
            wait_for("document.getElementById('messages').textContent.includes('Second line')")
            controller._emit('stream', '**First line**\nSecond line\nThird line')
            wait_for("document.getElementById('messages').textContent.includes('Third line')")
            assert window.evaluate_js("document.getElementById('messages').textContent.split('First line').length - 1") == 1
            report['checks'].append('native WebView2, offline Markdown/LaTeX, folder bridge, chat switching, multiline streaming')
        except Exception:
            failures.append(traceback.format_exc())
        finally:
            controller.busy = False
            window.destroy()

    webview.start(check, gui='edgechromium' if sys.platform == 'win32' else None, private_mode=True)
    if failures:
        raise AssertionError(failures[0])


if __name__ == '__main__':
    run()
