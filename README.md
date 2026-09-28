# Offline Local RAG

A Windows desktop app for private local chat, document research, and reviewed work on project files. No API key or cloud inference is used. OCR, document extraction, project tools, and installed models run on the device.

## Run

Open `dist/OfflineRAG.exe`. The first launch loads **Qwen3.5 2B Q4_K_M**. A verified copy is in this project's `models` directory, which the executable can find. **Use cached models only** is enabled by default. If a model is missing, allow downloads in Model settings while online and load it once; then re-enable cached-only operation. For another computer, copy the `models` folder beside the executable before going offline.

The previous executable is preserved as `dist/OfflineRAG.previous.exe`, and the version immediately before the frontend update is in `dist/OfflineRAG.before-frontend.exe`.

The interface uses Microsoft Edge WebView2, which is already installed on this computer. Other Windows computers need the [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/). Markdown, equation rendering, code highlighting, and their fonts are bundled in the executable and work offline; no browser tab or CDN is required.

## Chats, files, and memory

- **New chat** starts a separate conversation. All messages save automatically, including partial replies. Select a saved chat to resume it after closing or replacing the executable.
- **Folders** is a separate sidebar section. Use **+** to create a folder, its **…** button to rename or delete it, and **Move** above a conversation to organise an existing chat. A new chat is created in the selected folder. **All chats** and **Unfiled** provide quick views; search filters chat titles within the selected section. Deleting a folder moves its chats to Unfiled without deleting messages, notes, or attachments. Folder membership and the selected section persist across restarts. Existing chats start in Unfiled.
- Responses render Markdown headings, bold/italic text, lists, task lists, quotes, links, tables, and highlighted code. LaTeX supports `$…$`, `$$…$$`, `\(…\)`, `\[…\]`, supported `\begin{…}` environments, and fenced `math`, `latex`, or `tex` blocks. Ordinary dollar amounts stay as currency. KaTeX supports mathematical LaTeX, not complete TeX documents or arbitrary packages; unsupported commands remain readable. Raw HTML is displayed as text, and remote images are not fetched automatically.
- **Copy** preserves the original message; **Copy code** copies just the code. Formatting updates during streaming and when old chats reopen. The conversation follows new output only while you are at the bottom; **Latest response** takes you back. The composer supports **Enter** to send and **Shift+Enter** for a new line. Unsent drafts remain available while switching chats during the current session.
- **Attach files** accepts multiple PDF, TXT, MD/Markdown, HTML/HTM, JSON, JSONL/NDJSON, CSV/TSV, YAML/YML, XML, LOG, and RST files. Extracted text is stored with the chat, so you can move or delete the original files. Use **Files** to review or remove attachments. Duplicate contents are not indexed twice in one chat.
- **Memory notes** saves up to 1,000 characters of facts or preferences for that chat. Notes are bounded to 384 model tokens; unusually token-dense notes may be excerpted. Recent complete exchanges and relevant excerpts from older exchanges are recalled automatically. Each chat has separate memory and documents.
- The context selector offers **4,096**, **8,192** (default), and **16,384** tokens. Select **Load / retry** to apply model or context changes. Prompts use the actual model tokenizer and reserve room for the reply. Long history and documents are selectively excerpted; the whole transcript remains saved. Replies allow up to 768 tokens; ask to continue for longer answers.
- Keyword retrieval works immediately. **Enable semantic search** downloads a small embedding model and adds semantic matching to the current chat's saved files. The embedding model is reused for future imports and launches. For older chats that only have keyword indexing, click the button in that chat to add embeddings. If the embedding cache cannot load, keyword search remains available.
- **Stop** interrupts generation or file import after the current processing step. **Export chat** saves a readable Markdown transcript or JSON with messages, memory notes, and attachment metadata (not the full attachment contents).
- Document excerpts are quoted reference data, separated from the user's request. HTML scripts are not executed or fetched; model role tokens in documents are neutralised. A small language model can still misunderstand adversarial text, so inspect its answers.

Scanned PDFs are read automatically with Windows' on-device OCR. Sparse pages and pages containing images also receive OCR, including mixed text/scan PDFs. Progress shows the current page; Stop cancels the OCR worker. Text and page references are saved together only after extraction succeeds. Reattach PDFs rejected by an older version: those failed imports did not save their contents.

PNG, JPEG, BMP, TIFF, Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), and common source-code files are also accepted. OCR extracts text, not general visual reasoning about diagrams or photos. OCR quality depends on scan clarity and installed Windows recognition languages. Office files are read without running macros or external links. Excel values are saved/cached values; formulas are not recalculated. TIFF import currently reads the first frame only. Office images are not OCRed unless attached separately.

