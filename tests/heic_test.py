"""HEIC/HEIF (Apple photos) support: Convert Image reads .heic and converts it
to PNG/JPEG/WEBP (and can write HEIC), and the image tools accept .heic input.

Run:  python tests/heic_test.py
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


def main() -> int:
    from PIL import Image

    from mico360.core import processors as P
    from mico360.core.tools import IMAGES, TOOLS_BY_ID
    from mico360.ui.file_collector import collect_files

    # The tool + accept-sets recognise HEIC.
    check(".heic is an accepted image type (tools)", ".heic" in IMAGES)
    check("Convert Image offers HEIC output",
          any(v == "heic" for v, _ in TOOLS_BY_ID["image_convert"].options[0].choices))

    td = Path(tempfile.mkdtemp(prefix="mico360_heic_"))
    out = td / "out"
    o = {"overwrite": True}

    # Make a real .heic to work from.
    src = td / "photo.heic"
    try:
        Image.new("RGB", (240, 160), (160, 32, 31)).save(src, "HEIF")
    except Exception as exc:  # noqa: BLE001
        check("pillow-heif can write a .heic sample", False, str(exc))
        return 1
    check("created a .heic sample", src.exists() and src.stat().st_size > 0)

    # collect_files picks up the .heic.
    check("collect_files accepts a .heic file",
          collect_files([str(src)], IMAGES) == [src])

    # HEIC -> PNG
    r = P.image_convert(src, out, {**o, "format": "png"}, REP)
    check("HEIC → PNG produced a valid image",
          r[0].suffix == ".png" and r[0].exists())
    with Image.open(r[0]) as im:
        check("HEIC → PNG has the right size", im.size == (240, 160), str(im.size))

    # HEIC -> JPG
    r = P.image_convert(src, out, {**o, "format": "jpg", "quality": 85}, REP)
    with Image.open(r[0]) as im:
        check("HEIC → JPEG produced (RGB)",
              r[0].suffix == ".jpg" and im.mode == "RGB", f"{r[0].suffix} {im.mode}")

    # HEIC -> WEBP
    r = P.image_convert(src, out, {**o, "format": "webp"}, REP)
    check("HEIC → WEBP produced", r[0].suffix == ".webp" and r[0].exists())

    # PNG -> HEIC (write path)
    png = td / "pic.png"
    Image.new("RGB", (100, 80), (30, 120, 200)).save(png)
    r = P.image_convert(png, out, {**o, "format": "heic"}, REP)
    check("PNG → HEIC produced a valid .heic",
          r[0].suffix == ".heic" and r[0].exists())
    with Image.open(r[0]) as im:
        check("written HEIC re-opens with the right size", im.size == (100, 80))

    # Other image tools accept HEIC input too.
    r = P.image_resize(src, out, {**o, "mode": "percent", "percent": 50}, REP)
    check("Resize Image accepts a HEIC input", r and r[0].exists())
    r = P.image_compress(src, out, {**o, "level": "low", "format": "jpg"}, REP)
    check("Compress Image accepts a HEIC input", r and r[0].exists())

    import shutil
    shutil.rmtree(td, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} HEIC check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All HEIC checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
