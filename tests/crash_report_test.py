"""Privacy-respecting crash reporting: a report is written locally and an
easy (manual) way to send it is offered — nothing is sent automatically.

Run:  python tests/crash_report_test.py
"""
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
    from mico360 import __version__
    from mico360.config import settings
    from mico360.core import crash

    # Build a real traceback to format.
    try:
        raise ValueError("boom-xyz")
    except ValueError:
        exc_type, exc, tb = sys.exc_info()

    report = crash.format_report(exc_type, exc, tb)
    check("report names the app + version", __version__ in report)
    check("report includes the traceback + error", "Traceback" in report
          and "boom-xyz" in report and "ValueError" in report)
    check("report includes the OS", "OS:" in report)

    # Seed a recent log so we can verify it gets bundled next to the report.
    from mico360.paths import logs_dir
    seed_log = logs_dir() / "_crashtest_seed.log"
    seed_log.write_text("line-A\nLOGMARKER-42\nline-C\n", encoding="utf-8")

    path = crash.write_report(report)
    check("report is written to a local file", path is not None and path.exists()
          and path.suffix == ".txt", str(path))
    if path:
        check("written report round-trips", "boom-xyz" in path.read_text(encoding="utf-8"))
        bundled = path.with_suffix(".log")
        check("the last log is bundled next to the report",
              bundled.exists() and "LOGMARKER-42" in bundled.read_text(encoding="utf-8"),
              str(bundled))
        for p in (path, path.with_suffix(".log")):
            try:
                p.unlink()
            except OSError:
                pass
    try:
        seed_log.unlink()
    except OSError:
        pass

    url = crash.mailto_url(report)
    check("a prefilled mailto link is offered (manual send only)",
          url.startswith("mailto:info@mico360.com") and "subject=" in url
          and "body=" in url)

    # --- GitHub issue (pre-filled, user-submitted; no token, no auto-post) ---
    title = crash.issue_title(exc_type, exc)
    check("issue title is concise + names the error",
          title.startswith("Crash: ValueError") and "boom-xyz" in title
          and len(title) <= 120, title)

    gh = crash.github_issue_url(title, report, path)
    check("GitHub issue URL targets this repo's new-issue form",
          gh.startswith("https://github.com/mico360om/mico360doctoolkit/issues/new?"))
    check("issue URL carries title, body and the crash label",
          "title=" in gh and "body=" in gh and "labels=crash" in gh)
    check("issue URL stays under GitHub's length limit", len(gh) <= 7000, str(len(gh)))
    check("nothing is auto-posted (it's just a prefilled link)",
          gh.count("/issues/new") == 1 and "api.github.com" not in gh)

    # A huge log must be trimmed so the link still opens (no 414).
    big = crash.github_issue_url("Crash: X", "Q" * 50_000 + "\n", path)
    check("oversized report is trimmed to fit the URL", len(big) <= 7000, str(len(big)))
    check("trim leaves a breadcrumb to the saved report", "truncated" in big.lower())

    prev = settings.crash_reports_enabled
    settings.crash_reports_enabled = False
    check("crash_reports_enabled persists (off)", settings.crash_reports_enabled is False)
    settings.crash_reports_enabled = True
    check("crash_reports_enabled persists (on)", settings.crash_reports_enabled is True)
    settings.crash_reports_enabled = prev

    print()
    if failures:
        print(f"{len(failures)} crash-report check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All crash-report checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
