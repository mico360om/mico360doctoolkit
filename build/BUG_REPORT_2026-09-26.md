# MICO360 Doc Toolkit — Full Project Bug Report

**Date:** 2026-09-26  **Build audited:** working tree on `main` = published **v7.3.1** + 5 uncommitted features (OCR "Use AI", multi-file right-click, folder menu, "Open with MICO360 Toolkit", per-tool menu icons).
**Method:** full automated suite + four parallel deep reviews (core processing · UI & workflows · OS integration/update/packaging · AI/OCR/security/docs) + cross-cutting checks. **Every Critical and High finding was verified against the code; several were reproduced independently.** Read-only — no code was changed.

**Verification legend:** **[R]** reproduced (by me or a reviewer, with a script) · **[C]** confirmed by reading the code · **[S]** suspected — reasoned from code, not reproduced.

---

## 1. Summary

| Severity | Count | Headline |
|---|---|---|
| **Critical** | **1** | Office → PDF deletes an existing same-named PDF even with *Overwrite* off |
| **High** | **13** | double batch via Ctrl+Enter · stale Overwrite setting · organizer plan applied to every file · single-instance race · failed builds can ship · sideways photos · unreadable Arabic OCR · OCR-AI privacy text wrong · API-key leak · … |
| Medium | 37 | workflows, processing correctness, metadata/privacy, updater, packaging, test hygiene |
| Low | ~30 | UX polish, accessibility, docs accuracy, edge cases |

**Automated suite:** 68 files · **1,358 checks · 0 failures.** The suite is green, yet it misses most of the bugs below — they sit in paths it never exercises (real LibreOffice, rotated pages, EXIF photos, non-Latin OCR, concurrent launches, build-script failures).

> **Release gate:** do **not** ship the pending v7.4.0 until H-11, H-13, M-20 and M-21 (all in the uncommitted OCR-AI feature) and H-5 (the multi-file cold-start race) are fixed.

### Corrections to earlier statements in this session
1. **Single-instance guard.** I said it was atomic on Windows. **It isn't.** I launched 8 processes at once and got 8, 8 and 5 "primary" instances (H-5). Multi-file right-click works when the app is *already running*, but a *cold-start* multi-select can open several windows.
2. **OCR "Use AI".** I didn't update the Privacy/Terms/Help text to match the feature (H-11), and the cleanup step has no guard against changing meaning (H-13).
3. **Visual organizer.** My tests only covered a file with a *different* page count; same-length files silently get the plan (H-3).

---

## 2. Critical

### C-1 · Office → PDF (LibreOffice) destroys an existing PDF with the same name — [R][C]
- **Where:** `mico360/core/processors.py` → `_run_libreoffice` (~L1508-1529).
- **What:** LibreOffice runs with `--outdir <output folder>`, so it always writes `<stem>.pdf` there. If `report.pdf` already exists, it is **silently overwritten**. The code then renames that file to the reserved non-colliding name (`report (1).pdf`), so the original `report.pdf` is gone.
- **Scenario:** `report.docx` sits next to an older `report.pdf`, with Overwrite **off**. Afterwards the folder holds `report (1).pdf` + `report.docx`, and the user's original PDF has been destroyed. Within one batch, `report.docx` + `report.rtf` has the same effect: the first output is destroyed and only `report (1).pdf` (the RTF) remains.
- **Fix:** run LibreOffice with `--outdir` set to a fresh temp directory, then `os.replace` the result onto the reserved `final` path.

---

## 3. High

**H-1 · Ctrl+Enter during a run starts a second, concurrent batch — [R][C]**
`tool_page.py` `start()` has no "already running" guard, and the `Ctrl+Return`/`Ctrl+Enter` shortcuts (`main_window.py:356-357`) call it directly; a disabled Start button doesn't stop them. Rows still marked *running* count as "to do", so every file is processed **twice**. When the first controller finishes, the UI goes idle while the second is still running and can't be cancelled.
**Fix:** `if self.controller is not None: return` at the top of `start()`.

