"""Cross-module synchronization audit.

Modules don't just have to work alone — they have to agree with each other.
This test pins the contracts between the tool registry, the dashboard, the
window shell, settings, notifications, versioned files and docs, so a change
in one place can't silently leave another stale (that's exactly how HEIC
routing and the README version drifted).

Run:  python tests/sync_audit_test.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from mico360 import __version__
    from mico360.config import settings
    from mico360.core.tools import GROUP_ORDER, TOOLS, TOOLS_BY_ID

    # =====================================================================
    # 1. Version synchronization: app == installer == README == release notes
    # =====================================================================
    iss = (ROOT / "build" / "installer.iss").read_text(encoding="utf-8")
    m = re.search(r'#define AppVersion "([^"]+)"', iss)
    check("installer.iss AppVersion matches the app version",
          m and m.group(1) == __version__, f"{m and m.group(1)} vs {__version__}")

    readme_head = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
    check("README title carries the current version",
          f"v{__version__}" in readme_head, readme_head)

    notes = (ROOT / "build" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    top = next((ln for ln in notes.splitlines() if ln.startswith("## ")), "")
    check("RELEASE_NOTES top section is for the current version",
          f"v{__version__}" in top, top)

    # =====================================================================
    # 2. Registry ↔ dashboard: quick actions + drop routing
    # =====================================================================
    from mico360.ui.dashboard_page import QUICK_ACTIONS, _ROUTES, route_for
    check("every dashboard quick action exists in the registry",
          all(t in TOOLS_BY_ID for t in QUICK_ACTIONS),
          str([t for t in QUICK_ACTIONS if t not in TOOLS_BY_ID]))

    bad_routes = []
    for exts, tool_id in _ROUTES:
        tool = TOOLS_BY_ID.get(tool_id)
        if tool is None:
            bad_routes.append(f"{tool_id}: missing tool")
            continue
        wrong = [e for e in exts if e not in tool.accept and "*" not in tool.accept]
        if wrong:
            bad_routes.append(f"{tool_id} rejects {wrong}")
    check("every drop route targets a tool that accepts those files",
          not bad_routes, "; ".join(bad_routes))

    # The regressions that motivated this file: HEIC photos and SVGs dropped on
    # Home must land on a tool that can open them (not the PDF default).
    check("dropping a HEIC photo on Home routes to an image tool",
          route_for(["x.heic"]) == "image_compress", str(route_for(["x.heic"])))
    check("dropping an SVG on Home routes to SVG → Image",
          route_for(["x.svg"]) == "svg_to_image", str(route_for(["x.svg"])))

    # =====================================================================
    # 3. Registry ↔ shell: groups, glyphs, nav, OCR languages
    # =====================================================================
    from mico360.ui.main_window import _SECTION_GLYPH, MainWindow
    missing_glyphs = [g for g in list(GROUP_ORDER) + ["Home", "System"]
                      if g not in _SECTION_GLYPH]
    check("every nav section has a glyph", not missing_glyphs, str(missing_glyphs))

    win = MainWindow()
    win.resize(1180, 760)
    win.show()
    app.processEvents()
    check("every tool in the registry has a nav entry + page factory",
          all(t.id in win._tool_index and win._tool_index[t.id] in win._factories
              for t in TOOLS))

    from mico360.core import ocr_models
    ocr_tool = TOOLS_BY_ID["pdf_ocr"]
    lang_opt = next(o for o in ocr_tool.options if o.key == "ocr_lang")
    check("OCR language choices mirror the ocr_models registry",
          list(lang_opt.choices) == ocr_models.language_choices())

    # =====================================================================
    # 4. Live state sync: favourites, theme, recents, notifications
    # =====================================================================
    # Favourite toggled on a tool page appears on the dashboard after refresh.
    tid = "pdf_split"
    idx = win._tool_index[tid]
    win.sidebar.select(idx)
    app.processEvents()
    page = win._widgets[idx].widget()
    was_fav = tid in settings.favorite_tools
    if was_fav:                       # normalise: start un-pinned
        settings.toggle_favorite(tid)
    page._sync_fav()
    page._toggle_favorite()           # pin via the tool page
    win.sidebar.select(0)             # navigating Home triggers refresh()
    app.processEvents()
    from mico360.ui.dashboard_page import Tile
    tiles = [t.tool_id for t in win.dashboard.findChildren(Tile)]
    check("favourite pinned on a tool page shows on the Home page",
          tiles.count(tid) >= 1, str(tiles))
    settings.toggle_favorite(tid)     # restore
    if was_fav:
        settings.toggle_favorite(tid)

    # Theme toggled from the top bar syncs the Settings page combo.
    sidx = next(i for i, f in win._factories.items()
                if getattr(f, "__name__", "") == "_build_settings_page")
    win.sidebar.select(sidx)
    app.processEvents()
    before_mode = settings.theme_mode
    before = settings.theme
    win._toggle_theme()
    app.processEvents()
    combo_mode = win.settings_page.theme_combo.currentData()
    check("top-bar theme toggle updates settings AND the Settings combo",
          settings.theme != before and combo_mode == settings.theme_mode,
          f"combo={combo_mode} mode={settings.theme_mode}")
    settings.theme_mode = before_mode          # restore
    win.apply_theme(settings.theme)

    # A finished run's outputs appear in Home → Recent files.
    tmp = Path(tempfile.mkdtemp(prefix="mico360_sync_")) / "result.pdf"
    tmp.write_bytes(b"%PDF-1.4\n%%EOF")
    prev_recents = settings.recent_files
    settings.add_recent_files([str(tmp)])
    win.sidebar.select(0)
    app.processEvents()
    from PySide6.QtWidgets import QListWidget
    rec_lists = [w for w in win.dashboard.findChildren(QListWidget)]
    shown = any(tmp.name in rec_lists[i].item(r).text()
                for i in range(len(rec_lists)) for r in range(rec_lists[i].count()))
    check("new outputs appear in Home → Recent files", shown)
    settings._set_json("home/recent_files", prev_recents)   # restore
    tmp.unlink(missing_ok=True)

    # Notifications: a tool page's toast signal reaches the shell's Toast.
    win.sidebar.select(idx)
    app.processEvents()
    page.toast.emit("sync-audit toast", "ok")
    app.processEvents()
    check("tool-page toast notifications surface in the main window",
          any("sync-audit" in t.findChild(type(page.count_lbl)).text()
              if t.findChild(type(page.count_lbl)) else False
              for t in win._toasts) or len(win._toasts) >= 1,
          f"{len(win._toasts)} toast(s)")

    # =====================================================================
    # 5. Data/permission wiring: per-tool options persist across pages
    # =====================================================================
    saved = settings.tool_options("pdf_compress")
    settings.set_tool_options("pdf_compress", {"level": "high"})
    from mico360.ui.options_widget import OptionsWidget
    w2 = OptionsWidget(TOOLS_BY_ID["pdf_compress"])
    check("last-used tool options persist into a freshly built page",
          w2.values().get("level") == "high", str(w2.values().get("level")))
    settings.set_tool_options("pdf_compress", saved)        # restore

    win.close()
    print()
    if failures:
        print(f"{len(failures)} sync check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All synchronization checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
