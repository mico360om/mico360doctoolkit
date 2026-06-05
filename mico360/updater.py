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
_HEADERS = {"User-Agent": f"MICO360-Doc-Toolkit/{__version__}",
            "Accept": "application/vnd.github+json"}
_CHUNK = 256 * 1024


@dataclass
class UpdateInfo:
    version: str          # clean, e.g. "5.1.0"
    url: str              # installer download URL
    asset_name: str       # installer file name
    sha256: str | None    # expected hash (None if no sidecar)
    notes: str            # release notes (markdown)
    page: str             # human release page


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


def check_for_update(json_fetcher=_get_json) -> UpdateInfo | None:
    """Return UpdateInfo if the latest GitHub release is newer, else None.

    ``json_fetcher`` is injectable for testing. Raises on network errors so the
    caller can show a message; returns None when simply up to date."""
    data = json_fetcher(API_LATEST)
    tag = data.get("tag_name") or data.get("name") or ""
    if not tag or not is_newer(tag):
        return None
    assets = data.get("assets", []) or []
    installer = _pick_installer(assets)
    if not installer:
        return None
    name = installer["name"]
    sha = None
    sidecar = next((a for a in assets
                    if str(a.get("name", "")).lower() in
                    (name.lower() + ".sha256", "sha256.txt")
                    or str(a.get("name", "")).lower().endswith(".sha256")), None)
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
    )


# --- download + verify ---------------------------------------------------
# Reconnect tuning. GitHub's release CDN throughput can swing wildly per
# connection (seen: 0.2–14 MB/s within seconds), so if a connection runs slow we
# drop it and reconnect — resuming via HTTP Range — to chase a faster edge and to
# survive stalls, without ever re-downloading the bytes we already have.
_DL_WINDOW = 6.0            # seconds per throughput sample
_DL_MIN_SPEED = 300 * 1024  # below this for a full window → reconnect
_DL_MAX_STUCK = 6           # consecutive no-progress reconnects before giving up


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
                            if (win_b / (now - win_t) < _DL_MIN_SPEED
                                    and total and done < total):
                                break            # too slow → reconnect for a faster edge
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
