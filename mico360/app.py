"""Application bootstrap."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from mico360 import __app_name__
from mico360.config import settings
from mico360.logging_setup import get_logger, setup_logging
from mico360.paths import resource_path
from mico360.theme import stylesheet


def _set_windows_app_id() -> None:
    """Make Windows group the taskbar icon under our own AppUserModelID."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "MICO360.DocToolkit.1")
        except Exception:
            pass


def configure_high_dpi() -> None:
    """Make the app crisp and correctly sized at every Windows display-scaling
    level (100 / 125 / 150 / 175 / 200 / 250 / 300 %) and on per-monitor
    mixed-DPI multi-monitor setups.

    The key piece is the *rounding policy*: ``PassThrough`` keeps fractional
    scale factors (1.25, 1.5, 1.75, 2.5 …) exact instead of rounding them to a
    whole number, so the UI neither shrinks nor balloons on those settings.
    Must run **before** the QApplication is created.
    """
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    # Harmless on Qt 6 (scaling is always on there); kept for safety/back-compat.
    for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        if hasattr(Qt, attr):
            try:
                QApplication.setAttribute(getattr(Qt, attr), True)
            except Exception:
                pass


def main() -> int:
    setup_logging()
    log = get_logger()
    _set_windows_app_id()
    configure_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("MICO360")

    logo = resource_path("logo.png")
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))

    app.setStyleSheet(stylesheet(settings.theme))

    # Import here so a failure shows after QApplication exists (for message boxes).
    from mico360.ui.main_window import MainWindow

    try:
        win = MainWindow()
        win.show()
    except Exception:
        log.exception("Failed to start UI")
        raise

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
