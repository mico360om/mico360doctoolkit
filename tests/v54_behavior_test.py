"""v5.4 behavioural tests: multi-file batches, save-next-to-source for new
tools, file-option persistence, and window drop-routing.

Run:  python tests/v54_behavior_test.py
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

from PySide6.QtCore import QEventLoop, QMimeData, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDropEvent
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


def run(page, out=None, timeout_ms=30000):
    if out is not None:
        page.out_edit.setText(str(out))
    page.chk_overwrite.setChecked(True)
    res = {}
    loop = QEventLoop()
    page.start()
    if page.controller is None:
        return res
    page.controller.finished.connect(lambda s: (res.update(s), loop.quit()))
    g = QTimer(); g.setSingleShot(True); g.timeout.connect(loop.quit); g.start(timeout_ms)
    loop.exec()
    return res


def main() -> int:
    setup_logging()
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(stylesheet(settings.theme))
    saved_out = settings.output_dir
    saved_same = settings.same_as_source

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        settings.output_dir = str(out)

        # --- multi-file batch (Organize-rotate 3 PDFs -> 3 outputs) -----
        p = ToolPage(TOOLS_BY_ID["pdf_organize"])
        p.chk_same.setChecked(False)
        files = [str(make_pdf(tmp / f"r{i}.pdf")) for i in range(3)]
        p.add_paths(files)
        oc = p.options_widget._controls
        oc["operation"].setCurrentIndex(oc["operation"].findData("rotate"))
        oc["angle"].setCurrentIndex(oc["angle"].findData(90))
        s = run(p, out)
        check("multi-file: 3 PDFs -> 3 ok", s.get("ok") == 3 and s.get("failed") == 0,
              f"ok={s.get('ok')} failed={s.get('failed')}")
        check("multi-file: 3 outputs", len(s.get("outputs") or []) == 3,
              str(len(s.get("outputs") or [])))

        # --- save next to source (Add Page Numbers) ---------------------
        beside = tmp / "beside"; beside.mkdir()
        src = make_pdf(beside / "doc.pdf")
        original = src.read_bytes()
        p = ToolPage(TOOLS_BY_ID["pdf_page_numbers"])
        p.chk_same.setChecked(True)        # save next to source
        p.add_paths([str(src)])
        s = run(p)
        produced = (s.get("outputs") or [None])[0]
        check("save-next-to-source: numbered name beside source",
              produced and Path(produced).name == "doc (1).pdf"
              and Path(produced).parent == beside, str(produced))
        check("save-next-to-source: original untouched",
              src.read_bytes() == original)

        # --- file-option persistence (Watermark Image image_path) -------
        prev = settings.tool_options("image_watermark")
        wp = ToolPage(TOOLS_BY_ID["image_watermark"])
        wp.options_widget._controls["wm_type"].setCurrentIndex(
            wp.options_widget._controls["wm_type"].findData("image"))
        wp.options_widget._controls["image_path"].setText(r"C:\logo.png")
        wp.options_widget.save()
        # rebuild a fresh page -> the file path should be remembered
        wp2 = ToolPage(TOOLS_BY_ID["image_watermark"])
        check("file-option persisted across page rebuilds",
              wp2.options_widget._controls["image_path"].text() == r"C:\logo.png",
              wp2.options_widget._controls["image_path"].text())
        settings.set_tool_options("image_watermark", prev)

        # --- window drop routing ----------------------------------------
        from mico360.ui.main_window import MainWindow
        w = MainWindow()
        w.setAttribute(Qt.WA_DontShowOnScreen, True); w.show(); app.processEvents()

        def drop(paths):
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
            ev = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime,
                            Qt.LeftButton, Qt.NoModifier)
            w.dropEvent(ev)
            app.processEvents()

        def page_of(tid):
            idx = w._tool_index[tid]
            wrap = w._widgets.get(idx)
            return wrap.widget() if isinstance(wrap, QScrollArea) else wrap

        # On Merge PDF, dropping PDFs should add them to Merge (not jump away).
        w.open_tool("pdf_merge"); app.processEvents()
        merge_pdfs = [str(make_pdf(tmp / f"m{i}.pdf")) for i in range(2)]
        before = len(page_of("pdf_merge").files)
        drop(merge_pdfs)
        check("drop on compatible tool adds files there",
              len(page_of("pdf_merge").files) == before + 2,
              str(len(page_of("pdf_merge").files)))
        check("drop on compatible tool stays on that tool",
              w.stack.currentWidget() is w._widgets[w._tool_index["pdf_merge"]])

        # Dropping an image while on Merge (PDF-only) routes to image_compress.
        img = tmp / "pic.png"
        from PIL import Image
        Image.new("RGB", (40, 40), (1, 2, 3)).save(img)
        drop([str(img)])
        check("incompatible drop routes to a matching tool",
              w.stack.currentWidget() is w._widgets[w._tool_index["image_compress"]])
        check("routed drop preloads the file",
              len(page_of("image_compress").files) == 1)

    settings.output_dir = saved_out
    settings.same_as_source = saved_same
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v5.4 behavioural checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
