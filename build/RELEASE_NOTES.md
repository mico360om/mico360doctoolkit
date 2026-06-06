## MICO360 Doc Toolkit v6.5.1

**Queue polish & fixes.**

- **Readable right-click menu in Light mode.** The context menu could appear
  see-through / black on the light theme — it's now a proper opaque menu in both
  themes, with clearly-readable (and clearly-disabled) items.
- **No more stalls when resizing during a batch.** Status updates no longer
  rebuild the whole list or re-read every file on each completion, so the window
  stays responsive even if you resize it mid-run.
- **Long file names no longer cut off awkwardly.** Each row now shows a status
  dot, the file name (middle-trimmed so the extension stays visible), a size /
  message line, and a status label — with the full path on hover.
- **Clearer progress.** A taller progress bar with a percentage, an estimated
  time remaining, and a “Current: <file>” caption that always identifies the
  file being processed.
- **Live queue count** showing working / pending / done / failed at a glance.

---

## MICO360 Doc Toolkit v6.5.0

**A real file queue — more room, more control.**

The input panel is now a proper **queue** built for batches:

- **More space for your files.** The big drag-and-drop box is now a slim band, so
  the file list gets most of the panel — you can see far more files at once.
- **Clear status at a glance.** An empty queue reads **“0 files”**; a populated one
  shows the item count plus **pending / done / failed** totals and total size.
- **Toolbar controls:** **Add files**, **Remove selected**, **Remove finished**
  (clears done *and* failed), and **Clear all**.
- **Right-click any row** (works on multi-selection) for: **Open source folder**,
  **Open output folder**, **Move to top**, **Move to bottom**, **Duplicate row(s)**,
  **Retry failed/done row(s)**, **Remove from queue**, and **Delete from disk**
  (sent to the **Recycle Bin** after a confirmation — recoverable).
- **Drag to reorder**, multi-select, and **Del** to remove — selection and status
  stay consistent as you go. The same file can be queued more than once
  (Duplicate), each row tracked independently.

---

## MICO360 Doc Toolkit v6.4.0

**GPU-accelerated OCR — automatically uses your graphics card.**

Making scanned PDFs searchable (OCR) is the heaviest number-crunching this app
does, and it now runs on your **GPU** when you have one:

- **Automatic, on any GPU.** Uses **DirectML**, so it works on **any** modern
  graphics card — NVIDIA, AMD or Intel, laptop or desktop. The app detects the
  GPU **on whatever PC it's installed on** and uses it; no configuration.
- **Big speedup.** On a typical discrete GPU, OCR model inference runs **on the
  order of 5–9× faster** than CPU. The OCR progress line now tells you whether
  it's running on **GPU (DirectML)** or **CPU**.
- **Never breaks anything.** On a PC without a usable GPU it silently falls back
  to the CPU — same results, just slower. A new **Settings → Processing → "Use
  the GPU for OCR when available"** switch (on by default) lets you force CPU.
- **Safe under load.** GPU OCR processes pages in the correct order without the
  multi-threading that a GPU can't share, so bulk OCR is rock-solid.

> Only OCR benefits from the GPU — compression, conversion and image tools are
> CPU/codec work and already run in parallel across your CPU cores.

---

## MICO360 Doc Toolkit v6.3.0

**Office conversion now works on any PC — LibreOffice is built in.**

The Windows installer now **bundles the LibreOffice conversion engine**, so
**Word / Excel / PowerPoint → PDF**, **PDF → Office**, and **Document → Markdown**
work out of the box with **nothing else to install** — even on PCs without
Microsoft Office.

- **Legacy `.doc`, `.xls`, `.ppt`, `.rtf`, `.odt` now convert reliably.** Previously a
  legacy `.doc` (or a mis-named file) could fail on every engine; the bundled engine
  handles them all.
- **No more conversion stalls/crashes** from a flaky Microsoft Word automation path —
  the built-in engine is tried first and one bad file can never stop the batch.
- **Self-healing Markdown conversion:** a corrupt or mis-named `.docx` is automatically
  repaired through LibreOffice and retried instead of failing.

> The installer is larger because the conversion engine ships inside it — that's the
> price of "works everywhere with zero setup."

---

**Lossless compression with verified, zero-data-loss integrity.**

Compression now guarantees your file's **content and structure stay 100 % identical** —
nothing is removed, renamed or altered, only the file size goes down.

- **Lossless is the new default.** Compress strips redundant data and recompresses
  internal streams **without touching image data, text, fonts or layout**. The result
  is then **verified** byte-for-byte against the original — text, image bytes, fonts,
  links, metadata, bookmarks, embedded files **and** rendered pixels must all match.
  If even one thing would change, the **original is kept untouched** instead.
- **Strict integrity check.** A built-in verifier compares the output to the source and
  blocks any change with data loss. It reliably detects altered text, dropped pages, or
  modified images (proven by tamper tests).
- **Lossy levels still available** (Low / Medium / High / Target size) for maximum
  shrink on image-heavy PDFs — and even these are checked to preserve **all text,
  links, bookmarks and attachments**.
- **Images** get a lossless mode too — PNG / WebP / TIFF are re-packed and verified
  **pixel-identical**; formats that can't shrink losslessly keep the original.
- **Every other tool audited.** Merge, split, organize, watermark, page numbers,
  metadata, protect/unlock and sign were all tested to confirm they change **only**
  what they're meant to and never silently drop text or images.

> No setting to change — just compress. You'll see files that don't compress safely are
> returned unchanged rather than degraded.

---

## MICO360 Doc Toolkit v6.2.1

**macOS support — now with a correct cross-platform updater.**

MICO360 Doc Toolkit runs on **macOS** as well as Windows — same app, tools and UI:

- **macOS `.dmg`** — download, drag the app into Applications, done. Built for
  **Apple Silicon** (M1 / M2 / M3 and newer).
- **Native behaviour** — "Open output" reveals files in **Finder**, follows the
  macOS **light/dark** appearance, and finds **LibreOffice** in `/Applications`.

**Fix (vs 6.2.0):** the auto-updater now matches each download to **its own**
SHA-256 checksum. On a release that ships both a Windows `.exe` and a macOS
`.dmg`, the previous build could check a file against the *other* file's hash and
wrongly reject a valid update — now each OS verifies the correct installer.

> **Unsigned build:** on first launch, right-click the app → **Open** (or allow it
> in **System Settings → Privacy & Security**) to get past Gatekeeper's
> "unidentified developer" prompt.

Everything from v6.1.x (resumable, reconnect-on-slow update downloads; UI/UX
refresh) and v6.0.0 (multi-resolution / high-DPI, single-instance, crash guard)
carries over on both platforms.

---
*This release is also the update manifest: the tag is the version, this text is the
release notes, and the attached Setup `.exe` / `.dmg` (+ `.sha256`) is what the app
installs.*
