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

    # Isolation: never write the user's real settings INI or updates folder.
    import tempfile
    from PySide6.QtCore import QSettings
    from mico360.config import settings
    real_settings_store = settings._s
    settings._s = QSettings(os.path.join(tempfile.mkdtemp(prefix="mico360_ini_"),
                                         "t.ini"), QSettings.IniFormat)
    import mico360.updater as U
    tmp_updates = tempfile.mkdtemp(prefix="mico360_updates_")
    U.updates_dir = lambda: tmp_updates
    try:
        return _main(app, main_tid)
    finally:
        settings._s = real_settings_store


def _main(app, main_tid) -> int:
    from PySide6.QtCore import QObject, QTimer
    import mico360.updater as U
    from mico360 import __version__
    from mico360.updater import UpdateInfo
    from mico360.ui import update_ui
    from mico360.ui.update_ui import UpdateDialog, start_check
    real_check = U.check_for_update

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

    # --- "checksum-verified" is only promised when there is a checksum ----
    def _tip(w):
        return (w.toolTip() + " " + w.accessibleDescription()).lower()
    no_sum = UpdateDialog(rich, None)          # sha256=None, no sidecar URL
    check("no checksum -> Install tooltip does NOT claim 'checksum-verified'",
          "checksum-verified" not in _tip(no_sum.btn_install)
          and "no checksum" in _tip(no_sum.btn_install), _tip(no_sum.btn_install))
    no_sum.deleteLater()
    with_sum = UpdateDialog(UpdateInfo("9.9.9", "http://x/S.exe", "S.exe", "a" * 64,
                                       "", "http://x"), None)
    check("checksum known -> Install tooltip says 'checksum-verified'",
          "checksum-verified" in _tip(with_sum.btn_install))
    with_sum.deleteLater()
    late_sum = UpdateDialog(UpdateInfo("9.9.9", "http://x/S.exe", "S.exe", None, "",
                                       "http://x", sha256_url="http://x/S.exe.sha256"),
                            None)
    check("checksum fetchable later -> still promised (download enforces it)",
          "checksum-verified" in _tip(late_sum.btn_install))
    late_sum.deleteLater()

    # --- the download worker uses the STABLE folder (so Retry resumes) ----
    real_download = U.download
    seen_dl: dict = {}

    def fake_download(info, dest_dir=None, progress=None, is_cancelled=None):
        seen_dl["dest_dir"] = dest_dir
        return os.path.join(dest_dir or "", info.asset_name)
    U.download = fake_download
    try:
        w = update_ui.DownloadWorker(rich)
        w.run()
        w2 = update_ui.DownloadWorker(rich)     # a Retry builds a fresh worker
        first = seen_dl.get("dest_dir")
        w2.run()
    finally:
        U.download = real_download
    check("DownloadWorker downloads into updater.updates_dir()",
          first == U.updates_dir(), str(first))
    check("Retry reuses the same folder (resume, not restart)",
          seen_dl.get("dest_dir") == first)

    # --- completion caption: 'checksum verified' only when it truly was ---
    real_apply = U.apply_and_exit
    applied: list = []
    U.apply_and_exit = lambda path, sha=None: applied.append((path, sha))
    try:
        import hashlib
        good = os.path.join(U.updates_dir(), "Good-Setup.exe")
        with open(good, "wb") as fh:
            fh.write(b"installer")
        good_sha = hashlib.sha256(b"installer").hexdigest()
        ok_dlg = UpdateDialog(UpdateInfo("9.9.9", "http://x/G.exe", "Good-Setup.exe",
                                         good_sha, "", "http://x"), None)
        ok_dlg._on_done(good)
        check("verified download -> caption says 'checksum verified'",
              "checksum verified" in ok_dlg.progress_caption.text(),
              ok_dlg.progress_caption.text())
        check("installer launched with its expected hash",
              applied and applied[-1] == (good, good_sha), str(applied))
        ok_dlg.deleteLater()

        unverified = os.path.join(U.updates_dir(), "Other-Setup.exe")
        with open(unverified, "wb") as fh:
            fh.write(b"something else")
        bad_dlg = UpdateDialog(UpdateInfo("9.9.9", "http://x/O.exe", "Other-Setup.exe",
                                          None, "", "http://x"), None)
        bad_dlg._on_done(unverified)
        check("unverified file -> caption does NOT claim 'checksum verified'",
              "verified" not in bad_dlg.progress_caption.text().lower(),
              bad_dlg.progress_caption.text())
        bad_dlg.deleteLater()
    finally:
        U.apply_and_exit = real_apply
    # And the real apply_and_exit refuses the unverified file outright.
    refused = False
    try:
        U.apply_and_exit(unverified)
    except RuntimeError:
        refused = True
    check("real apply_and_exit refuses an unverified installer", refused)

    # --- a successful check sweeps stale downloads, keeping the offered one ---
    real_cleanup = U.cleanup_downloads
    swept: list = []
    U.cleanup_downloads = lambda keep_asset=None, **k: swept.append(keep_asset) or 0
    try:
        U.check_for_update = lambda *a, **k: fake
        update_ui.CheckWorker().run()
        U.check_for_update = lambda *a, **k: None
        update_ui.CheckWorker().run()

        def _boom(*a, **k):
            raise RuntimeError("offline")
        U.check_for_update = _boom
        update_ui.CheckWorker().run()
    finally:
        U.cleanup_downloads = real_cleanup
        U.check_for_update = real_check
    check("check found -> cleanup keeps the offered installer",
          swept[:1] == ["Setup.exe"], str(swept))
    check("up to date -> cleanup sweeps everything stale",
          swept[1:2] == [None], str(swept))
    check("failed check -> no cleanup", len(swept) == 2, str(swept))

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

    # Pre-release ordering in the pending-update check: running the final
    # release satisfies a marker for its own release candidate, but a running
    # rc never satisfies a marker for the final.
    shown: list = []

    class _FakeDone:
        def __init__(self, version, when, parent=None):
            shown.append(version)

        def exec(self):
            return 0
    real_done = update_ui.UpdateCompletedDialog
    real_cleanup = U.cleanup_downloads
    update_ui.UpdateCompletedDialog = _FakeDone
    U.cleanup_downloads = lambda *a, **k: swept.append("launch") or 0
    try:
        settings.pending_update = {"version": f"{__version__}-rc2", "started": 1.0}
        maybe_show_update_completed(None)
        check("final release satisfies a marker for its -rc (dialog shown)",
              shown == [f"{__version__}-rc2"], str(shown))
        check("after a completed update, stale downloads are swept",
              swept[-1:] == ["launch"], str(swept))
        maj, mnr, pat = U.parse_version(__version__)
        settings.pending_update = {"version": f"{maj}.{mnr}.{pat + 1}", "started": 1.0}
        maybe_show_update_completed(None)
        check("an older running version never confirms a newer target",
              len(shown) == 1, str(shown))
    finally:
        update_ui.UpdateCompletedDialog = real_done
        U.cleanup_downloads = real_cleanup

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All update-UI threading checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    # Skip Qt's crash-prone offscreen teardown at interpreter shutdown
    # (a lingering C++ object can abort finalization with 0xC0000409,
    #  masking an otherwise-clean pass). Flush and exit with the result.
    import os as _os, sys as _sys
    _sys.stdout.flush(); _sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
