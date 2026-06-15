"""Regression test for the auto-update threading bug.

The update check runs on a background QThread, but its result callback — which
creates the UpdateDialog (a QWidget) — MUST run on the GUI thread. Creating a
widget off the GUI thread shows a blank window and crashes the app.

This test stubs the network check and asserts the callback (and a dialog built
inside it) run on the main thread.

Run:  python tests/update_ui_test.py
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from PySide6.QtCore import QObject, QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    main_tid = threading.get_ident()

    import mico360.updater as U
    from mico360 import __version__
    from mico360.updater import UpdateInfo
    from mico360.ui.update_ui import UpdateDialog, start_check

    fake = UpdateInfo("9.9.9", "http://x/Setup.exe", "Setup.exe", None,
                      "## What's new\n- fix", "http://x")

    # --- found path: callback + dialog must be on the GUI thread ---------
    U.check_for_update = lambda *a, **k: fake
    parent = QObject()
    result: dict = {}

    def on_found(info):
        result["tid"] = threading.get_ident()
        # Building a widget here is exactly what crashed off-thread.
        try:
            dlg = UpdateDialog(info, None)
            result["dialog_ok"] = True
            dlg.deleteLater()
        except Exception as exc:  # pragma: no cover
            result["dialog_ok"] = False
            result["err"] = str(exc)
        result["version"] = info.version
        app.quit()

    start_check(parent, on_found)
    QTimer.singleShot(8000, app.quit)  # safety net
    app.exec()

    check("found callback ran on the GUI (main) thread",
          result.get("tid") == main_tid,
          f"main={main_tid} cb={result.get('tid')}")
    check("UpdateDialog built without error on GUI thread",
          result.get("dialog_ok") is True, result.get("err", ""))
    check("callback received the UpdateInfo", result.get("version") == "9.9.9")

    # --- up-to-date path also delivers on the GUI thread -----------------
    U.check_for_update = lambda *a, **k: None
    parent2 = QObject()
    utd: dict = {}

    def on_utd():
        utd["tid"] = threading.get_ident()
        app.quit()

    start_check(parent2, lambda info: None, on_utd)
    QTimer.singleShot(8000, app.quit)
    app.exec()
    check("up-to-date callback ran on the GUI thread",
          utd.get("tid") == main_tid, f"main={main_tid} cb={utd.get('tid')}")

    # --- failed path delivers the error on the GUI thread ----------------
    def boom(*a, **k):
        raise RuntimeError("network down")
    U.check_for_update = boom
    parent3 = QObject()
    failed: dict = {}

    def on_failed(msg):
        failed["tid"] = threading.get_ident()
        failed["msg"] = msg
        app.quit()

    start_check(parent3, lambda info: None, None, on_failed)
    QTimer.singleShot(8000, app.quit)
    app.exec()
    check("failed callback ran on the GUI thread",
          failed.get("tid") == main_tid, f"main={main_tid} cb={failed.get('tid')}")
    check("failed callback received the error text",
          "network down" in (failed.get("msg") or ""), repr(failed.get("msg")))

    # --- rich dialog: status badge, version line, meta, failure state ----
    rich = UpdateInfo(
        "9.9.9", "http://x/Setup-Latest.exe", "Setup-Latest.exe", None,
        "**New features**\n- Shiny thing\n**Bugs fixed**\n- Fixed a hang",
        "http://x", size=10 * 1024 * 1024, published_at="2026-06-07T12:00:00Z")
    dlg = UpdateDialog(rich, None)
    check("dialog opens in 'Available' state", dlg.badge.text() == "Available",
          dlg.badge.text())
    from PySide6.QtWidgets import QLabel
    ver_lbls = [w.text() for w in dlg.findChildren(QLabel)
                if w.objectName() == "UpdVersions"]
    check("dialog shows current → new version",
          ver_lbls and __version__ in ver_lbls[0] and "9.9.9" in ver_lbls[0],
          str(ver_lbls))
    dlg._on_failed("disk full")
    check("failure flips badge to 'Failed'", dlg.badge.text() == "Failed")
    check("failure shows Retry and hides Install",
          (not dlg.btn_retry.isHidden()) and dlg.btn_install.isHidden())
    check("failure shows the error text",
          "disk full" in dlg.error.text(), dlg.error.text())
    dlg.deleteLater()

    # --- post-install confirmation marker logic --------------------------
    from mico360.config import settings
    from mico360.ui.update_ui import maybe_show_update_completed
    # A marker for a version we are NOT yet running -> cleared, no dialog shown.
    settings.pending_update = {"version": "999.0.0", "started": 1.0}
    maybe_show_update_completed(None)
    check("pending-update marker is cleared after the startup check",
          settings.pending_update == {}, str(settings.pending_update))
    # No marker -> no-op, no crash.
    maybe_show_update_completed(None)
    check("no marker -> safe no-op", settings.pending_update == {})

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All update-UI threading checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