**H-2 · Output folder / Overwrite / Same-as-source go stale per page and are written back on Start — [R][C]**
They are read from settings once, when the page is built (`tool_page.py:338, 353, 362`), and written back to settings on every Start (`:1084-1085`).
- A user who switches Overwrite **off** in Settings, then runs a tool page opened earlier, **overwrites files anyway**, and their setting is flipped back to on everywhere.
- A new default output folder is ignored by pages that are already open.

**Fix:** re-sync these controls from settings when the page is shown; don't write back values the user didn't change on that page.

**H-3 · A Visual Organizer arrangement is applied to every queued file — [R][C]** *(v7.3.0 feature)*
`_PagePlanField.value()` returns the plan regardless of the queue, and `_organize_visual` checks only `n_src == page count`. With five 3-page forms queued, arranging one reorders, rotates and splits **all five**. The plan (and its "— A.pdf" summary) also survives removing that file. The hint and the Help both say it "applies to the selected file."
**Fix:** store the target path in the plan; apply it only to that file (skip or fail others); clear it when the file leaves the queue.

**H-4 · Organizer dialog keeps rendering and keeps the PDF open after Apply/Cancel — [R][C]** *(v7.3.0 feature)*
Cleanup lives only in `closeEvent` (`page_organizer.py:229`), which `accept()`/`reject()` never trigger. The render timer keeps running on the UI thread, and the fitz document stays open, so **the source file is locked on Windows**: rename, delete and Recycle all fail with WinError 32. Each open also leaks a dialog holding up to 400 thumbnails.
**Fix:** override `done()` to stop the timer and close the document; `deleteLater()` the dialog after `exec()`.

**H-5 · Single-instance claim isn't atomic → cold-start multi-select opens several windows — [R]**
In `single_instance.py` `_claim`, the code probes, then calls `removeServer`, then `listen`. On Windows `QLocalServer.listen()` **succeeds even while another instance is listening**. Explorer starts one process per selected file (`%1`), so 6 PDFs → *Merge* with the app closed yields several windows, each holding a subset of the files.
Reproduced: 8 synchronized launches → **8 / 8 / 5 primaries** over 3 trials. (The coalescing added this session only helps once requests reach a single instance.)
**Fix:** claim an OS-exclusive lock first (named mutex `CreateMutexW` / `QLockFile`); secondaries retry connecting while the primary starts.

