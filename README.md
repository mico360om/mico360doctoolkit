# MICO360 Doc Toolkit  ·  v5.5.0

A modern Windows 10/11 desktop app for PDF & image management — a **Dashboard**
home plus 25 tools to compress, merge, split, organize, protect, watermark, sign,
OCR, and convert between PDF, Office, and image formats. Clean themed UI,
drag-and-drop anywhere, bulk/folder processing, multi-threaded batches, toasts and
activity logs.

![brand: maroon / black / white]

> **v5.4** — a new **Dashboard** home (quick actions, favourites, recent files,
> drop-anywhere); a **searchable, collapsible** sidebar; new PDF tools (**Rotate /
> Delete / Extract Pages, Add Page Numbers, Sign, Edit Metadata, Searchable OCR**);
> new conversions (**PDF→Excel, Excel→PDF, PowerPoint→PDF**); new image tools
> (**Resize, Convert, Watermark**); **Light/Dark/System** theme, **detailed progress
> with ETA**, and **toasts**.
>
> **v5.3** — **Watermark PDF** can now stamp a **logo / image** (not just text) —
> choose a picture, size, opacity and angle.
>
> **v5.2** — three new PDF tools: **Organize** (rotate / delete / extract / reorder
> pages), **Protect** (AES-256 password, or unlock), and **Watermark** (diagonal
> text) — plus **drag-to-reorder** files in Merge.
>
> **v5.1** — **better OCR** (higher-resolution recognition, low-confidence noise
> filtered out, text rebuilt in proper reading order, and the engine loaded once
> for faster batches) and an **expanded Help** (new OCR, auto-update and keyboard
> shortcut sections).
>
> **v5.0** — **built-in auto-update via GitHub Releases.** The app checks for new
> versions on startup (and on demand from **Settings → Updates**), shows the
> release notes, then downloads the installer, **verifies it with SHA-256**, and
> upgrades in place — keeping your settings. No new dependency (standard-library
> `urllib`). The latest GitHub release *is* the update manifest.
>
> **v4.0** — **follows your Windows light/dark theme** by default (and remembers
> your choice), a theme-aware white logo, **borderless checkboxes**, About Us /
> Terms / Privacy in Settings, a more detailed Help, and a **fast, lazy startup**
> that fixes app/system hangs on launch.
>
> **v3.2** — **OCR for scanned PDFs** (PDF→Word / PowerPoint now recognise text
> from image-only pages), **remembers your last-used options** per tool, optional
> **bundled Ghostscript** for stronger PDF compression, and a real **Inno Setup
> installer**.
>
> **v3.1** — Word→PDF works out of the box (engine chain), **compress to a
> target file size** (e.g. 250 KB), **PDF→PowerPoint** = editable text with an
> automatic page-image fallback (no more empty slides), and a **per-file status**
> system (done / failed / pending) that skips finished files until you hit *Redo*.
> Responsive interface: collapsible sidebar, reflowing panels, light/dark, chips.

## Features

| Tool | Notes |
|------|-------|
| **Compress PDF** | Low / Medium / High, **target file size**, or custom DPI + JPEG quality |
| **Merge PDF** | Combine many PDFs into one |
| **Split PDF** | Per page, fixed page-count, or custom ranges (`1-3, 5, 8-10`) |
| **Organize PDF** | Rotate, delete, extract, or reorder pages |
| **Protect PDF** | Add an **AES-256** password, or unlock with the current one |
| **Watermark PDF** | Text **or logo/image** stamp — size, opacity, angle, colour |
| **PDF → Word** | Fully editable `.docx` text + layout (pdf2docx) |
| **PDF → PowerPoint** | **Editable text boxes**, one slide per page |
| **Word → PDF** | Engine chain: LibreOffice → MS Word → built-in fallback (always works) |
| **PDF → Image** | JPG / PNG / WEBP / BMP / TIFF, selectable DPI |
| **Image → PDF** | One PDF each, or combined |
| **Compress Image** | Presets, **target file size**, or custom quality + resize / format change |

Supported image formats: **JPG, JPEG, PNG, WEBP, BMP, TIFF**.

### Highlights
- **Responsive UI** — collapsible sidebar (auto-collapses on narrow windows),
  panels that reflow side-by-side → stacked, usable from small to maximized.
- **Drag & drop** files *and* folders (folders scanned recursively).
- **Bulk / batch** processing with a live progress bar, status chips and per-file results.
- **Multi-threaded** — uses all CPU cores (configurable in Settings).
- **Originals preserved** — outputs go to a folder you choose, or next to the source.
- **Light & dark** themes in the brand palette, switchable from the top bar.
- **Activity log** + rotating file logs for troubleshooting.

## Run from source

```powershell
# Python 3.10+ (tested on 3.14)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

> **Tip:** if your project folder is inside OneDrive/Dropbox, create the venv
> *outside* the synced folder to avoid file-lock errors during install.

### External engines (optional — the app works without them)
- **Ghostscript** — best PDF compression. Without it, a built-in PyMuPDF
  compressor is used automatically.
- **Word → PDF engine chain** — the app picks the best available, in order:
  1. **LibreOffice** (bundled in `vendor/`, or installed/auto-detected) — highest fidelity.
  2. **Microsoft Word** via COM, when Office is installed.
  3. **Built-in converter** (python-docx + reportlab) — text, headings, basic
     styling and tables; no external program required, so Word→PDF *always* works.

The app auto-detects engines on PATH / standard install dirs, or you can set exact
paths in **Settings → External tools**. For maximum fidelity with zero setup,
drop a portable LibreOffice under `vendor/libreoffice/` (see `vendor/README.md`)
and it will be bundled into the build.

## Build a Windows installer

```powershell
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

