"""Target file size can be typed in KB or MB (Compress Image / Compress PDF).

* The "Target size" row is a number plus a KB / MB unit picker.
* Whatever the unit, the tool still receives ``target_kb`` in whole KB, so the
  processors and saved settings work exactly as before.
* A saved size of 1 MB or more opens in MB ("2.50 MB", not "2560 KB").
* Switching the unit keeps the same size; flipping back and forth is lossless.
* Values are held to the option's minimum and maximum.

Run:  python tests/target_size_unit_test.py   (or via tests/run_suite.py)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if not os.environ.get("MICO360_SETTINGS_FILE"):
    os.environ["MICO360_SETTINGS_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="mico360_target_"), "DocToolkit.ini")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from mico360.config import settings
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.options_widget import OptionsWidget, _SizeField

    for tool_id in ("image_compress", "pdf_compress"):
        opt = next(o for o in TOOLS_BY_ID[tool_id].options if o.key == "target_kb")
        check(f"{tool_id}: target size is a KB/MB field", opt.kind == "size", opt.kind)

    settings.set_tool_options("image_compress", {})
    ow = OptionsWidget(TOOLS_BY_ID["image_compress"])
    sf = ow._controls["target_kb"]
    check("the control is a size field with a unit picker", isinstance(sf, _SizeField)
          and [sf.unit.itemText(i) for i in range(sf.unit.count())] == ["KB", "MB"])
    check("default 250 KB opens in KB", sf.unit.currentText() == "KB"
          and ow.values()["target_kb"] == 250, f"{sf.spin.value()} {sf.unit.currentText()}")

    # Type 2.5 MB -> the tool gets 2560 KB.
    sf.unit.setCurrentIndex(sf.unit.findText("MB"))
    sf.spin.setValue(2.5)
    check("2.5 MB is passed on as 2560 KB", ow.values()["target_kb"] == 2560,
          str(ow.values()["target_kb"]))

    # Switching units keeps the size, and a round trip loses nothing.
    sf.unit.setCurrentIndex(sf.unit.findText("KB"))
    check("switching to KB shows 2560 KB", sf.spin.value() == 2560
          and ow.values()["target_kb"] == 2560, str(sf.spin.value()))
    sf.spin.setValue(250)
    sf.unit.setCurrentIndex(sf.unit.findText("MB"))
    sf.unit.setCurrentIndex(sf.unit.findText("KB"))
    check("KB -> MB -> KB keeps 250 KB exactly", ow.values()["target_kb"] == 250,
          str(ow.values()["target_kb"]))

    # Saved as KB, reopened in MB when 1 MB or more.
    sf.unit.setCurrentIndex(sf.unit.findText("MB"))
    sf.spin.setValue(3)
    ow.save()
    check("the saved setting is plain KB", settings.tool_options("image_compress")
          .get("target_kb") == 3072, str(settings.tool_options("image_compress")))
    ow2 = OptionsWidget(TOOLS_BY_ID["image_compress"])
    sf2 = ow2._controls["target_kb"]
    check("a saved 3072 KB reopens as 3.00 MB", sf2.unit.currentText() == "MB"
          and abs(sf2.spin.value() - 3.0) < 1e-9 and ow2.values()["target_kb"] == 3072,
          f"{sf2.spin.value()} {sf2.unit.currentText()}")

    # Limits: the option's minimum and maximum still apply in either unit.
    sf2.spin.setValue(sf2.spin.maximum() + 100)
    check("the maximum (200000 KB) is enforced in MB",
          ow2.values()["target_kb"] <= 200000, str(ow2.values()["target_kb"]))
    sf2.set_kb(1)
    check("the minimum (5 KB) is enforced", ow2.values()["target_kb"] == 5,
          str(ow2.values()["target_kb"]))

    # An old saved value that isn't a number falls back to the default.
    settings.set_tool_options("pdf_compress", {"target_kb": "oops"})
    ow3 = OptionsWidget(TOOLS_BY_ID["pdf_compress"])
    check("a bad saved value falls back to 250 KB", ow3.values()["target_kb"] == 250,
          str(ow3.values()["target_kb"]))
    settings.set_tool_options("image_compress", {})
    settings.set_tool_options("pdf_compress", {})

    # Savings are worded, not signed: "+90%" used to read as if the file grew.
    from mico360.core.util import size_change
    cases = {(1000, 100): "90% smaller", (1000, 1040): "4% larger",
             (1000, 1000): "same size", (1000, 998): "same size", (0, 50): "same size"}
    bad = {k: size_change(*k) for k, v in cases.items() if size_change(*k) != v}
    check("size_change words savings and growth", not bad, str(bad))

    # A real target-size run logs "N% smaller" and lands under the target.
    import numpy as np
    from PIL import Image
    from mico360.core import processors as P
    work = Path(tempfile.mkdtemp(prefix="mico360_target_run_"))
    rng = np.random.default_rng(7)
    y, x = np.mgrid[0:1200, 0:1600]
    pix = np.stack([(x / 7) % 256, (y / 5) % 256, ((x + y) / 11) % 256], -1)
    pix = (pix + rng.normal(0, 20, pix.shape)).clip(0, 255).astype("uint8")
    src = work / "photo.png"
    Image.fromarray(pix).save(src)
    lines: list[str] = []

    class _Report:
        def __call__(self, msg, *a, **k):
            lines.append(str(msg))
        cancelled = staticmethod(lambda: False)

        def progress(self, *a):
            pass

    out = P.image_compress(src, work / "out", {"level": "target", "target_kb": 1024,
                                               "format": "keep", "max_dimension": 0,
                                               "quality": 65}, _Report())
    size = Path(out[0]).stat().st_size
    summary = next((ln for ln in lines if "→" in ln), "")
    check("a 1 MB target lands at or under 1 MB", size <= 1024 * 1024, f"{size / 1024:.0f} KB")
    check("the log says 'N% smaller', with no '+' sign",
          summary.endswith("% smaller)") and "(+" not in summary, summary)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Target size unit checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
