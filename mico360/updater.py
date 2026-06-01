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


def _pick_installer(assets: list[dict]) -> dict | None:
    exes = [a for a in assets if str(a.get("name", "")).lower().endswith(".exe")]
    # Prefer the Setup/installer exe over a standalone one-file exe.
    setup = [a for a in exes if "setup" in str(a.get("name", "")).lower()]
    return (setup or exes or [None])[0]


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
def download(info: UpdateInfo, dest_dir: str | None = None,
             progress=None, is_cancelled=None) -> str:
    """Download the installer to a temp file, verifying its SHA-256 if known.

    ``progress(done, total)`` and ``is_cancelled() -> bool`` are optional.
    Returns the downloaded file path. Raises on cancellation or checksum failure.
    """
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="mico360_update_")
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, info.asset_name)

    req = urllib.request.Request(info.url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as fh:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if is_cancelled and is_cancelled():
                fh.close()
                try:
                    os.remove(path)
                except OSError:
                    pass
                raise RuntimeError("Update cancelled.")
            chunk = resp.read(_CHUNK)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)

    if info.sha256:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest().lower() != info.sha256.lower():
            try:
                os.remove(path)
            except OSError:
                pass
            raise RuntimeError("The downloaded update failed its integrity check "
                               "and was discarded. Please try again later.")
    return path


def apply_and_exit(setup_path: str) -> None:
    """Launch the installer silently (it closes & upgrades the running app), then
    quit so the files can be replaced. The user approves the standard UAC prompt."""
    args = [setup_path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
            "/NOCANCEL"]
    creationflags = 0x08000000 if sys.platform.startswith("win") else 0  # no console
    subprocess.Popen(args, close_fds=True, creationflags=creationflags)


def is_configured() -> bool:
    """False while the GitHub repo placeholders haven't been set to a real repo."""
    return bool(GITHUB_OWNER and GITHUB_REPO) and "/" not in GITHUB_OWNER
