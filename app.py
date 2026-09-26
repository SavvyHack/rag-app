"""Desktop UI. Tk stays on the main thread; workers report through a queue."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import sys
import threading
from tkinter import filedialog, messagebox
import customtkinter as ctk
from documents import SUPPORTED
from rag_engine import Engine, MODELS
from storage import Store


class StandaloneRAGApp(ctk.CTk):
    def __init__(self, store=None, auto_load=True):
        super().__init__()
        self.title("Offline Local RAG")
        self.geometry("1180x780")
        self.minsize(940, 640)
        self.store = store or Store()
        self.engine = Engine(self.store)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = self.closing = False
        self.job = self.worker = self.assistant_id = self.stream_start = None
        self.last_error = ""
        self.chat_buttons, self.action_widgets = [], []
        self.setup_ui()
        chats = self.store.chats()
        saved = self.store.setting("active_chat")
        self.chat_id = saved if saved and self.store.chat(saved) else (chats[0]['id'] if chats else self.store.create_chat())
        self.select_chat(self.chat_id)
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.after(60, self.drain_events)
        if auto_load:
            self.after(150, self.load_model_background)

    def button(self, parent, text, command, **kwargs):
        button = ctk.CTkButton(parent, text=text, command=command, **kwargs)
        self.action_widgets.append(button)
        return button

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(self, width=220)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(sidebar, text="Saved chats", font=ctk.CTkFont(size=21, weight="bold")).grid(row=0, column=0, padx=12, pady=(15, 6))
        self.button(sidebar, "+ New chat", self.new_chat).grid(row=1, column=0, padx=12, pady=8, sticky="ew")
        self.chat_list = ctk.CTkScrollableFrame(sidebar, width=195)
        self.chat_list.grid(row=2, column=0, sticky="nsew", padx=6, pady=5)
        self.chat_list.grid_columnconfigure(0, weight=1)
        self.button(sidebar, "Rename chat", self.rename_chat).grid(row=3, column=0, padx=12, pady=4, sticky="ew")
        self.button(sidebar, "Export chat", self.export_chat).grid(row=4, column=0, padx=12, pady=4, sticky="ew")
        self.button(sidebar, "Delete chat", self.delete_chat, fg_color="#733b43", hover_color="#924b55").grid(row=5, column=0, padx=12, pady=4, sticky="ew")
        ctk.CTkLabel(sidebar, text="Chats save automatically\non this device.", text_color="#aab4c2").grid(row=6, column=0, pady=12)
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)
        settings = ctk.CTkFrame(main)
        settings.grid(row=0, column=0, sticky="ew")
        settings.grid_columnconfigure(0, weight=1)
        profile = self.store.setting("model", "balanced")
        if profile not in MODELS:
            profile = "balanced"
        self.model_choice = ctk.StringVar(value=MODELS[profile].label)
        self.model_menu = ctk.CTkOptionMenu(settings, variable=self.model_choice, values=[s.label for s in MODELS.values()], width=310)
        self.model_menu.grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        self.action_widgets.append(self.model_menu)
        context = str(self.store.setting("context", 8192))
        self.context_choice = ctk.StringVar(value=context if context in {"4096", "8192", "16384"} else "8192")
        self.context_menu = ctk.CTkOptionMenu(settings, variable=self.context_choice, values=["4096", "8192", "16384"], width=95)
        self.context_menu.grid(row=0, column=1, padx=4, pady=8)
        self.action_widgets.append(self.context_menu)
        self.button(settings, "Load / retry", self.load_model_background, width=100).grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkLabel(settings, text="Context tokens · larger windows use more memory. Models run locally on your CPU.", text_color="#aab4c2", anchor="w").grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 6), sticky="ew")
        toolbar = ctk.CTkFrame(main)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.button(toolbar, "Attach files", self.upload_files, width=120).pack(side="left", padx=6, pady=8)
        self.button(toolbar, "Files", self.manage_files, width=70).pack(side="left", padx=4)
        self.button(toolbar, "Memory notes", self.edit_memory, width=120).pack(side="left", padx=4)
        self.button(toolbar, "Enable semantic search", self.enable_semantic, width=175).pack(side="left", padx=4)
        self.stop_btn = ctk.CTkButton(toolbar, text="Stop", command=self.stop, width=65, state="disabled")
        self.stop_btn.pack(side="right", padx=6)
        self.status_label = ctk.CTkLabel(main, text="Starting…", anchor="w", justify="left", wraplength=780, text_color="#b8c7dc")
        self.status_label.grid(row=2, column=0, sticky="ew", padx=5, pady=(8, 0))
        self.status_label.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(200, event.width - 15)))
        self.chat_title = ctk.CTkLabel(main, text="", anchor="w", font=ctk.CTkFont(size=18, weight="bold"))
        self.chat_title.grid(row=3, column=0, sticky="ew", padx=5, pady=6)
        self.chat_display = ctk.CTkTextbox(main, wrap="word", font=ctk.CTkFont(size=15), state="disabled")
        self.chat_display.grid(row=4, column=0, sticky="nsew")
        bottom = ctk.CTkFrame(main, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        self.input_field = ctk.CTkEntry(bottom, placeholder_text="Ask a question, with or without attached files…", height=38)
        self.input_field.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.input_field.bind("<Return>", lambda event: self.send_message())
        self.send_btn = ctk.CTkButton(bottom, text="Send", width=90, height=38, command=self.send_message, state="disabled")
        self.send_btn.grid(row=0, column=1)
        self.detail_btn = ctk.CTkButton(main, text="Error details", command=self.show_error, width=110)
        self.detail_btn.grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.detail_btn.grid_remove()

    def set_status(self, text):
        self.status_label.configure(text=text)

    def ready_status(self):
        count = len(self.store.documents(self.chat_id))
        if self.engine.llm:
            search = "semantic + keyword search" if self.engine.embedder else "keyword search"
            self.set_status(f"Ready · {MODELS[self.engine.profile].label.split(' · ')[1]} · {self.engine.context_size:,} tokens · {count} files · {search}")
        else:
            self.set_status("Chats are available. Load a model to send messages.")

    def refresh_chats(self):
        for widget in self.chat_list.winfo_children():
            widget.destroy()
        self.chat_buttons.clear()
        for row, chat in enumerate(self.store.chats()):
            button = ctk.CTkButton(self.chat_list, text=chat['title'][:26], anchor="w", width=175,
                                  fg_color="#275b87" if chat['id'] == self.chat_id else "#33383f",
                                  command=lambda cid=chat['id']: self.select_chat(cid),
                                  state="disabled" if self.busy else "normal")
            button.grid(row=row, column=0, padx=2, pady=3, sticky="ew")
            self.chat_buttons.append(button)
        chat = self.store.chat(self.chat_id)
        self.chat_title.configure(text=chat['title'][:75] if chat else "")

    def select_chat(self, chat_id):
        if self.busy:
            return
        self.chat_id = chat_id
        self.store.set_setting("active_chat", chat_id)
        self.refresh_chats()
        self.render_chat()
        self.ready_status()

    def render_chat(self):
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        messages = self.store.messages(self.chat_id)
        if not messages:
            self.chat_display.insert("end", "Start a conversation or attach documents.\n\nSupported: PDF, text, Markdown, HTML, JSON / JSONL, CSV / TSV, YAML, XML, and logs.\n\nYour messages, attached text, and memory notes are saved automatically. Use Memory notes for details you want to keep available in long chats.\n")
        for message in messages:
            role = "You" if message['role'] == 'user' else "Assistant"
            status = message['status']
            label = "" if status == "complete" else (" · unfinished" if status == "streaming" and not self.busy else " · " + status)
            self.chat_display.insert("end", f"{role}{label}\n")
            if self.busy and message['id'] == self.assistant_id:
                self.stream_start = self.chat_display.index("end-1c")
            self.chat_display.insert("end", (message['content'] or ("Thinking…" if status == "streaming" and self.busy else "[No response saved]")) + "\n\n")
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def show_stream(self, content):
        if self.stream_start is None:
            return
        self.chat_display.configure(state="normal")
        self.chat_display.delete(self.stream_start, "end-1c")
        self.chat_display.insert("end", content + " ▌")
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def new_chat(self):
        if not self.busy:
            self.select_chat(self.store.create_chat())

    def rename_chat(self):
        title = ctk.CTkInputDialog(text="Chat name:", title="Rename chat").get_input()
        if title and title.strip():
            self.store.update_chat(self.chat_id, title=title.strip())
            self.refresh_chats()

    def delete_chat(self):
        if messagebox.askyesno("Delete chat", "Permanently delete this chat, its memory notes, and attached text?"):
            self.store.delete_chat(self.chat_id)
            chats = self.store.chats()
            self.select_chat(chats[0]['id'] if chats else self.store.create_chat())

    def export_chat(self):
        path = filedialog.asksaveasfilename(defaultextension=".md", initialfile="chat.md", filetypes=[("Markdown", "*.md"), ("JSON", "*.json")])
        if not path:
            return
        chat, messages = self.store.chat(self.chat_id), self.store.messages(self.chat_id)
        if Path(path).suffix.lower() == ".json":
            text = json.dumps({"chat": chat, "messages": messages, "documents": self.store.documents(self.chat_id)}, ensure_ascii=False, indent=2)
        else:
            text = f"# {chat['title']}\n\n"
            if chat['notes']:
                text += f"## Memory notes\n\n{chat['notes']}\n\n"
            text += "\n\n".join(f"## {m['role'].title()} ({m['status']})\n\n{m['content']}" for m in messages)
        try:
            Path(path).write_text(text, encoding="utf-8")
            self.set_status("Chat exported.")
        except OSError as error:
            messagebox.showerror("Could not export", str(error))

    def edit_memory(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Memory notes for this chat")
        dialog.geometry("580x360")
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="Save names, preferences, and project facts here. Up to 1,000 characters.\nNotes are kept with this chat and included in future questions.").pack(padx=15, pady=12)
        field = ctk.CTkTextbox(dialog, wrap="word")
        field.pack(fill="both", expand=True, padx=15, pady=5)
        field.insert("1.0", self.store.chat(self.chat_id)['notes'])
        def save():
            notes = field.get("1.0", "end-1c").strip()
            if len(notes) > 1000:
                messagebox.showwarning("Notes too long", "Keep notes under 1,000 characters.", parent=dialog)
                return
            self.store.update_chat(self.chat_id, notes=notes)
            dialog.destroy()
            self.set_status("Memory notes saved.")
        ctk.CTkButton(dialog, text="Save notes", command=save).pack(pady=12)

    def manage_files(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Attached files")
        dialog.geometry("650x420")
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="Extracted text is saved with this chat, even if the original file moves.").pack(padx=10, pady=10)
        listing = ctk.CTkScrollableFrame(dialog)
        listing.pack(fill="both", expand=True, padx=12, pady=12)
        def refresh():
            for widget in listing.winfo_children():
                widget.destroy()
            docs = self.store.documents(self.chat_id)
            if not docs:
                ctk.CTkLabel(listing, text="No files attached.").pack(pady=15)
            for document in docs:
                row = ctk.CTkFrame(listing)
                row.pack(fill="x", pady=4)
                ctk.CTkLabel(row, text=f"{document['name'][:55]}\n{document['chunk_count']} sections", anchor="w").pack(side="left", padx=8)
                def remove(doc_id=document['id']):
                    self.store.delete_document(self.chat_id, doc_id)
                    refresh()
                    self.ready_status()
                ctk.CTkButton(row, text="Remove", width=75, command=remove).pack(side="right", padx=8)
        refresh()

    def set_busy(self, busy):
        self.busy = busy
        for widget in self.action_widgets + self.chat_buttons:
            widget.configure(state="disabled" if busy else "normal")
        self.send_btn.configure(state="normal" if not busy and self.engine.llm else "disabled")
        self.input_field.configure(state="disabled" if busy else "normal")
        self.stop_btn.configure(state="normal" if busy and self.job in {"answer", "import", "semantic"} else "disabled")

    def start_job(self, kind, function):
        if self.busy:
            return False
        self.job = kind
        self.cancel.clear()
        self.last_error = ""
        self.detail_btn.grid_remove()
        self.set_busy(True)
        def work():
            try:
                self.events.put(("done", (kind, function())))
            except Exception as error:
                logging.exception("%s failed", kind)
                self.events.put(("error", (kind, str(error))))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        return True

    def emit(self, kind, value):
        self.events.put((kind, value))

    def load_model_background(self):
        profile = next(key for key, spec in MODELS.items() if spec.label == self.model_choice.get())
        context = int(self.context_choice.get())
        self.start_job("load", lambda: self.engine.load(profile, context, self.emit))

    def upload_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Supported documents", " ".join('*' + suffix for suffix in SUPPORTED)), ("All files", "*.*")])
        if paths:
            chat_id = self.chat_id
            self.start_job("import", lambda: self.engine.import_files(chat_id, paths, self.emit, self.cancel))

    def enable_semantic(self):
        chat_id = self.chat_id
        self.start_job("semantic", lambda: self.engine.reindex(chat_id, self.emit, self.cancel))

    def send_message(self):
        if self.busy or not self.engine.llm:
            return
        query = self.input_field.get().strip()
        if not query:
            return
        self.assistant_id = self.store.begin_turn(self.chat_id, query)
        chat_id, assistant_id = self.chat_id, self.assistant_id
        self.input_field.delete(0, "end")
        self.start_job("answer", lambda: self.engine.answer(chat_id, query, assistant_id, self.emit, self.cancel))
        self.refresh_chats()
        self.render_chat()

    def stop(self):
        self.cancel.set()
        self.stop_btn.configure(state="disabled")
        self.set_status("Stopping after the current processing step…")

    def show_error(self):
        messagebox.showerror("Error details", self.last_error + f"\n\nLog: {self.store.directory / 'app.log'}")

    def drain_events(self):
        for _ in range(100):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                if not self.closing:
                    self.set_status(value)
            elif kind == "stream":
                self.show_stream(value)
            elif kind in {"done", "error"}:
                job, result = value
                self.set_busy(False)
                self.job = None
                self.stream_start = None
                self.refresh_chats()
                self.render_chat()
                self.ready_status()
                if kind == "error":
                    self.last_error = result
                    self.set_status(f"Could not finish: {result.splitlines()[0][:160]}")
                    self.detail_btn.grid()
                elif job == "load":
                    self.store.set_setting("model", result['profile'])
                    self.store.set_setting("context", result['context_size'])
                elif job == "import":
                    self.set_status(f"Import {'stopped' if result['cancelled'] else 'finished'} · {len(result['successes'])} files · {len(result['errors'])} errors")
                    if result['errors'] and not self.closing:
                        messagebox.showwarning("File import results", "\n".join(result['successes'] + result['errors']))
                elif job == "answer" and result['status'] == 'stopped':
                    self.set_status("Stopped. Partial response saved.")
                if self.closing:
                    self.destroy()
                    return
        self.after(60, self.drain_events)

    def close_app(self):
        if self.busy and self.job in {"answer", "import", "semantic"}:
            self.closing = True
            self.stop()
            self.set_status("Finishing the current step and saving before closing…")
        else:
            self.destroy()

    def report_callback_exception(self, exc_type, value, traceback):
        logging.error("UI callback failed", exc_info=(exc_type, value, traceback))
        messagebox.showerror("Could not complete action", str(value))


def main():
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    store = Store()
    handler = RotatingFileHandler(store.directory / "app.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    StandaloneRAGApp(store).mainloop()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from self_test import run
        run()
    else:
        main()
