"""Tooltips: every non-obvious control on every page explains itself, the
wording is consistent, and tooltips are accessible (screen-reader description
set) without obstructing the UI (word-wrapped, not screen-wide).

Run:  python tests/tooltips_test.py
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


def has_tip(w) -> bool:
    return bool(w.toolTip().strip())


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from mico360.core.tools import TOOLS
    from mico360.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1180, 760)
    win.show()
    app.processEvents()

    # --- helper contract: hover text wraps + screen readers get the text ----
    from PySide6.QtWidgets import QLabel
    from mico360.ui.widgets import tip
    probe = QLabel()
    tip(probe, "Explains <things> & wraps.")
    check("tip(): tooltip is rich-text so it word-wraps (no screen-wide line)",
          probe.toolTip().startswith("<qt>"))
    check("tip(): markup in the text is escaped", "&lt;things&gt;" in probe.toolTip())
    check("tip(): same text is exposed to screen readers",
          probe.accessibleDescription() == "Explains <things> & wraps.")

    # --- sidebar -------------------------------------------------------------
    sb = win.sidebar
    check("sidebar: search box has a tooltip + accessible name",
          has_tip(sb._search) and sb._search.accessibleName() != "")
    check("sidebar: every section header explains collapse/expand",
          all(has_tip(g["header"]) for g in sb._groups))
    tool_names = {t.name: t for t in TOOLS}
    expanded_ok = all(has_tip(it) for it in sb._items
                      if it._label in tool_names)  # tagline as tooltip
    check("sidebar (expanded): tool items carry their tagline", expanded_ok)
    sb.set_collapsed(True)
    app.processEvents()
    collapsed_ok = all(it._label.lower() in it.toolTip().lower() for it in sb._items)
    check("sidebar (icon-only): every item names itself in the tooltip", collapsed_ok)
    sb.set_collapsed(False)
    app.processEvents()

    # --- every tool page -------------------------------------------------------
    bad: list[str] = []
    for t in TOOLS:
        idx = win._tool_index[t.id]
        win.sidebar.select(idx)
        app.processEvents()
        page = win._widgets[idx].widget()
        controls = {
            "Add": page.btn_add, "Remove": page.btn_remove_sel,
            "Remove done": page.btn_remove_fin, "Clear": page.btn_clear,
            "Start": page.btn_start, "Open output": page.btn_open,
            "Cancel": page.btn_cancel, "Save beside": page.chk_same,
            "Overwrite": page.chk_overwrite, "Queue list": page.file_list,
            "Progress": page.progress, "Status chip": page.header_chip,
            "Favourite": page.btn_fav,
        }
        for label, w in controls.items():
            if not has_tip(w):
                bad.append(f"{t.id}:{label}")
        # Options: every option that has a hint exposes it on the control too.
        for opt in t.options:
            ctrl = page.options_widget._controls.get(opt.key)
            if ctrl is None:
                continue
            if ctrl.accessibleName() != opt.label:
                bad.append(f"{t.id}:{opt.key}:a11y-name")
            if opt.hint and not has_tip(ctrl):
                bad.append(f"{t.id}:{opt.key}:hint-tooltip")
        # Dynamic path tooltip must stay PLAIN text (exact-match contract).
        if page.out_edit.toolTip().startswith("<qt>"):
            bad.append(f"{t.id}:out_edit-must-stay-plain")
    check(f"tool pages ({len(TOOLS)}): queue/actions/output/options all covered",
          not bad, ", ".join(bad[:8]))

    # --- settings page ---------------------------------------------------------
    sidx = next(i for i, f in win._factories.items()
                if getattr(f, "__name__", "") == "_build_settings_page")
    win.sidebar.select(sidx)
    app.processEvents()
    sp = win.settings_page
    for name, w in {
        "theme combo": sp.theme_combo, "workers": sp.workers,
        "GPU OCR": sp.chk_gpu_ocr, "check updates": sp.btn_check,
        "auto update": sp.chk_auto_update, "crash reports": sp.chk_crash,
        "engine download": sp.btn_engine, "engine auto": sp.chk_auto_engine,
        "ocr lang combo": sp.ocr_lang_combo, "ocr lang download": sp.btn_ocr_lang,
        "gs path": sp.gs_edit, "lo path": sp.lo_edit,
    }.items():
        check(f"settings: {name} has a tooltip", has_tip(w))
    # Mnemonic fix: the ampersand shows literally (no "Terms _Conditions").
    from PySide6.QtWidgets import QPushButton
    terms = [b for b in sp.findChildren(QPushButton) if "Terms" in b.text()]
    check("settings: 'Terms & Conditions' shows a literal ampersand",
          terms and all("&&" in b.text() for b in terms),
          terms[0].text() if terms else "not found")

    # --- log page + dashboard ---------------------------------------------------
    lp = win.log_page
    lp_btns = [b for b in lp.findChildren(QPushButton)]
    check("activity log: its buttons explain themselves",
          lp_btns and all(has_tip(b) for b in lp_btns))

    win.sidebar.select(0)
    app.processEvents()
    dash = win.dashboard
    from mico360.ui.dashboard_page import Tile
    tiles = dash.findChildren(Tile)
    check("dashboard: every quick-action tile carries its tagline",
          tiles and all(has_tip(t) and t.accessibleName() for t in tiles))

    # --- update dialog ------------------------------------------------------------
    from mico360.ui.update_ui import UpdateDialog
    from mico360.updater import UpdateInfo
    dlg = UpdateDialog(UpdateInfo(version="9.9.9", url="https://x/s.exe",
                                  asset_name="s.exe", sha256=None, notes="- x",
                                  page="https://x", size=1, published_at=""))
    for name, w in {"install": dlg.btn_install, "later": dlg.btn_later,
                    "retry": dlg.btn_retry, "github": dlg.btn_page}.items():
        check(f"update dialog: {name} button has a tooltip", has_tip(w))

    win.close()
    print()
    if failures:
        print(f"{len(failures)} tooltip check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All tooltip checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    # Skip Qt's crash-prone offscreen teardown at interpreter shutdown
    # (a lingering C++ object can abort finalization with 0xC0000409,
    #  masking an otherwise-clean pass). Flush and exit with the result.
    import os as _os, sys as _sys
    _sys.stdout.flush(); _sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