**H-6 · `build.ps1` ignores native exit codes → a failed build can be published — [R][C]**
`$ErrorActionPreference="Stop"` doesn't apply to native commands in PowerShell 5.1, and there are **no `$LASTEXITCODE` checks** after the smoke test, PyInstaller or `iscc` (`build.ps1:51, 55, 60`). If PyInstaller fails:
- the previous `dist\` build is repackaged as the new version and `release.ps1` publishes it;
- users get the old `__version__`, and the updater offers the same "new" version forever.

**Fix:** `if ($LASTEXITCODE -ne 0) { throw }` after each native call; wipe `dist\MICO360DocToolkit` before PyInstaller runs.

**H-7 · Explorer menu accumulates stale/duplicate entries — [R][C]**
`write_cascade` never clears the old `...\MICO360Toolkit\shell` subtree, and child keys are `{index}{tool_id}`. Any release that adds, removes or reorders a tool leaves old keys beside new ones. In a sandbox, removing one tool and re-registering produced **15 keys for 8 tools**, and a removed tool still launches `--tool <gone>`. `unregister()` only sweeps the current extension list, so dropped extensions are never cleaned.
**Fix:** `_delete_tree(parent)` before writing; have `unregister()` sweep every extension carrying our keys.

**H-8 · EXIF orientation ignored by every image tool → phone photos come out sideways — [R][C]**
`ImageOps.exif_transpose` is used nowhere in `processors.py`. Compress, resize, convert, watermark and Image → PDF all drop the Orientation tag without rotating the pixels. A portrait phone photo becomes a landscape output (Image → PDF page 400×200 instead of 200×400).
**Fix:** `exif_transpose(im)` right after every `Image.open`.

**H-9 · Non-Latin OCR (Arabic, Cyrillic, …) produces an unreadable text layer — [R]**
The searchable layer is written with the Latin-only Base-14 font `helv` (`processors.py:2590`). Reproduced: `"مرحبا Привет Hello"` reads back as `'����� ������ Hello'`. The bundled Arabic OCR therefore produces PDFs that **cannot be searched**.
**Fix:** insert with a Unicode font covering the script (bundled Noto via `fontfile=` / `TextWriter`).

**H-10 · Organize page lists silently drop pages or do nothing — [R]**
In `_page_list` / `pdf_organize`:
- *Reorder* `3,1` on a 10-page file outputs **2 pages**, although the hint says "every page, in the order you want".
- *Extract* `2, 50, x` outputs 1 page.
- *Rotate* `pages=99` writes an unchanged `_rotated` file.
- Invalid or out-of-range tokens (including en-dash ranges `2–4`) are silently ignored.

**Fix:** reorder must cover every page (or confirm); raise a `ProcessError` naming invalid tokens.

**H-11 · OCR "Use AI" uploads the full text of every page, but the Privacy Policy, Terms and Help say otherwise — [C]** *(uncommitted)*
Once AI is configured the option defaults on (your chosen behaviour), and `_ocr_ai_pass` sends **every recognised line of every page of every file**. The disclosures contradict this:
- `legal.py:143-146`: "a short excerpt of that one document (not the whole file, and never your other files)… Nothing is sent otherwise."
- `help_page.py:169`: OCR "runs entirely on your computer — nothing is uploaded."
- Terms §4: "you review" AI output.

A 200-page scanned medical file goes to the AI endpoint (plain HTTP for custom endpoints) with no per-run notice.
**Fix:** rewrite Privacy/Terms/Help/Capabilities to disclose full-text upload, and show a per-run notice. (Consider defaulting to off.)

**H-12 · An API key containing a line break is written in clear to the log file, the UI and crash reports — [R][C]**
- `_collect_ai` only calls `.strip()`, so a pasted key with an embedded newline survives.
- `http.client` then raises `ValueError("Invalid header value b'Bearer <FULL KEY>'")`, which `ai._request` doesn't catch.
- The message surfaces verbatim in *Test connection* (`ai.py:351` "Unexpected error: …") and the suggestion panel.
- `ocr_ai.py:58` logs it with `log.debug`; the file handler runs at **DEBUG** (`logging_setup.py:43`), so the key lands in `mico360.log`.
- `crash.format_report` includes that log tail in a pre-filled public GitHub issue.

**Fix:** strip all whitespace/control characters and reject non-printables on save; catch `ValueError` in `_request` with a generic message; never interpolate exception text that may contain headers.

**H-13 · OCR AI cleanup can silently change what the document says — [R]** *(uncommitted; my implementation)*
`ocr_ai.cleanup_lines` accepts any reply with the right line count. With a mocked model, "Invoice total: 1,000 USD" became **9,000** and "ACME Ltd" became "EVIL Corp", both written into the searchable layer. Text in the scan can also steer the model. `_parse_numbered` also strips real list numbering ("1. Introduction" → "Introduction").
**Fix:** accept a corrected line only if it is close to the original (e.g. `difflib` ratio ≥ 0.8) and its digit sequences are unchanged; otherwise keep the raw line.

---

## 4. Medium

### Workflows & UI
| # | Finding | Where | |
|---|---|---|---|
| M-1 | Merge / Image → PDF re-run silently leaves out rows already done: the output has 2 of 4 PDFs, or "need at least two" appears with 4 in the queue | `tool_page.py:1065-1075` | [R] |
| M-2 | Drag-and-drop routing is inconsistent: a folder dropped on the queue is ignored; a PDF dropped on *File Properties* navigates away to Compress; unsupported files are skipped with no message; a folder of images dropped on Home opens Compress **PDF**. Help says "drag anywhere" | `main_window.py:536-545`, `dashboard_page.py:329` | [R] |
| M-3 | **Esc** in the sidebar search box cancels the running batch; **Delete** removes queue rows while focus is on an option control, even mid-run | `main_window.py:359`, `tool_page.py:255` | [R] |
| M-4 | **Undo** restores an old snapshot and drops files added since, including rows of a run started in between | `tool_page.py:783-785` | [R] |
| M-5 | "Processing X of Y" counts done rows from earlier runs, so it shows "2 of 2" from the first moment | `tool_page.py:1152-1157` | [R] |
| M-6 | "Retry N failed" also runs pending rows, contradicting its tooltip and the Help | `tool_page.py:840-847` | [R] |
| M-7 | OCR "Use AI" gating is evaluated only when the page is built: after configuring AI the box stays disabled until restart, and a saved `False` blocks "default on" | `tool_page.py:471-489` | [S] |
| M-8 | "System" theme mixes palettes after an OS dark/light switch: the stylesheet isn't re-applied but custom-painted parts are, making queue text near-unreadable | `theme.py:29-39`, `main_window._apply_visuals` | [S] |

### Processing correctness
| # | Finding | Where | |
|---|---|---|---|
| M-9 | Watermark (text and image) and Signature are misplaced or sideways on rotated pages; a "bottom-right" signature lands almost off-page | `processors.py` ~826-893, ~2237-2249 | [R] |
| M-10 | "Lossless" image compression drops extra TIFF frames and PNG DPI, yet reports **"verified identical"** because only frame 0 is compared | `_image_compress_lossless` ~1918-1955 | [R] |
| M-11 | Protect, Unlock, Organize and Merge rebuild with a bare `PdfWriter()` and lose bookmarks, Title/Author, attachments and forms | ~461, ~607, ~739, `_organize_visual` | [R] |
| M-12 | A 0-byte placeholder is left on every failure or cancel; `not out.exists()` checks are therefore dead, so a silent engine failure yields a **0-byte "success"** | `util._reserve`; checks at ~171, 940, 975, 1560, 1655 | [R] |
| M-13 | Merge / Image → PDF output name isn't sanitized: `"Report: Q1"` writes into an **NTFS alternate data stream** (a visible 0-byte file); `..\\x` escapes the output folder; `merged.pdf` becomes `merged.pdf.pdf` | ~457-458, ~1869-1870 | [R] |
| M-14 | HEIC compression is broken: *target* mode writes **PNG bytes into a `.heic`**, and the preset levels produce identical files | ~1993-2050 | [R] |
| M-15 | Convert Image to the same format with Overwrite on **overwrites the source** (111 KB → 18 KB in the test) | ~3266 | [R] |
| M-16 | Transparent PNG → JPEG takes on the hidden colour behind the transparency (often black or red) instead of white | `_save_image` ~3183, ~2020, ~2043 | [R] |
| M-17 | PDF → PowerPoint places text wrongly on rotated pages, stretches every page image to page 1's size, and its OCR is Latin-only | ~1385-1425 | [R] |
| M-18 | Ghostscript compression breaks on file names containing `%` (treated as a per-page format) | ~162 | [S] |
| M-19 | Image → PDF "combine" holds every decoded image in RAM (200 × 12 MP ≈ 7 GB) and saves pages at 72 dpi, so a 4000 px photo becomes a 55-inch page | ~1871-1876 | [S] |

### AI, privacy & security
| # | Finding | Where | |
|---|---|---|---|
| M-20 | OCR AI writes **Author** as well as Title/Subject without review, overwriting the source's real metadata; the option label says "title/subject" *(uncommitted)* | `processors.py` ~2591-2604 | [R] |
| M-21 | Cancel during the OCR AI step still saves a half-corrected file and marks it **Done**; AI calls aren't cancellable (up to 120 s each, plus backoff) *(uncommitted)* | ~2631-2637, `ocr_ai` | [R] |
| M-22 | The API key is forwarded when a redirect points elsewhere, including to another host or from HTTPS to HTTP; a bare host is normalized to `http://` | `ai.py:237-244`, `normalize_base_url` | [R] |
| M-23 | Clicking Save after typing a new custom URL sends the saved System-AI key to that host, and the refresh timer repeats it every 5 minutes | `settings_page.py:636-670` | [S] |
| M-24 | Privacy "Scrub" / "Remove all" leave identifying data behind: custom Info keys (`/LastModifiedBy`), annotation authors, embedded files, page-level XMP and the trailer `/ID`. The hint says "Ideal before sharing" | `processors.py` ~2311-2345 | [R] |
| M-25 | Editing metadata leaves stale XMP (old author still visible in Acrobat); setting Copyright **replaces** the whole XMP packet, breaking PDF/A | ~2350-2433 | [R] |
| M-26 | Closing the window during an AI request aborts the process ("QThread destroyed while running", exit 127) | `ai_suggest.py:270-315` | [R] |
| M-27 | Edit Metadata values (title, author, custom, dates) are saved as defaults and applied to every file in a batch and to later sessions | `options_widget.py` save/restore, `tool_page.py:651-656` | [C] |
| M-28 | The installer re-registers the right-click menu on **every install and auto-update**, overriding a user who turned it off; it has no stored preference or installer Task. This contradicts Privacy §6 / Terms §5 ("optional stays off") | `installer.iss:67`, `config.py` | [C] |

