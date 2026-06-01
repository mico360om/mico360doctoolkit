## MICO360 Doc Toolkit v5.1.1

**Critical fix: the auto-update window.**

- Fixed a crash where checking for updates could show a blank window and close the
  app. The update check runs in the background, and its result (and the update
  dialog) now correctly run on the app's main thread.

> If you're on v5.0.0 or v5.1.0 and the in-app updater doesn't work, download and
> run this installer once from the releases page; auto-update works normally from
> v5.1.1 onward.

Also includes everything from v5.1: improved OCR for scanned PDFs (higher-resolution
recognition, low-confidence noise filtered out, text rebuilt in proper reading
order, engine loaded once for faster batches) and an expanded Help.

---
*This release is also the update manifest: the tag is the version, this text is the
release notes, and the attached Setup `.exe` (+ `.sha256`) is what the app installs.*
