"""Auto-update via the GitHub Releases API.

The "manifest" is simply the repo's *latest release*: its tag is the version, its
body is the release notes, and its assets contain the installer (Setup .exe) plus
an optional ``<setup>.sha256`` sidecar for integrity verification.

Flow: check_for_update() -> (if newer) download() the installer with progress and
SHA-256 verification -> apply_and_exit() runs the installer silently, which closes
the running app and upgrades it in place (the Inno Setup AppId is stable).

Uses only the Python standard library (no extra dependency).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass

from mico360 import __version__

# --- Configure your GitHub repository here -------------------------------
# Repo: https://github.com/mico360om/mico360doctoolkit
GITHUB_OWNER = "mico360om"
GITHUB_REPO = "mico360doctoolkit"

API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
REPO_SHORT = f"github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
# Fallbacks that DON'T use api.github.com (which is rate-limited per-IP — a shared
# office/NAT address hits the 60/hr cap — and is blocked by some firewalls that
# still allow github.com). The Atom feed and the download host are on github.com.
ATOM_FEED = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases.atom"
DOWNLOAD_BASE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest/download/"
_HEADERS = {"User-Agent": f"MICO360-Doc-Toolkit/{__version__}",
            "Accept": "application/vnd.github+json"}
_CHUNK = 1 << 20          # 1 MB reads — fewer loop iterations on a fast link


@dataclass
class UpdateInfo:
    version: str          # clean, e.g. "5.1.0"
    url: str              # installer download URL
    asset_name: str       # installer file name
    sha256: str | None    # expected hash (None if no sidecar)
    notes: str            # release notes (markdown)
    page: str             # human release page
    size: int = 0         # installer size in bytes (0 = unknown)
    published_at: str = ""  # ISO release date (may be "" via the Atom fallback)


def format_release_date(iso: str) -> str:
    """ISO timestamp -> friendly date, e.g. 'June 07, 2026' (empty stays empty)."""
    if not iso:
        return ""
    try:
        import datetime
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except Exception:
        return iso[:10]


# Section headers we recognise in release notes, mapped to a bucket.
_NOTE_HEADER_KEYWORDS = (
    ("security", "security"),
    ("fix", "fixes"), ("bug", "fixes"),
    ("feature", "features"), ("new", "features"), ("added", "features"),
    ("improvement", "features"), ("enhancement", "features"), ("change", "features"),
)


def categorize_notes(notes: str) -> dict:
    """Split release-notes markdown into {'features','fixes','security','other'}
    lists of plain-text bullet lines. Uses section headers when present, else
    classifies each bullet by keywords — so the UI can show 'New features',
    'Bugs fixed' and 'Security improvements' separately."""
    buckets = {"features": [], "fixes": [], "security": [], "other": []}
    current = None
    for raw in (notes or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        is_header = (raw.lstrip().startswith("#")
                     or (line.startswith("**") and line.rstrip(":").endswith("**")))
        if is_header:
            low = line.lower()
            current = None
            for kw, bucket in _NOTE_HEADER_KEYWORDS:
                if kw in low:
                    current = bucket
                    break
            continue
        m = re.match(r"^\s*[-*•]\s+(.*)$", raw)
        if not m:
            continue
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(1))
        text = re.sub(r"[*_`]", "", text).strip()
        if not text:
            continue
        bucket = current
        if bucket is None:
            tl = text.lower()
            if any(k in tl for k in ("security", "vulnerab", "cve", "encrypt",
                                     "signed", "sign ")):
                bucket = "security"
            elif any(k in tl for k in ("fix", "bug", "no longer", "stall", "crash",
                                       "resolved", "couldn't", "wasn't", "hang")):
                bucket = "fixes"
            else:
                bucket = "features"
        buckets[bucket].append(text)
    return buckets


# --- version helpers -----------------------------------------------------
def clean_version(tag: str) -> str:
    return (tag or "").strip().lstrip("vV").strip()


def parse_version(s: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for chunk in clean_version(s).split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])  # type: ignore[return-value]


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


# --- network -------------------------------------------------------------
def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https)
        return resp.read()


def _get_json(url: str, timeout: int = 20) -> dict:
    return json.loads(_get(url, timeout).decode("utf-8"))


def _installer_ext() -> str:
    """The installer file extension this OS can install."""
    if sys.platform == "darwin":
        return ".dmg"
    return ".exe"   # Windows (and the default)


def _pick_installer(assets: list[dict]) -> dict | None:
    ext = _installer_ext()
    matches = [a for a in assets
               if str(a.get("name", "")).lower().endswith(ext)]
    # Prefer the "setup" installer over any other matching file, and a
    # versioned name over the stable "…-Latest" copy.
    setup = [a for a in matches if "setup" in str(a.get("name", "")).lower()]
    pref = setup or matches
    versioned = [a for a in pref if "latest" not in str(a.get("name", "")).lower()]
    return (versioned or pref or [None])[0]


def _latest_tag_via_atom(timeout: int = 20) -> str | None:
    """Read the newest release tag from the repo's Atom feed (github.com, not the
    rate-limited api.github.com). The first entry is the latest release."""
    raw = _get(ATOM_FEED, timeout).decode("utf-8", "replace")
    # Each entry links to …/releases/tag/<tag>; the first is the newest.
    m = re.search(r"/releases/tag/([^\"'<>\s]+)", raw)
    return m.group(1) if m else None


def _stable_asset_names() -> tuple[str, str]:
    """The stable (version-less) installer + checksum names for this OS — these
    are always reachable at releases/latest/download/ without the API."""
    if _installer_ext() == ".dmg":
        name = "MICO360-DocToolkit-macos-Latest.dmg"
        return name, name + ".sha256.txt"
    name = "MICO360-DocToolkit-Setup-Latest.exe"
    return name, name + ".sha256"


def _check_via_atom() -> UpdateInfo | None:
    """API-free update check: get the latest tag from the Atom feed and build the
    install info from the stable releases/latest/download URLs. Used when the API
    is unreachable (rate-limited / firewalled)."""
    tag = _latest_tag_via_atom()
    if not tag or not is_newer(tag):
        return None
    name, sidecar_name = _stable_asset_names()
    sha = None
    try:
        sha = _get(DOWNLOAD_BASE + sidecar_name).decode("utf-8").split()[0].strip()
    except Exception:
        sha = None
    # The API gave us nothing, so size/notes are unknown here — fetch the size
    # cheaply with a HEAD request so the UI can still show it.
    size = 0
    try:
        req = urllib.request.Request(DOWNLOAD_BASE + name, headers=_HEADERS,
                                     method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            size = int(resp.headers.get("Content-Length") or 0)
    except Exception:
        size = 0
    return UpdateInfo(
        version=clean_version(tag),
        url=DOWNLOAD_BASE + name,
        asset_name=name,
        sha256=sha,
        notes="",
        page=RELEASES_PAGE,
        size=size,
        published_at="",
    )


def check_for_update(json_fetcher=_get_json) -> UpdateInfo | None:
    """Return UpdateInfo if the latest GitHub release is newer, else None.

    Tries the GitHub API first; if that fails (rate limit / firewall / TLS), falls
    back to the Atom feed + stable download URLs so the check still works on PCs
    where api.github.com is unreachable. ``json_fetcher`` is injectable for tests;
    the Atom fallback only runs for the default (real-network) fetcher."""
    try:
        data = json_fetcher(API_LATEST)
    except Exception:
        # API unreachable — try the api-free path (real network only).
        if json_fetcher is _get_json:
            return _check_via_atom()
        raise
    tag = data.get("tag_name") or data.get("name") or ""
    if not tag or not is_newer(tag):
        return None
    assets = data.get("assets", []) or []
    installer = _pick_installer(assets)
    if not installer:
        return None
    name = installer["name"]
    sha = None
    # Match the checksum sidecar to THIS installer only. A blanket
    # "any .sha256" match would grab the wrong file's hash on a release that
    # ships both a .exe and a .dmg (each with its own sidecar) — which would
    # then fail the integrity check and block a perfectly good update.
    want = (name.lower() + ".sha256", name.lower() + ".sha256.txt")
    sidecar = next((a for a in assets
                    if str(a.get("name", "")).lower() in want), None)
    if sidecar:
        try:
            sha = _get(sidecar["browser_download_url"]).decode("utf-8").split()[0].strip()
        except Exception:
            sha = None
    return UpdateInfo(
        version=clean_version(tag),
        url=installer["browser_download_url"],
        asset_name=name,
        sha256=sha,
        notes=str(data.get("body", "") or ""),
        page=data.get("html_url") or RELEASES_PAGE,
        size=int(installer.get("size") or 0),
        published_at=str(data.get("published_at") or ""),
    )


# --- download + verify ---------------------------------------------------
# Reconnect tuning. GitHub's release CDN throughput can swing wildly per
# connection (seen: 0.2–14 MB/s within seconds), so if a connection runs slow we
# drop it and reconnect — resuming via HTTP Range — to chase a faster edge and to
# survive stalls, without ever re-downloading the bytes we already have.
_DL_WINDOW = 5.0            # seconds per throughput sample
_DL_MIN_SPEED = 300 * 1024  # absolute floor: below this for a full window → reconnect
_DL_MAX_STUCK = 6           # consecutive no-progress reconnects before giving up
# Adaptive "faster-edge" hunt: if the connection has *demonstrated* it can go fast
# (a window at/above _DL_FAST) but the current edge has since fallen below this
# fraction of that best, drop and reconnect to chase a faster CDN edge. Because it
# only triggers once a fast window has been seen, it never makes a genuinely slow
# connection thrash — those keep streaming and only reconnect on the absolute floor.
_DL_FAST = 2 * 1024 * 1024  # 2 MB/s — marks a "this pipe is fast" window
_DL_DEGRADE_FRAC = 0.5      # reconnect if a fast pipe drops below half its best


def _should_reconnect(speed: float, best: float, has_remaining: bool) -> bool:
    """Decide whether to drop the current connection and resume on a fresh (hopefully
    faster) CDN edge, given the latest window ``speed`` and the best window ``best``
    seen so far. Pure function so the policy is unit-testable."""
    if not has_remaining:
        return False
    if speed < _DL_MIN_SPEED:                       # stalled / very slow edge
        return True
    if best >= _DL_FAST and speed < best * _DL_DEGRADE_FRAC:
        return True                                 # fast pipe stuck on a degraded edge
    return False


class _Cancelled(Exception):
    pass


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def download(info: UpdateInfo, dest_dir: str | None = None,
             progress=None, is_cancelled=None) -> str:
    """Download the installer (resumable), verifying its SHA-256 if known.

    The download survives a flaky/variable connection: it writes to a ``.part``
    file and, on a stall, drop, or a sustained-slow window, reconnects with an
    HTTP ``Range`` request to resume from where it left off (and to grab a faster
    CDN edge). ``progress(done, total)`` and ``is_cancelled() -> bool`` are
    optional. Returns the final file path; raises on cancellation or checksum
    failure.
    """
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="mico360_update_")
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, info.asset_name)
    part = path + ".part"

    total: int | None = None
    stuck = 0
    best_speed = 0.0          # best window throughput seen (persists across reconnects)
    while True:
        existing = os.path.getsize(part) if os.path.exists(part) else 0
        if total is not None and existing >= total > 0:
            break
        headers = dict(_HEADERS)
        headers["Accept"] = "application/octet-stream"   # we want the raw asset
        if existing:
            headers["Range"] = f"bytes={existing}-"
        try:
            req = urllib.request.Request(info.url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                ranged = getattr(resp, "status", 200) == 206
                if total is None:
                    crange = resp.headers.get("Content-Range") or ""
                    if "/" in crange:
                        total = int(crange.rsplit("/", 1)[-1])
                    else:
                        total = int(resp.headers.get("Content-Length") or 0) or None
                if existing and not ranged:      # server ignored Range → restart
                    existing = 0
                done = existing
                with open(part, "ab" if existing else "wb") as fh:
                    win_t = time.monotonic()
                    win_b = 0
                    emit_t = win_t
                    emit_b = done
                    while True:
                        if is_cancelled and is_cancelled():
                            raise _Cancelled()
                        chunk = resp.read(_CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        win_b += len(chunk)
                        now = time.monotonic()
                        # Throttle UI progress updates: at most ~10/sec (or per
                        # 1 MB). Emitting a cross-thread Qt signal for every 256 KB
                        # chunk floods the UI thread and, via GIL contention, can
                        # actually slow the download on a busy / low-end machine.
                        if progress and (now - emit_t >= 0.1
                                         or done - emit_b >= (1 << 20)):
                            progress(done, total or 0)
                            emit_t, emit_b = now, done
                        if now - win_t >= _DL_WINDOW:
                            speed = win_b / (now - win_t)
                            if speed > best_speed:
                                best_speed = speed
                            if _should_reconnect(speed, best_speed,
                                                 bool(total and done < total)):
                                break            # slow/degraded edge → chase a faster one
                            win_t, win_b = now, 0
                    if progress:                 # final position for this round
                        progress(done, total or 0)
        except _Cancelled:
            _safe_remove(part)
            raise RuntimeError("Update cancelled.")
        except Exception:                        # network blip → resume & retry
            pass

        new_size = os.path.getsize(part) if os.path.exists(part) else 0
        if total and new_size >= total:
            break
        if new_size <= existing:                 # made no progress this round
            stuck += 1
            if stuck > _DL_MAX_STUCK:
                raise RuntimeError(
                    "The update download kept stalling on the network. Please try "
                    "again, or download it from the Releases page.")
            time.sleep(min(1.0 + stuck, 5.0))
        else:
            stuck = 0

    if info.sha256:
        h = hashlib.sha256()
        with open(part, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest().lower() != info.sha256.lower():
            _safe_remove(part)
            raise RuntimeError("The downloaded update failed its integrity check "
                               "and was discarded. Please try again later.")
    os.replace(part, path)
    return path


def apply_and_exit(setup_path: str) -> None:
    """Start installing the downloaded update, then let the app quit.

    * Windows — run the Inno Setup installer silently; it closes the running app,
      upgrades in place, and relaunches. The user approves the standard UAC prompt.
    * macOS — open the downloaded ``.dmg`` so the user can drag the new app into
      Applications (the standard, signing-free update flow).
    """
    if sys.platform == "darwin":
        subprocess.Popen(["open", setup_path], close_fds=True)
        return
    args = [setup_path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
            "/NOCANCEL"]
    creationflags = 0x08000000 if sys.platform.startswith("win") else 0  # no console
    subprocess.Popen(args, close_fds=True, creationflags=creationflags)


def is_configured() -> bool:
    """False while the GitHub repo placeholders haven't been set to a real repo."""
    return bool(GITHUB_OWNER and GITHUB_REPO) and "/" not in GITHUB_OWNER
