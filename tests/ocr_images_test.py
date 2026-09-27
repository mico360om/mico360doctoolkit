"""OCR accepts images and outputs a searchable PDF.

JPG (incl. a phone photo stored sideways with an EXIF rotation), PNG, a
multi-page TIFF and HEIC each become a PDF whose pages look like the image
and carry an invisible, searchable text layer. The tool page accepts images
and says so. Uses the real OCR engine on generated images.

Run:  python tests/ocr_images_test.py   (or via tests/run_suite.py)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if not os.environ.get("MICO360_SETTINGS_FILE"):
    os.environ["MICO360_SETTINGS_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="ocrimgtest_ini_"), "DocToolkit.ini")
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


# Not "mico360_ocrimg_…": that prefix is the app's own temp folder, which the
# "no temporary files left behind" check looks for.
TD = Path(tempfile.mkdtemp(prefix="ocrimgtest_files_"))


def _app_temp_dirs() -> set:
    import glob
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "mico360_ocrimg_*")))


APP_TEMP_BEFORE = _app_temp_dirs()


def page_image(text: str, size=(1275, 1650), px=48):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", px)
    except Exception:
        font = ImageFont.load_default()
    im = Image.new("RGB", size, "white")
    ImageDraw.Draw(im).text((100, 160), text, fill="black", font=font)
    return im


def pdf_text(p: Path) -> list[str]:
    import fitz
    d = fitz.open(str(p))
    t = [" ".join(pg.get_text().split()) for pg in d]
    d.close()
    return t


def main() -> int:
    from mico360.core import processors as P
    quiet = lambda *a, **k: None
    out = TD / "out"

    # PNG
    png = TD / "note.png"
    page_image("Delivery note 7731").save(png, dpi=(150, 150))
    o = P.pdf_ocr(png, out, {"overwrite": True}, quiet)[0]
    t = pdf_text(o)
    check("PNG → searchable PDF", o.suffix == ".pdf" and o.name == "note_searchable.pdf"
          and "Delivery note 7731" in t[0], f"{o.name} {t}")

    # JPG phone photo stored sideways + EXIF Orientation=6 → upright page
    jpg = TD / "phone.jpg"
    im = page_image("Receipt total 42.50").rotate(90, expand=True)   # stored landscape
    ex = im.getexif(); ex[0x0112] = 6                               # "rotate 90 CW to view"
    im.save(jpg, exif=ex.tobytes(), quality=92)
    o = P.pdf_ocr(jpg, out, {"overwrite": True}, quiet)[0]
    import fitz
    d = fitz.open(str(o)); r = d[0].rect; d.close()
    t = pdf_text(o)
    check("sideways phone photo becomes an upright (portrait) page", r.height > r.width, str(r))
    check("…and its text is read", "Receipt total 42.50" in t[0], str(t))

    # multi-page TIFF → one PDF page per frame
    tif = TD / "scan.tif"
    frames = [page_image(f"Page number {n}") for n in (1, 2, 3)]
    frames[0].save(tif, save_all=True, append_images=frames[1:], dpi=(150, 150))
    o = P.pdf_ocr(tif, out, {"overwrite": True}, quiet)[0]
    t = pdf_text(o)
    check("multi-page TIFF → one searchable page per frame",
          len(t) == 3 and all(f"Page number {n}" in t[n - 1] for n in (1, 2, 3)), str(t))

    # HEIC (iPhone)
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        heic = TD / "iphone.heic"
        page_image("Invoice 5520").save(heic, "HEIF", quality=90)
        o = P.pdf_ocr(heic, out, {"overwrite": True}, quiet)[0]
        check("HEIC → searchable PDF", "Invoice 5520" in pdf_text(o)[0], str(pdf_text(o)))
    except ImportError:
        print("(HEIC skipped: pillow-heif not installed)")

    # the page keeps the picture, and the text layer is invisible
    d = fitz.open(str(out / "note_searchable.pdf"))
    has_img = bool(d[0].get_images())
    invisible = all(s.get("type") == 3 for s in d[0].get_texttrace())
    d.close()
    check("the page shows the original image with an invisible text layer",
          has_img and invisible)

    # a damaged image gives a clear message, not a crash
    bad = TD / "broken.jpg"
    bad.write_bytes(b"not really a jpeg")
    from mico360.core.util import ProcessError
    try:
        P.pdf_ocr(bad, out, {"overwrite": True}, quiet)
        check("a damaged image gives a clear error", False)
    except ProcessError as exc:
        check("a damaged image gives a clear error", "broken.jpg" in str(exc), str(exc)[:80])
    leftover = _app_temp_dirs() - APP_TEMP_BEFORE
    check("no temporary files are left behind", not leftover, str(sorted(leftover))[:120])

    # a long line: every word, up to the last, is searchable (the text layer
    # used to run past the page edge and lose the line's final words)
    long_img = TD / "long_line.png"
    from PIL import Image, ImageDraw, ImageFont
    try:
        f11 = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 46)
    except Exception:
        f11 = ImageFont.load_default()
    im = Image.new("RGB", (2480, 3508), "white")
    line = "Dear Mr Rahman, thank you for your order number 48213 dated 14 March 2026. The total"
    ImageDraw.Draw(im).text((200, 300), line, fill="black", font=f11)
    im.save(long_img, dpi=(300, 300))
    o = P.pdf_ocr(long_img, out, {"overwrite": True}, quiet)[0]
    d = fitz.open(str(o))
    last_found = bool(d[0].search_for("total")) and bool(d[0].search_for("2026"))
    inside = all(d[0].rect.contains(fitz.Rect(s["bbox"])) or
                 fitz.Rect(s["bbox"]).x1 <= d[0].rect.x1 + 1
                 for s in d[0].get_texttrace())
    d.close()
    check("the last words of a long line are searchable", last_found)
    check("the invisible text stays inside the page", inside)

    # rotated scanned pages: the searchable text lines up with the printed words
    for rot in (90, 180, 270):
        base = page_image("Quarterly report for the Muscat office")
        stored = base.rotate(rot, expand=True)
        png_r = TD / f"rot{rot}.png"; stored.save(png_r)
        w_, h_ = stored.size
        dd = fitz.open(); pp = dd.new_page(width=w_ * 72 / 150, height=h_ * 72 / 150)
        pp.insert_image(pp.rect, filename=str(png_r)); pp.set_rotation(rot)
        src_r = TD / f"rot{rot}.pdf"; dd.save(str(src_r)); dd.close()
        o = P.pdf_ocr(src_r, out, {"overwrite": True}, quiet)[0]
        dd = fitz.open(str(o)); pp = dd[0]
        pix = pp.get_pixmap(dpi=72)
        ink = [(x, y) for y in range(0, pix.height, 2) for x in range(0, pix.width, 2)
               if pix.pixel(x, y)[0] < 100]
        hits = pp.search_for("Quarterly")
        ok = bool(ink and hits)
        if ok:
            ix0 = min(x for x, _ in ink); iy0 = min(y for _, y in ink); iy1 = max(y for _, y in ink)
            v = fitz.Rect(hits[0]) * pp.rotation_matrix
            vx0, vy0 = min(v.x0, v.x1), min(v.y0, v.y1)
            vx1, vy1 = max(v.x0, v.x1), max(v.y0, v.y1)
            ok = abs(vx0 - ix0) < 10 and vy0 < iy1 and vy1 > iy0 and (vx1 - vx0) > (vy1 - vy0)
        dd.close()
        check(f"on a {rot}° rotated page the searchable text sits on the printed words", ok)

    # the preview shows a phone photo upright (its rotation tag is honoured)
    # the tool page accepts images and says so
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.tool_page import ToolPage, drop_prompt
    tool = TOOLS_BY_ID["pdf_ocr"]
    check("OCR tool accepts PDFs and images",
          {".pdf", ".jpg", ".png", ".tif", ".heic"} <= tool.accept)
    title, fmts = drop_prompt(tool.accept)
    check("drop band says PDFs or images, with the formats",
          "PDFs or images" in title and "JPG" in fmts and "HEIC" in fmts, f"{title} | {fmts}")
    page = ToolPage(tool)
    thumb = page._thumbnail(jpg)
    check("the queue preview shows a sideways-stored phone photo upright",
          thumb is not None and thumb.height() > thumb.width(),
          f"{thumb.width()}x{thumb.height()}" if thumb is not None else "none")
    page.add_paths([png, tif, TD / "out"])
    names = sorted(it.path.name for it in page.items)
    check("images can be queued on the OCR page", "note.png" in names and "scan.tif" in names,
          str(names))
    from mico360 import shell_integration as si
    check("right-clicking an image offers OCR", "pdf_ocr" in si.ext_actions().get(".jpg", []))
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("OCR image checks passed.")
    return 0


if __name__ == "__main__":
    try:
        _rc = main()
    finally:
        import shutil
        shutil.rmtree(TD, ignore_errors=True)
    sys.stdout.flush()
    os._exit(_rc)
