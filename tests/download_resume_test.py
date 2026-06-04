"""Resumable update download: a partial .part file is resumed via HTTP Range
(not re-downloaded), and the result still verifies its SHA-256.

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


class _RangeHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            start = int(rng.split("=", 1)[1].split("-", 1)[0])
            RANGE_REQUESTS.append(start)
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

    srv.shutdown()
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All download-resume checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
