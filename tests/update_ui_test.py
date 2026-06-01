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

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All update-UI threading checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
