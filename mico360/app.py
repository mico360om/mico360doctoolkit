"""Application bootstrap."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from mico360 import __app_name__
from mico360.config import settings
from mico360.logging_setup import get_logger, setup_logging
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


_crash_relay = None      # UI-thread QObject that shows the crash dialog


def install_crash_relay() -> None:
    """Create (on the UI thread, after the QApplication) the relay the crash hook
    uses to show its dialog from exceptions raised on worker threads — a
    QMessageBox built off the UI thread can crash the whole app."""
    global _crash_relay
    from PySide6.QtCore import QObject, Signal

    class _Relay(QObject):
        show = Signal(object)

    _crash_relay = _Relay()
    _crash_relay.show.connect(lambda args: _show_crash_dialog(*args))


def install_crash_guard(log) -> None:
    """Last-resort handler: log any uncaught exception and keep the app alive
    with a friendly message instead of crashing to the desktop."""
    import threading

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
        args = (exc_type, exc, report, path, log)
        if threading.current_thread() is not threading.main_thread():
            if _crash_relay is not None:
                try:
                    _crash_relay.show.emit(args)      # queued to the UI thread
                except RuntimeError:
                    pass
            return
        _show_crash_dialog(*args)

    sys.excepthook = _hook
    threading.excepthook = lambda a: _hook(a.exc_type, a.exc_value, a.exc_traceback)


def _show_crash_dialog(exc_type, exc, report, path, log) -> None:
    """Show the crash dialog (UI thread only)."""
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


def parse_cli(argv: list[str]) -> dict | None:
    """Interpret the command line. Returns a request dict, or None for a plain
    launch. Shapes:
      {"action": "register"} / {"action": "unregister"}   — shell menu setup
      {"action": "open", "tool": <id|None>, "files": [...]} — open a tool/file
    """
    import os
    args = list(argv[1:])
    if not args:
        return None
    if "--selftest" in args:
        # Post-build check of the packaged app (see mico360/selftest.py).
        i = args.index("--selftest")
        path = args[i + 1] if i + 1 < len(args) else "mico360_selftest.json"
        return {"action": "selftest", "report": os.path.abspath(path)}
    if "--register-shell" in args:
        return {"action": "register", "force": "--force" in args}
    if "--unregister-shell" in args:
        return {"action": "unregister", "opt_out": "--opt-out" in args}
    tool = None
    files: list[str] = []
    i = 0
    only_files = False
    while i < len(args):
        a = args[i]
        if not only_files:
            if a == "--":                # everything after this is a path
                only_files = True
                i += 1
                continue
            if a in ("--tool", "-t") and i + 1 < len(args):
                tool = args[i + 1]
                i += 2
                continue
            # Unknown flags are ignored — unless it's a real file whose name
            # starts with "-" (e.g. "-draft.pdf"), which used to be dropped.
            if a.startswith("-") and not os.path.exists(a):
                i += 1
                continue
        files.append(_normalize_cli_path(a))
        i += 1
    if files:
        return {"action": "open", "tool": tool, "files": files}
    return None


def _normalize_cli_path(a: str) -> str:
    """Make a command-line path absolute (a forwarded request is handled by
    the already-running instance, whose working directory differs) and repair
    a drive/share root mangled by argv quoting: Explorer passes "E:\\" for a
    folder-background click on a drive root, which parses as  E:"  ."""
    import os
    if a.endswith('"'):
        a = a[:-1] + "\\"
    try:
        return os.path.abspath(a)
    except (OSError, ValueError):
        return a


def main() -> int:
    setup_logging()
    log = get_logger()

    cli = parse_cli(sys.argv)
    if cli and cli["action"] == "selftest":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from mico360 import selftest
        rc = selftest.run(cli["report"])
        log.info("self-test finished: %s", "passed" if rc == 0 else "FAILED")
        # Exit straight away: the report is written, and Qt's headless teardown
        # at interpreter shutdown can crash (0xC0000409 on Windows), turning a
        # passed self-test into a failing exit code for the build pipeline.
        import logging
        logging.shutdown()
        for stream in (sys.stdout, sys.stderr):      # None in the windowed app
            if stream is not None:
                try:
                    stream.flush()
                except Exception:
                    pass
        # Tear Qt down while Python is still whole: leaving the QApplication
        # to the DLL-unload stage of os._exit faulted inside PySide6 (an access
        # violation Windows logged as "MICO360DocToolkit stopped working").
        try:
            qapp = QApplication.instance()
            if qapp is not None:
                qapp.closeAllWindows()
                qapp.processEvents()
                qapp.shutdown()
        except Exception:
            log.debug("Qt shutdown before exit failed", exc_info=True)
        os._exit(rc)

    # Shell-integration setup runs without the GUI (used by the installer).
    if cli and cli["action"] in ("register", "unregister"):
        from mico360 import shell_integration
        if cli["action"] == "register":
            # The installer / auto-update re-registers on every run; a user who
            # turned the menu off keeps it off (only an explicit choice in the
            # interactive installer, --force, turns it back on).
            if settings.shell_menu_opt_out and not cli.get("force"):
                log.info("shell register: skipped (turned off by the user)")
                return 0
            ok = shell_integration.register()
            if ok:
                settings.shell_menu_opt_out = False
        else:
            ok = shell_integration.unregister()
            if ok and cli.get("opt_out"):
                settings.shell_menu_opt_out = True
        log.info("shell %s: %s", cli["action"], "ok" if ok else "skipped")
        return 0 if ok else 1

    install_crash_guard(log)
    _set_windows_app_id()
    configure_high_dpi()

    app = QApplication(sys.argv)
    install_crash_relay()
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
    from mico360.ui.icons import app_icon
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

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

    # Installed app only: keep a registered right-click menu pointing at this
    # exe (a moved install / older build left entries launching a dead path).
    if getattr(sys, "frozen", False) and not settings.shell_menu_opt_out:
        try:
            from mico360 import shell_integration
            log.info("shell menu self-check: %s", shell_integration.self_heal())
        except Exception:
            log.debug("shell menu self-check failed", exc_info=True)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
