## MICO360 Doc Toolkit v5.5.1

**Faster OCR, smaller download — same quality.**

- **Faster OCR on large scans** — a single scanned PDF now OCRs its pages **in
  parallel** (the recognised text is byte-for-byte identical; only the speed
  changes). A 12-page scan dropped from ~18s to ~7s (~2.4× faster). Batches of
  multiple files were already parallel.
- **Slimmer install / faster updates** — trimmed unused Qt components (QML/Quick,
  QtPdf, QtNetwork, Multimedia, Charts) and Qt translations from the bundle, so the
  installer and auto-update download are smaller, with no change in functionality.
- Hardened deep-testing pass (large concurrent batches, big multi-page PDFs,
  repeated runs) — all green.

Everything from v5.5.0: the design refresh (bold sidebar headings, consolidated
Organize PDF, Protect confirm/show-hide, Watermark position grid, Settings tabs),
plus the v5.4.x reliability fixes (Office conversions serialised, toast stacking).

---
*This release is also the update manifest: the tag is the version, this text is the
release notes, and the attached Setup `.exe` (+ `.sha256`) is what the app installs.*
