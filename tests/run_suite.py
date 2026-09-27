#!/usr/bin/env python
"""Run the test suites, each in its own process, safely.

* Every suite gets a per-test timeout, so one hung suite can't stall the run.
* Every suite gets its own throw-away settings file (MICO360_SETTINGS_FILE), so
  tests never read or rewrite the real %APPDATA%\\MICO360\\DocToolkit.ini.
* stdin is closed (some suites misbehave when a background runner leaves it
  open) and Qt runs offscreen.

Usage:
    python tests/run_suite.py                   # every tests/*_test.py
    python tests/run_suite.py smoke icons       # just these (name or file)
    python tests/run_suite.py --timeout 300
Exit code 0 only if every selected suite passed.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _select(names: list[str]) -> list[Path]:
    every = sorted(HERE.glob("*_test.py"))
    if not names:
        return every
    picked = []
    for n in names:
        stem = Path(n).stem
        if not stem.endswith("_test"):
            stem += "_test"
        p = HERE / f"{stem}.py"
        if not p.exists():
            raise SystemExit(f"No such suite: {n}")
        picked.append(p)
    return picked


def run_one(path: Path, timeout: int) -> tuple[str, float, str]:
    work = Path(tempfile.mkdtemp(prefix="mico360_suite_"))
    env = dict(os.environ)
    env["MICO360_SETTINGS_FILE"] = str(work / "DocToolkit.ini")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    t0 = time.monotonic()
    try:
        p = subprocess.run([sys.executable, str(path)], cwd=str(HERE.parent), env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        status = "PASS" if p.returncode == 0 else f"FAIL (rc={p.returncode})"
        tail = (p.stdout + p.stderr)[-3000:]
    except subprocess.TimeoutExpired as exc:
        status = f"TIMEOUT (>{timeout}s)"
        out = exc.stdout or b""
        tail = (out.decode("utf-8", "replace") if isinstance(out, bytes) else out)[-3000:]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return status, time.monotonic() - t0, tail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("suites", nargs="*")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per suite")
    ap.add_argument("-q", "--quiet", action="store_true", help="no output tails")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):     # suite output is UTF-8
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    failed = []
    for path in _select(a.suites):
        status, secs, tail = run_one(path, a.timeout)
        print(f"{status:<22} {secs:7.1f}s  {path.name}", flush=True)
        if status != "PASS":
            failed.append(path.name)
            if not a.quiet:
                print("    " + tail.replace("\n", "\n    "), flush=True)
    print(f"\n{len(failed)} failed" + (": " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