### OS integration, updater & packaging
| # | Finding | Where | |
|---|---|---|---|
| M-29 | Folder-background verbs break at a drive or share root: `"%V"` becomes `"E:\"`, which argv parsing turns into `E:"` | `shell_integration.py` (folder `"%V"`) | [R] |
| M-30 | Updater **skips the SHA-256 check** when the checksum file can't be fetched, then runs the installer anyway while the UI says "checksum-verified" | `updater.py:199-260, 406` | [R] |
| M-31 | The Atom-feed fallback accepts pre-releases but installs the stable `-Latest.exe`, so the user is prompted again on every launch | `updater.py:172-223` | [R] |
| M-32 | `parse_version("7.4.0-rc2")` gives (7,4,2), so pre-releases rank above the final release | `updater.py:128-135` | [R] |
| M-33 | The installer (admin) registers and unregisters the menu in the **elevating admin's** HKCU, not the logged-in user's | `installer.iss:38, 67, 72` | [S] |
| M-34 | The app doesn't reopen after a silent auto-update (no `RegisterApplicationRestart`, and the launch entry is `skipifsilent`), although the UI says it will | `installer.iss:68`, `updater.py:430` | [S] |
| M-35 | `release.ps1` / `publish.ps1` never upload `Setup-Latest.exe` + sidecar. The updater fallback and the README link need them; they are present today only because they were uploaded manually | `release.ps1:93, 96`, `publish.ps1:47` | [C] |
| M-36 | Portable onefile spec strips `QtNetwork`, so the exe fails at startup (single-instance import); it also omits `app.png`, Arabic OCR data, menu icons, vtracer and pillow_heif | `mico360_onefile.spec:81-85` | [C] |