This will:
1. create a build venv (under `%LOCALAPPDATA%`),
2. install deps + PyInstaller,
3. generate the icon, run the smoke test,
4. build `dist\MICO360DocToolkit\` (onedir),
5. compile `dist\installer\MICO360-DocToolkit-Setup-1.0.0.exe` if
   [Inno Setup 6](https://jrsoftware.org/isdl.php) (`iscc`) is on PATH.

Drop Ghostscript/LibreOffice into `vendor/` first if you want them bundled into
the installer.

## Releasing & auto-update (GitHub manifest)

The app's auto-updater reads the repository's **latest GitHub Release** as its
manifest — the tag is the version (`vX.Y.Z`), the body is the release notes, and
the attached `Setup .exe` (+ a `.sha256` sidecar) is what gets installed.

1. Set your repo once in `mico360/updater.py`:
   ```python
   GITHUB_OWNER = "MICO360"
   GITHUB_REPO  = "MICO360-Doc-Toolkit"
   ```
2. Bump `__version__` in `mico360/__init__.py` and `AppVersion` in
   `build/installer.iss`, then cut a release:
   ```powershell
   powershell -ExecutionPolicy Bypass -File build\release.ps1
   ```
   This builds the installer, writes `<installer>.sha256`, and — if the GitHub
   CLI (`gh`) is authenticated — runs `gh release create vX.Y.Z` uploading both
   files. Without `gh`, it prints the exact manual steps.

On launch (and from **Settings → Updates**) the app calls the GitHub API, and if
a newer release exists it shows the notes, downloads the installer, verifies the
SHA-256, then runs it silently (`/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`)
to upgrade in place and relaunch. Auto-check can be turned off in Settings.

## Project layout

```
mico360/
├── app.py              # bootstrap (QApplication)
├── config.py           # persistent settings (QSettings)
├── theme.py            # v2 design tokens + light/dark stylesheets
├── paths.py            # resource/user paths (source & frozen)
├── logging_setup.py    # rotating file log + Qt log bridge
├── core/
│   ├── tools.py        # declarative registry of the 10 tools + options
│   ├── processors.py   # the actual compress/convert/merge/split logic
│   ├── engine.py       # QThreadPool batch controller (multi-threaded)
│   ├── deps.py         # Ghostscript / LibreOffice discovery
│   └── util.py         # output-path & subprocess helpers
└── ui/
    ├── main_window.py  # responsive shell: top bar + collapsible sidebar + pages
    ├── sidebar.py      # collapsible brand sidebar with grouped navigation
    ├── tool_page.py    # responsive tool page: drop zone, options, run, progress
    ├── options_widget.py, widgets.py, file_collector.py
    ├── settings_page.py, help_page.py, log_page.py
build/                  # make_icon.py, mico360.spec, installer.iss, build.ps1
tests/                  # smoke, ui_construct, compression_levels, full_coverage,
                        # functional_ui, responsive
```

## Testing

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python tests\smoke_test.py               # all processors on generated samples (happy path)
python tests\full_coverage_test.py       # every tool + edge cases + helpers
python tests\ui_construct.py             # builds the full UI + sidebar collapse/nav
python tests\compression_levels_test.py  # asserts Low/Medium/High actually differ
python tests\functional_ui_test.py       # drives real ToolPages end-to-end (per-file + aggregate)
python tests\responsive_test.py          # sidebar thresholds, theme sync, panel reflow
python tests\v3_features_test.py         # Word→PDF chain, target-size, editable PPTX + image fallback
python tests\v32_features_test.py        # remember-options + OCR for scanned PDFs
python tests\status_test.py              # per-file done/skip/redo status behaviour
python tests\qa_fixes_test.py            # atomic naming, error wrapping, aggregate output
python tests\progress_test.py            # real intra-file 0->100 progress (not a jump)
python tests\v4_features_test.py         # system-theme default, lazy startup, legal docs, logo
python tests\updater_test.py             # version compare, release parsing, download + SHA-256 verify
python tests\v51_features_test.py        # OCR engine caching, confidence filter, row reconstruction, Help
python tests\update_ui_test.py           # update check/dialog runs on the GUI thread (no crash)
python tests\v52_features_test.py        # Organize/Protect/Watermark PDF, page-spec parser, merge reorder
python tests\v54_features_test.py        # Rotate/Delete/Extract, page numbers, sign, metadata, OCR, Office, image tools
python tests\all_tools_test.py           # EVERY tool driven end-to-end through the real UI + engine
python tests\v54_behavior_test.py        # multi-file, save-next-to-source, file-option persistence, drop routing
python tests\v54_round4_test.py          # protect/unlock UI, cancellation, no-results search, fav integration
python tests\v54_ui_test.py              # Dashboard, drop routing, favourites, theme mode, toast
python tests\v54_functional_test.py      # new tools driven end-to-end through real UI widgets + engine
python tests\v54_edge_test.py            # error handling, corrupt input, real PDF->Excel table extraction
python tests\sidebar_test.py             # tool search + collapsible categories
python tests\v55_features_test.py        # consolidated Organize, Protect confirm/show-hide, Watermark position, posgrid/password kinds
```

## Compatibility
Windows 10 / 11, 64-bit. Python 3.10+.

## Licensing
App © MICO360. Bundles/depends on Ghostscript (AGPL) and LibreOffice (MPL-2.0);
review their terms before commercial redistribution.
