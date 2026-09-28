# Validation — 28 September 2026

## Native OCR and offline workspace

- 39 Python regression checks passed across the core and workspace suites. Coverage includes real Windows OCR for a scanned PDF and PNG; a mixed native-text/scanned PDF with preserved page numbers; cancellation without partial imports; Word, Excel, and PowerPoint extraction; cached spreadsheet formula labels; project path boundaries; reviewed edits, exact-byte Undo, and stale-file rejection; rejected/cancelled actions; command output and timeout; Plan mode restrictions; chat duplication; cached-only model loading; and tool-output role injection/token budgeting.
- 12 Microsoft Edge UI tests passed. New coverage exercises mode changes and workflows, automatic workspace opening for review, escaped edit previews, approval/rejection controls, Stop visibility, Undo, and automatic OCR guidance. Workspace and review screenshots were visually inspected at `build/ui-workspace.png` and `build/ui-review.png`; earlier narrow-layout checks still pass.
- `build/source-workspace-smoke.json`: passed with real Qwen3.5 2B CPU inference, scanned PDF OCR, native WebView2, and a complete local-model task. The model proposed `greeting.md`, received approval restricted to that synthetic file, saved it, read it back, and finished.
- `build/exe-workspace-smoke.json`: the same checks passed in the packaged executable with `frozen: true` and exit code 0 (54.28 seconds). The OCR helper was successfully found and executed from the packaged app. No cloud inference or real user documents were used.
- Built `dist/OfflineRAG.exe` (67,329,608 bytes). Existing database migration is additive; tests use isolated temporary databases. Source files pass the whitespace check; the generated third-party highlighting bundle contains intentional whitespace in grammar strings.
- Scope: Windows 10/11 native OCR with an installed recognition language. Office imports read text and cached values, not embedded media or recalculated formulas. TIFF reads the first frame. Commands require individual review and are not OS-sandboxed. No unattended task resumption or complete Codex feature parity is claimed; see README for supported features and remaining capabilities.

## Prior validation — 26 September 2026

## Frontend update

- 24 Python regression tests passed, including the original backend suite, an existing-database migration, folder lifecycle and persistence, chat moves, export fidelity, and saving partial output on shutdown.
- 8 Microsoft Edge browser tests passed: invoice bold text and currency, lists, tables, sources, LaTeX delimiters/environments, code highlighting, entities, task lists, safe model output, folders, drafts, streaming, scroll position, and layout at 860 × 620. Rendering requested no remote resources.
- Source native WebView2 smoke passed. Report: `build/source-frontend-smoke.json`.
- Rebuilt `dist/OfflineRAG.exe` passed the frozen smoke test with exit code 0: saved data reopening, document retrieval, real CPU inference, history recall, token budgeting, native WebView2, offline Markdown/LaTeX, folder creation through the actual JS/Python bridge, chat switching, and multiline streaming. Report: `build/exe-frontend-smoke.json`.
- The packaged model answered the synthetic question with both “Taylor” and “ORCHID-728”. The tests used temporary synthetic data; the real chat database was not used.
- Browser screenshots were inspected at standard and minimum sizes: `build/ui-invoice.png`, `build/ui-math.png`, and `build/ui-narrow.png`. Tables and long code scroll horizontally inside the response.
- The prior working app was copied to `dist/OfflineRAG.before-frontend.exe`; the older `dist/OfflineRAG.previous.exe` is also retained.
- The rich-text interface requires WebView2 (installed on this computer). Its renderer libraries and equation fonts are bundled locally. Mathematical LaTeX is supported through KaTeX; full TeX documents, executable HTML, and remote images are not rendered as active content.

## Earlier backend validation

- 18 regression tests passed in the existing Python 3.14.5 environment.
- Source smoke test passed: SQLite reopen, saved document retrieval, real embedding creation, real CPU inference, conversation recall, token-budget enforcement, desktop widgets, chat switching, and multiline streaming.
- Rebuilt `dist/OfflineRAG.exe` passed the same smoke test with `frozen: true` and exit code 0. Report: `build/exe-smoke.json`.
- The real model answered a synthetic question using both the saved name “Taylor” and the attached document's exact launch code “ORCHID-728”. No real user documents were used for these checks.
- The Light profile successfully exercised the application's public-model download, progress reporting, SHA-256 verification, 4,096-token load, and CPU inference. Both Balanced and Light GGUF files are available in `models/`.
- The actual rebuilt desktop window was opened and visually inspected. It reached Ready with Qwen3.5 2B and an 8,192-token context, with the saved-chat sidebar and controls visible.
- The prior executable remains in `dist/OfflineRAG.previous.exe`.

Validation was performed on this Windows x64 computer. No phone, macOS, Linux, GPU, or broad hardware benchmark testing was performed. The Compatible Qwen2.5 download's exact filename, size, checksum, and pinned revision were verified against its public repository; inference testing used the two newer Qwen3.5 profiles.