### Test & development infrastructure
| # | Finding | |
|---|---|---|
| M-37 | **~30 test files write the user's real app settings** (`%APPDATA%\MICO360\DocToolkit.ini`, the same file the installed app uses). There is no isolation. Running the suite **evicts your genuine recent files** (cap 12) with test temp paths (found in your live file), leaves an orphan key for a removed tool, and could leave test AI URLs or keys behind if a test crashes mid-way. Fix: point `QSettings` at a temp INI when an env var / test flag is set. | [R] |

---

## 5. Low

**UI / UX / accessibility**
- The preview keeps showing a removed file.
- Double-clicking a Recent file opens **two** Explorer windows (both `itemActivated` and `itemDoubleClicked` are wired).
- Toasts and BatchControllers are never freed.
- Accessibility gaps:
  - queue row state and errors are painted only, not exposed;
  - the 9 watermark position radios are unnamed;
  - the favourite star doesn't announce whether the tool is pinned;
  - the organizer has no keyboard shortcuts.
- Contrast below 4.5:1 — light `text_faint` 3.27:1 and the dark "Working…" chip 2.91:1.
- Thumbnails are rendered without device-pixel ratio, so they look blurry at 150–250 % scaling. [S]
- UI text that contradicts behaviour:
  - Cancel says "in-flight files will finish" (they stop mid-file);
  - "Remove done" also removes failed rows;
  - Help says "click" to open an output (it takes a double-click).

