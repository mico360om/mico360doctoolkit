"""v5.5 adversarial/edge tests: confirm-password paths, all 9 watermark
positions, posgrid persistence, password show/hide, settings tabs, and the
headless 'failed batch does not hang' guard.

Run:  python tests/v55_edge_test.py
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
from PySide6.QtWidgets import QApplication, QLineEdit

from mico360.config import settings
from mico360.core.tools import TOOLS_BY_ID
from mico360.logging_setup import setup_logging
from mico360.theme import stylesheet
from mico360.ui.tool_page import ToolPage

failures: list[str] = []
rep = lambda m: None  # noqa: E731


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def raises(fn):
    from mico360.core.processors import ProcessError
    try:
        fn(); return False
    except ProcessError:
        return True


def _pdf(p, pages=2, w=400, h=400):
    import fitz
    d = fitz.open()
    for _ in range(pages):
        d.new_page(width=w, height=h)
    d.save(str(p)); d.close(); return p


def _run(page, out, timeout_ms=20000):
    page.chk_same.setChecked(False)
    page.chk_overwrite.setChecked(True)
    page.out_edit.setText(str(out))
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
    from mico360.core import processors as P
    import fitz
    saved_out = settings.output_dir

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        settings.output_dir = str(out)
        src = _pdf(tmp / "doc.pdf", 2)
        o = {"overwrite": True}

        # --- confirm-password paths -------------------------------------
        check("protect: empty confirm -> mismatch error",
              raises(lambda: P.pdf_protect(src, out,
                     {**o, "operation": "protect", "password": "pw",
                      "confirm_password": ""}, rep)))
        check("protect: confirm None (not passed) -> allowed",
              not raises(lambda: P.pdf_protect(src, out,
                     {**o, "operation": "protect", "password": "pw"}, rep)))
        # unlock ignores confirm entirely
        rp = P.pdf_protect(src, out, {**o, "operation": "protect", "password": "pw",
                                      "confirm_password": "pw"}, rep)
        ru = P.pdf_protect(rp[0], out, {**o, "operation": "unlock", "password": "pw",
                                        "confirm_password": "ignored"}, rep)
        from pypdf import PdfReader
        check("unlock ignores confirm field", not PdfReader(str(ru[0])).is_encrypted)

        # --- all 9 watermark positions ----------------------------------
        big = _pdf(tmp / "big.pdf", 1, w=600, h=600)

        def place(position):
            r = P.pdf_watermark(big, out, {**o, "wm_type": "text", "text": "WM",
                                           "rotation": 0, "opacity": 90, "font_size": 20,
                                           "position": position}, rep)
            d = fitz.open(str(r[0]))
            ws = [w for w in d[0].get_text("words") if w[4] == "WM"]
            d.close()
            if not ws:
                return None
            x0, y0 = ws[0][0], ws[0][1]
            return x0, y0

        ok_all = True
        for pos, want in [("top-left", ("L", "T")), ("top-right", ("R", "T")),
                          ("bottom-left", ("L", "B")), ("bottom-right", ("R", "B")),
                          ("center", ("C", "M")), ("top-center", ("C", "T")),
                          ("bottom-center", ("C", "B")), ("middle-left", ("L", "M")),
                          ("middle-right", ("R", "M"))]:
            xy = place(pos)
            if xy is None:
                ok_all = False; continue
            x, y = xy
            hx = "L" if x < 200 else ("R" if x > 400 else "C")
            vy = "T" if y < 200 else ("B" if y > 400 else "M")
            if (hx, vy) != want:
                ok_all = False
                print(f"    position {pos}: got ({hx},{vy}) want {want} at ({x:.0f},{y:.0f})")
        check("watermark: all 9 positions place correctly", ok_all)

    # --- posgrid persistence ------------------------------------------
    from mico360.ui.options_widget import OptionsWidget, _PosGrid
    prev = settings.tool_options("pdf_watermark")
    ow = OptionsWidget(TOOLS_BY_ID["pdf_watermark"])
    ow._controls["position"]._buttons["bottom-right"].setChecked(True)
    ow.save()
    ow2 = OptionsWidget(TOOLS_BY_ID["pdf_watermark"])
    check("posgrid selection persists across rebuilds",
          isinstance(ow2._controls["position"], _PosGrid)
          and ow2._controls["position"].value() == "bottom-right",
          ow2._controls["position"].value())
    settings.set_tool_options("pdf_watermark", prev)

    # --- password show/hide toggle ------------------------------------
    from PySide6.QtWidgets import QPushButton
    op = OptionsWidget(TOOLS_BY_ID["pdf_protect"])
    pwd = op._controls["password"]
    holder = op._rows["password"][1]            # field = holder(line edit + eye)
    eye = holder.findChild(QPushButton)
    check("password starts hidden", pwd.echoMode() == QLineEdit.Password)
    eye.setChecked(True)
    check("eye toggle reveals password", pwd.echoMode() == QLineEdit.Normal)
    eye.setChecked(False)
    check("eye toggle hides again", pwd.echoMode() == QLineEdit.Password)

    # --- settings tabs --------------------------------------------------
    from mico360.ui.settings_page import SettingsPage
    from PySide6.QtWidgets import QTabWidget
    sp = SettingsPage()
    tabw = sp.findChild(QTabWidget)
    labels = [tabw.tabText(i) for i in range(tabw.count())]
    check("settings has 5 tabs",
          labels == ["General", "Processing", "Output", "Updates", "Advanced"], str(labels))
    check("theme combo still accessible after tab refactor",
          hasattr(sp, "theme_combo") and sp.theme_combo.count() == 3)

    # --- headless: a failing batch completes without hanging ------------
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "o"; out.mkdir()
        settings.output_dir = str(out)
        bad = _pdf(Path(td) / "b.pdf", 1)
        page = ToolPage(TOOLS_BY_ID["pdf_protect"])
        page.add_paths([str(bad)])
        c = page.options_widget._controls
        c["operation"].setCurrentIndex(c["operation"].findData("protect"))
        c["password"].setText("aaa")
        c["confirm_password"].setText("bbb")   # mismatch -> the unit fails
        s = _run(page, out)
        check("failing batch returns (no headless modal hang)", bool(s), "no finished")
        check("failing batch reports the failure", s.get("failed", 0) == 1,
              f"failed={s.get('failed')}")
        check("failing batch chip shows error",
              page.header_chip.property("chipState") == "err")

    settings.output_dir = saved_out
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v5.5 edge checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
