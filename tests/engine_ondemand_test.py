"""On-demand LibreOffice engine: path resolution + ensure/auto-download logic
(the actual ~340 MB download is mocked — not exercised in tests)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from mico360.config import settings
    from mico360.core import deps, engines

    # Paths
    root = engines.engine_root()
    check("engine_root lives under the user data dir / engines / libreoffice",
          "engines" in str(root).lower() and "libreoffice" in str(root).lower(),
          str(root))
    check("engine_soffice is …/program/soffice.exe",
          engines.engine_soffice().parts[-2:] == ("program", "soffice.exe"))
    check("is_engine_installed returns a bool",
          isinstance(engines.is_engine_installed(), bool))

    # find_libreoffice() includes the on-demand engine path in its search.
    import inspect
    src = inspect.getsource(deps.find_libreoffice)
    check("find_libreoffice checks the engine dir", "engines" in src and "libreoffice" in src)

    # Setting round-trips.
    prev = settings.auto_download_engine
    settings.auto_download_engine = False
    check("auto_download_engine persists (off)", settings.auto_download_engine is False)
    settings.auto_download_engine = True
    check("auto_download_engine persists (on)", settings.auto_download_engine is True)
    settings.auto_download_engine = prev

    # ensure_libreoffice behaviour with the resolver + downloader mocked.
    real_find = deps.find_libreoffice
    real_dl = engines.download_engine
    try:
        deps.find_libreoffice = lambda: r"X:\already\program\soffice.exe"
        check("ensure returns an already-present engine (no download)",
              engines.ensure_libreoffice() == r"X:\already\program\soffice.exe")

        deps.find_libreoffice = lambda: None
        check("ensure(auto=False) when missing returns None (no download)",
              engines.ensure_libreoffice(auto=False) is None)

        calls = []
        engines.download_engine = (
            lambda report=None, is_cancelled=None: (calls.append(1)
                                                    or r"Y:\dl\program\soffice.exe"))
        got = engines.ensure_libreoffice(auto=True)
        if sys.platform.startswith("win"):
            check("ensure(auto=True) when missing triggers the download",
                  got == r"Y:\dl\program\soffice.exe" and len(calls) == 1, f"{got} {calls}")
        else:
            check("ensure(auto=True) is a no-op off Windows (manual install)",
                  got is None)
    finally:
        deps.find_libreoffice = real_find
        engines.download_engine = real_dl

    # download_engine refuses to run off Windows.
    if not sys.platform.startswith("win"):
        raised = False
        try:
            engines.download_engine()
        except RuntimeError:
            raised = True
        check("download_engine raises off Windows", raised)

    print()
    if failures:
        print(f"{len(failures)} engine check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All on-demand engine checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
