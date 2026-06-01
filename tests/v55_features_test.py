"""v5.5 tests: consolidated Organize PDF, Protect confirm-password + show/hide,
Watermark position grid, and the new password / posgrid option kinds.

Run:  python tests/v55_features_test.py
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


def _pdf(p, pages=4):
    import fitz
    d = fitz.open()
    for i in range(pages):
        pg = d.new_page(width=400, height=400)
        pg.insert_text((50, 60), f"PAGE {i + 1}", fontsize=18)
    d.save(str(p)); d.close(); return p


def main() -> int:
    from PySide6.QtWidgets import QApplication, QLineEdit
    if QApplication.instance() is None:
        QApplication([])
    from mico360.core import processors as P
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.options_widget import OptionsWidget, _PosGrid
    import fitz

    # --- consolidation: rotate/delete/extract are gone as separate tools --
    check("Rotate/Delete/Extract removed as separate tools",
          all(t not in TOOLS_BY_ID for t in ("pdf_rotate", "pdf_delete", "pdf_extract")))
    check("Organize PDF still present", "pdf_organize" in TOOLS_BY_ID)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        src = _pdf(tmp / "doc.pdf", 4)
        o = {"overwrite": True}

        # Organize covers all four operations
        r = P.pdf_organize(src, out, {**o, "operation": "rotate", "angle": 90, "pages": "1"}, rep)
        d = fitz.open(str(r[0])); check("organize rotate works", d[0].rotation == 90); d.close()
        r = P.pdf_organize(src, out, {**o, "operation": "delete", "del_pages": "2"}, rep)
        d = fitz.open(str(r[0])); check("organize delete works", d.page_count == 3); d.close()
        r = P.pdf_organize(src, out, {**o, "operation": "extract", "ext_pages": "3,1"}, rep)
        d = fitz.open(str(r[0])); check("organize extract works", d.page_count == 2); d.close()
        r = P.pdf_organize(src, out, {**o, "operation": "reorder", "order": "4,3,2,1"}, rep)
        d = fitz.open(str(r[0])); check("organize reorder works", d.page_count == 4); d.close()

        # --- Protect: confirm password ---------------------------------
        check("protect: mismatched confirm -> error",
              raises(lambda: P.pdf_protect(src, out,
                     {**o, "operation": "protect", "password": "abc",
                      "confirm_password": "xyz"}, rep)))
        r = P.pdf_protect(src, out, {**o, "operation": "protect",
                                     "password": "abc", "confirm_password": "abc"}, rep)
        from pypdf import PdfReader
        check("protect: matching confirm -> encrypted",
              PdfReader(str(r[0])).is_encrypted)

        # --- Watermark position ----------------------------------------
        def wm_y(position):
            rr = P.pdf_watermark(src, out, {**o, "wm_type": "text", "text": "WMARK",
                                            "rotation": 0, "opacity": 80, "font_size": 24,
                                            "position": position}, rep)
            doc = fitz.open(str(rr[0]))
            ys = [w[1] for w in doc[0].get_text("words") if w[4] == "WMARK"]
            doc.close()
            return min(ys) if ys else None
        top = wm_y("top-left")
        bot = wm_y("bottom-right")
        check("watermark top-left is near the top", top is not None and top < 150, str(top))
        check("watermark bottom-right is near the bottom", bot is not None and bot > 250, str(bot))
        check("position changes placement", top is not None and bot is not None and bot > top)

    # --- option widget: posgrid + password kinds -----------------------
    ow = OptionsWidget(TOOLS_BY_ID["pdf_watermark"])
    pg = ow._controls["position"]
    check("position control is a _PosGrid", isinstance(pg, _PosGrid))
    pg._buttons["top-right"].setChecked(True)
    check("posgrid reports selected value", ow.values().get("position") == "top-right")

    op = OptionsWidget(TOOLS_BY_ID["pdf_protect"])
    pwd = op._controls["password"]
    check("password control is a line edit", isinstance(pwd, QLineEdit))
    check("password echo is hidden by default", pwd.echoMode() == QLineEdit.Password)
    pwd.setText("  spaced pass  ")
    check("password is read verbatim (not stripped)",
          op.values().get("password") == "  spaced pass  ")
    op.save()
    from mico360.config import settings
    check("password is NOT persisted to settings",
          "password" not in settings.tool_options("pdf_protect"))

    # --- bold section heading present in stylesheet --------------------
    from mico360.theme import stylesheet
    css = stylesheet("dark")
    check("nav section heading is bold (800)", "font-weight: 800" in css)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v5.5 feature checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
