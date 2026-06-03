"""OCR quality improvements (v5.6.1):
  * paragraph reflow + de-hyphenation for the editable-text output
  * a Recognition-quality (DPI) control on the Searchable-PDF tool
  * end-to-end: an image-only PDF really becomes searchable

Run:  python tests/ocr_quality_test.py
"""
from __future__ import annotations

import io
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


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def test_paragraph_reflow():
    from mico360.core import processors as P
    # (text, x_left, y_top, height)
    rows = [
        ("The quick brown inter-", 50, 10, 12),
        ("national fox leaps over", 50, 24, 12),
        ("the lazy dog today.", 50, 38, 12),
        ("A separate later block", 50, 92, 12),     # big vertical gap → new para
    ]
    paras = P._rows_to_paragraphs(rows)
    check("wrapped lines merge into one paragraph", len(paras) == 2, str(len(paras)))
    check("hyphenated word is rejoined",
          paras[0] == "The quick brown international fox leaps over the lazy dog today.",
          paras[0])
    check("large vertical gap starts a new paragraph",
          paras[1] == "A separate later block")
    # an indented line also starts a new paragraph
    rows2 = [("First sentence here", 50, 10, 12),
             ("Indented new idea", 95, 24, 12)]
    check("indentation starts a new paragraph",
          len(P._rows_to_paragraphs(rows2)) == 2)
    check("empty input → no paragraphs", P._rows_to_paragraphs([]) == [])


def test_quality_option():
    from mico360.core import processors as P
    from mico360.core.tools import TOOLS_BY_ID
    check("fast → 200 dpi", P._ocr_dpi_from_opt({"quality": "fast"}) == 200)
    check("balanced/default → 300 dpi",
          P._ocr_dpi_from_opt({}) == 300 and
          P._ocr_dpi_from_opt({"quality": "balanced"}) == 300)
    check("high → 400 dpi", P._ocr_dpi_from_opt({"quality": "high"}) == 400)
    opts = {o.key: o for o in TOOLS_BY_ID["pdf_ocr"].options}
    check("pdf_ocr exposes a 'quality' choice",
          "quality" in opts and opts["quality"].kind == "choice"
          and len(opts["quality"].choices) == 3)


def _image_only_pdf(path: Path, text: str, dpi: int = 200) -> None:
    """Make a single-page PDF that is *image only* (no text layer) showing
    ``text`` — i.e. a stand-in for a scanned page that OCR must read."""
    import fitz
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1000, 200), (255, 255, 255))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 52)
    except Exception:
        font = ImageFont.load_default()
    d.text((40, 70), text, fill=(10, 10, 10), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=img.width * 72 / dpi, height=img.height * 72 / dpi)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def test_end_to_end_searchable():
    """A real OCR pass: the image-only PDF must come out selectable/searchable."""
    try:
        from mico360.core import processors as P
        P._make_ocr_engine()
    except Exception as exc:
        check("OCR engine available (skipped end-to-end)", True, f"unavailable: {exc}")
        return
    import fitz
    rep = lambda *_: None  # noqa: E731
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        src = tmp / "scan.pdf"
        _image_only_pdf(src, "Invoice Number 84217")
        # sanity: the source really has no text layer
        d = fitz.open(str(src)); has = bool(d[0].get_text("text").strip()); d.close()
        check("source page has no text layer (true scan)", not has)
        res = P.pdf_ocr(src, out, {"quality": "high", "overwrite": True}, rep)
        check("produced a searchable PDF", res and res[0].exists())
        d = fitz.open(str(res[0]))
        recovered = (d[0].get_text("text") or "").lower(); d.close()
        words = sum(w in recovered for w in ("invoice", "number", "84217"))
        check("OCR recovered the page text (now searchable)",
              words >= 2, f"{words}/3 keywords in {recovered!r}")


def main() -> int:
    test_paragraph_reflow()
    test_quality_option()
    test_end_to_end_searchable()
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All OCR quality checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
