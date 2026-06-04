## MICO360 Doc Toolkit v6.0.0

**Display-ready everywhere — full multi-resolution, high-DPI and multi-monitor support.**

The app now adapts cleanly to any screen, scaling level, and window size:

- **Every resolution** — HD (1280×720), Full HD, QHD/2K, 4K UHD, 5K+, and
  ultrawide (21:9 / 32:9) panels.
- **Every Windows scaling setting** — 100 %, 125 %, 150 %, 175 %, 200 %, 250 %,
  300 %. Fractional scales now render the UI at its exact size (no shrinking or
  ballooning) thanks to an explicit *PassThrough* DPI rounding policy, with
  crisp text and graphics.
- **Opens fully on-screen, always** — the window is sized and centred to the
  monitor it opens on, so it never starts larger than a small or heavily-scaled
  display. The minimum size was lowered so it fits comfortably even at 250–300 %.
- **Multi-monitor** — opens on the monitor under your cursor, and when dragged to
  a smaller or differently-scaled monitor it shrinks to fit instead of spilling
  off-screen.
- **No clipping** — narrow or highly-scaled windows scroll their content rather
  than cutting it off, while the layout stays the same width as you switch tools.

Built on Qt's layout engine (docking / grids / flex-style rows), so panels,
forms, dialogs and the dashboard reflow to the available space at any size.

Everything from v5.7.x carries over: the consolidated **PDF → …**,
**Office → PDF**, and **Document → Markdown** converters, the OCR improvements,
and the lighter ~108 MB installer.

---
*This release is also the update manifest: the tag is the version, this text is the
release notes, and the attached Setup `.exe` (+ `.sha256`) is what the app installs.*
