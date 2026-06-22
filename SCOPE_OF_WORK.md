# MICO360 Doc Toolkit — Scope of Work & Feature Specification

**Product:** MICO360 Doc Toolkit
**Version:** 6.7.0
**Publisher:** MICO360
**Platforms:** Windows 10/11 (64‑bit) and macOS (Apple Silicon)
**Document date:** 2026‑06‑07
**Contact:** info@mico360.com · github.com/mico360om/mico360doctoolkit

---

## 1. Overview

MICO360 Doc Toolkit is a fast, private, all‑in‑one desktop application for working with
**PDF, image, Office and vector files**. It bundles everything a user needs to compress,
convert, organise, secure, and edit documents into a single installer that runs entirely
**offline, on the user's own computer** — no accounts, no uploads, no subscriptions.

The application is built as a native desktop app (PySide6/Qt) with a declarative tool
registry, a multi‑threaded batch engine, a modern responsive UI, and a built‑in
auto‑update system delivered through GitHub Releases.

### 1.1 Goals & objectives

| Objective | How it is met |
|---|---|
| **Privacy by design** | All processing is 100% local; the only network call is the optional update check. |
| **Zero setup** | The conversion engine (LibreOffice) and OCR models ship inside the installer — works on any PC with nothing else to install. |
| **Never lose data** | Originals are never modified; lossless modes are verified content‑identical; deletes go to the Recycle Bin. |
| **Fast** | Multi‑threaded batch processing across CPU cores; GPU‑accelerated OCR. |
| **Always current** | Built‑in, verified auto‑update with a clear, detailed update experience. |
| **Cross‑platform** | One codebase ships to Windows and macOS. |

---

## 2. Scope

### 2.1 In scope

- A Windows and macOS desktop application with a graphical UI.
- 21 document/image/vector tools (see §5).
- A batch **queue** with per‑file status, drag‑reorder, and rich actions.
- A **Dashboard** home screen (favourites, recent files, activity).
- Light / Dark / System theming, responsive layout, multi‑monitor / high‑DPI support.
- Bundled third‑party engines (LibreOffice, OCR models) and optional external tools
  (Ghostscript) for the smallest lossy PDF compression.
- Built‑in **auto‑update** (download, SHA‑256 verify, install, confirm) with a fallback
  source and a detailed update screen.
- In‑app **Help**, **About Us**, **Terms & Conditions**, **Privacy Policy**.
- Packaged installers: Windows `.exe` (Inno Setup) and macOS `.dmg`.
- Continuous build of the macOS app via cloud CI; automated test suite.

### 2.2 Out of scope

- Cloud storage / online accounts / server‑side processing.
- Real‑time collaboration or multi‑user editing.
- Mobile (iOS/Android) and web (browser) versions.
- Telemetry, advertising, or usage analytics.
- E‑signature legal certification / digital certificate signing (a visual signature
  stamp is provided; cryptographic PDF signing is not in scope).

---

## 3. Platforms & system requirements

| Item | Windows | macOS |
|---|---|---|
| OS | Windows 10 / 11, 64‑bit | macOS 11+ (Apple Silicon) |
| Disk | ~1.5 GB installed (bundled engines) | ~1 GB |
| RAM | 4 GB minimum, 8 GB recommended | 8 GB recommended |
| GPU (optional) | Any Direct3D‑12 GPU accelerates OCR | CPU OCR (DirectML is Windows‑only) |
| Internet | Only for optional updates | Only for optional updates |
| Privileges | Standard user (admin only for install / setting file Owner) | Standard user |

---

## 4. Architecture & technology

- **UI framework:** PySide6 / Qt Widgets (declarative tool registry → UI is generated
  from data, so adding a tool is a data change).
- **Batch engine:** `QThreadPool`‑based controller that turns a tool + input list into
  concurrent work units, emitting progress/result signals to the UI.
- **PDF:** PyMuPDF (render, compress, SVG rasterise), pypdf (merge/split/encrypt),
  pdfplumber/pdfminer (table extraction), pdf2docx (PDF→Word), reportlab.
- **Office:** Bundled **LibreOffice** (headless) for all Office↔PDF/Markdown conversion;
  Microsoft Office via COM used opportunistically when present.
- **Images:** Pillow (compress/convert/resize/watermark), img2pdf.
- **OCR:** RapidOCR + ONNX Runtime, **GPU‑accelerated via DirectML** with automatic CPU
  fallback.
- **Vector:** PyMuPDF (SVG→image), vtracer (image→SVG tracing).
- **Compression engines:** PyMuPDF/Pillow (default); Ghostscript optional for smallest
  lossy PDFs.
- **Packaging:** PyInstaller (onedir) + Inno Setup (Windows `.exe`); PyInstaller `.app`
  + `hdiutil` (macOS `.dmg`).
- **Updates:** GitHub Releases as the manifest; resumable, integrity‑checked downloader.
- **Persistence:** QSettings (preferences only) + a local activity log.

---

## 5. Features — tools (21)

Tools are grouped in the sidebar by category. Every tool runs as a batch over the queue,
remembers its last‑used options, and writes outputs to a chosen folder **or** beside the
originals (numbered, never overwriting). **Originals are never modified.**

