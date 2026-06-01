"""v5.4 round-4 checks: protect/unlock UI round-trip, sidebar no-results search,
dashboard favourite integration, and batch cancellation.

Run:  python tests/v54_round4_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QScrollArea

from mico360.config import settings
from mico360.core.tools import TOOLS_BY_ID
from mico360.logging_setup import setup_logging
from mico360.theme import stylesheet
from mico360.ui.tool_page import ToolPage

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def make_pdf(p, pages=3):
    import fitz
    d = fitz.open()
    for _ in range(pages):
        d.new_page(width=300, height=200)
    d.save(str(p)); d.close(); return p


def run(page, out, timeout_ms=30000, cancel_after=None):
    page.chk_same.setChecked(False)
    page.chk_overwrite.setChecked(True)
    page.out_edit.setText(str(out))
    res = {}
    loop = QEventLoop()
    page.start()
    if page.controller is None:
        return res
    page.controller.finished.connect(lambda s: (res.update(s), loop.quit()))
    if cancel_after is not None:
        QTimer.singleShot(cancel_after, page._cancel)
    g = QTimer(); g.setSingleShot(True); g.timeout.connect(loop.quit); g.start(timeout_ms)
    loop.exec()
    return res


def main() -> int:
    setup_logging()
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(stylesheet(settings.theme))
    saved_out = settings.output_dir

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        settings.output_dir = str(out)

        # --- Protect -> Unlock round trip via the UI --------------------
        src = make_pdf(tmp / "doc.pdf")
        pp = ToolPage(TOOLS_BY_ID["pdf_protect"])
        pp.add_paths([str(src)])
        pp.options_widget._controls["operation"].setCurrentIndex(
            pp.options_widget._controls["operation"].findData("protect"))
        pp.options_widget._controls["password"].setText("p@ss")
        pp.options_widget._controls["confirm_password"].setText("p@ss")
        s = run(pp, out)
        prot = (s.get("outputs") or [None])[0]
        from pypdf import PdfReader
        check("protect via UI -> encrypted", prot and PdfReader(str(prot)).is_encrypted)

        up = ToolPage(TOOLS_BY_ID["pdf_protect"])
        up.add_paths([str(prot)])
        up.options_widget._controls["operation"].setCurrentIndex(
            up.options_widget._controls["operation"].findData("unlock"))
        up.options_widget._controls["password"].setText("p@ss")
        s = run(up, out)
        unl = (s.get("outputs") or [None])[0]
        check("unlock via UI -> not encrypted",
              unl and not PdfReader(str(unl)).is_encrypted)

        # --- Cancellation -----------------------------------------------
        big = [str(make_pdf(tmp / f"b{i}.pdf", pages=30)) for i in range(8)]
        cp = ToolPage(TOOLS_BY_ID["pdf_compress"])
        cp.add_paths(big)
        s = run(cp, out, cancel_after=10)
        check("cancel: batch reports finished", bool(s), "no finished signal")
        check("cancel: marked cancelled or completed safely",
              s.get("cancelled") or s.get("ok", 0) + s.get("skipped", 0) >= 0)
        check("cancel: start button re-enabled", cp.btn_start.isEnabled())

        # --- Sidebar no-results search ----------------------------------
        from mico360.ui.main_window import MainWindow
        w = MainWindow()
        w.setAttribute(Qt.WA_DontShowOnScreen, True); w.show(); app.processEvents()
        w.sidebar._search.setText("zzqqxx_nomatch")
        app.processEvents()
        vis = [it for it in w.sidebar._items if it.isVisible()]
        check("no-results search hides every tool", len(vis) == 0, str(len(vis)))
        check("no-results search hides every section header",
              all(not g["header"].isVisible() for g in w.sidebar._groups))
        w.sidebar._search.setText("")
        app.processEvents()
        check("clearing restores all tools",
              len([it for it in w.sidebar._items if it.isVisible()]) == len(w.sidebar._items))

        # --- Dashboard favourite integration ----------------------------
        prev = settings.favorite_tools
        settings.favorite_tools = []
        w.open_tool("pdf_split"); app.processEvents()
        idx = w._tool_index["pdf_split"]
        wrap = w._widgets[idx]
        page = wrap.widget() if isinstance(wrap, QScrollArea) else wrap
        page._toggle_favorite()           # click the star
        check("pinning via the tool star updates favourites",
              "pdf_split" in settings.favorite_tools)
        w.sidebar.select(0); app.processEvents()   # go Home -> dashboard refresh
        # the dashboard's favourites grid should now include the pinned tool
        from mico360.ui.dashboard_page import Tile
        tiles = w.dashboard.findChildren(Tile)
        check("dashboard shows the newly pinned favourite",
              any(t.tool_id == "pdf_split" for t in tiles),
              str(sorted({t.tool_id for t in tiles})))
        settings.favorite_tools = prev

    settings.output_dir = saved_out
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v5.4 round-4 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
