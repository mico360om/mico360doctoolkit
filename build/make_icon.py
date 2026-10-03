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
centred on a rounded maroon brand tile.

Every size is drawn for its size, so the icon is sharp everywhere:
  * 16-48 px (taskbar, title bar, Explorer lists): a simplified mark — a bold
    white "360" drawn at that exact pixel size. The detailed swoosh shrunk to
    these sizes was a blur.
  * 64 px and up: the full emblem, downscaled with light sharpening.
The .ico carries the in-between sizes Windows asks for at 125-200 % display
scaling (20, 40, 72, 96 px), so Windows never has to stretch one.

Pure Pillow, so all three formats build on any OS (no iconutil needed).

Run:  python build/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
WHITE = (255, 255, 255, 255)
EMBLEM_LEFT_FRAC = 0.365             # crop x: right of the MICO pill / gap (~x850/2330)
TILE = 1024                          # master canvas
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 72, 96, 128, 256]
SIMPLE_MAX = 48                      # sizes up to this use the simplified mark

# Heavy sans faces for the small mark, first found wins (Windows, macOS, Linux).
_BOLD_FONTS = (
    r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\seguibl.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


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


def _bold_font(px: int):
    for path in _BOLD_FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, px)
    return ImageFont.load_default(size=px)


def _small_mark(size: int) -> Image.Image:
    """The simplified icon for small sizes: a bold "360" drawn at this exact
    pixel size on the maroon tile (corners drawn at 4x for smooth edges).

    Up to 24 px the lettering spans the tile and is drawn on whole pixels (no
    anti-aliasing): strokes thinner than a pixel otherwise render grey and soft.
    """
    tile = _rounded_tile(size * 4, MAROON).resize((size, size), Image.LANCZOS)
    pixel_crisp = size <= 24
    width, height = (0.98, 0.80) if pixel_crisp else (0.88, 0.66)
    px = size * 2
    font = _bold_font(px)
    while px > 4:                     # largest text that fits the tile
        font = _bold_font(px)
        l, t, r, b = font.getbbox("360")
        if r - l <= size * width and b - t <= size * height:
            break
        px -= 1
    l, t, r, b = font.getbbox("360")
    x = round((size - (r - l)) / 2 - l)
    y = round((size - (b - t)) / 2 - t)
    draw = ImageDraw.Draw(tile)
    if pixel_crisp:
        draw.fontmode = "1"
    draw.text((x, y), "360", font=font, fill=WHITE)
    return tile


def render(size: int, master: Image.Image | None = None) -> Image.Image:
    """The icon drawn for one pixel size."""
    if size <= SIMPLE_MAX:
        return _small_mark(size)
    img = (master or build_master()).resize((size, size), Image.LANCZOS)
    if size <= 256:                  # restore edge contrast lost in the downscale
        img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
    return img


def write_all(master: Image.Image | None = None) -> list[Path]:
    """Write app.ico, app.icns and app.png; returns the paths written."""
    master = master or build_master()
    RES.mkdir(parents=True, exist_ok=True)
    frames = {s: render(s, master) for s in ICO_SIZES}
    # Pillow takes each size from append_images when one matches exactly.
    frames[256].save(DST, format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                     append_images=[frames[s] for s in ICO_SIZES if s != 256])
    icns = [render(w, master) for w, _ in ICNS_SIZES if w != 1024]
    master.save(DST_ICNS, format="ICNS", sizes=ICNS_SIZES, append_images=icns)
    render(PNG_SIZE, master).save(DST_PNG)
    return [DST, DST_ICNS, DST_PNG]


def main() -> None:
    master = build_master()
    for p in write_all(master):
        print(f"Wrote {p}")

    # Preview strip: every .ico size, on a light background.
    pad = 12
    strip = Image.new("RGBA", (sum(ICO_SIZES) + pad * (len(ICO_SIZES) + 1),
                               256 + pad * 2), (240, 240, 240, 255))
    x = pad
    for s in ICO_SIZES:
        strip.alpha_composite(render(s, master), (x, pad + (256 - s) // 2))
        x += s + pad
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    strip.save(PREVIEW)
    print(f"Wrote {PREVIEW}")


if __name__ == "__main__":
    main()
