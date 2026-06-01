"""Tests for the v2 responsive shell: sidebar collapse thresholds, manual
toggle, theme-toggle sync, and the panel reflow (ResponsiveRow).

Run:  python tests/responsive_test.py   (offscreen; no GUI shown)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Nav glyphs are emoji; keep printing them from crashing the cp1252 console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from mico360.config import settings
from mico360.theme import stylesheet
from mico360.ui import main_window as MW
from mico360.ui.main_window import MainWindow

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(stylesheet(settings.theme))
    saved_theme = settings.theme

    w = MainWindow()
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.show()
    app.processEvents()

    # --- responsive sidebar -------------------------------------------
    w.resize(1300, 800)
    app.processEvents()
    check("wide window -> sidebar expanded", not w.sidebar.collapsed)

    w.resize(700, 800)              # below NARROW
    app.processEvents()
    check("narrow window -> sidebar auto-collapses", w.sidebar.collapsed)

    w.resize(1300, 800)             # back above WIDE
    app.processEvents()
    check("re-widen -> sidebar auto-expands", not w.sidebar.collapsed)

    # manual toggle pins the state (records the explicit choice)
    w._toggle_sidebar()
    app.processEvents()
    check("manual toggle collapses", w.sidebar.collapsed)
    check("manual collapse records a pin", w._pinned is True, str(w._pinned))

    # collapsed nav items hide their label text (icon only)
    first = w.sidebar._items[0]
    check("collapsed nav item is icon-only", "\n" not in first.text() and
          len(first.text().strip()) <= 3, repr(first.text()))

    # A pinned-expanded sidebar is restored after a narrow->wide cycle (H-1 fix)
    w._toggle_sidebar()                      # pin expanded
    check("manual expand pins expanded", w._pinned is False, str(w._pinned))
    w.resize(700, 800); app.processEvents()  # narrow -> collapses for space
    check("narrow collapses even when pinned-expanded", w.sidebar.collapsed)
    w.resize(1300, 800); app.processEvents() # wide -> restores the pin
    check("wide restores the pinned-expanded state", not w.sidebar.collapsed)
    w._pinned = None
    w.sidebar.set_collapsed(False)

    # --- theme toggle from the top bar --------------------------------
    # Build the Settings page first (it's lazy now) so the combo can be checked.
    settings_idx = next(i for i, t in w._titles.items() if t == "Settings")
    w.sidebar.select(settings_idx)
    app.processEvents()
    settings.theme = "dark"
    w.apply_theme("dark")
    w._toggle_theme()
    check("top-bar theme toggle flips theme", settings.theme == "light", settings.theme)
    check("settings combo synced to theme",
          w.settings_page is not None and
          w.settings_page.theme_combo.currentData() == "light",
          str(w.settings_page and w.settings_page.theme_combo.currentData()))
    check("theme glyph updates", w.btn_theme.text() in ("☀", "🌙"))

    # --- panel reflow (ResponsiveRow) ---------------------------------
    # The real page is built from a ResponsiveRow; test the reflow logic
    # deterministically by exercising one directly (resize sets the geometry,
    # the handler reads self.width()).
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent
    from PySide6.QtWidgets import QLabel
    from mico360.ui.widgets import ResponsiveRow

    tool_idx = min(w._tool_index.values())        # first actual tool page (Home is 0)
    w.sidebar.select(tool_idx); app.processEvents()
    cont = w._widgets[tool_idx]
    page = cont.widget() if isinstance(cont, QScrollArea) else cont
    check("tool page body is a ResponsiveRow", isinstance(page.body, ResponsiveRow))

    rr = ResponsiveRow(QLabel("a"), QLabel("b"), threshold=820)
    rr.resize(1000, 400)
    rr.resizeEvent(QResizeEvent(QSize(1000, 400), QSize(0, 0)))
    check("wide -> panels side by side", rr._horizontal is True, str(rr._horizontal))
    rr.resize(600, 400)
    rr.resizeEvent(QResizeEvent(QSize(600, 400), QSize(1000, 400)))
    check("narrow -> panels stacked", rr._horizontal is False, str(rr._horizontal))

    # thresholds are sane (narrow < wide)
    check("NARROW < WIDE thresholds", MW.NARROW < MW.WIDE, f"{MW.NARROW}/{MW.WIDE}")

    settings.theme = saved_theme
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All responsive checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
