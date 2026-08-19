"""Dropdowns must LOOK like dropdowns.

Styling QComboBox::drop-down moves Qt onto the stylesheet path, where it stops
drawing the native arrow; a ::down-arrow rule with only a size then renders
nothing, so every combo box in the app looked like a plain text field. This
renders real combos with the real stylesheet and checks the arrow is actually
painted, in both themes.

Run:  python tests/combobox_arrow_test.py
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


def arrow_rows(app, combo):
    """Per-row widths of the mark painted in the drop-down zone. A chevron
    narrows row by row; a flat dash has a constant width."""
    combo.resize(260, 36)
    combo.show()
    app.processEvents()
    img = combo.grab().toImage()
    w, h = img.width(), img.height()
    bg = img.pixelColor(w // 2, h // 2)

    def differs(c):
        return (abs(c.red() - bg.red()) + abs(c.green() - bg.green())
                + abs(c.blue() - bg.blue())) > 40

    out = []
    for y in range(4, h - 4):
        n = sum(1 for x in range(w - 28, w - 2) if differs(img.pixelColor(x, y)))
        if n:
            out.append(n)
    return out


def arrow_pixel_count(app, combo) -> int:
    """Pixels in the drop-down zone that differ from the field background."""
    combo.resize(260, 36)
    combo.show()
    app.processEvents()
    img = combo.grab().toImage()
    w, h = img.width(), img.height()
    bg = img.pixelColor(w // 2, h // 2)

    def differs(c):
        return (abs(c.red() - bg.red()) + abs(c.green() - bg.green())
                + abs(c.blue() - bg.blue())) > 40

    return sum(1 for x in range(w - 26, w - 4) for y in range(6, h - 6)
               if differs(img.pixelColor(x, y)))


def main() -> int:
    from PySide6.QtWidgets import QApplication, QComboBox
    from mico360.theme import stylesheet
    app = QApplication.instance() or QApplication([])

    for theme in ("light", "dark"):
        app.setStyleSheet(stylesheet(theme))

        plain = QComboBox()
        plain.addItems(["qwen2.5:0.5b", "llama3.1:8b"])
        rows = arrow_rows(app, plain)
        check(f"{theme}: a dropdown shows a visible arrow", sum(rows) >= 10,
              f"{sum(rows)} px")
        check(f"{theme}: the arrow is a chevron, not a flat dash",
              len(rows) >= 3 and len(set(rows)) >= 3, str(rows))

        editable = QComboBox()
        editable.setEditable(True)
        editable.addItems(["qwen2.5:0.5b", "llama3.1:8b"])
        n = arrow_pixel_count(app, editable)
        check(f"{theme}: an EDITABLE dropdown shows a visible arrow too",
              n >= 10, f"{n} px")

        css = stylesheet(theme)
        # The fix is to leave these sub-controls alone so Qt paints its own
        # chevron; styling either one is what broke the arrow in the first place.
        active = "\n".join(l for l in css.splitlines()
                           if not l.strip().startswith("/*") and "*/" not in l)
        check(f"{theme}: the stylesheet doesn't suppress the native arrow",
              "QComboBox::down-arrow" not in active
              and "QComboBox::drop-down" not in active)

    # The real Settings AI model box is the one the user reported.
    from mico360.config import settings
    from mico360.ui.settings_page import SettingsPage
    app.setStyleSheet(stylesheet(settings.theme))
    sp = SettingsPage()
    check("Settings model field is a combo box",
          isinstance(sp.ai_model, QComboBox))
    n = arrow_pixel_count(app, sp.ai_model)
    check("Settings model field renders its dropdown arrow", n >= 10, f"{n} px")

    print()
    if failures:
        print(f"{len(failures)} arrow check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All dropdown-arrow checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    # Skip Qt's crash-prone offscreen teardown at interpreter shutdown
    # (a lingering C++ object can abort finalization with 0xC0000409,
    #  masking an otherwise-clean pass). Flush and exit with the result.
    import os as _os, sys as _sys
    _sys.stdout.flush(); _sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
