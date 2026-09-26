# Validation — 26 September 2026

- 18 regression tests passed in the existing Python 3.14.5 environment.
- Source smoke test passed: SQLite reopen, saved document retrieval, real embedding creation, real CPU inference, conversation recall, token-budget enforcement, desktop widgets, chat switching, and multiline streaming.
- Rebuilt `dist/OfflineRAG.exe` passed the same smoke test with `frozen: true` and exit code 0. Report: `build/exe-smoke.json`.
- The real model answered a synthetic question using both the saved name “Taylor” and the attached document's exact launch code “ORCHID-728”. No real user documents were used for these checks.
- The Light profile successfully exercised the application's public-model download, progress reporting, SHA-256 verification, 4,096-token load, and CPU inference. Both Balanced and Light GGUF files are available in `models/`.
- The actual rebuilt desktop window was opened and visually inspected. It reached Ready with Qwen3.5 2B and an 8,192-token context, with the saved-chat sidebar and controls visible.
- The prior executable remains in `dist/OfflineRAG.previous.exe`.

Validation was performed on this Windows x64 computer. No phone, macOS, Linux, GPU, or broad hardware benchmark testing was performed. The Compatible Qwen2.5 download's exact filename, size, checksum, and pinned revision were verified against its public repository; inference testing used the two newer Qwen3.5 profiles.
