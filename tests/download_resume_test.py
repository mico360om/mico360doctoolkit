"""Resumable update download: a partial .part file is resumed via HTTP Range
(not re-downloaded), and the result still verifies its SHA-256.

Also covers: the stable per-user download folder (a cancelled/failed attempt is
resumed by the next one — what the dialog's Retry does), a .part left from a
DIFFERENT build being discarded, an already-complete .part (HTTP 416), and a
server that sends no Content-Length (the download must still complete).

The updates folder is redirected to a temp dir — the real one is never touched.

Run:  python tests/download_resume_test.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


PAYLOAD = (b"MICO360-UPDATE-PAYLOAD-" * 5000)   # ~115 KB
RANGE_REQUESTS = []
REQUESTS = []


class _RangeHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        REQUESTS.append(self.path)
        if self.path.endswith("/nolength.bin"):
            # No Content-Length, no Range support: the body simply ends when the
            # server closes the connection (HTTP/1.0).
            self.send_response(200)
            self.end_headers()
            self.wfile.write(PAYLOAD)
            return
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            start = int(rng.split("=", 1)[1].split("-", 1)[0])
            RANGE_REQUESTS.append(start)
            if start >= len(PAYLOAD):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(PAYLOAD)}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = PAYLOAD[start:]
            self.send_response(206)
            self.send_header("Content-Range",
                             f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)

    def log_message(self, *a):  # silence
        pass


def main() -> int:
    from mico360 import updater

    # Redirect the stable per-user updates folder to a temp dir.
    stable = tempfile.mkdtemp(prefix="mico360_updates_")
    updater.updates_dir = lambda: stable

    srv = HTTPServer(("127.0.0.1", 0), _RangeHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/update.bin"
    sha = hashlib.sha256(PAYLOAD).hexdigest()
    info = updater.UpdateInfo(version="9.9.9", url=url, asset_name="update.bin",
                              sha256=sha, notes="", page="")

    # 1) Fresh download works (no .part yet).
    d1 = tempfile.mkdtemp(prefix="mico360_dl1_")
    out = updater.download(info, dest_dir=d1)
    check("fresh download completes", os.path.getsize(out) == len(PAYLOAD))
    check("fresh download verifies SHA-256", os.path.exists(out))

    # 2) Resume: pre-seed a .part with the first 40 % and download again — it must
    #    request the REMAINDER via Range and finish correctly (not restart).
    d2 = tempfile.mkdtemp(prefix="mico360_dl2_")
    part = os.path.join(d2, "update.bin.part")
    seed = len(PAYLOAD) * 2 // 5
    with open(part, "wb") as f:
        f.write(PAYLOAD[:seed])
    RANGE_REQUESTS.clear()
    out2 = updater.download(info, dest_dir=d2)
    check("resumed download completes to full size",
          os.path.getsize(out2) == len(PAYLOAD))
    check("resumed file matches original bytes (sha)",
          hashlib.sha256(Path(out2).read_bytes()).hexdigest() == sha)
    check("server received a Range request starting at the seeded offset",
          any(r == seed for r in RANGE_REQUESTS), str(RANGE_REQUESTS))
    check("the .part file was promoted to the final file (no leftover)",
          os.path.exists(out2) and not os.path.exists(part))

    # 3) A corrupt .part that yields the wrong bytes still fails the checksum
    #    (integrity preserved) — seed mismatched data the server can't fix.
    #    Here the server is authoritative, so a wrong-sha info should fail.
    bad = updater.UpdateInfo(version="9.9.9", url=url, asset_name="update.bin",
                             sha256="0" * 64, notes="", page="")
    d3 = tempfile.mkdtemp(prefix="mico360_dl3_")
    try:
        updater.download(bad, dest_dir=d3)
        check("bad checksum is rejected", False, "no error raised")
    except RuntimeError as exc:
        check("bad checksum is rejected", "integrity" in str(exc).lower())

    # 4) Stable folder + Retry: cancel mid-download, then download again with
    #    NO dest_dir (what the dialog's Retry does) — it must resume, not restart.
    for n in os.listdir(stable):
        os.remove(os.path.join(stable, n))
    polls = {"n": 0}

    def cancel_after_first_chunk():
        polls["n"] += 1
        return polls["n"] > 1
    try:
        updater.download(info, is_cancelled=cancel_after_first_chunk)
        check("cancel raises", False, "no error raised")
    except RuntimeError as exc:
        check("cancel raises", "cancel" in str(exc).lower(), str(exc))
    spart = os.path.join(stable, "update.bin.part")
    kept = os.path.getsize(spart) if os.path.exists(spart) else 0
    check("cancel keeps the partial in the stable folder (so Retry can resume)",
          kept > 0, f"kept={kept}")
    RANGE_REQUESTS.clear()
    REQUESTS.clear()
    out4 = updater.download(info)            # Retry: default = stable folder
    check("retry completes in the stable folder",
          os.path.dirname(out4) == stable and os.path.getsize(out4) == len(PAYLOAD))
    check("retry resumed from the kept bytes (Range at the partial's size)",
          kept in RANGE_REQUESTS, f"kept={kept} ranges={RANGE_REQUESTS}")
    check("retry result verifies", updater.is_verified(out4, sha))

    # 4b) A mid-file partial of THIS build (matching marker) in the stable
    #     folder is resumed by a plain download() — Range at its exact size.
    os.remove(out4)
    seed_b = len(PAYLOAD) // 3
    with open(spart, "wb") as f:
        f.write(PAYLOAD[:seed_b])
    with open(spart + ".sha256", "w") as f:
        f.write(sha)
    RANGE_REQUESTS.clear()
    out4b = updater.download(info)
    check("stable-folder partial of the same build resumes via Range",
          RANGE_REQUESTS == [seed_b] and os.path.getsize(out4b) == len(PAYLOAD),
          str(RANGE_REQUESTS))
    check("marker file is removed once the download completes",
          not os.path.exists(spart + ".sha256"))
    out4 = out4b

    # 5) A .part left by a DIFFERENT build (its marker names another hash) is
    #    discarded instead of being glued onto this download.
    os.remove(out4)
    with open(spart, "wb") as f:
        f.write(b"X" * 1000)
    with open(spart + ".sha256", "w") as f:
        f.write("1" * 64)
    RANGE_REQUESTS.clear()
    out5 = updater.download(info)
    check("a partial from another build is discarded (no Range resume)",
          RANGE_REQUESTS == [] and os.path.getsize(out5) == len(PAYLOAD),
          str(RANGE_REQUESTS))

    # 6) An already-complete .part (app closed before verifying): the server
    #    answers 416 — treat as done, verify, don't loop or re-download.
    os.remove(out5)
    with open(spart, "wb") as f:
        f.write(PAYLOAD)
    REQUESTS.clear()
    out6 = updater.download(info)
    check("complete partial + HTTP 416 finishes without re-downloading",
          os.path.getsize(out6) == len(PAYLOAD) and len(REQUESTS) == 1,
          f"requests={len(REQUESTS)}")

    # 7) An over-long .part (416 with a smaller total) restarts cleanly.
    os.remove(out6)
    with open(spart, "wb") as f:
        f.write(PAYLOAD + b"JUNK")
    out7 = updater.download(info)
    check("over-long partial is discarded and re-downloaded",
          hashlib.sha256(Path(out7).read_bytes()).hexdigest() == sha)

    # 8) No Content-Length: the download must complete at a clean EOF.
    nolen = updater.UpdateInfo(version="9.9.9",
                               url=f"http://127.0.0.1:{port}/nolength.bin",
                               asset_name="nolength.bin", sha256=sha,
                               notes="", page="")
    d8 = tempfile.mkdtemp(prefix="mico360_dl8_")
    seen = {"total": None, "done": 0}

    def prog(done, total):
        seen["done"], seen["total"] = done, total
    res: dict = {}

    def _run():
        try:
            res["out"] = updater.download(nolen, dest_dir=d8, progress=prog)
        except Exception as exc:          # pragma: no cover
            res["err"] = str(exc)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(30)
    check("download without Content-Length completes (no hang)",
          not t.is_alive() and "out" in res, res.get("err", "timed out" if t.is_alive() else ""))
    check("...with the full, verified payload",
          "out" in res and os.path.getsize(res["out"]) == len(PAYLOAD)
          and updater.is_verified(res["out"], sha))
    check("...reporting progress with an unknown total",
          seen["done"] == len(PAYLOAD) and seen["total"] == 0, str(seen))

    srv.shutdown()

    # --- adaptive faster-edge policy (pure, no network) ---------------------
    FAST = updater._DL_FAST
    FLOOR = updater._DL_MIN_SPEED
    # No reconnect when there's nothing left to fetch.
    check("no reconnect once the file is complete",
          updater._should_reconnect(1, 1, has_remaining=False) is False)
    # Absolute floor: a stalled/very slow edge always reconnects.
    check("reconnects below the absolute slow floor",
          updater._should_reconnect(FLOOR - 1, FLOOR - 1, True) is True)
    # A genuinely slow connection (best is also slow) keeps streaming — no thrash.
    check("slow connection does NOT thrash above the floor",
          updater._should_reconnect(FLOOR + 1, FLOOR + 1, True) is False)
    # A fast pipe that has degraded to <50% of its best chases a faster edge.
    check("fast pipe reconnects when its edge degrades",
          updater._should_reconnect(FAST * 0.4, FAST * 2, True) is True)
    # A fast pipe holding near its best keeps streaming.
    check("fast pipe stays put while healthy",
          updater._should_reconnect(FAST * 1.8, FAST * 2, True) is False)
    check("download uses 1 MB read chunks", updater._CHUNK >= (1 << 20))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All download-resume checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    # Skip Qt's crash-prone offscreen teardown at interpreter shutdown
    # (a lingering C++ object can abort finalization with 0xC0000409,
    #  masking an otherwise-clean pass). Flush and exit with the result.
    import os as _os, sys as _sys
    _sys.stdout.flush(); _sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
