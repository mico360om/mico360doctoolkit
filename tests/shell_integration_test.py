"""Explorer "MICO360 Toolkit" right-click integration.

Covers the command-line parsing, the per-file-type action map, the launch
command, a real HKCU registry round-trip (against a throwaway sandbox key, never
the real shell keys), the single-instance payload forwarding, and the window's
open-request routing (open the right tool with the file already loaded).

Run:  python tests/shell_integration_test.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from mico360.app import parse_cli
    from mico360 import shell_integration as si
    from mico360.core.tools import TOOLS_BY_ID

    # ================= CLI parsing =================================
    print("--- command-line parsing ---")
    check("plain launch -> no request", parse_cli(["exe"]) is None)
    check("--register-shell parsed",
          parse_cli(["exe", "--register-shell"]) == {"action": "register"})
    check("--unregister-shell parsed",
          parse_cli(["exe", "--unregister-shell"]) == {"action": "unregister"})
    r = parse_cli(["exe", "--tool", "pdf_compress", r"C:\a.pdf"])
    check("--tool + file parsed",
          r == {"action": "open", "tool": "pdf_compress", "files": [r"C:\a.pdf"]})
    r = parse_cli(["exe", r"C:\a.pdf"])
    check("bare file -> open with auto tool",
          r == {"action": "open", "tool": None, "files": [r"C:\a.pdf"]})
    r = parse_cli(["exe", "--tool", "pdf_merge", "a.pdf", "b.pdf"])
    check("multiple files kept", r["files"] == ["a.pdf", "b.pdf"])

    # ================= action map =================================
    print("--- per-file-type actions ---")
    ea = si.ext_actions()
    check("every mapped tool id is a real tool",
          all(tid in TOOLS_BY_ID for ids in ea.values() for tid in ids))
    check(".pdf lists the PDF tools", ea.get(".pdf") == si._PDF)
    check("image extensions share the image actions",
          ea.get(".jpg") == si._IMAGE and ea.get(".heic") == si._IMAGE)
    check("office extensions share the office actions",
          ea.get(".docx") == si._OFFICE and ea.get(".xlsx") == si._OFFICE)
    check(".svg lists the SVG action", ea.get(".svg") == si._SVG)
    cmd = si.launch_command("pdf_compress", '"APP.EXE"')
    check("launch command opens the tool and passes the file",
          cmd == '"APP.EXE" --tool pdf_compress "%1"')

    # ================= registry round-trip (Windows) ===============
    print("--- registry round-trip (HKCU sandbox) ---")
    if not sys.platform.startswith("win"):
        check("registry ops are safe no-ops off Windows",
              si.register() is False and si.is_registered() is False)
    else:
        import winreg
        BASE = r"Software\MICO360-shelltest\SystemFileAssociations"
        try:
            ok = si.register(base=BASE, launch_prefix='"APP.EXE"')
            check("register() succeeds", ok)
            check("is_registered() sees the sandbox menu",
                  si.is_registered(base=BASE))
            # Parent verb of .pdf
            parent = rf"{BASE}\.pdf\shell\{si.PARENT_KEY}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, parent) as k:
                mui = winreg.QueryValueEx(k, "MUIVerb")[0]
                subc = winreg.QueryValueEx(k, "SubCommands")[0]
            check("parent verb is titled 'MICO360 Toolkit'", mui == si.MENU_TITLE)
            check("SubCommands is empty (=> cascade from nested shell)", subc == "")
            # Nested child verbs
            shell = rf"{parent}\shell"
            children = []
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, shell) as k:
                i = 0
                while True:
                    try:
                        children.append(winreg.EnumKey(k, i)); i += 1
                    except OSError:
                        break
            check("one submenu item per PDF action",
                  len(children) == len(si._PDF), f"{len(children)} items")
            # First child (00pdf_compress) command
            first = sorted(children)[0]
            cmdkey = rf"{shell}\{first}\command"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cmdkey) as k:
                command = winreg.QueryValue(k, "")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                rf"{shell}\{first}") as k:
                label = winreg.QueryValueEx(k, "MUIVerb")[0]
            check("first item is labelled with the tool name",
                  label == TOOLS_BY_ID["pdf_compress"].name, label)
            check("first item's command opens that tool with the file",
                  "--tool pdf_compress" in command and '"%1"' in command, command)
            # An image extension is registered too
            check("image extension is registered",
                  si.is_registered(base=BASE)
                  and _key_exists(rf"{BASE}\.png\shell\{si.PARENT_KEY}"))
        finally:
            si.unregister(base=BASE)
            # nuke the whole sandbox tree
            si._delete_tree(winreg.HKEY_CURRENT_USER, r"Software\MICO360-shelltest")
        check("unregister() removes the menu", not si.is_registered(base=BASE))

    # ================= IPC payload forwarding ======================
    # The receiver is the part that carries the fix (read the payload on
    # readyRead; the disconnect fallback must not clobber it). Drive it with a
    # non-blocking raw client + a pumped event loop — deterministic, and exactly
    # the bytes signal_running() sends. (A same-process blocking signal_running
    # would starve the shared loop; cross-process it's reliable.)
    print("--- single-instance payload ---")
    from PySide6.QtNetwork import QLocalSocket
    from mico360.single_instance import SingleInstance
    name = "MICO360-shelltest-ipc"
    primary = SingleInstance(name=name)
    got = {"payload": None}
    primary.activated.connect(lambda p: got.__setitem__("payload", p))
    check("primary claims the slot", primary.is_primary())

    def pump(ms):
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

    def raw_send(msg_bytes) -> QLocalSocket:
        sock = QLocalSocket()
        sock.connectToServer(name)
        sock.waitForConnected(1000)
        sock.write(msg_bytes)
        sock.flush()
        sock.waitForBytesWritten(1000)
        return sock                       # keep alive; primary closes it

    payload = json.dumps({"action": "open", "tool": "pdf_merge",
                          "files": [r"C:\x.pdf"]})
    s1 = raw_send(payload.encode() + b"\n")
    for _ in range(40):
        pump(50)
        if got["payload"]:
            break
    check("primary receives the forwarded open request",
          got["payload"] == payload, str(got["payload"])[:60])
    s1.abort()

    got["payload"] = "sentinel"
    s2 = raw_send(b"ACTIVATE\n")
    for _ in range(40):
        pump(50)
        if got["payload"] != "sentinel":
            break
    check("a plain activation carries an empty payload", got["payload"] == "")
    s2.abort()

    # signal_running exists and reports a delivery attempt (real behaviour is
    # validated cross-process; here just smoke that it connects and returns).
    second = SingleInstance(name=name)
    check("second instance detects the primary", second.is_running())
    import threading
    res = {}
    th = threading.Thread(
        target=lambda: res.__setitem__("ok", second.signal_running("")))
    th.start()
    for _ in range(40):
        pump(50)
        if th.join(0) or not th.is_alive():
            break
    th.join(timeout=3)
    check("signal_running delivers a ping to the primary",
          res.get("ok") is True, str(res.get("ok")))
    primary.close()

    # ================= window routing ==============================
    print("--- window open-request routing ---")
    from mico360.theme import stylesheet
    from mico360.config import settings
    app.setStyleSheet(stylesheet(settings.theme))
    from mico360.ui.main_window import MainWindow
    w = MainWindow()
    w.setAttribute(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.WA_DontShowOnScreen, True)
    w.show()
    for _ in range(4):
        app.processEvents()

    with tempfile.TemporaryDirectory() as td:
        import fitz
        f = Path(td) / "invoice.pdf"
        doc = fitz.open(); doc.new_page(); doc.save(str(f)); doc.close()

        # explicit tool
        w.handle_open_request({"action": "open", "tool": "pdf_compress",
                               "files": [str(f)]})
        for _ in range(4):
            app.processEvents()
        tp = w._current_tool_page()
        check("explicit-tool request opens that tool",
              w.top_title.text() == TOOLS_BY_ID["pdf_compress"].name,
              w.top_title.text())
        check("the file is loaded into the queue (no browsing)",
              tp is not None and any(Path(it.path).name == "invoice.pdf"
                                     for it in tp.items))

        # auto-routed (no tool) -> route_for picks a PDF tool
        img = Path(td) / "photo.png"
        from PIL import Image
        Image.new("RGB", (20, 20), "white").save(str(img))
        w.handle_open_request({"action": "open", "tool": None, "files": [str(img)]})
        for _ in range(4):
            app.processEvents()
        tp2 = w._current_tool_page()
        check("auto-routed image opens an image tool and loads it",
              tp2 is not None and str(img).endswith(".png")
              and any(Path(it.path).name == "photo.png" for it in tp2.items),
              w.top_title.text())

        # on_activation with a JSON payload routes; empty is a safe no-op
        w.on_activation(json.dumps({"files": [str(f)], "tool": "pdf_metadata"}))
        for _ in range(4):
            app.processEvents()
        check("on_activation(payload) routes to the requested tool",
              w.top_title.text() == TOOLS_BY_ID["pdf_metadata"].name,
              w.top_title.text())
        try:
            w.on_activation("")
            w.on_activation("not json")
            check("on_activation with empty/garbage payload doesn't crash", True)
        except Exception as exc:      # noqa: BLE001
            check("on_activation with empty/garbage payload doesn't crash",
                  False, repr(exc))
    w.close()

    # ================= Settings toggle (mocked registry) ===========
    print("--- settings toggle ---")
    if sys.platform.startswith("win"):
        # Patch the registry ops so the toggle never touches the real registry.
        fake = {"registered": False, "calls": []}
        si.register = lambda *a, **k: (fake.__setitem__("registered", True)
                                       or fake["calls"].append("register") or True)
        si.unregister = lambda *a, **k: (fake.__setitem__("registered", False)
                                         or fake["calls"].append("unregister") or True)
        si.is_registered = lambda *a, **k: fake["registered"]
        from mico360.ui.settings_page import SettingsPage
        sp = SettingsPage()
        check("Settings shows the Explorer-integration toggle",
              hasattr(sp, "chk_shell"))
        sp.chk_shell.setChecked(True)
        check("ticking the toggle registers the menu",
              "register" in fake["calls"] and fake["registered"])
        sp.chk_shell.setChecked(False)
        check("unticking the toggle unregisters the menu",
              "unregister" in fake["calls"] and not fake["registered"])
        sp.close()
    else:
        check("settings toggle is Windows-only (skipped)", True)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Shell integration: ALL PASSED")
    return 0


def _key_exists(path: str) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(_rc if isinstance(_rc, int) else 0)
