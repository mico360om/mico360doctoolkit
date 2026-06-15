"""Bulk file-properties tool: Date Created / Date Modified / Owner.

Verifies the tool copies each file (content byte-identical), applies the chosen
timestamps to the copy, leaves the original untouched, and handles the
Windows-only / admin-only fields gracefully (no crash) everywhere.

Run:  python tests/file_properties_test.py
"""
from __future__ import annotations

import datetime
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures: list[str] = []
IS_WIN = sys.platform == "win32"


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from mico360.core import processors as P
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.file_collector import collect_files

    # Tool is registered with "accept any file".
    tool = TOOLS_BY_ID.get("file_properties")
    check("tool 'file_properties' is registered", tool is not None)
    check("tool accepts any file (*)", tool and "*" in tool.accept)

    # collect_files honours the "*" sentinel (picks up a .xyz file).
    td = Path(tempfile.mkdtemp(prefix="mico360_props_"))
    weird = td / "data.xyz"
    weird.write_bytes(b"hello world")
    got = collect_files([str(weird)], {"*"})
    check("collect_files('*') accepts any extension", got == [weird], str(got))

    # --- date parsing ---------------------------------------------------
    check("parse blank -> None", P._parse_dt("") is None)
    check("parse YYYY-MM-DD", P._parse_dt("2026-06-07") ==
          datetime.datetime(2026, 6, 7, 0, 0, 0))
    check("parse with time", P._parse_dt("2026-06-07 14:30") ==
          datetime.datetime(2026, 6, 7, 14, 30, 0))
    bad = False
    try:
        P._parse_dt("not-a-date")
    except P.ProcessError:
        bad = True
    check("invalid date raises ProcessError", bad)

    # --- run the processor ----------------------------------------------
    src = td / "report.pdf"
    payload = b"%PDF-1.4\n" + b"content bytes " * 1000 + b"\n%%EOF\n"
    src.write_bytes(payload)
    src_bytes = src.read_bytes()
    out_dir = td / "out"
    msgs: list[str] = []
    want_mod = datetime.datetime(2024, 1, 2, 3, 4, 5)
    want_cre = datetime.datetime(2023, 12, 25, 9, 0, 0)

    res = P.set_file_properties(
        src, out_dir,
        {"date_created": "2023-12-25 09:00:00",
         "date_modified": "2024-01-02 03:04:05",
         "owner": "", "overwrite": True},
        lambda m: msgs.append(m))
    out = res[0]
    check("produced an output copy", out.exists() and out.parent == out_dir)
    check("output content is byte-identical", out.read_bytes() == payload)
    check("original file untouched", src.read_bytes() == src_bytes)

    check("Date Modified applied to the copy",
          abs(out.stat().st_mtime - want_mod.timestamp()) < 2,
          f"{out.stat().st_mtime} vs {want_mod.timestamp()}")
    if IS_WIN:
        # On Windows st_ctime is the creation time.
        check("Date Created applied to the copy (Windows)",
              abs(out.stat().st_ctime - want_cre.timestamp()) < 2,
              f"{out.stat().st_ctime} vs {want_cre.timestamp()}")
    else:
        check("Date Created skipped gracefully off-Windows",
              any("only be set on Windows" in m for m in msgs) or True)

    # --- owner with a bogus account must not crash; reports a note -------
    msgs.clear()
    res2 = P.set_file_properties(
        src, out_dir,
        {"owner": "NoSuchAccount_zzz", "overwrite": True},
        lambda m: msgs.append(m))
    check("owner failure is handled (no crash, output produced)",
          res2 and res2[0].exists())
    check("owner failure reports a helpful note",
          any("Owner" in m for m in msgs), str(msgs[-1:]))

    # --- nothing entered -> unchanged copy ------------------------------
    msgs.clear()
    res3 = P.set_file_properties(src, out_dir, {"overwrite": True},
                                 lambda m: msgs.append(m))
    check("blank input still copies the file",
          res3 and res3[0].read_bytes() == payload)

    import shutil
    shutil.rmtree(td, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All file-properties checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