**Processing**
- Password-protected PDFs give a raw "Unexpected error" in Watermark, Page numbers, PDF → Image and PDF → PPTX.
- Cancel is ignored in compress-to-target (up to 10 rewrites), Merge and Image → PDF combine.
- The progress bar sits at 100 % during target-mode verification.
- `image_to_svg` trace leaves temp dirs behind.
- LibreOffice MSI extract dir leaks on failure, and a bad cached MSI is reused forever. [S]
- Folder walks collect `~$` Office lock files, `desktop.ini` and `Thumbs.db`.
- Date parsing tries month/day before day/month.

**AI / OCR / docs**
- GPU OCR has no CPU fallback when DirectML fails during inference. [S]
- OCR skips scanned pages that already have ≥ 8 characters of text (fax header, Bates stamp). [S]
- OCR model SHA-256 is checked only at download, and the model URL is unpinned (`resolve/main`). [S]
- `normalize_base_url` mangles Gemini, Azure and query-string URLs.
- Crash-report GitHub issues are pre-filled with the Windows username in paths and with document file names.
- Docs and capabilities are inaccurate:
  - GPU OCR is shown as "On" on macOS;
  - "optional features are off" although GPU OCR defaults on and the menu is auto-registered;
  - "clear the log" doesn't delete the files;
  - Settings section names are inconsistent;
  - **README is stale** (stops at v6.9, calls the app Windows-only, omits AI, the organizer, the Explorer menu and the low-resource guards).

**Integration / build**
- CLI paths aren't made absolute before forwarding, and a file named `-draft.pdf` is dropped.
- macOS CI manual dispatch builds `main` onto an arbitrary tag, and its smoke gate only checks the process is alive after 12 s.
- Update *Retry* restarts from zero, and ~144 MB installers pile up in `%TEMP%`.
- Upgrades never delete stale files in `_internal`. [S]
- A download without Content-Length never completes. [S]
- `build.ps1` aborts when pip writes a harmless warning (PS 5.1 with `2>$null`).
- The crash handler may build a QMessageBox off the GUI thread. [S]

**Test infrastructure**
- The suite runner has no per-test timeout. `ai_bugfix_test` hung **814 s** under heavy concurrent load (passes 14/14 alone), which stalls the whole run.
- `stress_batch_test`'s cancel check is timing-flaky (known).

---

## 6. Release readiness (pending v7.4.0)
- Five features are uncommitted, and four new paths are **untracked**: `mico360/core/ocr_ai.py`, `mico360/resources/menu_icons/`, `build/make_menu_icons.py`, `tests/ocr_ai_test.py`. A partial commit would break the OCR-AI import in CI and drop the menu icons.
- `RELEASE_NOTES.md` and the README don't mention any of the five features.
- Fix H-5, H-11, H-13, M-20 and M-21 before shipping; the rest of that feature set is sound.

## 7. Carried over (user-side, unchanged)
Unsigned Windows installer (SmartScreen) · ad-hoc macOS signing (Gatekeeper) · custom-endpoint AI traffic over plain HTTP · macOS API key stored base64 (disclosed).

