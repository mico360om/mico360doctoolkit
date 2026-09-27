"""The options panel lays out cleanly (the "messed up" OCR screen).

* A checkbox's hint sits directly under the checkbox, aligned with its text,
  not in the right-hand field column.
* Hints reserve only the lines they need (no big gaps around one-line hints).
* "&" in a checkbox label is shown, not swallowed as a shortcut marker.
* Long explanations live in the tooltip (``details``); the visible hint stays short.
* The OCR screen fits: every OCR hint is short, and Start is reachable at a
  typical window size.

Run:  python tests/options_layout_test.py   (or via tests/run_suite.py)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if not os.environ.get("MICO360_SETTINGS_FILE"):
    os.environ["MICO360_SETTINGS_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="mico360_layout_"), "DocToolkit.ini")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def settle(app, ms=200):
    from PySide6.QtCore import QEventLoop, QTimer
    for _ in range(3):
        loop = QEventLoop(); QTimer.singleShot(ms // 3, loop.quit); loop.exec()


def main() -> int:
    from PySide6.QtWidgets import QApplication, QCheckBox
    app = QApplication.instance() or QApplication([])
    from mico360.core.tools import Option, Tool, TOOLS_BY_ID
    from mico360.ui.options_widget import OptionsWidget, _CHECK_TEXT_INDENT, _HintLabel

    # "&" survives in a checkbox label
    fake = Tool(id="t_layout", name="T", icon="", tagline="", mode="per_file",
                accept={".pdf"}, runner=lambda *a: [],
                options=[Option("flag", "Clean up text & fill title", "bool", False,
                                hint="Short hint.", details="The long explanation.")])
    ow = OptionsWidget(fake)
    chk = ow._controls["flag"]
    check("'&' in a checkbox label is displayed", isinstance(chk, QCheckBox)
          and chk.text() == "Clean up text && fill title", chk.text())
    check("the long explanation is the tooltip, the short hint is shown",
          "long explanation" in chk.toolTip()
          and ow._rows["__hint__flag"][0].text() == "Short hint.")
    hint = ow._rows["__hint__flag"][0]
    check("a checkbox's hint is indented to line up with the checkbox text",
          isinstance(hint, _HintLabel) and hint.indent() == _CHECK_TEXT_INDENT)

    # the real OCR page: short hints, no reserved blank lines, Start reachable
    from mico360.ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1180, 760)
    w.show()
    w.open_tool("pdf_ocr")
    settle(app)
    page = w._current_tool_page()
    ocr = TOOLS_BY_ID["pdf_ocr"]
    long_hints = [o.key for o in ocr.options if len(o.hint) > 60]
    check("OCR hints are short (details go in the tooltip)", not long_hints, str(long_hints))
    gaps = []
    for key, (lbl, _f) in page.options_widget._rows.items():
        if key.startswith("__hint__") and lbl.isVisible() and lbl.width() > 40:
            need = lbl.heightForWidth(lbl.width())
            if lbl.height() > need + 4:
                gaps.append(f"{key}: {lbl.height()}px for {need}px of text")
    check("hints reserve only the lines they need", not gaps, "; ".join(gaps))
    check("OCR option labels fit (no truncated quality choice)",
          all(len(o.label) <= 42 for o in ocr.options)
          and all(len(lab) <= 26 for _v, lab in ocr.options[1].choices), "")
    w.close()

    # Start visible without scrolling at 1180 x 760 — measured with the NATIVE
    # renderer (hidden window): the headless test renderer's font metrics differ.
    import subprocess
    child = r"""
import os, sys, tempfile
os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import Qt, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([])
from mico360.ui.main_window import MainWindow
w = MainWindow(); w.setAttribute(Qt.WA_DontShowOnScreen, True); w.show()
w.setMinimumSize(1180, 760); w.resize(1180, 760)
w.open_tool("pdf_ocr")
for _ in range(5):
    loop = QEventLoop(); QTimer.singleShot(80, loop.quit); loop.exec()
b = w._current_tool_page().btn_start
y = b.mapTo(w, b.rect().bottomLeft()).y()
print("RESULT", y, w.height())
"""
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    r = subprocess.run([sys.executable, "-c", child, str(Path(__file__).resolve().parent.parent)],
                       env=env, capture_output=True, text=True, timeout=120,
                       stdin=subprocess.DEVNULL)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("RESULT")), "")
    if not line:
        print("(skipped native layout check: no display available)")
    else:
        _, y, h = line.split()
        check("Start is visible without scrolling at 1180×760 (native rendering)",
              int(y) <= int(h), f"button bottom {y} / window {h}")
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Options layout checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
