"""SVG ⇄ image tools: rasterise SVG to PNG/JPG/WEBP, and image to SVG
(vector trace + exact embed).

Run:  python tests/svg_conversion_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures: list[str] = []
REP = lambda *_: None  # noqa: E731


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60">'
       '<rect width="100" height="60" fill="#A0201F"/>'
       '<circle cx="50" cy="30" r="20" fill="#ffffff"/></svg>')


def main() -> int:
    from PIL import Image

    from mico360.core import processors as P
    from mico360.core.tools import TOOLS_BY_ID

    check("svg_to_image tool registered", "svg_to_image" in TOOLS_BY_ID)
    check("image_to_svg tool registered", "image_to_svg" in TOOLS_BY_ID)

    td = Path(tempfile.mkdtemp(prefix="mico360_svg_"))
    out = td / "out"
    svg = td / "logo.svg"
    svg.write_text(SVG)
    opt = {"overwrite": True}

    # --- SVG -> image ---------------------------------------------------
    r = P.svg_to_image(svg, out, {**opt, "format": "png", "width": 400}, REP)
    check("SVG → PNG produced", r[0].exists() and r[0].suffix == ".png")
    with Image.open(r[0]) as im:
        check("PNG width honoured (400px)", im.width == 400, str(im.size))
        check("PNG keeps transparency (RGBA)", im.mode in ("RGBA", "P"), im.mode)

    r = P.svg_to_image(svg, out, {**opt, "format": "jpg", "width": 200}, REP)
    with Image.open(r[0]) as im:
        check("SVG → JPEG produced (no alpha, RGB)",
              r[0].suffix == ".jpg" and im.mode == "RGB" and im.width == 200,
              f"{r[0].suffix} {im.mode} {im.size}")

    r = P.svg_to_image(svg, out, {**opt, "format": "webp", "width": 0}, REP)
    with Image.open(r[0]) as im:
        check("SVG → WEBP at native size", r[0].suffix == ".webp" and im.width == 100,
              str(im.size))

    # --- image -> SVG (embed) -------------------------------------------
    png = td / "pic.png"
    Image.new("RGB", (80, 50), (20, 120, 200)).save(png)
    r = P.image_to_svg(png, out, {**opt, "mode": "embed"}, REP)
    txt = r[0].read_text(encoding="utf-8")
    check("Image → SVG (embed) is valid SVG", r[0].suffix == ".svg" and "<svg" in txt)
    check("embed SVG carries the raster as a data URI",
          "data:image" in txt and "base64," in txt)
    check("embed SVG keeps the image dimensions",
          'width="80"' in txt and 'height="50"' in txt)

    # --- image -> SVG (trace) -------------------------------------------
    # A flat two-colour image traces cleanly to vector paths.
    flat = td / "flat.png"
    im = Image.new("RGB", (120, 120), (255, 255, 255))
    for y in range(120):
        for x in range(120):
            if (x - 60) ** 2 + (y - 60) ** 2 < 35 ** 2:
                im.putpixel((x, y), (160, 32, 31))
    im.save(flat)
    r = P.image_to_svg(flat, out, {**opt, "mode": "trace", "colors": "color"}, REP)
    txt = r[0].read_text(encoding="utf-8")
    check("Image → SVG (trace) is valid SVG", r[0].suffix == ".svg" and "<svg" in txt)
    check("trace SVG contains real vector paths (not a data URI)",
          ("<path" in txt or "<polygon" in txt) and "data:image" not in txt,
          txt[:60])

    # --- round trip: SVG -> PNG -> readable -----------------------------
    r2 = P.svg_to_image(r[0], out, {**opt, "format": "png", "width": 120}, REP)
    with Image.open(r2[0]) as im2:
        check("traced SVG renders back to a 120px PNG", im2.width == 120, str(im2.size))

    import shutil
    shutil.rmtree(td, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All SVG conversion checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
