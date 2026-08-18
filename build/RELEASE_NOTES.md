## MICO360 Doc Toolkit v6.9.6

**Dropdowns now look like dropdowns.**

- **Fixed: every dropdown in the app was drawn without its arrow**, so menus such as
  **Model**, **Use**, **Theme** and the tool options looked like plain text boxes and
  there was no sign you could open them. They now show the usual chevron and read
  clearly as dropdowns, in both light and dark themes.

---

## MICO360 Doc Toolkit v6.9.5

**Fixes the crash when testing an AI connection.**

- **Fixed: the app closed when you pressed "Test connection" in Settings -> AI and the
  test did not succeed.** The success case worked, but any failure (wrong URL, server
  unreachable, rejected key) hit an internal error while colouring the message and
  brought the app down - exactly when you needed to see what was wrong. The result is
  now shown properly in both light and dark themes, whatever the outcome.
- Messages coming back from an AI server are now displayed safely even if they contain
  special characters.

**Improved: pick your AI model from a list**
- **Model** in **Settings -> AI** is now a **dropdown** instead of a text box. Press
  **Refresh** and it fills with every model your API key is actually allowed to use, so
  you can just pick one instead of typing an id from memory.
- You can still **add** a model that isn't listed - type its id and save. **Remove**
  takes an entry out of your list (it is not deleted from the server).
- Your list is remembered, and a refresh against an unreachable server reports the
  problem instead of failing silently.

---

## MICO360 Doc Toolkit v6.9.4

**AI metadata suggestions, and rock-solid file import.**

**New: AI Metadata Generator**
- On the **Edit Metadata** page, click **Suggest with AI** and the app reads the selected
  document and proposes a **Title, Author, Subject, Keywords, Description, Category and
  Language**.
- **Nothing is applied until you say so.** Every suggestion appears in an editable box with
  its own **Apply**, plus **Apply all** and **Dismiss** - so you can accept, tweak, or ignore
  each field.

**New: Settings -> AI**
- Choose **System AI** (provided for you) or **My own AI API** - any OpenAI-compatible
  service. Set the API URL, key and model, and use **Test connection** to check it works.
- **Your API key is encrypted on your computer** and is never shown again after saving.
- AI is **off by default**. When you do use it, only a short excerpt of that one document is
  sent - never the whole file.

**Improved: file import never gives up**
- Importing a folder now streams through it instead of loading the whole tree first, skips
  folders it isn't allowed to read, and can't be tripped up by broken shortcuts, disconnected
  network drives or over-long names.
- The queue now **tells you what it skipped** ("12 unsupported file(s) skipped") instead of
  silently dropping files, and very large imports stop safely at a sensible limit.
- A corrupt, empty or damaged file is **flagged as failed with a clear reason** while every
  other file in the batch keeps processing.

**Bug fixes**
- Corrupt and password-protected PDFs now explain themselves instead of showing a technical
  error.
- PowerPoint text is now read from grouped shapes, tables and speaker notes too.
- An image-only Office file now gets advice you can actually follow (convert to PDF, then
  run OCR) instead of being pointed at a PDF-only tool.

---

## MICO360 Doc Toolkit v6.9.3

**Important fix: Searchable PDF (OCR) no longer crashes on multiple files.**

**Bug fixes**
- **Fixed the app closing unexpectedly during OCR.** Running **Searchable PDF (OCR)** on
  **more than one file at a time** could crash the app on PCs using GPU acceleration —
  two files were reading from the graphics card at the same moment, which isn't allowed.
  OCR work is now correctly serialised on the GPU. Single-file OCR, and OCR on CPU-only
  PCs, keep their full speed.
