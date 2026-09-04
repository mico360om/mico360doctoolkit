"""Monochrome line-icon set: mapping, rendering, tinting, and theme/active
re-colouring in the real widgets (sidebar nav, dashboard tiles, tool header,
theme toggle). Verifies the emoji→SVG replacement works everywhere and doesn't
regress the nav/tiles.

Run:  python tests/icons_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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


def _opaque_pixels(pm) -> int:
    img = pm.toImage()
    n = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            if img.pixelColor(x, y).alpha() > 20:
                n += 1
    return n


def _avg_color(pm):
    img = pm.toImage()
    r = g = b = c = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            px = img.pixelColor(x, y)
            if px.alpha() > 20:
                r += px.red(); g += px.green(); b += px.blue(); c += 1
    c = c or 1
    return (r // c, g // c, b // c)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from mico360.ui import icons
    from mico360.core.tools import TOOLS, TOOLS_BY_ID

    # ================= mapping ====================================
    print("--- icon mapping ---")
    unmapped = [t.id for t in TOOLS if t.id not in icons.TOOL_ICON]
    check("every tool has an explicit icon mapping", not unmapped, str(unmapped))
    bad_shape = [(tid, nm) for tid, nm in icons.TOOL_ICON.items()
                 if nm not in icons._SHAPES]
    check("every mapped icon name is a real shape", not bad_shape, str(bad_shape))
    check("tool_icon_name falls back to 'file' for unknown ids",
          icons.tool_icon_name("nope") == "file")

    # ================= every shape renders ========================
    print("--- rendering ---")
    empty = [n for n in icons._SHAPES
             if _opaque_pixels(icons.pixmap(n, 24, "#E5323C", 1.0)) < 4]
    check("every icon renders visible strokes (no blank icons)",
          not empty, str(empty))
    pm = icons.pixmap("lock", 24, "#E5323C", 1.0)
    check("rendered pixmap has the requested size", pm.width() == 24, pm.width())

    # ================= tinting works ==============================
    print("--- tinting ---")
    red = _avg_color(icons.pixmap("lock", 32, "#E5323C", 1.0))
    white = _avg_color(icons.pixmap("lock", 32, "#FFFFFF", 1.0))
    check("icon takes the requested colour (red)",
          red[0] > 120 and red[0] > red[2] + 40, str(red))
    check("same icon renders white when asked", min(white) > 180, str(white))
    check("different colours produce different pixels", red != white)
    # cache returns the same object for the same key
    a = icons.pixmap("tag", 20, "#123456", 1.0)
    b = icons.pixmap("tag", 20, "#123456", 1.0)
    check("pixmaps are cached", a is b)

    # ================= IconLabel + theme_color ====================
    print("--- IconLabel ---")
    lbl = icons.IconLabel("droplet", 22, "primary")
    check("IconLabel builds and shows a pixmap",
          lbl.pixmap() is not None and not lbl.pixmap().isNull())
    check("IconLabel.refresh_icon exists (for theme re-tint)",
          callable(getattr(lbl, "refresh_icon", None)))
    from mico360.config import settings
    settings.theme_mode = "dark"
    c1 = icons.theme_color("primary")
    settings.theme_mode = "light"
    c2 = icons.theme_color("primary")
    check("theme_color changes with the theme", c1 != c2, f"{c1} vs {c2}")

    # ================= real widgets ===============================
    print("--- widgets (nav / tiles / header) ---")
    from mico360.theme import stylesheet
    settings.theme_mode = "dark"
    app.setStyleSheet(stylesheet("dark"))
    from mico360.ui.main_window import MainWindow
    from PySide6.QtCore import Qt
    w = MainWindow(); w.resize(1200, 800)
    w.setAttribute(Qt.WA_DontShowOnScreen, True); w.show()
    for _ in range(6):
        app.processEvents()

    # nav items carry an icon (not emoji text)
    navs = w.sidebar._items
    with_icon = [n for n in navs if getattr(n, "_icon_name", "")]
    check("all nav items have a line icon", len(with_icon) == len(navs),
          f"{len(with_icon)}/{len(navs)}")
    check("nav item shows the icon, not an emoji glyph in the text",
          all("🏠" not in n.text() and "⚙" not in n.text() for n in navs))

    # active nav icon is white; inactive is the muted nav colour
    home = navs[0]
    home.setChecked(True); home.refresh_icon()
    for _ in range(2):
        app.processEvents()
    check("active nav item icon is not empty", not home.icon().isNull())

    # dashboard tiles use IconLabel chips (not emoji)
    w.sidebar.select(0)
    for _ in range(4):
        app.processEvents()
    IL = icons.icon_label_type()
    check("IconLabel gives a single shared type (isinstance works)",
          isinstance(icons.IconLabel("file"), IL))
    from mico360.ui.dashboard_page import Tile
    tiles = w.dashboard.findChildren(Tile)
    tile_icons = [t.findChild(IL) for t in tiles]
    found = [ic for ic in tile_icons if ic is not None]
    check("dashboard tiles render an icon chip",
          bool(tiles) and len(found) == len(tiles)
          and all(not ic.pixmap().isNull() for ic in found),
          f"{len(found)}/{len(tiles)} tiles")

    # tool-page header icon matches the tool
    w.open_tool("pdf_protect")
    for _ in range(4):
        app.processEvents()
    tp = w._current_tool_page()
    hdr = tp.findChild(IL, "ToolIcon")
    check("tool header shows a (non-blank) icon",
          hdr is not None and not hdr.pixmap().isNull())

    # theme toggle recolours every icon without error
    try:
        w.apply_theme("light")
        for _ in range(4):
            app.processEvents()
        w.apply_theme("dark")
        for _ in range(4):
            app.processEvents()
        check("theme toggle re-tints icons without error", True)
    except Exception as exc:      # noqa: BLE001
        check("theme toggle re-tints icons without error", False, repr(exc))
    check("theme toggle button has an icon", not w.btn_theme.icon().isNull())

    # ================= glyph → icon migration (B-4) ===============
    print("--- remaining glyphs replaced ---")
    tp = w._current_tool_page()
    fav = tp.btn_fav
    check("favourite button is an icon button (no ★/☆ text)",
          fav.text() == "" and not fav.icon().isNull())
    was = "pdf_protect" in settings.favorite_tools
    img_off = fav.icon().pixmap(20, 20).toImage()
    settings.toggle_favorite("pdf_protect"); tp._sync_fav()
    img_on = fav.icon().pixmap(20, 20).toImage()
    check("favourite icon changes when pinned (outline → filled)", img_off != img_on)
    if ("pdf_protect" in settings.favorite_tools) != was:
        settings.toggle_favorite("pdf_protect"); tp._sync_fav()
    from PySide6.QtWidgets import QPushButton, QLabel, QListWidget
    eye = tp.options_widget.findChild(QPushButton, "EyeToggle")
    check("password eye is an icon button (no 👁 text)",
          eye is not None and eye.text() == "" and not eye.icon().isNull())
    if eye is not None:
        e0 = eye.icon().pixmap(18, 18).toImage()
        eye.setChecked(True)
        e1 = eye.icon().pixmap(18, 18).toImage()
        eye.setChecked(False)
        check("eye icon swaps while the password is revealed", e0 != e1)
    check("v55 contract kept: eye is still a checkable QPushButton",
          eye is not None and isinstance(eye, QPushButton) and eye.isCheckable())
    drops = [d for d in tp.findChildren(QLabel, "DropGlyph")]
    check("drop-zone glyphs are icon labels (no ⬇ text)",
          drops and all(d.text() == "" and d.pixmap() is not None
                        and not d.pixmap().isNull() for d in drops), f"{len(drops)}")
    from mico360.ui.widgets import Toast
    t = Toast(w, "Saved", "ok")
    t_text = t.findChild(QLabel, "ToastText")
    check("toast text carries no ✓/✗ glyph (icon label instead)",
          t_text is not None and t_text.text() == "Saved"
          and t.findChild(IL) is not None)
    t.close()
    # recent files list: icon + bare filename
    prev = settings.recent_files
    settings.add_recent_files([__file__])
    w.sidebar.select(0)
    for _ in range(3):
        app.processEvents()
    lists = w.dashboard.findChildren(QListWidget)
    items = [ls.item(r) for ls in lists for r in range(ls.count())]
    mine = [it for it in items if it.text() == Path(__file__).name]
    check("recent-file rows use an icon, not a 📄 prefix",
          mine and not mine[0].icon().isNull())
    settings._set_json("home/recent_files", prev)
    # update dialog + notes sections
    from mico360.ui import update_ui as uu
    sec = uu._notes_section("Bugs fixed", ["a", "b"], "bug")
    head = sec.findChild(QLabel, "UpdSectionHead")
    check("update-notes section header is icon + plain title",
          head is not None and head.text() == "Bugs fixed"
          and sec.findChild(IL) is not None)
    import re as _re
    # Real emoji plus the specific symbol glyphs the icon set replaced. Plain
    # text status marks (✓ ✗ ⚠ ↻ •) in log lines are fine and not matched.
    emoji = _re.compile("[\U0001F300-\U0001FAFF⭐⬆⬇★☆⚙☀]")
    src_files = ["widgets.py", "tool_page.py", "options_widget.py",
                 "dashboard_page.py", "update_ui.py", "main_window.py"]
    leftovers = []
    for fn in src_files:
        txt = (Path(icons.__file__).parent / fn).read_text(encoding="utf-8")
        for i, line in enumerate(txt.splitlines(), 1):
            if emoji.search(line) and "☰" not in line:
                leftovers.append(f"{fn}:{i}")
    check("no emoji/symbol icon glyphs left in the migrated UI modules",
          not leftovers, str(leftovers[:6]))

    # ================= system-theme cache (B-2) ===================
    print("--- system theme cache ---")
    import mico360.theme as theme_mod
    calls = {"n": 0}
    orig = theme_mod._read_system_theme

    def counting():
        calls["n"] += 1
        return "dark"
    theme_mod._read_system_theme = counting
    theme_mod.invalidate_system_theme_cache()
    for _ in range(40):
        theme_mod.system_theme()
    theme_mod._read_system_theme = orig
    theme_mod.invalidate_system_theme_cache()
    check("40 system-theme reads hit the OS once (cached)", calls["n"] == 1,
          str(calls["n"]))

    # ================= square app icon (B-1) ======================
    print("--- app icon ---")
    from mico360.paths import resource_path
    from PySide6.QtGui import QImage
    png = resource_path("app.png")
    img = QImage(str(png)) if png.exists() else QImage()
    check("app.png exists and is square", not img.isNull() and img.width() == img.height()
          and img.width() >= 256, f"{img.width()}x{img.height()}")
    check("main window icon is set", not w.windowIcon().isNull())
    check("app.icns exists for the macOS bundle", resource_path("app.icns").exists())
    w.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Icons: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(_rc if isinstance(_rc, int) else 0)