### 5.1 PDF

| # | Tool | Description | Key options |
|---|---|---|---|
| 1 | **Compress PDF** | Reduce file size. **Lossless** (default) removes redundancy with zero change to images/text/fonts/layout and is **verified content‑identical**; lossy levels re‑encode images for a smaller file. | Lossless / Low / Medium / High / Target size / Custom (DPI + quality) |
| 2 | **Merge PDF** | Combine multiple PDFs into one; drag to reorder. | Output name, order |
| 3 | **Split PDF** | Split every page, into fixed page counts, or by custom ranges (e.g. `1‑3, 5, 8‑10`). | Mode, ranges |
| 4 | **Organize PDF** | Rotate, delete, extract, or reorder pages. | Operation, page sets |
| 5 | **Protect PDF** | Add a password (AES‑256) or remove one. Passwords are never stored. | Protect / Unlock, password |
| 6 | **Watermark PDF** | Stamp text or a logo/image across pages. | Text/logo, opacity, angle, 3×3 position |
| 7 | **Add Page Numbers** | Insert page numbers. | Position, style (`1` / `1 / N` / `Page 1`), start |
| 8 | **Sign PDF** | Stamp a signature image on first/last/every page. | Image, placement |
| 9 | **Edit Metadata** | Set Title, Author, Subject, Keywords. | Text fields |
| 10 | **Searchable PDF (OCR)** | Add an invisible, selectable text layer to scanned PDFs. **GPU‑accelerated** (DirectML) with CPU fallback. | Recognition quality (200/300/400 dpi) |
| 11 | **PDF → …** | Convert a PDF to **Word**, **PowerPoint**, **Excel**, or **Images**, with optional OCR for scanned pages. | Target, OCR, DPI, format |

### 5.2 Convert

| # | Tool | Description | Key options |
|---|---|---|---|
| 12 | **Office → PDF** | Word / Excel / PowerPoint → PDF, type auto‑detected. Built‑in LibreOffice engine — works with no Microsoft Office, including legacy `.doc/.xls/.ppt`. | — |
| 13 | **Document → Markdown** | Word / Excel / PowerPoint / PDF → clean Markdown (headings, bold/italic, lists, tables). | — |
| 14 | **Image → PDF** | Combine images into one PDF, or one PDF per image. | Combine, name |
| 15 | **SVG → Image** | Rasterise `.svg` to PNG / JPEG / WEBP at a chosen width. PNG/WEBP keep transparency. | Format, width, background |
| 16 | **Image → SVG** | **Trace** to real vector paths (logos / line art; colour or B&W) or **Embed** the image exactly (photos). | Mode, colours |

### 5.3 Images

| # | Tool | Description | Key options |
|---|---|---|---|
| 17 | **Compress Image** | Reduce image size. Lossless (verified pixel‑identical) or presets / target size / custom quality. | Level, target, quality, format, resize |
| 18 | **Resize Image** | Batch resize by dimensions or percentage. | Width/height/percent |
| 19 | **Convert Image** | Change format (PNG / JPG / WEBP / TIFF / BMP). | Output format |
| 20 | **Watermark Image** | Stamp text or a logo onto images. | Text/logo, opacity, angle, position |

### 5.4 System

| # | Tool | Description | Key options |
|---|---|---|---|
| 21 | **Edit File Properties** | Bulk‑set Windows file properties on any files: **Date Created**, **Date Modified**, **Owner**. Writes to a copy (originals untouched, content byte‑identical). | Dates, owner (owner needs admin) |

---

## 6. Features — application

### 6.1 The queue (input panel)

- A proper **file queue**: a compact drag‑and‑drop band plus a large file list.
- Per‑row **status** (Queued / Working / Done / Failed) with a coloured dot, file size,
  output name or failure reason; long names are middle‑elided with the full path on hover.
- A **live count** (working / pending / done / failed) in the header.
- **Drag to reorder**; multi‑select; **Delete** key removes rows.
- Toolbar: **Add files**, **Remove selected**, **Remove finished**, **Clear all**.
- Right‑click menu (multi‑select aware): Open source / output folder, Move to top /
  bottom, Duplicate row(s), Retry failed/done, Remove from queue, **Delete from disk
  (→ Recycle Bin, with confirmation)**.
- The same file can be queued more than once (Duplicate); each row is tracked
  independently.

### 6.2 Dashboard (Home)

- Quick actions, **favourite tools** (pin with ☆), **recent files**, and **last activity**.
- **Drag & drop files anywhere** in the window → routed to a sensible tool.

### 6.3 Processing & output

- Multi‑threaded batch processing across CPU cores (configurable worker count).
- Live progress bar with **percentage**, **current file**, and **estimated time remaining**.
- Outputs to a chosen folder, or **beside originals** named `name (1).ext`.
- **Originals are never modified**; failed files keep a clear reason; a batch can be
  cancelled and finished rows retried.

### 6.4 Appearance & UX