- **Corrupt or password-protected PDFs now give a clear message** ("this file is
  password-protected — remove the password first") instead of a technical error.
- **Queue sizes are always shown.** Duplicated rows showed "?" instead of their file
  size and were left out of the queue's total — both fixed.
- Dropping an **iPhone HEIC photo or an SVG** on the Home page now opens the right tool
  instead of reporting "no supported files".
- The Settings button that read "Terms _Conditions" now shows **Terms & Conditions**.

**Improvements**
- **Helpful tooltips throughout the app.** Every button, option, filter and status badge
  now explains what it does, what to type, any shortcut, and any warning — and the same
  text is available to screen readers.

---

## MICO360 Doc Toolkit v6.9.2

**macOS build fixes — feature-complete and installable.**

- **Fixed the macOS build so it matches Windows.** The Mac app was missing three things
  that had been added on Windows: the **Arabic OCR** dictionary, **HEIC** photo support,
  and **Image → SVG** tracing. All three now ship in the `.dmg`.
- **The Mac app is now ad-hoc code-signed**, which resolves the *"app is damaged / can't
  be opened"* error on Apple Silicon. On first launch you still clear Gatekeeper the normal
  way for an unsigned-developer app — **right-click → Open** (or run
  `xattr -dr com.apple.quarantine "/Applications/MICO360 Doc Toolkit.app"`).
- The macOS build now **self-verifies** in CI (it fails the build if any of those pieces
  are missing), so this can't silently regress again.

> Apple Silicon (M1/M2/M3+), macOS 11+. Intel Macs aren't supported by this build yet.

---

## MICO360 Doc Toolkit v6.9.1

**A complete metadata editor + easier error reporting.**

**Edit Metadata — now every field**
- The **Edit Metadata** tool now covers **every document property**, not just Title/
  Author/Subject/Keywords: **Creator, Producer, creation & modification dates**, custom
  properties (**Company, Manager, Category, Comments**), **Copyright** (written to XMP),
  document **Language** (accessibility), the **Trapped** flag, and a "show Title instead of
  file name in the window bar" option. Blank fields are left untouched.
- Add your **own custom properties** — one `Key = Value` per line (shown in Acrobat's
  Custom tab).
- A **Privacy** menu: **Scrub identifying info** (clears Author/Creator/Producer/Company/
  Manager/Comments and resets the dates, while keeping Title/Subject/Keywords), or
  **Remove all metadata** (also strips XMP) — ideal before sharing a file.

**Easier error reporting — straight to GitHub, still fully opt-in.**

- The opt-in crash reporter can now **open a pre-filled GitHub issue** for you (title, error
  and recent log already filled in) — you **review it and press Submit** yourself. Copy and
  email options remain. As always, **nothing is sent automatically**.
- Each crash now **bundles a copy of the most recent log** next to the saved report, so the
  full context is easy to attach.

> Why a pre-filled issue rather than instant submit? Auto-posting would mean shipping a
> GitHub token inside the app (which could be extracted and misused). The pre-filled form
> keeps you in control of exactly what's shared — no token, no surprises.

**Faster updates**
- The in-app updater now downloads in larger 1 MB blocks and, on a fast connection,
  **hunts for a faster download edge** if the one it landed on underperforms — so updates
  (and the one-time engine / OCR-language downloads) finish quicker. Resume-on-drop and
  checksum verification are unchanged.

---

## MICO360 Doc Toolkit v6.9.0

**A much smaller installer, Arabic OCR, queue thumbnails — and tools grouped the way you work.**

**Smaller installer & faster updates**
- **The installer is now ~135 MB instead of ~480 MB — less than a third the size.** The
  LibreOffice conversion engine is no longer bundled — it's **downloaded once,
  automatically**, the first time you convert an Office file (Office → PDF / Document →
  Markdown), into a folder that **survives app updates**. So you download the engine a
  single time, ever — and every future **auto-update is much smaller and faster**, with
  much less to install.
- **You're in control:** a new **Settings → External tools → Conversion engine** section
  shows the engine status, lets you **download it ahead of time**, and lets you turn the
  automatic download off (then it'll ask / you can install LibreOffice yourself).

> Note: if you already have LibreOffice installed, the app uses it and downloads nothing.

**New features**
- **Multi-language OCR — now reads Arabic.** The **Searchable PDF (OCR)** tool (and
  scanned-PDF → Word) has a new **Language** selector. English/Latin is built in; **Arabic**
  downloads a small model (~8 MB) once on first use, into a folder that survives updates.
  Right-to-left text is reconstructed in natural reading order. You can also pre-download
  languages in **Settings → Performance → OCR languages**.
- **Thumbnail preview in the queue** — selecting a file in the queue now shows a quick
  **preview** of it (PDF, image incl. HEIC, or SVG) so you can confirm you've got the right one.

**Improvements**
- **Tools are now grouped by what you're doing** — *Convert, Optimize, Edit, Organize,
  Secure, Recognize, Files* — instead of by file type, so the right tool is easier to find.
- **Crisper layout** — fixed a slight horizontal scrollbar that could appear at ~1100–1200 px
  window widths; pages now reflow cleanly at every size.
- **Privacy-respecting error reporting (opt-in).** If something ever goes wrong, the app
  saves a report **on your computer** and offers to copy or email it to us — **nothing is
  ever sent automatically**. Turn it off in **Settings → Updates**.

---

## MICO360 Doc Toolkit v6.8.0

**HEIC photos + smoother large-file compression.**

**New features**
- **HEIC / HEIF support** — **Convert Image** now opens **iPhone/Apple `.heic` photos**
  and converts them to PNG, JPEG, WEBP, TIFF or BMP (and can save HEIC too). HEIC is
  accepted across all image tools (compress, resize, watermark, Image → PDF, Image → SVG).

**Bug fixes**
- **Compression progress no longer "sticks" on large files.** The percentage now keeps
  moving through both the compression and the content‑verification steps, so big PDFs
  show real progress instead of appearing frozen.
- Verifying large PDFs is **much faster** (the heaviest per‑page check is skipped on big
  files — content safety is unchanged), and the status messages are clearer.
- The "Ghostscript not found" line was just informational (the app uses its built‑in
  compressor); it's been reworded so it no longer looks like an error.

---

## MICO360 Doc Toolkit v6.7.0

**SVG conversion, both ways.**

**New features**
- **SVG → Image** — rasterise `.svg` vector files to **PNG / JPEG / WEBP** at a
  chosen width (0 = the SVG's own size). PNG/WEBP keep transparency; JPEG is
  flattened onto a background.
- **Image → SVG** — **Trace** an image into real vector paths (best for logos &
  line art; full-colour or black & white), or **Embed** the image exactly inside an
  SVG (best for photos).

**Improvements**
- The **update screen** now spells out the **current version** and the **new
  version** clearly, and shows a **direct GitHub link** so you can always download
  the installer manually from the repository. The repository link is also available
  any time in **Settings → Updates**.

---

## MICO360 Doc Toolkit v6.6.0

**New tool, a detailed update experience, and refreshed Help & legal.**

**New features**
- **Edit File Properties** (new tool, under *System*): bulk-set **Date Created**,
  **Date Modified** and **Owner** on any files. Type a date (or *now*); blank keeps
  the current value. Your originals are never changed — a copy with the new
  properties is written to your output folder.
- **A complete, detailed update screen.** When an update is available you now see the
  app name, your current version → the new version, a clear **status** (Available /
  Downloading / Installing / Completed / Failed), the **download size**, **release
  date**, and what changed split into **New features / Bugs fixed / Security
  improvements** — with a live **progress bar showing percentage and time remaining**,
  a restart notice, and a **Retry** button if anything fails. After updating, a
  **confirmation** shows the installed version and time. No more vague "Updating…".

**Improvements**
- Refreshed **Help**, **About Us**, **Terms & Conditions** and **Privacy Policy** to
  match the latest features (file queue, GPU OCR, built-in LibreOffice, Windows +
  macOS), with consistent contact details (info@mico360.com). The Privacy Policy now
  clearly states the only network activity is the optional update check.

---

## MICO360 Doc Toolkit v6.5.2

**More reliable update checks.**

- **Fixes “Couldn’t check for update” on some PCs.** The check used only the
  GitHub API, which is rate-limited *per network address* (so on an office network
  where several PCs share one internet connection, some would hit the cap) and is
  blocked by some firewalls. It now automatically **falls back to a second source
  on github.com**, so the check succeeds even where the API is unavailable.

> Note: a PC that currently shows the error needs **one manual update** to this
> version (use “Open release page” and run the installer). After that, automatic
> updates keep working reliably.

---

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
