"""The post-build self-test mode (``--selftest``) runs green from source.

The same mode is run against the frozen .exe after every build; this suite
keeps it working between builds.

Run:  python tests/selftest_mode_test.py   (or via tests/run_suite.py)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if not os.environ.get("MICO360_SETTINGS_FILE"):
    os.environ["MICO360_SETTINGS_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="mico360_st_"), "DocToolkit.ini")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from mico360.app import parse_cli
    r = parse_cli(["exe", "--selftest", "out.json"])
    check("--selftest is parsed with its report path",
          r == {"action": "selftest", "report": os.path.abspath("out.json")}, str(r))

    report = Path(tempfile.mkdtemp(prefix="mico360_st_out_")) / "report.json"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    p = subprocess.run([sys.executable, str(ROOT / "run.py"), "--selftest", str(report)],
                       env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    check("self-test exits 0", p.returncode == 0, f"rc={p.returncode}")
    data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    bad = [r["check"] + ": " + r["detail"] for r in data.get("results", []) if not r["ok"]]
    check("every self-test check passed", data.get("ok") is True and not bad, "; ".join(bad)[:400])
    check("self-test covers the tools, OCR and the UI",
          data.get("passed", 0) >= 50
          and any(r["check"] == "Searchable PDF (OCR)" for r in data.get("results", []))
          and any(r["check"].startswith("User interface") for r in data.get("results", [])))
    check("a readable .txt summary is written next to the JSON",
          report.with_suffix(".txt").exists())
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Self-test mode checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
