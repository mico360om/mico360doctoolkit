"""Application bootstrap."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
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


def main() -> int:
    setup_logging()
    log = get_logger()
    _set_windows_app_id()

    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

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
