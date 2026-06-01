"""Regression test: Low / Medium / High compression must actually differ.

Guards against the class of bug where the preset selector was ignored:
  * the PyMuPDF PDF fallback rebuilt losslessly regardless of level, and
  * image_compress always used the (hidden) custom quality spinbox value.

Both produced byte-identical output for every preset. Here we build genuinely
compressible inputs and assert a strict size gradient  high < medium < low.

Run:  python tests/compression_levels_test.py
Exits non-zero on failure. Runs entirely offscreen; exercises the built-in
PyMuPDF / Pillow paths (Ghostscript is not required and is intentionally not
used so the fallback itself is what gets tested).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []
rep = lambda m: None  # noqa: E731


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"[PASS] {name}")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}: {exc}")
        failures.append(name)


def _photo(path: Path, w: int = 1600, h: int = 1200) -> Path:
    """A smooth gradient compresses well with JPEG (unlike pure noise)."""
    from PIL import Image
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (x * 255 // w, y * 255 // h, (x + y) * 255 // (w + h))
    img.save(path, quality=95)
    return path


def _image_pdf(path: Path, photo: Path, pages: int = 3) -> Path:
    import fitz
    doc = fitz.open()
    for _ in range(pages):
        pg = doc.new_page(width=612, height=792)  # US Letter
        pg.insert_image(pg.rect, filename=str(photo))
    doc.save(str(path))
    doc.close()
    return path


def _sizes(fn) -> dict[str, int]:
    return {lvl: fn(lvl) for lvl in ("low", "medium", "high")}


def main() -> int:
    from mico360.core import deps
    from mico360.core import processors as P

    engine = "Ghostscript" if deps.find_ghostscript() else "PyMuPDF fallback"
    print(f"PDF compression engine in use: {engine}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        out = tmp / "out"
        out.mkdir()
        photo = _photo(tmp / "photo.jpg")
        pdf = _image_pdf(tmp / "img.pdf", photo)

        def compress_pdf(level: str) -> int:
            paths = P.pdf_compress(pdf, out, {"level": level, "overwrite": True}, rep)
            return paths[0].stat().st_size

        def compress_img(level: str) -> int:
            # Mimic the UI, which always passes the hidden quality spinbox value.
            paths = P.image_compress(
                photo, out,
                {"level": level, "quality": 65, "format": "jpg", "overwrite": True},
                rep,
            )
            return paths[0].stat().st_size

        def assert_gradient(label: str, sizes: dict[str, int]) -> None:
            lo, me, hi = sizes["low"], sizes["medium"], sizes["high"]
            assert lo > me > hi, f"{label} not monotonic: {sizes}"
            # And they must be meaningfully different, not just off-by-a-byte.
            assert (lo - hi) > lo * 0.10, f"{label} difference too small: {sizes}"

        check("pdf_compress levels differ (low>medium>high)",
              lambda: assert_gradient("pdf", _sizes(compress_pdf)))
        check("image_compress levels differ (low>medium>high)",
              lambda: assert_gradient("image", _sizes(compress_img)))

        # Custom must honour explicit dpi / quality.
        def custom_pdf(dpi: int, q: int) -> int:
            paths = P.pdf_compress(
                pdf, out,
                {"level": "custom", "dpi": dpi, "jpeg_quality": q, "overwrite": True},
                rep,
            )
            return paths[0].stat().st_size

        def assert_custom_responsive() -> None:
            big = custom_pdf(200, 90)   # high dpi, high quality -> larger
            small = custom_pdf(72, 30)  # low dpi, low quality   -> smaller
            assert big > small, f"custom not responsive to dpi/quality: {big} vs {small}"

        check("pdf_compress custom honours dpi/quality", assert_custom_responsive)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All compression-level checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
