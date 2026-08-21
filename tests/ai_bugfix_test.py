"""Regressions for the 2026-08-21 bug report fixes.

BUG-1  Test connection runs OFF the UI thread (an unreachable host must not
       freeze the window for the full connect timeout).
BUG-2  A hand-added model id survives a background model-list refresh and is
       labelled as the user's own, not "offline or switched off".
BUG-3  masked_key never reveals more than ~a third of a key and fully masks
       anything under 12 characters (a fixed first-5+last-4 rule leaked 82% of
       an 11-character key).

Run:  python tests/ai_bugfix_test.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


KEY = "mico_bugfix_key_0123456789"
MODELS = [["srv-a", "srv-b"]]
GET_SLEEP = [0.0]


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            self.send_response(401); self.end_headers(); self.wfile.write(b"{}")
            return
        if GET_SLEEP[0]:
            time.sleep(GET_SLEEP[0])
        b = json.dumps({"data": [{"id": m} for m in MODELS[0]]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)


def main() -> int:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from mico360.config import settings
    from mico360.core import ai as ai_core
    from mico360.ui.settings_page import SettingsPage

    # ================= BUG-3: masked_key ==========================
    print("--- BUG-3: masked_key ---")
    leak = None
    for n in range(6, 60):
        k = "k" * n
        m = ai_core.masked_key(k)
        revealed = sum(1 for c in m if c != "•")
        if revealed > n / 3 + 1e-9:
            leak = (n, revealed, m)
            break
    check("masked_key never reveals more than a third", leak is None, str(leak))
    check("keys under 12 chars are fully masked",
          all(set(ai_core.masked_key("k" * n)) == {"•"} for n in range(1, 12)))
    check("the 11-char case that leaked 82% is now fully masked",
          set(ai_core.masked_key("mico_abcdef")) == {"•"})
    real = "mico_test_key_abcdefghijklmnop"
    check("a real long key still shows a recognisable head + last-4",
          ai_core.masked_key(real).startswith("mico_")
          and ai_core.masked_key(real).endswith(real[-4:])
          and real not in ai_core.masked_key(real))

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/v1"

    saved = (settings.ai_enabled, settings.ai_source, settings.ai_base_url,
             settings.ai_model, settings.ai_api_key_sealed,
             list(settings.ai_models), list(settings.ai_custom_models))
    settings.ai_enabled = True
    settings.ai_source = ai_core.SOURCE_CUSTOM
    settings.ai_base_url = base
    settings.ai_model = ""
    settings.ai_api_key_sealed = ai_core.seal_key(KEY)
    settings.ai_models = []
    settings.ai_custom_models = []

    def pump(ms):
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

    sp = SettingsPage()
    settle = lambda: [pump(50) for _ in range(120)
                      if getattr(sp, "_models_thread", None) is not None]
    await_test = lambda: [pump(50) for _ in range(300)
                          if getattr(sp, "_test_thread", None) is not None]
    listed = lambda: [sp.ai_model.itemText(i) for i in range(sp.ai_model.count())]

    def wait(pred, ms=8000):
        w = 0
        while not pred() and w < ms:
            pump(100); w += 100
        return pred()

    MODELS[0] = ["srv-a", "srv-b"]
    sp.show()
    wait(lambda: {"srv-a", "srv-b"} <= set(listed()))

    # ================= BUG-1: Test connection is non-blocking ======
    print("--- BUG-1: Test connection off the UI thread ---")
    # Quiesce the model machinery so nothing else is in flight during timing.
    for _ in range(60):
        if (getattr(sp, "_models_thread", None) is None
                and not getattr(sp, "_models_again", False)):
            break
        pump(50)
    GET_SLEEP[0] = 3.0                        # server takes 3s to answer /models
    t0 = time.time()
    sp._test_ai()
    dt = time.time() - t0
    # A synchronous test would block for the full 3s+ server response; the async
    # one returns in a few ms. 1.5s cleanly separates the two with margin.
    check("_test_ai() returns immediately (does not block the UI thread)",
          dt < 1.5, f"{dt:.2f}s")
    check("it shows 'Testing…' and disables the button while the worker runs",
          "Testing" in sp.ai_status.text() and not sp.btn_ai_test.isEnabled(),
          sp.ai_status.text()[:30])
    for _ in range(160):                     # up to 8s (server sleeps 3s)
        pump(50)
        if getattr(sp, "_test_thread", None) is None:
            break
    check("the result is delivered when the worker finishes",
          "<span" in sp.ai_status.text() and sp.btn_ai_test.isEnabled(),
          sp.ai_status.text()[:40])
    GET_SLEEP[0] = 0.0
    while getattr(sp, "_test_thread", None) is not None:
        pump(50)

    # ================= BUG-2: hand-added model survives refresh ====
    print("--- BUG-2: hand-added model preserved across refresh ---")
    settle()
    sp.ai_model.setEditText("my-custom:v1")
    sp._save_ai()
    settle()
    check("a typed model is remembered as the user's own",
          "my-custom:v1" in settings.ai_custom_models)

    sp.refresh_models_async(quiet=True)
    settle()
    ls = listed()
    check("the hand-added model SURVIVES a refresh (dropdown)",
          "my-custom:v1" in ls, str(ls))
    check("the hand-added model survives in settings",
          "my-custom:v1" in settings.ai_custom_models
          and "my-custom:v1" in settings.ai_models)
    st = sp.ai_models_state.text()
    check("it is labelled the user's own, not 'offline or switched off'",
          "Your own" in st and "my-custom:v1" in st and "Hidden" not in st,
          st[:90])

    # A real server model going offline is still hidden — but the custom one stays.
    MODELS[0] = ["srv-a"]
    sp.refresh_models_async(quiet=True)
    settle()
    ls = listed()
    check("an offline server model is hidden, custom model kept",
          "srv-b" not in ls and "my-custom:v1" in ls and "srv-a" in ls, str(ls))
    st = sp.ai_models_state.text()
    check("status reports srv-b hidden AND the custom one as your own",
          "srv-b" in st and "Your own" in st, st[:90])

    # Remove the custom one -> gone from the custom list.
    i = sp.ai_model.findText("my-custom:v1")
    sp.ai_model.setCurrentIndex(i)
    sp._remove_model()
    check("removing a hand-added model drops it from the custom list",
          "my-custom:v1" not in settings.ai_custom_models
          and "my-custom:v1" not in listed())

    sp._stop_model_work()
    sp.close()
    pump(100)
    (settings.ai_enabled, settings.ai_source, settings.ai_base_url,
     settings.ai_model, settings.ai_api_key_sealed, settings.ai_models,
     settings.ai_custom_models) = saved
    srv.shutdown()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Bug-fix regressions: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    import os as _os
    sys.stdout.flush(); sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
