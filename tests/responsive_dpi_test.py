"""v6 — display adaptability: high-DPI scaling, multi-resolution window fitting,
and no-clipping / stable-width layout across sizes.

Run:  python tests/responsive_dpi_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    # 1) High-DPI rounding policy must be PassThrough, set before the QApplication.
    from mico360.app import configure_high_dpi
    configure_high_dpi()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    check("high-DPI rounding policy = PassThrough (exact fractional scales)",
          QGuiApplication.highDpiScaleFactorRoundingPolicy()
          == Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 2) Window size fits every supported resolution × scaling combination.
    from mico360.ui.main_window import (MainWindow, fit_window_size,
                                        MIN_W, MIN_H, PREF_W, PREF_H)
    resolutions = [("HD", 1280, 720), ("FHD", 1920, 1080), ("QHD", 2560, 1440),
                   ("4K", 3840, 2160), ("5K", 5120, 2880),
                   ("UW21:9", 3440, 1440), ("UW32:9", 5120, 1440)]
    scales = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
    over = []
    for name, pw, ph in resolutions:
        for s in scales:
            lw, lh = int(pw / s), int(ph / s)      # logical screen size
            availh = lh - 48                        # rough taskbar allowance
            if lw < MIN_W or availh < MIN_H:
                continue                            # unrealistic tiny logical size
            w, h = fit_window_size(PREF_W, PREF_H, MIN_W, MIN_H, lw, availh)
            if w > lw or h > availh:
                over.append(f"{name}@{int(s*100)}%")
    check("window fits every realistic resolution × scaling combo",
          not over, f"overflow on: {over}")

    # 3) fit_window_size clamps correctly at the extremes.
    check("fit clamps DOWN to the screen",
          fit_window_size(PREF_W, PREF_H, MIN_W, MIN_H, 800, 600) == (800, 600))
    check("fit never exceeds preferred on a huge screen",
          fit_window_size(PREF_W, PREF_H, MIN_W, MIN_H, 9999, 9999) == (PREF_W, PREF_H))
    check("fit never drops below the minimum",
          fit_window_size(PREF_W, PREF_H, MIN_W, MIN_H, 300, 300) == (MIN_W, MIN_H))

    # 4) The window itself: small minimum + opens on-screen.
    win = MainWindow(); win.show()
    for _ in range(4):
        app.processEvents()
    check("minimum window size is small enough for scaled displays",
          (win.minimumWidth(), win.minimumHeight()) == (MIN_W, MIN_H),
          f"{win.minimumWidth()}x{win.minimumHeight()}")
    avail = win._current_screen().availableGeometry()
    check("opens within the available screen area",
          win.width() <= avail.width() and win.height() <= avail.height())

    # 5) Stable width: at a fixed comfortable size, every tool lays out to the
    #    same content width (no per-selection jump).
    win.resize(1180, 760)
    for _ in range(4):
        app.processEvents()
    widths = set()
    for tid in ("pdf_merge", "pdf_watermark", "to_markdown", "pdf_convert",
                "image_compress"):
        idx = win._tool_index.get(tid)
        win.sidebar.select(idx)
        for _ in range(4):
            app.processEvents()
        page = win._widgets[idx].widget()
        widths.add(page.minimumSizeHint().width())
    check("all tools share one layout width (no width jump)", len(widths) == 1, str(widths))

    # 6) No clipping at a narrow / heavily-scaled window: content scrolls
    #    horizontally instead of being cut off (as-needed H scrollbar).
    win.resize(560, 480)
    for _ in range(5):
        app.processEvents()
    idx = win._tool_index.get("pdf_watermark")
    win.sidebar.select(idx)
    for _ in range(5):
        app.processEvents()
    wrap = win._widgets[idx]
    page = wrap.widget()
    viewport_w = wrap.viewport().width()
    needs = page.minimumSizeHint().width() > viewport_w
    can_scroll_h = wrap.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    # Either it fits, or it can scroll — never clipped with the bar disabled.
    check("narrow window scrolls instead of clipping",
          (not needs) or can_scroll_h,
          f"needs_scroll={needs} h_policy_as_needed={can_scroll_h}")
    check("vertical scrollbar reserved (consistent width)",
          wrap.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOn)

    # 7) Multi-monitor: moving to a smaller screen shrinks the window to fit.
    class _FakeScreen:
        def __init__(self, w, h):
            from PySide6.QtCore import QRect
            self._r = QRect(0, 0, w, h)
        def availableGeometry(self):
            return self._r
    win.resize(1180, 760)
    win._on_screen_changed(_FakeScreen(900, 650))
    check("window shrinks when moved to a smaller monitor",
          win.width() <= 900 and win.height() <= 650,
          f"{win.width()}x{win.height()}")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All responsive / DPI checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
