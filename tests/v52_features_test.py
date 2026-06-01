"""v5.2 feature tests: new PDF tools — Organize (rotate/delete/extract/reorder),
Protect/Unlock (password), Watermark — plus the page-spec parser and the
Merge drag-reorder sync.

Run:  python tests/v52_features_test.py
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


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _make_pdf(path: Path, pages: int) -> Path:
    import fitz
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=400, height=300)
        pg.insert_text((50, 80), f"PAGE {i + 1}", fontsize=28)
    doc.save(str(path))
    doc.close()
    return path


def _page_label(pdf_path: Path, index: int) -> str:
    import fitz
    doc = fitz.open(str(pdf_path))
    txt = doc[index].get_text("text").strip()
    doc.close()
    return txt


def main() -> int:
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication([])

    from mico360.core import processors as P
    from mico360.core.tools import TOOLS_BY_ID

    # --- registry wired up ----------------------------------------------
    for tid in ("pdf_organize", "pdf_protect", "pdf_watermark"):
        check(f"tool '{tid}' registered", tid in TOOLS_BY_ID)

    # --- page-spec parser -----------------------------------------------
    check("_page_list ordered + ranges", P._page_list("3,1,2-4", 10) == [2, 0, 1, 2, 3])
    check("_page_list clamps out-of-range", P._page_list("0,5,99", 5) == [4])
    check("_page_list reverse range", P._page_list("3-1", 5) == [2, 1, 0])
    check("_page_list all", P._page_list("all", 3, default_all=True) == [0, 1, 2])
    check("_page_list empty -> none", P._page_list("", 3) == [])

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        src = _make_pdf(tmp / "doc.pdf", 5)

        # --- Organize: delete pages 2 and 4 -> keep 1,3,5 ----------------
        r = P.pdf_organize(src, out, {"operation": "delete", "del_pages": "2,4",
                                      "overwrite": True}, rep)
        import fitz
        d = fitz.open(str(r[0])); npages = d.page_count; d.close()
        check("delete: 5 - 2 = 3 pages", npages == 3, str(npages))
        check("delete: first kept page is PAGE 1", _page_label(r[0], 0) == "PAGE 1")
        check("delete: second kept page is PAGE 3", _page_label(r[0], 1) == "PAGE 3")

        # --- Organize: reorder -> 3,1,2,4,5 ------------------------------
        r = P.pdf_organize(src, out, {"operation": "reorder", "order": "3,1,2,4,5",
                                      "overwrite": True}, rep)
        check("reorder: first page is PAGE 3", _page_label(r[0], 0) == "PAGE 3")
        check("reorder: second page is PAGE 1", _page_label(r[0], 1) == "PAGE 1")

        # --- Organize: extract only 5,1 ---------------------------------
        r = P.pdf_organize(src, out, {"operation": "extract", "ext_pages": "5,1",
                                      "overwrite": True}, rep)
        d = fitz.open(str(r[0])); n2 = d.page_count; d.close()
        check("extract: 2 pages", n2 == 2, str(n2))
        check("extract: order respected (5 then 1)",
              _page_label(r[0], 0) == "PAGE 5" and _page_label(r[0], 1) == "PAGE 1")

        # --- Organize: rotate page 1 by 90 ------------------------------
        r = P.pdf_organize(src, out, {"operation": "rotate", "angle": 90,
                                      "pages": "1", "overwrite": True}, rep)
        d = fitz.open(str(r[0])); rot = d[0].rotation; rot2 = d[1].rotation; d.close()
        check("rotate: page 1 rotated 90", rot == 90, str(rot))
        check("rotate: page 2 untouched", rot2 == 0, str(rot2))

        # --- Protect then Unlock ----------------------------------------
        rp = P.pdf_protect(src, out, {"operation": "protect", "password": "s3cret",
                                      "overwrite": True}, rep)
        from pypdf import PdfReader
        rd = PdfReader(str(rp[0]))
        check("protect: output is encrypted", rd.is_encrypted)
        # wrong password fails
        bad = False
        try:
            P.pdf_protect(rp[0], out, {"operation": "unlock", "password": "nope",
                                       "overwrite": True}, rep)
        except P.ProcessError:
            bad = True
        check("unlock: wrong password rejected", bad)
        # right password unlocks
        ru = P.pdf_protect(rp[0], out, {"operation": "unlock", "password": "s3cret",
                                        "overwrite": True}, rep)
        check("unlock: output not encrypted", not PdfReader(str(ru[0])).is_encrypted)

        # --- Watermark (text) -------------------------------------------
        rw = P.pdf_watermark(src, out, {"wm_type": "text", "text": "DRAFT",
                                        "opacity": 25, "font_size": 40,
                                        "rotation": 45, "color": "red",
                                        "overwrite": True}, rep)
        d = fitz.open(str(rw[0]))
        wm_text = "DRAFT" in d[0].get_text("text")
        same_pages = d.page_count == 5
        d.close()
        check("watermark text: present on page", wm_text)
        check("watermark text: page count preserved", same_pages)
        # empty watermark text is rejected
        empty = False
        try:
            P.pdf_watermark(src, out, {"wm_type": "text", "text": "  ",
                                       "overwrite": True}, rep)
        except P.ProcessError:
            empty = True
        check("watermark text: empty text rejected", empty)

        # --- Watermark (logo / image) -----------------------------------
        from PIL import Image
        logo = tmp / "logo.png"
        Image.new("RGBA", (200, 120), (200, 30, 30, 255)).save(logo)
        before_imgs = len(fitz.open(str(src))[0].get_images())
        ri = P.pdf_watermark(src, out, {"wm_type": "image",
                                        "image_path": str(logo), "opacity": 50,
                                        "scale": 35, "rotation": 30,
                                        "overwrite": True}, rep)
        d = fitz.open(str(ri[0]))
        after_imgs = len(d[0].get_images())
        n_pages = d.page_count
        d.close()
        check("watermark image: an image was added to the page",
              after_imgs > before_imgs, f"{before_imgs}->{after_imgs}")
        check("watermark image: page count preserved", n_pages == 5, str(n_pages))
        # missing / unset image path is rejected
        noimg = False
        try:
            P.pdf_watermark(src, out, {"wm_type": "image", "image_path": "",
                                       "overwrite": True}, rep)
        except P.ProcessError:
            noimg = True
        check("watermark image: missing image rejected", noimg)
        badpath = False
        try:
            P.pdf_watermark(src, out, {"wm_type": "image",
                                       "image_path": str(tmp / "nope.png"),
                                       "overwrite": True}, rep)
        except P.ProcessError:
            badpath = True
        check("watermark image: nonexistent path rejected", badpath)

    # --- options widget builds for new tools (unique keys, no clash) -----
    from mico360.ui.options_widget import OptionsWidget
    ow = OptionsWidget(TOOLS_BY_ID["pdf_organize"])
    keys = set(ow.values().keys())
    check("organize options have unique keys",
          {"operation", "angle", "pages", "del_pages", "ext_pages", "order"} <= keys,
          str(sorted(keys)))

    # --- watermark 'file' option kind builds & reads a path --------------
    from PySide6.QtWidgets import QLineEdit
    ow2 = OptionsWidget(TOOLS_BY_ID["pdf_watermark"])
    check("watermark has wm_type + image_path options",
          {"wm_type", "image_path", "scale"} <= set(ow2.values().keys()),
          str(sorted(ow2.values().keys())))
    ctrl = ow2._controls.get("image_path")
    check("image_path control is a readable line edit", isinstance(ctrl, QLineEdit))
    ctrl.setText(r"C:\logo.png")
    check("image_path value reads back", ow2.values().get("image_path") == r"C:\logo.png",
          repr(ow2.values().get("image_path")))

    # --- Merge drag-reorder sync ----------------------------------------
    from mico360.ui.tool_page import ToolPage
    from PySide6.QtCore import Qt
    page = ToolPage(TOOLS_BY_ID["pdf_merge"])
    a, b, c = Path("a.pdf"), Path("b.pdf"), Path("c.pdf")
    page.files = [a, b, c]
    page._refresh_list()
    # simulate a drag that moved row 0 (a) to the end: reorder the list items
    it = page.file_list.takeItem(0)
    page.file_list.addItem(it)
    page._sync_order_from_list()
    check("merge reorder syncs self.files", page.files == [b, c, a],
          str([p.name for p in page.files]))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v5.2 feature checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
