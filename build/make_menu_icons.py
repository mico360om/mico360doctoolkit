"""Generate a small per-tool .ico for the Explorer right-click submenu.

Each tool's monochrome line-icon (from mico360.ui.icons) is rendered in the
brand red and written to mico360/resources/menu_icons/<tool_id>.ico as a
multi-size icon (16/24/32/48 px) so Windows can pick the crisp size for the
menu at any DPI. The registered verbs point at these files, so the submenu
shows a distinct icon per tool instead of the generic app icon.

Runs offscreen (QtSvg render) so it works on a headless build runner.

Run:  python build/make_menu_icons.py
"""
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MENU_COLOR = "#E5323C"          # brand red — reads on light and dark menus
OUT_DIR = ROOT / "mico360" / "resources" / "menu_icons"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48)]
_BASE = 64                      # render once at this size, PIL downsamples


def _pil_from_qpixmap(pm):
    from PySide6.QtCore import QBuffer, QByteArray
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    pm.toImage().save(buf, "PNG")
    buf.close()
    from PIL import Image
    return Image.open(io.BytesIO(bytes(ba))).convert("RGBA")


def write_menu_icons() -> list[Path]:
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from mico360.core.tools import TOOLS
    from mico360.ui import icons

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for tool in TOOLS:
        name = icons.tool_icon_name(tool.id)
        pm = icons.pixmap(name, _BASE, MENU_COLOR, 1.0)
        dst = OUT_DIR / f"{tool.id}.ico"
        _pil_from_qpixmap(pm).save(dst, format="ICO", sizes=ICO_SIZES)
        written.append(dst)
    return written


def main() -> None:
    paths = write_menu_icons()
    print(f"Wrote {len(paths)} menu icon(s) to {OUT_DIR}")


if __name__ == "__main__":
    main()
