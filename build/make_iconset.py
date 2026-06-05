"""Generate a macOS .iconset folder (PNG sizes) from the app icon master.

Cross-platform (pure PIL). On a macOS build runner, follow up with:
    iconutil -c icns build/MICO360.iconset -o mico360/resources/app.icns

Run:  python build/make_iconset.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_icon import build_master   # noqa: E402  (square maroon "360" master)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "MICO360.iconset"


def main() -> None:
    from PIL import Image
    master = build_master()                       # 1024×1024 RGBA
    OUT.mkdir(parents=True, exist_ok=True)
    # macOS expects these exact names (base size + @2x retina variant).
    for base in (16, 32, 128, 256, 512):
        master.resize((base, base), Image.LANCZOS).save(OUT / f"icon_{base}x{base}.png")
        master.resize((base * 2, base * 2), Image.LANCZOS).save(
            OUT / f"icon_{base}x{base}@2x.png")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
