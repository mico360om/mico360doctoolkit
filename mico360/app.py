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


def install_crash_guard(log) -> None:
    """Last-resort handler: log any uncaught exception and keep the app alive
    with a friendly message instead of crashing to the desktop."""
    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        # Always write a local report; never transmit anything automatically.
        report = path = None
        try:
            from mico360.core import crash
            report = crash.format_report(exc_type, exc, tb)
            path = crash.write_report(report)
        except Exception:
            pass
        try:
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtWidgets import QApplication, QMessageBox
            from mico360.config import settings
            if (QApplication.instance() is None
                    or QGuiApplication.platformName() == "offscreen"
                    or not settings.crash_reports_enabled):
                return
            box = QMessageBox(QMessageBox.Warning, __app_name__,
                              "Something went wrong, but the app is still running.\n\n"
                              f"{exc_type.__name__}: {exc}\n\n"
                              "A report was saved on your computer. You can send it to "
                              "help us fix it — nothing is sent unless you choose to.")
            b_email = box.addButton("Email report", QMessageBox.AcceptRole)
            b_copy = box.addButton("Copy details", QMessageBox.ActionRole)
            box.addButton("Continue", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is b_copy and report:
                QApplication.clipboard().setText(report)
            elif clicked is b_email and report:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                from mico360.core import crash
                QDesktopServices.openUrl(QUrl(crash.mailto_url(report)))
        except Exception:
            pass
    sys.excepthook = _hook


def main() -> int:
    setup_logging()
    log = get_logger()
    install_crash_guard(log)
    _set_windows_app_id()
    configure_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("MICO360")

    # --- single instance: a second launch raises the first and exits ---
    from mico360.single_instance import SingleInstance
    guard = SingleInstance()
    if guard.is_running():
        guard.signal_running()      # bring the existing window forward
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QMessageBox
        if QGuiApplication.platformName() != "offscreen":
            QMessageBox.information(
                None, __app_name__,
                f"{__app_name__} is already running.\n\n"
                "We've brought the open window to the front for you.")
        log.info("Second instance blocked; signalled the running one.")
        return 0

    logo = resource_path("logo.png")
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))

    app.setStyleSheet(stylesheet(settings.theme))

    # Import here so a failure shows after QApplication exists (for message boxes).
    from mico360.ui.main_window import MainWindow

    try:
        win = MainWindow()
        guard.setParent(win)                       # tie its lifetime to the window
        guard.activated.connect(win.bring_to_front)
        win.show()
    except Exception:
        log.exception("Failed to start UI")
        raise

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