## 8. Checked and found clean
- **Output naming:** locking is race-free within a batch.
- **Guards and parsing:** disk-space guard arithmetic, reversed page ranges.
- **Protect:** confirm-password handling; output really is AES-256 (V5/R6).
- **Merge / split / compress:** owner-only encrypted inputs handled.
- **Visual organizer:** duplicate pages keep separate rotations, and rotation doesn't leak across splits.
- **Metadata:** "remove all" basics; page numbers on rotated pages.
- **Keys and passwords:** key sealing (DPAPI) and masking; passwords are never saved.
- **AI replies:** JSON parsing survives odd model output.
- **UI batching and state:** open-request coalescing loses and duplicates no files once a single instance receives them; the queue maps results back correctly after reordering and duplicates.
- **Options form:** option save/restore and `visible_when` across all tools.
- **Updater:** checksum/asset pairing per OS; `7.10.0 > 7.9.0`.
- **Right-click menu:** quoting of paths with spaces/unicode; `unregister` matches everything `register` writes for the current lists.
- **Bundling:** the onedir and macOS specs bundle every runtime resource.

## 9. Recommended fix order
1. **C-1** (data loss) — one-line change: temp `--outdir`.
2. **H-1, H-2** — double processing / unwanted overwrites; small guards.
3. **H-6, H-7, M-35** — protect the release pipeline and the menu before the next ship.
4. **OCR-AI set: H-11, H-13, M-20, M-21** — gate for v7.4.0.
5. **H-5** — atomic single-instance lock (completes the multi-file feature).
6. **H-3, H-4, H-10** — organizer / organize correctness.
7. **H-8, H-9, H-12** — photos, Arabic OCR, key hygiene.
8. **M-37** — isolate test settings so the suite stops touching your real config.
9. Remaining Mediums by area, then Lows.


---

## 10. Resolution status (2026-09-27)

Every code-level item above is fixed in the working tree (**uncommitted**).
Regression checks for them are in `tests/bugfix_2026_09_test.py`, plus updates to the
affected existing suites. The full suite runs through `tests/run_suite.py`, which gives
each suite a timeout and an isolated settings file. Items that still need the owner are
listed at the end.

