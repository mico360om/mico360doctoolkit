"""Generate a multi-resolution Windows .ico from the logo PNG.

The logo is wide, so we letterbox it onto a square transparent canvas first.
Run:  python build/make_icon.py
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "logo.png"
DST = ROOT / "mico360" / "resources" / "app.ico"


def main() -> None:
    img = Image.open(SRC).convert("RGBA")
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    DST.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(DST, sizes=sizes)
    print(f"Wrote {DST}")


if __name__ == "__main__":
    main()
