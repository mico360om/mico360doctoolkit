## MICO360 Doc Toolkit v6.3.0

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
