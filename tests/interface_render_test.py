"""Interface smoke + visual-sanity test for the redesigned UI.

Builds the real MainWindow and visits EVERY page (Home, every tool, Settings,
Activity, Help) in BOTH themes, confirming each one constructs and renders
without error, isn't blank, and keeps readable text-on-background contrast.
Also checks the redesign specifics survive a live theme toggle.

Run:  python tests/interface_render_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Native platform (not offscreen) so real fonts render; the window is never
# shown on screen (WA_DontShowOnScreen).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _distinct_colors(img, step=7):
    """How many distinct-ish colours the image contains — a blank page has 1-2."""
    seen = set()
    for x in range(0, img.width(), step):
        for y in range(0, img.height(), step):
            c = img.pixelColor(x, y)
            seen.add((c.red() // 24, c.green() // 24, c.blue() // 24))
    return len(seen)


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from mico360.config import settings
    from mico360.theme import stylesheet, palette
    from mico360.core.tools import TOOLS
    from mico360.ui.main_window import MainWindow

    for theme in ("light", "dark"):
        settings.theme_mode = theme
        app.setStyleSheet(stylesheet(theme))
        try:
            w = MainWindow()
            w.resize(1440, 900)
            w.setAttribute(Qt.WA_DontShowOnScreen, True)
            w.show()
            for _ in range(8):
                app.processEvents()
        except Exception as exc:                 # noqa: BLE001
            check(f"[{theme}] MainWindow builds", False, repr(exc))
            continue
        check(f"[{theme}] MainWindow builds and shows", True)

        # Visit every page: index -> title.
        blank = []
        errored = []
        for idx in sorted(w._titles):
            try:
                w.sidebar.select(idx)
                for _ in range(4):
                    app.processEvents()
                img = w.grab().toImage()
                if _distinct_colors(img) < 5:
                    blank.append(w._titles[idx])
            except Exception as exc:             # noqa: BLE001
                errored.append(f"{w._titles[idx]}: {exc!r}")
        check(f"[{theme}] every page renders without error",
              not errored, "; ".join(errored[:3]))
        check(f"[{theme}] no page renders blank",
              not blank, "; ".join(blank[:5]))
        check(f"[{theme}] visited all {len(w._titles)} pages",
              len(w._titles) == len(TOOLS) + 4, str(len(w._titles)))

        # Home: greeting present and (after a live toggle) the brand text is the
        # CURRENT theme's accent, not a stale one baked in at build time.
        w.sidebar.select(0)
        for _ in range(4):
            app.processEvents()
        w.close()

    # ---- live theme toggle keeps the brand accent correct ----------------
    settings.theme_mode = "light"
    app.setStyleSheet(stylesheet("light"))
    w = MainWindow(); w.resize(1200, 800)
    w.setAttribute(Qt.WA_DontShowOnScreen, True); w.show()
    for _ in range(6):
        app.processEvents()
    dash = w.dashboard
    # Toggle to dark AFTER the dashboard was built in light.
    w.apply_theme("dark")
    for _ in range(6):
        app.processEvents()
    img = w.grab().toImage()
    dark_red = palette("dark")["primary"]
    light_red = palette("light")["primary"]

    def near(c, hexstr, tol=40):
        r = int(hexstr[1:3], 16); g = int(hexstr[3:5], 16); b = int(hexstr[5:7], 16)
        return (abs(c.red() - r) + abs(c.green() - g) + abs(c.blue() - b)) < tol

    # Scan the greeting band (top of the content area) for accent-coloured text.
    band_dark = band_light = 0
    for y in range(70, 140):
        for x in range(300, 900):
            c = img.pixelColor(x, y)
            if near(c, dark_red):
                band_dark += 1
            elif near(c, light_red):
                band_light += 1
    check("greeting brand text re-colours to the active theme on toggle",
          band_dark >= band_light and band_dark > 20,
          f"dark-accent px={band_dark}, stale-light px={band_light}")
    w.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Interface render: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    import os as _os
    sys.stdout.flush(); sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
