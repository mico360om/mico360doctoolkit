# Performance, Stability & Resource Review — v6.0.0

Goal: reliable, lightweight operation on low-resource systems (4 GB RAM,
dual-core, older hardware, limited disk). This documents the review, the
measurements taken, and the optimizations/hardening implemented.

## Measurements (offscreen, dev machine — indicative)

| Metric | Result | Notes |
|--------|--------|-------|
| Cold startup (import app → window shown) | **~284 ms** | app import 129 ms + window module 80 ms + build/show 75 ms |
| Process memory after startup (RSS) | **~85 MB** | mostly the Qt + Python runtime; fine on 4 GB |
| Python heap at startup (tracemalloc) | **3.8 MB** | our own allocations are tiny |
| Heavy modules loaded at startup | **none** | `fitz`, `cv2`, `onnxruntime`, `rapidocr`, `pdf2docx`, `numpy` stay unloaded until first use |
| Pages built before navigation | **1 / 22** | only the dashboard; every other page is built on first visit |
| Endurance: 60 batch runs (multi-page PDF compress) | **1.4 s (23 ms/run)** | sustained throughput |
| Memory growth over 60 runs (leak check) | **+0.2 MB** | essentially flat — no leak; per-run thread pool is released |

## 1. Performance & resource optimization

- **Lazy imports** — heavy engines (PyMuPDF, OpenCV, onnxruntime/RapidOCR,
  pdf2docx, numpy) are imported *inside* the processor that needs them, so a
  user who only merges PDFs never pays the OCR/vision import cost. Verified: none
  of those modules are loaded at startup.
- **Lazy page building** — the sidebar registers a *factory* per page; pages are
  constructed on first visit (1 of 22 built at launch). Startup never builds 22
  pages or scans the disk for external tools.
- **Cached singletons** — the OCR engine (several ONNX models) is built once and
  reused across every page and file, not per call.
- **Bounded parallelism** — the batch engine sizes its thread pool to
  `max(2, cpu-1)` (so a dual-core uses both cores without oversubscription), and
  the configurable worker count lets users cap it further. Per-page OCR within a
  single file is chunked so memory stays bounded on large scans.
- **Smaller footprint** — the installer dropped ~60 MB of unused bundled binaries
  (OpenCV video codec, Qt software-OpenGL, AVIF codec, Pythonwin/MFC) → 108 MB,
  less disk + faster install/download.
- **Resource release** — each run owns its own `QThreadPool`; when the run
  finishes the controller reference is dropped and the pool (and its threads) are
  freed. Confirmed flat RSS across 60 runs. Toasts auto-dismiss; update threads
  are quit/joined after use.
- **Reduced UI churn** — the responsive row only relays out when it actually
  crosses the stack/side-by-side threshold; the vertical scrollbar is reserved so
  switching tools never triggers a relayout/width change.

## 2. Stability & hang prevention

- **No work on the UI thread** — all file conversion/compression/OCR runs in
  `QThreadPool` workers (`engine.py`); the UI thread only handles signals. The
  window stays responsive during heavy batches.
- **Cancellation** — workers poll a shared `threading.Event`; long processor
  loops check `report.cancelled()` and bail promptly, so nothing runs away.
- **Timeouts on every external/blocking call**
  - LibreOffice / Ghostscript subprocess: `run_subprocess(..., timeout=600)`.
  - Update check / download (network): `urlopen(timeout=20/30)`.
  - Office COM + LibreOffice are serialized behind a lock with a unique temp
    profile per call (prevents the single-instance LibreOffice deadlock).
- **Defensive exception handling** — every worker wraps the processor in
  `try/except ProcessError` and a catch-all `except Exception`, turning any
  failure into a per-file "failed" result (logged) instead of crashing the batch.
- **Global crash guard** — a `sys.excepthook` logs any uncaught exception and
  shows a friendly, non-fatal message instead of crashing to the desktop.
- **Disk/IO errors** — file operations surface `OSError` (incl. "disk full") as a
  clear `ProcessError` shown against the offending file; the rest of the batch
  continues.

## 3. Single instance

- Implemented in `mico360/single_instance.py` using `QLocalServer`/`QLocalSocket`
  (a Windows named pipe), keyed to a stable per-user name.
- A second launch **detects** the running instance, **pings** it to come to the
  foreground (`MainWindow.bring_to_front()` restores + raises + `SetForegroundWindow`),
  shows **"… is already running."**, and **exits** without opening a duplicate.
- Survives sleep/hibernation (the pipe lives with the first process) and frees
  the slot automatically when that process exits or crashes (OS releases the
  pipe; `removeServer()` clears any stale socket on claim).
- Covered by `tests/single_instance_test.py` (detection, activation delivery,
  reclaim-after-close).

## 4. System compatibility

- **Resolution / DPI** — multi-resolution + per-monitor high-DPI support with a
  PassThrough rounding policy; window clamps to and centres on its screen; layout
  scrolls instead of clipping. See `responsive_dpi_test.py`.
- **Low memory / high CPU** — bounded thread pool, chunked OCR, streamed
  downloads (256 KB chunks), and no startup pre-loading keep peak usage low.
- **Limited disk** — IO errors are caught and reported per-file, not fatal.

## 5. QA

- Automated suite (32 test files) run under `QT_QPA_PLATFORM=offscreen` with a
  per-test timeout to catch hangs.
- Profiling/endurance numbers above captured with `tracemalloc` + `psutil`.

## Risks / future opportunities

- **Installer size (108 MB)** is dominated by the OCR stack (OpenCV + onnxruntime
  + models ≈ 90 MB). Making OCR an optional first-use download would roughly
  halve the installer — a larger change, deferred.
- **High-contrast mode** — the app uses its own themed palette and does not yet
  mirror Windows High-Contrast mode (spec lists this as *preferred*, not
  required).
