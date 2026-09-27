"""OCR keeps working after the first run (user report: "works only first time").

Covers the three things that made a second OCR look broken:
  * large text (headings, phone photos, 300/400 dpi renders) was split and
    mangled by the detector — now read at a size the model handles;
  * running OCR again on a PDF that already has a text layer silently did
    nothing — now a clear message, or "Redo OCR" replaces the old layer;
  * pressing Start / re-adding a finished file was a dead end — the row is
    queued to run again.
Uses the real OCR engine on generated scans.

Run:  python tests/ocr_rerun_test.py   (or via tests/run_suite.py)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if not os.environ.get("MICO360_SETTINGS_FILE"):
    os.environ["MICO360_SETTINGS_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="mico360_ocrre_"), "DocToolkit.ini")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


TD = Path(tempfile.mkdtemp(prefix="mico360_ocrre_files_"))


def scan(name: str, lines: list[str], px: int = 64, pages: int = 1) -> Path:
    import fitz
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", px)
    except Exception:
        font = ImageFont.load_default()
    doc = fitz.open()
    for pno in range(pages):
        im = Image.new("RGB", (1650, 2200), "white")
        d = ImageDraw.Draw(im)
        for k, t in enumerate(lines):
            d.text((120, 200 + k * int(px * 2.4)), t, fill="black", font=font)
        png = TD / f"{name}_{pno}.png"
        im.save(png)
        pg = doc.new_page(width=612, height=816)
        pg.insert_image(pg.rect, filename=str(png))
    p = TD / f"{name}.pdf"
    doc.save(str(p)); doc.close()
    return p


def text_of(p: Path) -> str:
    import fitz
    d = fitz.open(str(p))
    t = " ".join(pg.get_text() for pg in d)
    d.close()
    return " ".join(t.split())


def main() -> int:
    from mico360.core import processors as P
    from mico360.core.util import ProcessError
    quiet = lambda *a, **k: None

    # ---- large text at every quality ----------------------------------
    big = scan("big", ["RECEIPT page 1", "AMOUNT page 1"], px=64)
    for q in ("fast", "balanced", "high"):
        out = P.pdf_ocr(big, TD / f"q_{q}", {"quality": q, "overwrite": True}, quiet)[0]
        t = text_of(out)
        check(f"large text reads correctly at quality '{q}'",
              "RECEIPT page 1" in t and "AMOUNT page 1" in t, repr(t))
    small = scan("small", ["Invoice number 4471 dated 12 March"], px=34)
    t = text_of(P.pdf_ocr(small, TD / "small", {"overwrite": True}, quiet)[0])
    check("normal-size text still reads correctly", "4471" in t and "Invoice" in t, repr(t))

    # ---- several runs in a row ------------------------------------------
    docs = [scan("a", ["INVOICE page 1"]), scan("b", ["RECEIPT page 1"]),
            scan("c", ["CONTRACT page 1"])]
    want = ["INVOICE page 1", "RECEIPT page 1", "CONTRACT page 1"]
    seen = []
    for n, (d, w) in enumerate(list(zip(docs, want)) * 2, 1):
        t = text_of(P.pdf_ocr(d, TD / f"run{n}", {"overwrite": True}, quiet)[0])
        seen.append(w in t)
    check("six OCR runs in a row all read their text", all(seen), str(seen))

    # ---- OCR again on an already-OCR'd PDF ------------------------------
    first = P.pdf_ocr(docs[0], TD / "first", {"overwrite": True}, quiet)[0]
    try:
        P.pdf_ocr(first, TD / "again", {"overwrite": True}, quiet)
        check("OCR on an already-searchable PDF explains itself", False)
    except ProcessError as exc:
        check("OCR on an already-searchable PDF explains itself",
              "nothing to OCR" in str(exc) and "Redo OCR" in str(exc), str(exc)[:90])
    redo = P.pdf_ocr(first, TD / "redo", {"overwrite": True, "ocr_redo": True}, quiet)[0]
    t = text_of(redo)
    check("'Redo OCR' replaces the old layer (no doubled text)",
          t.count("INVOICE") == 1 and "INVOICE page 1" in t, repr(t))
    # real visible text is never removed by Redo
    import fitz
    digital = TD / "digital.pdf"
    d = fitz.open()
    d.new_page().insert_textbox(fitz.Rect(40, 40, 560, 780), "Real body text. " * 40,
                                fontsize=10)
    d.save(str(digital)); d.close()
    try:
        P.pdf_ocr(digital, TD / "digital_out", {"ocr_redo": True, "overwrite": True}, quiet)
        check("'Redo OCR' leaves real text pages alone", False, "no error raised")
    except ProcessError:
        d = fitz.open(str(digital))
        check("'Redo OCR' leaves real text pages alone",
              "Real body text" in d[0].get_text())
        d.close()

    # ---- the queue: re-adding a finished file runs it again -------------
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.tool_page import QueueItem, ToolPage
    page = ToolPage(TOOLS_BY_ID["pdf_ocr"])
    page.items = [QueueItem(path=docs[0], state="done", msg="→ a_searchable.pdf")]
    page._refresh_list()
    page.add_paths([docs[0]])
    check("re-adding a finished file queues it to run again",
          page.items[0].state == "pending" and len(page.items) == 1,
          f"{page.items[0].state} x{len(page.items)}")
    check("the log says it will run again",
          "run again" in page.log_view.toPlainText(), page.log_view.toPlainText()[-120:])
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("OCR re-run checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush()
    os._exit(_rc)
