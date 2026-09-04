"""Generate the square app icon for MICO360 Doc Toolkit in every format the
app and its installers need:

    mico360/resources/app.ico   Windows executable / installer / taskbar
    mico360/resources/app.icns  macOS .app bundle (Dock, Finder, Launchpad)
    mico360/resources/app.png   512 px square used for QApplication.setWindowIcon
                                (Dock icon when running from source on macOS,
                                Alt-Tab / title bar on Windows)

The brand logo is a wide wordmark ("MICO 360°"), which becomes an invisible
sliver when letterboxed into a square icon. Instead we build a proper square
app icon: the bold white "360° + swoosh" emblem (cropped from the white logo)
centred on a rounded maroon brand tile. This stays recognisable down to 16px.

Pure Pillow, so all three formats build on any OS (no iconutil needed).

Run:  python build/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC_WHITE = ROOT / "logo-w.png"      # all-white wordmark (for dark backgrounds)
SRC_COLOR = ROOT / "logo.png"        # full-colour wordmark
RES = ROOT / "mico360" / "resources"
DST = RES / "app.ico"
DST_ICNS = RES / "app.icns"
DST_PNG = RES / "app.png"
PNG_SIZE = 512
ICNS_SIZES = [(16, 16), (32, 32), (64, 64), (128, 128),
              (256, 256), (512, 512), (1024, 1024)]
PREVIEW = ROOT / "build" / "_work" / "icon_preview.png"   # scratch, not shipped

MAROON = (130, 20, 20, 255)          # sampled brand maroon (#821414)
EMBLEM_LEFT_FRAC = 0.365             # crop x: right of the MICO pill / gap (~x850/2330)
TILE = 1024                          # master canvas
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48),
             (64, 64), (128, 128), (256, 256)]


def _emblem() -> Image.Image:
    """Return the trimmed white '360° + swoosh' emblem as RGBA."""
    white = Image.open(SRC_WHITE).convert("RGBA")
    w, h = white.size
    crop = white.crop((int(w * EMBLEM_LEFT_FRAC), 0, w, h))
    bbox = crop.getbbox()            # trim transparent margins
    return crop.crop(bbox) if bbox else crop


def _rounded_tile(size: int, color, radius_frac: float = 0.22) -> Image.Image:
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    r = int(size * radius_frac)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=color)
    return tile


def build_master() -> Image.Image:
    tile = _rounded_tile(TILE, MAROON)
    emblem = _emblem()
    # Fit emblem into ~78% of the tile, centred.
    box = int(TILE * 0.78)
    ew, eh = emblem.size
    scale = min(box / ew, box / eh)
    emblem = emblem.resize((max(1, int(ew * scale)), max(1, int(eh * scale))),
                           Image.LANCZOS)
    ex = (TILE - emblem.width) // 2
    ey = (TILE - emblem.height) // 2
    tile.alpha_composite(emblem, (ex, ey))
    return tile


def write_all(master: Image.Image | None = None) -> list[Path]:
    """Write app.ico, app.icns and app.png; returns the paths written."""
    master = master or build_master()
    RES.mkdir(parents=True, exist_ok=True)
    master.save(DST, sizes=ICO_SIZES)
    # Pillow's ICNS writer embeds each requested size (incl. @2x retina slots).
    master.save(DST_ICNS, format="ICNS", sizes=ICNS_SIZES)
    master.resize((PNG_SIZE, PNG_SIZE), Image.LANCZOS).save(DST_PNG)
    return [DST, DST_ICNS, DST_PNG]


def main() -> None:
    master = build_master()
    for p in write_all(master):
        print(f"Wrote {p}")

    # Preview strip: render the icon at several sizes on a checker-ish bg.
    sizes = [16, 32, 48, 64, 128, 256]
    pad = 12
    strip = Image.new("RGBA", (sum(sizes) + pad * (len(sizes) + 1),
                               256 + pad * 2), (240, 240, 240, 255))
    x = pad
    for s in sizes:
        thumb = master.resize((s, s), Image.LANCZOS)
        strip.alpha_composite(thumb, (x, pad + (256 - s) // 2))
        x += s + pad
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    strip.save(PREVIEW)
    print(f"Wrote {PREVIEW}")


if __name__ == "__main__":
    main()
