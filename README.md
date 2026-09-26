# Offline Local RAG

A Windows desktop app for private local chat and questions about your files. No API key or cloud inference is used. First-time model downloads need internet, downloaded models and saved documents work offline.

## Run

Open `dist/OfflineRAG.exe`. The first launch loads **Qwen3.5 2B Q4_K_M**. A verified copy is in this project's `models` directory, which the executable can find. If you copy only the executable elsewhere, it downloads the selected model once into your user data folder. To avoid another download, copy the `models` folder next to the executable.

The previous executable is preserved as `dist/OfflineRAG.previous.exe`.

## Chats, files, and memory

- **New chat** starts a separate conversation. All messages save automatically, including partial replies. Select a saved chat to resume it after closing or replacing the executable.
- **Attach files** accepts multiple PDF, TXT, MD/Markdown, HTML/HTM, JSON, JSONL/NDJSON, CSV/TSV, YAML/YML, XML, LOG, and RST files. Extracted text is stored with the chat, so you can move or delete the original files. Use **Files** to review or remove attachments. Duplicate contents are not indexed twice in one chat.
- **Memory notes** saves up to 1,000 characters of facts or preferences for that chat. Notes are bounded to 384 model tokens; unusually token-dense notes may be excerpted. Recent complete exchanges and relevant excerpts from older exchanges are recalled automatically. Each chat has separate memory and documents.
- The context selector offers **4,096**, **8,192** (default), and **16,384** tokens. Select **Load / retry** to apply model or context changes. Prompts use the actual model tokenizer and reserve room for the reply. Long history and documents are selectively excerpted; the whole transcript remains saved. Replies allow up to 768 tokens; ask to continue for longer answers.
- Keyword retrieval works immediately. **Enable semantic search** downloads a small embedding model and adds semantic matching to the current chat's saved files. The embedding model is reused for future imports and launches. For older chats that only have keyword indexing, click the button in that chat to add embeddings. If the embedding cache cannot load, keyword search remains available.
- **Stop** interrupts generation or file import after the current processing step. **Export chat** saves a readable Markdown transcript or JSON with messages, memory notes, and attachment metadata (not the full attachment contents).
- Document excerpts are quoted reference data, separated from the user's request. HTML scripts are not executed or fetched; model role tokens in documents are neutralised. A small language model can still misunderstand adversarial text, so inspect its answers.

Scanned image-only PDFs need OCR before import. Files are limited to 25 MB / 2 million extracted characters / 2,500 sections each, and 10,000 sections per chat. Large documents are searched rather than supplied in full; broad summaries may omit material outside the selected excerpts.

## Storage

On Windows, chats, attached text, settings, logs, and downloaded caches live in:

`%LOCALAPPDATA%\OfflineRAG`

The database is `chats.sqlite3`. Closing the app and backing up this folder preserves chats and files across rebuilds. The executable location and working directory do not control where your chats are saved. An `OFFLINE_RAG_DATA_DIR` environment variable can override the data folder for testing or portable setups. Data is local and is not encrypted by the app.

## Models and hardware

| Profile | Quantised model | Download | Intended use |
| --- | --- | --- | --- |
| Balanced (default) | Qwen3.5 2B Q4_K_M | 1.28 GB | General desktop/laptop chat and document QA |
| Light | Qwen3.5 0.8B Q4_K_M | 533 MB | Lower memory use and faster, simpler answers |
| Compatible | Qwen2.5 1.5B Instruct Q4_K_M | 1.12 GB | Alternative using the original architecture, with its corrected download filename |

CPU inference requires no discrete GPU. Start with Light and a 4,096-token window on constrained hardware; 8 GB or more of system RAM is a practical starting point for Balanced, not a guarantee of speed on every device. The new default stays in the Qwen family because its 2B model offers a useful capability/size balance; Light trades answer quality for lower resource use. The tested runtime is llama-cpp-python 0.3.35.

This executable is **Windows x64 only**. It is not an Android/iOS app and will not run on phones. The small GGUF models can be used by suitable mobile runtimes, but this UI would need a separate mobile implementation and testing. Source builds on macOS/Linux also require their own dependencies and packaging; they have not been validated here.

Model downloads are pinned to verified revisions and checked with SHA-256. The original 404 was caused by requesting `Qwen2.5-1.5B-Instruct-Q4_K_M.gguf` instead of the repository's lowercase `qwen2.5-1.5b-instruct-q4_k_m.gguf`.

Sources: [Qwen3.5 2B model card](https://huggingface.co/Qwen/Qwen3.5-2B), [2B GGUF files](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/tree/f6d5376be1edb4d416d56da11e5397a961aca8ae), [0.8B GGUF files](https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/tree/6ab461498e2023f6e3c1baea90a8f0fe38ab64d0), [original model files](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/91cad51170dc346986eccefdc2dd33a9da36ead9). These model weights use Apache 2.0 licensing; retain their license notices when redistributing weights.

## Development and verification

The existing `venv` contains the dependencies. In PowerShell:

```powershell
.\venv\Scripts\python.exe app.py
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe self_test.py --output build\source-smoke.json --inference --semantic --ui
.\build.ps1
```

The smoke test uses temporary synthetic chats, exercises real CPU inference, and can download the embedding model. The frozen executable supports the same `--self-test --output <absolute-path> --inference --semantic --ui` checks. It never uses your real chat database during this test.

`requirements.txt` contains the direct pinned dependencies. `requirements-lock.txt` records the original installed environment's full pins for reference. Building llama-cpp-python without a matching wheel requires CMake and a supported C++ compiler.

Implementation: `app.py` handles the UI and worker queue; `storage.py` owns SQLite transactions; `documents.py` extracts and chunks files; `rag_engine.py` handles downloads, token budgets, memory, retrieval, and inference. PyInstaller includes CustomTkinter assets and native inference/embedding libraries. Detailed failures go to the rotating `app.log`; the UI offers **Error details** and **Load / retry**.

## Setup Instructions
```powershell
py -3.14 -m venv venv

python -m pip install --upgrade pip

python -m pip install --prefer-binary -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

python -m PyInstaller --noconfirm OfflineRAG.spec
```
