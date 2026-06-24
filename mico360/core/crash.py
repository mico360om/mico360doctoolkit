"""Privacy-respecting crash capture.

When an unexpected error occurs, a report is written **locally** and the user is
offered an easy way to send it — by copying the details or opening a pre-filled
email. **Nothing is ever transmitted automatically**; the user is always in
control of whether (and what) to send.
"""
from __future__ import annotations

import platform
import traceback
import urllib.parse
from pathlib import Path

from mico360 import __app_name__, __version__
from mico360.paths import logs_dir

REPORT_EMAIL = "info@mico360.com"


def format_report(exc_type, exc, tb) -> str:
    """A self-contained, human-readable crash report (no personal data beyond the
    error itself and the recent app log)."""
    import datetime
    parts = [
        f"{__app_name__} v{__version__} — crash report",
        f"Time:   {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"OS:     {platform.platform()}",
        f"Python: {platform.python_version()}",
        "",
        "Traceback:",
        "".join(traceback.format_exception(exc_type, exc, tb)).rstrip(),
    ]
    try:
        logs = sorted(logs_dir().glob("*.log"), key=lambda p: p.stat().st_mtime)
        if logs:
            tail = logs[-1].read_text(encoding="utf-8",
                                      errors="replace").splitlines()[-40:]
            parts += ["", "Recent log (last 40 lines):", *tail]
    except Exception:
        pass
    return "\n".join(parts)


def write_report(text: str) -> Path | None:
    """Save the report under the logs folder; returns its path (or None)."""
    try:
        import datetime
        d = logs_dir() / "crashes"
        d.mkdir(parents=True, exist_ok=True)
        f = d / ("crash_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                 + ".txt")
        f.write_text(text, encoding="utf-8")
        return f
    except Exception:
        return None


def mailto_url(text: str) -> str:
    """A mailto: link pre-filled with a (truncated) report — opens the user's
    email client; nothing is sent until the user presses send themselves."""
    subject = f"{__app_name__} v{__version__} crash report"
    body = text[:1500]
    return (f"mailto:{REPORT_EMAIL}?subject={urllib.parse.quote(subject)}"
            f"&body={urllib.parse.quote(body)}")
