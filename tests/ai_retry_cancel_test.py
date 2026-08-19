"""AI request retry (429/503) and cancel-in-flight.

* A transient 429/503 is retried automatically (honouring Retry-After); 502/504
  and permanent 4xx are not. list_models / Test connection do not retry (they run
  on the UI thread).
* A running "Suggest All with AI" can be cancelled: the panel frees immediately,
  the backoff wait is interrupted, and a late/blocking answer is discarded.

Offline: stub HTTP servers stand in for the platform. Run:
    python tests/ai_retry_cancel_test.py
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


KEY = "mico_retry_key_0123456789"

# Server behaviour is driven by these holders so one stub covers every case.
STATUS_SEQUENCE = [[]]     # statuses to serve on successive POSTs
POST_HITS = [0]
GET_HITS = [0]
RETRY_AFTER = ["0"]        # value of the Retry-After header on non-200s
POST_SLEEP = [0.0]         # seconds to block inside do_POST (simulate a slow node)
OK_BODY = {"choices": [{"index": 0, "finish_reason": "stop",
           "message": {"role": "assistant", "content": '{"title": "Doc"}'}}]}


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj, headers=None):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        return self.headers.get("Authorization") == f"Bearer {KEY}"

    def do_GET(self):
        GET_HITS[0] += 1
        if not self._auth():
            return self._send(401, {"error": {"message": "bad key"}})
        seq = STATUS_SEQUENCE[0]
        code = seq[min(GET_HITS[0] - 1, len(seq) - 1)] if seq else 200
        if code != 200:
            return self._send(code, {"error": {"message": f"status {code}"}},
                              {"Retry-After": RETRY_AFTER[0]})
        self._send(200, {"object": "list", "data": [{"id": "qwen2.5:0.5b"}]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)             # drain body (Windows RST guard)
        if POST_SLEEP[0]:
            time.sleep(POST_SLEEP[0])
        POST_HITS[0] += 1
        if not self._auth():
            return self._send(401, {"error": {"message": "bad key"}})
        seq = STATUS_SEQUENCE[0]
        code = seq[min(POST_HITS[0] - 1, len(seq) - 1)] if seq else 200
        if code != 200:
            return self._send(code, {"error": {"message": f"status {code}"}},
                              {"Retry-After": RETRY_AFTER[0]})
        self._send(200, OK_BODY)


def main() -> int:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from mico360.config import settings
    from mico360.core import ai as ai_core

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    cfg = ai_core.AiConfig(enabled=True, source=ai_core.SOURCE_CUSTOM,
                           base_url=base, api_key=KEY, model="qwen2.5:0.5b")

    def reset(seq, retry_after="0", sleep=0.0):
        STATUS_SEQUENCE[0] = seq
        POST_HITS[0] = 0
        GET_HITS[0] = 0
        RETRY_AFTER[0] = retry_after
        POST_SLEEP[0] = sleep

    # ================= retry on 503 =================================
    print("--- retry on transient 429/503 ---")
    reset([503, 503, 200])
    txt = ai_core.chat(cfg, [{"role": "user", "content": "x"}])
    check("chat retries through 503s and then succeeds",
          "Doc" in txt and POST_HITS[0] == 3, f"{POST_HITS[0]} attempts")

    reset([429, 200])
    txt = ai_core.chat(cfg, [{"role": "user", "content": "x"}])
    check("chat retries a 429 and succeeds", POST_HITS[0] == 2, f"{POST_HITS[0]}")

    # Persistent 503 -> gives up after MAX_RETRIES and reports cleanly.
    reset([503, 503, 503, 503, 503])
    err = None
    try:
        ai_core.chat(cfg, [{"role": "user", "content": "x"}])
    except ai_core.AiError as e:
        err = e
    check("a persistent 503 stops after MAX_RETRIES+1 attempts",
          err is not None and POST_HITS[0] == ai_core.MAX_RETRIES + 1,
          f"{POST_HITS[0]} attempts")
    check("the give-up message is the friendly 503 text",
          err is not None and "node" in str(err).lower(), str(err)[:50])

    # ================= NOT retried =================================
    print("--- statuses that must NOT be retried ---")
    reset([504, 200])
    try:
        ai_core.chat(cfg, [{"role": "user", "content": "x"}])
    except ai_core.AiError:
        pass
    check("504 is not retried (job may still be queued)", POST_HITS[0] == 1,
          f"{POST_HITS[0]}")

    reset([502, 200])
    try:
        ai_core.chat(cfg, [{"role": "user", "content": "x"}])
    except ai_core.AiError:
        pass
    check("502 (job failed) is not retried", POST_HITS[0] == 1, f"{POST_HITS[0]}")

    reset([400, 200])
    try:
        ai_core.chat(cfg, [{"role": "user", "content": "x"}])
    except ai_core.AiError:
        pass
    check("a 400 is not retried", POST_HITS[0] == 1, f"{POST_HITS[0]}")

    # list_models / Test connection run on the UI thread -> never retry.
    reset([503, 200])
    try:
        ai_core.list_models(cfg)
    except ai_core.AiError:
        pass
    check("list_models does not retry (UI-thread safe)", GET_HITS[0] == 1,
          f"{GET_HITS[0]}")

    # ================= Retry-After honoured =========================
    print("--- Retry-After honoured and capped ---")
    reset([503, 200], retry_after="1")
    t0 = time.time()
    ai_core.chat(cfg, [{"role": "user", "content": "x"}])
    dt = time.time() - t0
    check("a Retry-After of 1s is waited out before the retry", dt >= 0.9,
          f"{dt:.2f}s")

    # A Retry-After longer than the cap is not slept on — surfaces the message.
    reset([503, 200], retry_after="600")
    t0 = time.time()
    try:
        ai_core.chat(cfg, [{"role": "user", "content": "x"}])
    except ai_core.AiError:
        pass
    dt = time.time() - t0
    check("an over-cap Retry-After surfaces the message instead of blocking",
          dt < 2.0 and POST_HITS[0] == 1, f"{dt:.2f}s, {POST_HITS[0]} attempts")

    # ================= cancel interrupts the backoff ================
    print("--- cancel event ---")
    reset([503, 503, 200], retry_after="5")
    ev = threading.Event()
    # Fire the cancel shortly after the first 503, mid-backoff.
    threading.Timer(0.3, ev.set).start()
    t0 = time.time()
    err = None
    try:
        ai_core.chat(cfg, [{"role": "user", "content": "x"}], cancel=ev)
    except ai_core.AiError as e:
        err = e
    dt = time.time() - t0
    check("cancel interrupts a retry backoff promptly",
          err is not None and "cancel" in str(err).lower() and dt < 3.0,
          f"{dt:.2f}s: {err}")

    # A pre-set cancel is honoured before any request goes out.
    reset([200])
    ev2 = threading.Event(); ev2.set()
    err = None
    try:
        ai_core._request(cfg, "/models", cancel=ev2)
    except ai_core.AiError as e:
        err = e
    check("a pre-set cancel aborts before hitting the server",
          err is not None and "cancel" in str(err).lower() and GET_HITS[0] == 0)

    # ================= UI: cancel frees the panel ===================
    print("--- UI: Suggest -> Cancel ---")
    saved = (settings.ai_enabled, settings.ai_source, settings.ai_base_url,
             settings.ai_model, settings.ai_api_key_sealed)
    settings.ai_enabled = True
    settings.ai_source = ai_core.SOURCE_CUSTOM
    settings.ai_base_url = base
    settings.ai_model = "qwen2.5:0.5b"
    settings.ai_api_key_sealed = ai_core.seal_key(KEY)

    import tempfile
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.tool_page import ToolPage

    def pump(ms):
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

    with tempfile.TemporaryDirectory() as td:
        import fitz
        src = Path(td) / "d.pdf"
        doc = fitz.open(); pg = doc.new_page()
        pg.insert_text((60, 90), "Some Title"); pg.insert_text((60, 120), "Body text here.")
        doc.save(str(src)); doc.close()

        reset([200], sleep=1.0)          # server takes 1s to answer
        page = ToolPage(TOOLS_BY_ID["pdf_metadata"])
        panel = page.ai_panel
        page.add_paths([str(src)])
        pump(120)
        page.file_list.item(0).setSelected(True)

        panel.btn_suggest.click()
        pump(120)                        # request now in flight (server sleeping)
        token_before = panel._active_token
        # isVisibleTo(): the page isn't shown, so isVisible() is always False —
        # this asks "would it be visible if the panel were shown?".
        check("Cancel button appears while a request runs",
              panel.btn_cancel.isVisibleTo(panel)
              and not panel.btn_suggest.isEnabled())

        panel._cancel()
        check("Cancel frees the panel immediately",
              not panel.btn_cancel.isVisible()
              and panel.btn_suggest.isEnabled()
              and panel.btn_suggest.text() == "Suggest All with AI"
              and "cancel" in panel.status.text().lower(), panel.status.text())
        check("nothing was applied by the cancelled run", not panel._current)

        # The slow answer arrives after cancel — it must be discarded (stale token).
        pump(1300)
        check("a late answer after Cancel is ignored (stale token)",
              not panel._current and token_before != panel._active_token)

        panel._teardown_threads()
        pump(50)

    (settings.ai_enabled, settings.ai_source, settings.ai_base_url,
     settings.ai_model, settings.ai_api_key_sealed) = saved
    srv.shutdown()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("AI retry + cancel: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    import os as _os, sys as _sys
    _sys.stdout.flush(); _sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
