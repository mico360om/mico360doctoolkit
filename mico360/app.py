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
            get_logger().debug("AppUserModelID not set", exc_info=True)


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
        get_logger().debug("High-DPI rounding policy not applied", exc_info=True)
    # Harmless on Qt 6 (scaling is always on there); kept for safety/back-compat.
    for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        if hasattr(Qt, attr):
            try:
                QApplication.setAttribute(getattr(Qt, attr), True)
            except Exception:
                get_logger().debug("Qt attribute %s not applied", attr, exc_info=True)


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
            log.error("Could not write the crash report", exc_info=True)
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
                              "A report (with the recent log) was saved on your computer. "
                              "You can report it to help us fix it — nothing is sent "
                              "unless you choose to. \"Report on GitHub\" opens a "
                              "pre-filled issue for you to review and submit.")
            b_github = box.addButton("Report on GitHub", QMessageBox.AcceptRole)
            b_email = box.addButton("Email report", QMessageBox.ActionRole)
            b_copy = box.addButton("Copy details", QMessageBox.ActionRole)
            box.addButton("Continue", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is b_copy and report:
                QApplication.clipboard().setText(report)
            elif clicked in (b_email, b_github) and report:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                from mico360.core import crash
                if clicked is b_github:
                    url = crash.github_issue_url(
                        crash.issue_title(exc_type, exc), report, path)
                else:
                    url = crash.mailto_url(report)
                QDesktopServices.openUrl(QUrl(url))
        except Exception:
            log.debug("Crash dialog could not be shown", exc_info=True)
    sys.excepthook = _hook


def parse_cli(argv: list[str]) -> dict | None:
    """Interpret the command line. Returns a request dict, or None for a plain
    launch. Shapes:
      {"action": "register"} / {"action": "unregister"}   — shell menu setup
      {"action": "open", "tool": <id|None>, "files": [...]} — open a tool/file
    """
    args = list(argv[1:])
    if not args:
        return None
    if "--register-shell" in args:
        return {"action": "register"}
    if "--unregister-shell" in args:
        return {"action": "unregister"}
    tool = None
    files: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--tool", "-t") and i + 1 < len(args):
            tool = args[i + 1]
            i += 2
            continue
        if a.startswith("-"):        # ignore unknown flags
            i += 1
            continue
        files.append(a)
        i += 1
    if files:
        return {"action": "open", "tool": tool, "files": files}
    return None


def main() -> int:
    setup_logging()
    log = get_logger()

    # Shell-integration setup runs without the GUI (used by the installer).
    cli = parse_cli(sys.argv)
    if cli and cli["action"] in ("register", "unregister"):
        from mico360 import shell_integration
        ok = (shell_integration.register() if cli["action"] == "register"
              else shell_integration.unregister())
        log.info("shell %s: %s", cli["action"], "ok" if ok else "skipped")
        return 0 if ok else 1

    install_crash_guard(log)
    _set_windows_app_id()
    configure_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("MICO360")

    open_req = cli if (cli and cli["action"] == "open") else None

    # --- single instance: a second launch raises the first and exits ---
    from mico360.single_instance import SingleInstance
    guard = SingleInstance()
    if guard.is_running():
        # Forward an "open" request to the running window; otherwise just raise
        # it and tell the user it's already open.
        import json
        guard.signal_running(json.dumps(open_req) if open_req else "")
        if open_req is None:
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtWidgets import QMessageBox
            if QGuiApplication.platformName() != "offscreen":
                QMessageBox.information(
                    None, __app_name__,
                    f"{__app_name__} is already running.\n\n"
                    "We've brought the open window to the front for you.")
        log.info("Second instance %s the running one.",
                 "forwarded a request to" if open_req else "signalled")
        return 0

    # Square app icon — this is what the macOS Dock / Windows taskbar show when
    # running from source. (The wide word-mark squashes to a sliver there.)
    for name in ("app.png", "logo.png"):
        p = resource_path(name)
        if p.exists():
            app.setWindowIcon(QIcon(str(p)))
            break

    app.setStyleSheet(stylesheet(settings.theme))

    # Import here so a failure shows after QApplication exists (for message boxes).
    from mico360.ui.main_window import MainWindow

    try:
        win = MainWindow()
        guard.setParent(win)                       # tie its lifetime to the window
        guard.activated.connect(win.on_activation)
        win.show()
        if open_req is not None:                   # launched via the shell menu
            win.handle_open_request(open_req)
    except Exception:
        log.exception("Failed to start UI")
        raise

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
