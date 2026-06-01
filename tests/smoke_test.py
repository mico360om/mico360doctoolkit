"""Headless smoke test: imports + a few real processing operations.

Run:  python tests/smoke_test.py
Exits non-zero on any failure. Does not require a display for the processing
checks; it only imports the GUI modules (offscreen) without showing windows.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS, FAIL = "PASS", "FAIL"
failures: list[str] = []


def check(name: str, fn):
    try:
        fn()
        print(f"[{PASS}] {name}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{FAIL}] {name}: {exc!r}")
        failures.append(name)


# --- imports -------------------------------------------------------------
def t_imports():
    import fitz
    import pptx
    import pypdf
    from PIL import Image
    from mico360.core import engine, processors, tools
    from mico360.ui import main_window
    assert all([fitz, pypdf, pptx, Image, processors, tools, engine, main_window])


def _sample_pdf(path: Path, pages: int = 3) -> Path:
    import fitz
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"MICO360 sample page {i + 1}")
    doc.save(str(path))
    doc.close()
    return path


def _sample_image(path: Path) -> Path:
    from PIL import Image
    img = Image.new("RGB", (1200, 800), (160, 32, 31))
    for x in range(0, 1200, 4):
        for y in range(0, 800, 4):
            img.putpixel((x, y), ((x % 256), (y % 256), 128))
    img.save(path)
    return path


def main() -> int:
    check("imports", t_imports)

    from mico360.core import processors as P

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        out = tmp / "out"
        out.mkdir()
        rep = lambda m: None  # noqa: E731

        pdf = _sample_pdf(tmp / "doc.pdf")
        pdf2 = _sample_pdf(tmp / "doc2.pdf", 2)
        img = _sample_image(tmp / "pic.png")

        check("pdf_compress", lambda: _assert_files(
            P.pdf_compress(pdf, out, {"level": "medium"}, rep)))
        check("pdf_merge", lambda: _assert_files(
            P.pdf_merge([pdf, pdf2], out, {"output_name": "merged"}, rep)))
        check("pdf_split_each", lambda: _assert_files(
            P.pdf_split(pdf, out, {"mode": "each"}, rep), expected=3))
        check("pdf_split_ranges", lambda: _assert_files(
            P.pdf_split(pdf, out, {"mode": "ranges", "ranges": "1-2,3"}, rep), expected=2))
        check("pdf_to_pptx", lambda: _assert_files(
            P.pdf_to_pptx(pdf, out, {"dpi": 96}, rep)))
        check("pdf_to_image_png", lambda: _assert_files(
            P.pdf_to_image(pdf, out, {"format": "png", "dpi": 96}, rep), expected=3))
        check("pdf_to_image_tiff", lambda: _assert_files(
            P.pdf_to_image(pdf, out, {"format": "tiff", "dpi": 72}, rep), expected=3))
        check("pdf_to_image_webp", lambda: _assert_files(
            P.pdf_to_image(pdf, out, {"format": "webp", "dpi": 72}, rep), expected=3))
        check("pymupdf_compress_fallback", lambda: P._pymupdf_compress(
            pdf, out / "fallback.pdf", "high", {}, rep))
        check("image_to_pdf_combined", lambda: _assert_files(
            P.image_to_pdf([img], out, {"combine": True, "output_name": "imgs"}, rep)))
        check("image_compress", lambda: _assert_files(
            P.image_compress(img, out, {"level": "medium", "format": "jpg"}, rep)))
        check("pdf_to_word", lambda: _assert_files(
            P.pdf_to_word(pdf, out, {}, rep)))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All checks passed.")
    return 0


def _assert_files(result, expected: int | None = None):
    paths = list(result)
    assert paths, "no output produced"
    for p in paths:
        assert Path(p).exists(), f"missing output {p}"
        assert Path(p).stat().st_size > 0, f"empty output {p}"
    if expected is not None:
        assert len(paths) == expected, f"expected {expected} outputs, got {len(paths)}"


if __name__ == "__main__":
    raise SystemExit(main())
