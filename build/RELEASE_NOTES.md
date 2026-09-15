## MICO360 Doc Toolkit v7.3.1

**A tune-up for macOS and low-memory machines.**

**Improvements**
- **macOS memory-aware performance** — the automatic "how many files at once"
  setting now reads the Mac's installed memory and eases off on machines with
  less RAM, the same way it already did on Windows, so large jobs (OCR, big PDFs,
  image batches) stay stable instead of thrashing.
- **Sturdier macOS packaging** — the visual page organizer is now explicitly
  bundled into the macOS app, and the macOS build additionally runs the page
  organizer, low-resource and packaging test suites before every release.

This is a maintenance release. Everything from v7.3.0 — the visual page
organizer (drag, rotate, delete, split) and the low-resource resilience work —
is included.

_Windows: the installer updates in place — your settings and favourites are kept.
macOS: open the `.dmg` and drag the app to Applications._
