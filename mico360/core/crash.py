"""Privacy-respecting crash capture.

When an unexpected error occurs, a report is written **locally** (together with a
copy of the most recent log) and the user is offered easy ways to send it — open a
**pre-filled GitHub issue**, copy the details, or open a pre-filled email.

**Nothing is ever transmitted automatically.** The GitHub path opens the *New
issue* form in the browser, pre-filled, so the user reviews the contents and
presses **Submit** themselves. We deliberately do **not** post via the API: that
would require shipping a token in the app (extractable and abusable), and there is
no backend to relay through. The user is always in control of whether — and what —
to send.
"""
from __future__ import annotations

import platform
import shutil
import traceback
import urllib.parse
from pathlib import Path

from mico360 import __app_name__, __version__
from mico360.paths import logs_dir
from mico360.updater import REPO_URL

REPORT_EMAIL = "info@mico360.com"
ISSUE_LABEL = "crash"
# GitHub returns "414 URI Too Long" past ~8 KB. URL-encoding inflates log text
# (every newline/space becomes 3 chars), so we cap on the *encoded* URL length.
_MAX_ISSUE_URL = 7000
_LOG_TAIL_LINES = 60


def _latest_log() -> Path | None:
    try:
        logs = sorted(logs_dir().glob("*.log"), key=lambda p: p.stat().st_mtime)
        return logs[-1] if logs else None
    except Exception:
        return None


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
    log = _latest_log()
    if log is not None:
        try:
            tail = log.read_text(encoding="utf-8",
                                 errors="replace").splitlines()[-_LOG_TAIL_LINES:]
            parts += ["", f"Recent log (last {len(tail)} lines of {log.name}):", *tail]
        except Exception:
            pass
    return "\n".join(parts)


def write_report(text: str) -> Path | None:
    """Save the report under the logs folder and bundle a copy of the most recent
    full log next to it (``crash_<ts>.txt`` + ``crash_<ts>.log``). Returns the
    report's path (or None)."""
    try:
        import datetime
        d = logs_dir() / "crashes"
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        f = d / f"crash_{stamp}.txt"
        f.write_text(text, encoding="utf-8")
        # Bundle the full log so the user can attach it to an issue/email.
        log = _latest_log()
        if log is not None:
            try:
                shutil.copy2(log, d / f"crash_{stamp}.log")
            except Exception:
                pass
        return f
    except Exception:
        return None


def issue_title(exc_type, exc) -> str:
    """A concise, useful issue title derived from the exception."""
    name = getattr(exc_type, "__name__", "Error")
    msg = " ".join(str(exc).split())          # collapse whitespace/newlines
    title = f"Crash: {name}: {msg}".rstrip(": ").strip()
    return (title[:117] + "…") if len(title) > 118 else title


def github_issue_url(title: str, body: str, report_path: Path | None = None) -> str:
    """A pre-filled GitHub *New issue* URL. Opening it shows the issue form with
    the title/body already populated; the user reviews it and submits. No token,
    no automatic posting.

    The report body is trimmed until the *encoded* URL fits GitHub's limit, so the
    link always opens (rather than failing with '414 URI Too Long')."""
    note = ("\n\n---\n_Filed from the in-app crash reporter. "
            "Please add what you were doing when it happened._")
    if report_path is not None:
        note += (f"\n_A full report and log were saved on your computer at "
                 f"`{report_path}` and `{report_path.with_suffix('.log').name}` — "
                 f"please drag the `.log` here to attach it._")

    def build(b: str) -> str:
        params = urllib.parse.urlencode(
            {"title": title, "body": f"```\n{b}\n```{note}", "labels": ISSUE_LABEL})
        return f"{REPO_URL}/issues/new?{params}"

    trimmed, url = body, build(body)
    while len(url) > _MAX_ISSUE_URL and len(trimmed) > 200:
        # Drop ~ the overage (in raw chars) plus a margin, then re-measure.
        cut = max(200, len(trimmed) - (len(url) - _MAX_ISSUE_URL) - 200)
        trimmed = trimmed[:cut].rstrip() + "\n… (truncated — see the saved report)"
        url = build(trimmed)
    return url


def mailto_url(text: str) -> str:
    """A mailto: link pre-filled with a (truncated) report — opens the user's
    email client; nothing is sent until the user presses send themselves."""
    subject = f"{__app_name__} v{__version__} crash report"
    body = text[:1500]
    return (f"mailto:{REPORT_EMAIL}?subject={urllib.parse.quote(subject)}"
            f"&body={urllib.parse.quote(body)}")
