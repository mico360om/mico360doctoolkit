"""End-to-end functional tests for v5.4 tools: drive real ToolPages (with their
generated option widgets) through the engine to completion, and verify outputs,
status, the toast signal and recent-file recording.

Run:  python tests/v54_functional_test.py
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

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLineEdit, QSpinBox

from mico360.config import settings
from mico360.core.tools import TOOLS_BY_ID
from mico360.logging_setup import setup_logging
from mico360.theme import stylesheet
from mico360.ui.tool_page import ToolPage

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _set(page: ToolPage, key: str, value) -> None:
    ctrl = page.options_widget._controls[key]
    if isinstance(ctrl, QComboBox):
        ctrl.setCurrentIndex(ctrl.findData(value))
    elif isinstance(ctrl, QSpinBox):
        ctrl.setValue(int(value))
    elif isinstance(ctrl, QCheckBox):
        ctrl.setChecked(bool(value))
    elif isinstance(ctrl, QLineEdit):
        ctrl.setText(str(value))


def run(page: ToolPage, out: Path, timeout_ms: int = 30000) -> dict:
    page.chk_same.setChecked(False)
    page.chk_overwrite.setChecked(True)
    page.out_edit.setText(str(out))
    result: dict = {}
    toasts: list = []
    page.toast.connect(lambda m, k: toasts.append((m, k)))
    loop = QEventLoop()

    def on_finished(summary):
        result.update(summary)
        result["_toasts"] = toasts
        loop.quit()

    page.start()
    assert page.controller is not None
    page.controller.finished.connect(on_finished)
    guard = QTimer(); guard.setSingleShot(True); guard.timeout.connect(loop.quit)
    guard.start(timeout_ms)
    loop.exec()
    return result


def _pdf(path: Path, pages: int) -> Path:
    import fitz
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=400, height=300)
        pg.insert_text((50, 80), f"PAGE {i + 1}", fontsize=24)
    doc.save(str(path)); doc.close()
    return path


def _img(path: Path, size=(800, 600)) -> Path:
    from PIL import Image
    Image.new("RGB", size, (90, 140, 200)).save(path)
    return path


def main() -> int:
    setup_logging()
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(stylesheet(settings.theme))
    saved_out = settings.output_dir

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        settings.output_dir = str(out)
        import fitz

        # --- Organize: rotate (combo + text options) --------------------
        p = ToolPage(TOOLS_BY_ID["pdf_organize"])
        p.add_paths([str(_pdf(tmp / "r.pdf", 3))])
        _set(p, "operation", "rotate"); _set(p, "angle", 90); _set(p, "pages", "1")
        s = run(p, out)
        check("rotate: run ok", s.get("ok") == 1 and s.get("failed") == 0, str(s.get("ok")))
        outp = (s.get("outputs") or [None])[0]
        d = fitz.open(str(outp)); check("rotate: page 1 = 90°", d[0].rotation == 90); d.close()
        check("rotate: status chip 'ok'", p.header_chip.property("chipState") == "ok")
        check("rotate: success toast emitted",
              any(k == "ok" for _, k in s.get("_toasts", [])), str(s.get("_toasts")))
        check("rotate: progress completed",
              p.progress.value() == p.progress.maximum() and p.progress.maximum() > 0)

        # --- Edit Metadata (text fields) --------------------------------
        p = ToolPage(TOOLS_BY_ID["pdf_metadata"])
        p.add_paths([str(_pdf(tmp / "m.pdf", 1))])
        _set(p, "title", "Hello"); _set(p, "author", "QA")
        s = run(p, out)
        from pypdf import PdfReader
        meta = PdfReader(str((s.get("outputs") or [None])[0])).metadata
        check("metadata: title applied via UI", (meta or {}).get("/Title") == "Hello")

        # --- Add Page Numbers (two combos) ------------------------------
        p = ToolPage(TOOLS_BY_ID["pdf_page_numbers"])
        p.add_paths([str(_pdf(tmp / "n.pdf", 4))])
        _set(p, "position", "bottom-center"); _set(p, "format", "n_of_total")
        s = run(p, out)
        d = fitz.open(str((s.get("outputs") or [None])[0]))
        check("page numbers: '1 / 4' stamped via UI", "1 / 4" in d[0].get_text()); d.close()

        # --- Resize Image (combo + spinbox + checkbox) ------------------
        p = ToolPage(TOOLS_BY_ID["image_resize"])
        p.add_paths([str(_img(tmp / "ph.png"))])
        _set(p, "mode", "dimensions"); _set(p, "width", 400); _set(p, "keep_aspect", True)
        s = run(p, out)
        from PIL import Image
        im = Image.open((s.get("outputs") or [None])[0])
        check("resize: 800x600 -> 400x300 via UI", im.size == (400, 300), str(im.size)); im.close()

        # --- Convert Image (format combo) -------------------------------
        p = ToolPage(TOOLS_BY_ID["image_convert"])
        p.add_paths([str(_img(tmp / "c.png"))])
        _set(p, "format", "jpg")
        s = run(p, out)
        check("convert: produced .jpg via UI",
              (s.get("outputs") or [None])[0].suffix.lower() == ".jpg")

        # --- recent files were recorded across these runs ---------------
        check("recent files recorded after runs", len(settings.recent_files) >= 1,
              str(len(settings.recent_files)))

    settings.output_dir = saved_out
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v5.4 functional checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