- **Light / Dark / System** themes (follows the OS theme by default).
- Responsive layout (panels reflow when narrow), multi‑monitor and high‑DPI aware.
- Collapsible sidebar with tool search; keyboard navigation; tooltips throughout.
- Single‑instance (re‑launching focuses the running window).
- Transient toast notifications and an activity log.

### 6.5 Settings

- **Appearance:** System / Light / Dark.
- **Output:** default output folder, "open folder when done", overwrite behaviour.
- **Processing:** parallel worker count (0 = auto), **Use GPU for OCR** (with live
  availability hint).
- **Updates:** current version, manual check, automatic startup check toggle, and a
  permanent link to the GitHub repository for manual downloads.
- **External tools:** point to a specific LibreOffice or Ghostscript (both optional).

### 6.6 Help & legal

- In‑app **Help** (full how‑to for every tool, OCR, updates, shortcuts, troubleshooting).
- **About Us**, **Terms & Conditions**, **Privacy Policy** — all current, with contact
  `info@mico360.com`. The Privacy Policy discloses that the only network activity is the
  optional update check.

---

## 7. Auto‑update

- The app reads the repository's **latest GitHub Release** as the update manifest.
- A detailed **update screen** shows: app name, **current version → new version**,
  **download size**, **release date**, and the changes split into **New features / Bugs
  fixed / Security improvements**, plus a clear **status** (Available / Downloading /
  Installing / Completed / Failed), a **progress bar with % and time remaining**, a
  **restart notice**, an **error + Retry**, and a **direct GitHub repository link** for
  manual download.
- Downloads are **resumable** (survive slow/flaky connections) and **verified by SHA‑256**
  before installing.
- On Windows the installer upgrades in place and relaunches; on macOS the `.dmg` opens for
  drag‑install. After updating, a **confirmation** shows the installed version and time.
- Robust to restricted networks: if the GitHub API is rate‑limited or firewall‑blocked,
  the check **falls back to the releases Atom feed** so it still works.
- Fully optional — automatic checking can be turned off.

---

## 8. Non‑functional requirements

| Area | Requirement |
|---|---|
| **Privacy** | 100% local processing; no accounts, ads, tracking, or telemetry. Only the optional update check uses the network — no files or personal data are sent. |
| **Data safety** | Originals never modified; lossless modes verified content‑identical; deletions go to the Recycle Bin/Trash with confirmation. |
| **Performance** | Concurrent batch processing; GPU OCR (~5–9× faster than CPU on a discrete GPU); resumable downloads. |
| **Reliability** | Per‑file error isolation (one bad file never stops a batch); single‑instance; crash‑guarded startup. |
| **Compatibility** | Windows 10/11 and macOS; handles legacy Office formats via bundled LibreOffice. |
| **Security** | AES‑256 PDF passwords; SHA‑256 verification of updates; passwords never stored. |
| **Accessibility** | Keyboard navigation, scalable layout, light/dark/high‑contrast‑friendly themes. |

---

## 9. Quality assurance

- An automated test suite (40+ test files) covers every tool end‑to‑end through the real
  UI → engine → processor → output path, plus content‑integrity checks, queue behaviour,
  OCR (CPU and GPU), the updater, cross‑platform packaging, and responsive/DPI behaviour.
- The macOS application is built and smoke‑tested on every release via cloud CI.
- Each release runs the full suite before packaging.

---

## 10. Deliverables

1. Windows installer (`.exe`, Inno Setup) with bundled engines + a stable “Latest” copy.
2. macOS disk image (`.dmg`) for Apple Silicon + a stable “Latest” copy.
3. SHA‑256 checksums for every installer.
4. Published GitHub Release (the update manifest) with categorised release notes.
5. In‑app documentation (Help, About, Terms, Privacy).
6. Source code, build scripts, and the automated test suite.

---

## 11. Assumptions & constraints

- The installer bundles LibreOffice, which makes it large (~480 MB) and, consequently,
  auto‑updates download the full installer. (A future "on‑demand engine" option could
  reduce the installer to ~110 MB — see §12.)
- Setting a file's **Owner** requires running as administrator and a valid Windows account.
- GPU‑accelerated OCR uses **DirectML (Windows only)**; macOS OCR runs on CPU.
- Installers are currently **unsigned**, so first launch may show an "unknown
  publisher / unidentified developer" prompt.

---

## 12. Future enhancements (candidate roadmap)

- **On‑demand engine download** — ship a ~110 MB installer and fetch LibreOffice on first
  Office conversion (≈4× faster installs and auto‑updates).
- **Code signing / notarization** (Windows Authenticode + Apple notarization) to remove
  install warnings.
- **Delta updates** — download only what changed between versions.
- **New tools** — Batch Rename, Redact, visual page organiser (thumbnails), combine mixed
  inputs (images + PDFs + Office) into one PDF.
- **OCR** — multi‑language and table/layout recognition.
- **Job‑based tool grouping** and a command palette for faster navigation.

---

*© MICO360. MICO360 Doc Toolkit is provided as‑is; always keep backups of important files.
Bundles LibreOffice (MPL) and RapidOCR; uses Ghostscript (AGPL) when available.*
