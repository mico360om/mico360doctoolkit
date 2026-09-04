## MICO360 Doc Toolkit v7.2.0

**A cleaner, sharper look — and a Mac that finally shows its icon.**

**New: a crisp, tintable icon set**
- The emoji tool icons are gone. Every tool, the sidebar, the dashboard tiles and the
  tool headers now use a hand-tuned **monochrome line-icon set** that renders sharply at
  any screen scale (Retina and high-DPI included) and takes the **brand red**.
- The same set now drives the favourite **star**, the password **show/hide (eye)**, the
  drag-and-drop zones, toast messages and the update dialog — one consistent, professional
  look instead of OS-dependent emoji.

**Improvements**
- **macOS app icon** — the Dock, Launchpad and app switcher now show the proper square
  MICO360 tile instead of a squashed word-mark. It also shows correctly when running from
  source. The build now produces a real `.icns`.
- **Faster "System" theme on macOS** — the app remembers the current system appearance for
  a moment instead of asking the OS on every repaint, so switching pages and theming icons
  is snappier.
- **Native-looking type on macOS** — text uses San Francisco / Helvetica Neue and code uses
  SF Mono / Menlo where available.
- **Sturdier macOS builds** — the macOS package now bundles the exact same icon and AI
  components as Windows, so nothing renders blank on a Mac. A build check keeps the two in
  step from now on.

**Fixes**
- Better diagnostics — several previously-silent internal error paths now write to the log,
  so real problems are easier to trace.
- Housekeeping across the build scripts and a new pre-release test gate that runs the core
  suites before anything is published.

_Windows: the installer updates in place — your settings and favourites are kept.
macOS: open the `.dmg` and drag the app to Applications._