Files are limited to 25 MB / 2 million extracted characters / 2,500 sections each, and 10,000 sections per chat. PDFs are limited to 500 pages, Office archives to 50 MB expanded. Large documents are searched rather than supplied in full; broad summaries may omit material outside the selected excerpts.

## Offline workspace

- **Chat** answers questions and reads attached files. It cannot execute tools.
- **Plan** inspects a selected project, searches and reads files, extracts documents, and records a plan. It cannot write files or run commands.
- **Agent** runs a local model tool loop (up to 16 steps per request). It can inspect files, search text, read documents with OCR, create plans, propose text/code/Markdown/CSV/HTML files, and propose PowerShell commands. After reviewing results, ask it to continue for longer tasks.
- **Workspace → Choose folder** selects a project through the native folder picker. Switching into Plan or Agent without choosing a project creates an empty workspace in the app data folder. **Project files** previews text files; **Open folder** opens the folder in Explorer.
- **Review action** shows the exact file diff or command. **Apply change / Run command** approves one action; **Reject** declines it. Closing the review leaves it pending. Stop cancels pending work. File edits refuse to overwrite a file changed after the proposal, and **Undo edit** restores the exact original bytes when the file is still unchanged since that edit.
- **Activity** retains plans, tool results, command output, and review decisions in the chat database. Commands have a 60-second limit and bounded output. The file list shows up to 300 entries (the model can list 500); file reads are paginated and searches are bounded. Private/generated folders are excluded from file tools.
- **Workflows** provides editable starting prompts for document research, project review, implementing changes, spreadsheets as CSV, and documents as Markdown. **Duplicate chat** copies a conversation, notes, and attached text into a new chat. A duplicated project chat uses the same project folder.

File tools check that paths stay inside the chosen project. **Approved commands are not an operating-system sandbox**: they run with your Windows account and can reach other files or the network. Cached-only model settings control model/embedding downloads, not arbitrary commands or links you open. Only approve commands you trust. Tool outputs and documents are treated as reference data, not user instructions.

The small bundled models have limited coding and planning ability; inspect their proposed work. This is a local assistant workspace, not complete Codex feature parity. It does not include Codex's proprietary models, hosted agents, cloud connectors, live web search, voice, browser/computer automation, image generation, MCP/plugin execution, scheduled background tasks, multiple agents, or Git worktree management. Those require separate implementations and, for online services, connectivity. The supported local workflow is based on the public [Codex feature overview](https://learn.chatgpt.com/docs/features); Windows OCR uses [Microsoft's local OcrEngine](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine).

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

The local `venv` contains Python dependencies. Frontend development uses Node.js 22.12 or newer; end users only need the executable and WebView2. In PowerShell:

```powershell
npm ci
npm run build
npm test
.\venv\Scripts\python.exe app.py
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe self_test.py --output build\source-smoke.json --inference --semantic --ui
.\build.ps1
```

The smoke test uses temporary synthetic chats, exercises real CPU inference, and can download the embedding model. The frozen executable supports the same `--self-test --output <absolute-path> --inference --semantic --ui` checks. It never uses your real chat database during this test.

`requirements.txt` contains the direct pinned dependencies. `requirements-lock.txt` records the validated Python environment's full pins. `package-lock.json` pins frontend and browser-test dependencies. `npm run build` produces the checked-in `web/assets` bundle and fonts; rebuild it after editing `frontend/`. The browser tests use installed Microsoft Edge and synthetic chats. Building llama-cpp-python without a matching wheel requires CMake and a supported C++ compiler.

Implementation: `app.py` hosts the bundled interface in a native WebView2 window; `controller.py` serialises desktop actions and manages workers; `frontend/` implements the layout and safe rendering; `storage.py` owns SQLite transactions and additive migrations. `documents.py`, `ocr.py`, and the bundled `scripts/windows-ocr.ps1` handle native extraction. `rag_engine.py` handles retrieval and inference; `agent.py` implements schema-constrained tool requests and review pauses; `workspace.py` implements file tools, checked edits, Undo, and reviewed commands. PyInstaller includes the OCR helper, web assets, math fonts, WebView2 integration, and native inference/embedding libraries. Detailed failures go to the rotating `app.log`. The extended smoke-test options `--ocr --agent` exercise real scanned-PDF extraction and a real local-model edit using synthetic files only.

## Setup Instructions
```powershell
py -3.14 -m venv venv

.\venv\Scripts\python.exe -m pip install --upgrade pip

.\venv\Scripts\python.exe -m pip install --prefer-binary -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

npm ci
npm run build
.\build.ps1
```