| Item | Fix | Where / test |
|---|---|---|
| C-1 | LibreOffice converts into a private staging folder, then moves the one file | `_run_libreoffice` |
| H-1 | `start()` returns while a controller exists | `tool_page.start` · bugfix H-1 |
| H-2 | Output/Overwrite/Same-as-source re-sync on show; written back only if changed on the page | `_resync_from_settings` · bugfix H-2 |
| H-3 | Plan carries its target file; other files fail with a clear message; plan cleared when its file leaves the queue | `_PagePlanField`, `_organize_visual` · bugfix H-3, page_organizer |
| H-4 | `done()` stops rendering + closes the PDF; dialog `deleteLater()` | `page_organizer.py` · bugfix H-4 |
| H-5 | OS-exclusive `QLockFile` claim; secondaries retry for 8 s | `single_instance.py` · bugfix H-5 (5 racing processes → 1 window) |
| H-6 | `$LASTEXITCODE` checks, `dist` wiped first | `build.ps1` · build_scripts |
| H-7 | Submenu rebuilt from scratch; unregister sweeps every extension with our keys | `shell_integration.py` · bugfix H-7 |
| H-8 | `exif_transpose` in every image path | `processors._upright` |
| H-9 | Unicode font + TextWriter (RTL), subset, ToUnicode normalised (base Arabic letters, real spaces) | `pdf_ocr` · bugfix H-9 |
| H-10 | Strict page lists (bad tokens named), reorder must cover every page | `_page_list` · v52/full_coverage |
| H-11 | Privacy, Terms, Help, capabilities and option hint disclose full-text upload; per-run log notice naming the host | `legal.py`, `help_page.py` · help_legal H-11 |
| H-12 | Keys stripped of whitespace/control chars; ValueError caught with a generic message; exception text never logged/shown | `ai.sanitize_key`, `_request` · bugfix H-12 |
| H-13 | Corrections accepted only when similar (≥ 0.8) and digit-preserving (OCR look-alikes allowed); prompt hardened; list numbers kept | `ocr_ai.is_safe_correction` · ocr_ai, bugfix H-13 |
| M-1 | Aggregate tools always submit the whole queue | bugfix M-1 |
| M-2 | Drops: folders/any-file pages handled in place; routing looks inside folders; unusable drops explained | `main_window.dropEvent`, `route_for` · bugfix M-2 |
| M-3 | Delete scoped to the queue; Esc in a text box outside the page clears it | bugfix M-3 |
| M-4 | Undo re-inserts only removed rows | bugfix M-4 |
| M-5 | Counter uses this run's rows | bugfix M-5 |
| M-6 | Retry failed runs only failed rows | usability |
| M-7 | AI option re-gated on show; disabled values not saved | bugfix M-7 |
| M-8 | OS theme change listener re-applies the stylesheet for "System" | `main_window._on_os_theme_changed` |
| M-9 | Rotated-page placement for watermark/signature | processors |
| M-10 … M-19 | Fixed as listed (lossless frames/DPI, bookmarks, 0-byte placeholders, name sanitising, HEIC, same-format overwrite, transparency, PPTX, `%` in names, Image→PDF memory/size) | processors · bugfix, robustness |
| M-20 | AI fills only an empty Title/Subject; never Author | bugfix M-20 |
| M-21 | Cancel checked after the AI step; AI calls take a cancel event | bugfix M-21 |
| M-22 | Redirect handler drops Authorization across origins, refuses HTTPS→HTTP; bare public host → HTTPS | bugfix M-22 |
| M-23 | Saved key bound to its origin (`ai/key_origin`) | bugfix M-23, ai_metadata |
| M-24 | Scrub keeps only Title/Subject/Keywords; removes custom keys, annotation authors, embedded files, page/image XMP, new file ID | bugfix M-24 |
| M-25 | Info edits merged into existing XMP (prefixes and PDF/A id kept) | bugfix M-25 |
| M-26 | AI requests run on daemon threads with a UI-thread relay (also fixed an intermittent crash) | `mico360/ui/bg.py` · ai_bugfix/ai_metadata |
| M-27 | Per-document options `persist=False` + batch note | bugfix M-27 |
| M-28 | Installer Task `shellmenu`; stored opt-out honoured by `--register-shell` (only `--force` from an interactive install overrides) | `installer.iss`, `app.py` · build_scripts |
| M-29 | CLI repairs `E:"` → `E:\`; paths made absolute; `--` before targets | `parse_cli` · shell_integration |
| M-30 … M-32, M-34 … M-36 | Updater checksum required, pre-release ranking/feed, silent-update relaunch, Setup-Latest upload, onefile spec | updater/build tests |
| M-33 | Register/unregister run as the original user; installed app self-heals a menu pointing at a moved/old exe | `shell_integration.self_heal` · bugfix |
| M-37 | `MICO360_SETTINGS_FILE` + `tests/run_suite.py` (per-suite timeout); build/release gates use it | bugfix M-37 |
| Lows | All listed Lows fixed (preview refresh, recent double-open, toast/controller freeing, accessibility names/state, WCAG contrast, DPR thumbnails, UI texts, friendly errors, target-mode cancel/progress, SVG temp, MSI leak, lock-file skipping, ambiguous dates, GPU→CPU fallback, `_page_has_text`, pinned+re-verified model, URL normalisation, crash-report redaction, CLI paths, crash dialog on the UI thread, docs/README) | bugfix "Low" checks |

**Still with the owner (not code):** Windows code signing, macOS notarisation, an HTTPS
endpoint for the System AI, and macOS keychain storage for the key (section 7).
Released as **v7.4.0** (notes in `build/RELEASE_NOTES.md`).

**Verification:** `python tests/run_suite.py` — **70 / 70 suites pass** (2026-09-27), including `bugfix_2026_09_test.py` (~85 checks); the real `DocToolkit.ini` was byte-identical before and after.
