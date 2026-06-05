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
