"""Auto-update via the GitHub Releases API.

The "manifest" is simply the repo's *latest release*: its tag is the version, its
body is the release notes, and its assets contain the installer (Setup .exe) plus
a ``<setup>.sha256`` sidecar for integrity verification. The sidecar is REQUIRED:
an installer whose checksum can't be fetched is never downloaded or launched.

Flow: check_for_update() -> (if newer) download() the installer with progress and
SHA-256 verification -> apply_and_exit() runs the installer silently, which closes
the running app and upgrades it in place (the Inno Setup AppId is stable).

Downloads go to a stable per-user folder (``updates_dir()``) so an interrupted or
retried download resumes its ``.part`` file; cleanup_downloads() removes stale
installers/partials from it after a later successful check.

Uses only the Python standard library (no extra dependency).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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
# Per-tag asset host: releases/download/<tag>/<asset>. The Atom fallback uses this
# so the installer it downloads is exactly the version it announced.
DOWNLOAD_TAG_BASE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/"
_HEADERS = {"User-Agent": f"MICO360-Doc-Toolkit/{__version__}",
            "Accept": "application/vnd.github+json"}
_CHUNK = 1 << 20          # 1 MB reads — fewer loop iterations on a fast link


@dataclass
class UpdateInfo:
    version: str          # clean, e.g. "5.1.0"
    url: str              # installer download URL
    asset_name: str       # installer file name
    sha256: str | None    # expected hash (None = not fetched yet / no sidecar)
    notes: str            # release notes (markdown)
    page: str             # human release page
    size: int = 0         # installer size in bytes (0 = unknown)
    published_at: str = ""  # ISO release date (may be "" via the Atom fallback)
    sha256_url: str = ""  # where the checksum sidecar lives (re-fetched by
                          # download() if the check couldn't read it)


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
    ("improvement", "other"), ("enhancement", "other"), ("reliab", "other"),
    ("performance", "other"), ("accessib", "other"), ("change", "other"),
)


def categorize_notes(notes: str) -> dict:
    """Split release-notes markdown into {'features','fixes','security','other'}
    lists of plain-text bullet lines. Uses section headers when present, else
    classifies each bullet by keywords — so the UI can show 'New features',
    'Bugs fixed' and 'Security improvements' separately."""
    buckets = {"features": [], "fixes": [], "security": [], "other": []}
    current = None
    seen_version = False
    last_bucket = None          # where the previous bullet went (for wrapped lines)
    for raw in (notes or "").splitlines():
        line = raw.strip()
        if not line:
            last_bucket = None
            continue
        # Only THIS release's notes: stop at a horizontal rule or at a second
        # version heading (older releases appended below).
        if line in ("---", "***", "___"):
            break
        if raw.lstrip().startswith("#") and re.search(r"\bv?\d+\.\d+(\.\d+)?\b", line):
            if seen_version:
                break
            seen_version = True
            continue
        # A wrapped bullet: an indented line right after a bullet belongs to it.
        if (last_bucket is not None and raw[:1] in (" ", "\t")
                and not re.match(r"^\s*[-*•]\s+", raw)):
            extra = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            extra = re.sub(r"[*_`]", "", extra).strip()
            if extra and buckets[last_bucket]:
                buckets[last_bucket][-1] += " " + extra
            continue
        last_bucket = None
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
        last_bucket = bucket
    return buckets


# --- version helpers -----------------------------------------------------
def clean_version(tag: str) -> str:
    return (tag or "").strip().lstrip("vV").strip()


# major[.minor[.patch]] followed by an optional suffix: "-rc2", "beta1", "+build".
_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$")


def _split_version(s: str) -> tuple[tuple[int, int, int], str]:
    """-> ((major, minor, patch), pre-release suffix or '')."""
    m = _VERSION_RE.match(clean_version(s))
    if not m:
        return (0, 0, 0), ""
    nums = tuple(int(g) if g else 0 for g in m.group(1, 2, 3))
    rest = m.group(4).strip()
    # "+build" metadata doesn't change precedence (SemVer); a further ".N"
    # component isn't a pre-release either. Anything else ("-rc2", "beta",
    # "a1") marks a pre-release of that version.
    rest = rest.split("+", 1)[0]
    if not rest or rest.startswith("."):
        return nums, ""  # type: ignore[return-value]
    return nums, rest.lstrip("-_. ").lower()  # type: ignore[return-value]


def parse_version(s: str) -> tuple[int, int, int]:
    """(major, minor, patch) — the numeric part only, so "7.4.0-rc2" gives
    (7, 4, 0), never (7, 4, 2). Use version_key()/is_newer() to ORDER versions:
    they also rank a pre-release below its final release."""
    return _split_version(s)[0]


def is_prerelease(s: str) -> bool:
    """True for tags like v7.4.0-rc1 / 7.4.0-beta / 7.4.0a1."""
    return bool(_split_version(s)[1])


def version_key(s: str) -> tuple:
    """Sort key: 7.4.0-alpha < 7.4.0-beta < 7.4.0-rc2 < 7.4.0-rc10 < 7.4.0 < 7.4.1
    (and 7.10.0 > 7.9.0)."""
    nums, pre = _split_version(s)
    if not pre:
        return (*nums, 1, ())
    ids = tuple((0, int(tok), "") if tok.isdigit() else (1, 0, tok)
                for tok in re.findall(r"\d+|[a-z]+", pre))
    return (*nums, 0, ids)


def is_newer(remote: str, local: str = __version__) -> bool:
    return version_key(remote) > version_key(local)


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


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _is_sha256(value: str | None) -> bool:
    return bool(value) and bool(_SHA256_RE.match(str(value).strip().lower()))


def _fetch_sha256(url: str, attempts: int = 2) -> str | None:
    """Read a ``<hash>  <file>`` checksum sidecar; retry once on a transient
    failure. Returns the lower-case hex digest, or None if it can't be had."""
    if not url:
        return None
    for i in range(max(1, attempts)):
        try:
            tokens = _get(url).decode("utf-8", "replace").split()
            token = tokens[0].strip().lower() if tokens else ""
            if _is_sha256(token):
                return token
            return None            # fetched but malformed — retrying won't help
        except Exception:
            if i + 1 < attempts:
                time.sleep(0.5)
    return None


def _latest_tag_via_atom(timeout: int = 20) -> str | None:
    """Read the newest STABLE release tag from the repo's Atom feed (github.com,
    not the rate-limited api.github.com).

    The feed lists pre-releases too (v7.4.0-rc1, …), which the stable channel
    must never offer, so those are skipped; of the remaining tags the highest
    version wins (not merely the first entry)."""
    raw = _get(ATOM_FEED, timeout).decode("utf-8", "replace")
    # Each entry links to …/releases/tag/<tag>.
    tags: list[str] = []
    for tag in re.findall(r"/releases/tag/([^\"'<>\s]+)", raw):
        tag = urllib.parse.unquote(tag)
        if tag not in tags:
            tags.append(tag)
    stable = [t for t in tags
              if _VERSION_RE.match(clean_version(t)) and not is_prerelease(t)]
    if not stable:
        return None
    return max(stable, key=version_key)


def _versioned_asset_names(version: str) -> tuple[str, str]:
    """The installer + checksum names a release ``version`` ships for this OS
    (build/installer.iss and .github/workflows/build-macos.yml produce these)."""
    if _installer_ext() == ".dmg":
        name = f"MICO360-DocToolkit-macos-{version}.dmg"
        return name, name + ".sha256.txt"
    name = f"MICO360-DocToolkit-Setup-{version}.exe"
    return name, name + ".sha256"


def _head_size(url: str) -> int:
    """The API gave us nothing, so the size is unknown on the Atom path — fetch
    it cheaply with a HEAD request so the UI can still show it (0 = unknown)."""
    try:
        req = urllib.request.Request(url, headers=_HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return int(resp.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def _check_via_atom() -> UpdateInfo | None:
    """API-free update check: get the latest stable tag from the Atom feed and
    build the install info from that tag's own releases/download/<tag>/ URLs —
    so the installer (and its checksum) is exactly the announced version. Used
    when the API is unreachable (rate-limited / firewalled)."""
    tag = _latest_tag_via_atom()
    if not tag or not is_newer(tag):
        return None
    version = clean_version(tag)
    name, sidecar_name = _versioned_asset_names(version)
    base = DOWNLOAD_TAG_BASE + urllib.parse.quote(tag, safe="") + "/"
    sha_url = base + sidecar_name
    sha = _fetch_sha256(sha_url)
    return UpdateInfo(
        version=version,
        url=base + name,
        asset_name=name,
        sha256=sha,
        notes="",
        page=f"{REPO_URL}/releases/tag/{urllib.parse.quote(tag, safe='')}",
        size=_head_size(base + name),
        published_at="",
        sha256_url=sha_url,
    )


def check_for_update(json_fetcher=_get_json) -> UpdateInfo | None:
    """Return UpdateInfo if the latest GitHub release is newer, else None.

    Tries the GitHub API first; if that fails (rate limit / firewall / TLS), falls
    back to the Atom feed + per-tag download URLs so the check still works on PCs
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
    # Match the checksum sidecar to THIS installer only. A blanket
    # "any .sha256" match would grab the wrong file's hash on a release that
    # ships both a .exe and a .dmg (each with its own sidecar) — which would
    # then fail the integrity check and block a perfectly good update.
    want = (name.lower() + ".sha256", name.lower() + ".sha256.txt")
    sidecar = next((a for a in assets
                    if str(a.get("name", "")).lower() in want), None)
    sha_url = str(sidecar.get("browser_download_url") or "") if sidecar else ""
    # No sidecar / unreadable sidecar leaves sha256 None: the update is still
    # reported, but download() refuses to fetch or run it unverified.
    sha = _fetch_sha256(sha_url) if sha_url else None
    return UpdateInfo(
        version=clean_version(tag),
        url=installer["browser_download_url"],
        asset_name=name,
        sha256=sha,
        notes=str(data.get("body", "") or ""),
        page=data.get("html_url") or RELEASES_PAGE,
        size=int(installer.get("size") or 0),
        published_at=str(data.get("published_at") or ""),
        sha256_url=sha_url,
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


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest().lower()


def _read_token(path: str) -> str:
    try:
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            tokens = fh.read().split()
        return tokens[0].strip().lower() if tokens else ""
    except OSError:
        return ""


# --- stable download folder ------------------------------------------------
# A fixed per-user folder (not a fresh temp dir per attempt) so Retry — or the
# next launch — resumes the ``.part`` file instead of starting from zero, and so
# old installers don't pile up in %TEMP%.
_KEEP_RECENT_SECS = 15 * 60   # never delete a finished installer younger than this
                              # (it may be the one being installed right now)


def updates_dir() -> str:
    """The per-user folder update downloads live in (created on demand)."""
    from mico360.paths import user_data_dir
    d = os.path.join(str(user_data_dir()), "updates")
    os.makedirs(d, exist_ok=True)
    return d


def cleanup_downloads(keep_asset: str | None = None, dest_dir: str | None = None,
                      min_age: float = _KEEP_RECENT_SECS) -> int:
    """Delete stale installers / partial downloads from the updates folder.

    ``keep_asset`` (the installer currently on offer) and its ``.part`` companions
    are kept so a pending download can still resume. Finished installers touched
    within ``min_age`` seconds are kept too — one may be running right now (a
    file that's locked by a running installer simply fails to delete). Returns
    the number of files removed; never raises."""
    removed = 0
    try:
        d = dest_dir or updates_dir()
        names = os.listdir(d)
    except OSError:
        return 0
    keep = (keep_asset or "").lower()
    now = time.time()
    for name in names:
        low = name.lower()
        if keep and (low == keep or low.startswith(keep + ".")):
            continue
        full = os.path.join(d, name)
        try:
            if not os.path.isfile(full):
                continue
            partial = low.endswith(".part") or low.endswith(".part.sha256")
            if not partial and now - os.path.getmtime(full) < min_age:
                continue
            os.remove(full)
            removed += 1
        except OSError:
            pass
    return removed


# Installers download() has verified in this process: normcase(path) ->
# (sha256, size, mtime_ns). apply_and_exit() refuses anything not in here (or
# not matching an explicitly supplied hash).
_VERIFIED: dict[str, tuple[str, int, int]] = {}


def _mark_verified(path: str, sha: str) -> None:
    st = os.stat(path)
    _VERIFIED[os.path.normcase(os.path.abspath(path))] = (sha.lower(), st.st_size,
                                                          st.st_mtime_ns)


def is_verified(path: str, sha256: str | None = None) -> bool:
    """True if ``path`` is an installer whose SHA-256 has been checked — by
    download() in this session (and unchanged since), or against ``sha256``."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    rec = _VERIFIED.get(os.path.normcase(os.path.abspath(path)))
    want = (sha256 or "").strip().lower()
    if (rec and rec[1] == st.st_size and rec[2] == st.st_mtime_ns
            and (not want or rec[0] == want)):
        return True
    if _is_sha256(want):
        try:
            return _sha256_file(path) == want
        except OSError:
            return False
    return False


_NO_CHECKSUM_MSG = (
    "The update's checksum file couldn't be retrieved, so its integrity can't be "
    "verified and it won't be installed. Please try again later, or download it "
    "from the Releases page.")


def _require_sha256(info: UpdateInfo) -> str:
    """The expected hash for ``info`` — re-fetching the sidecar if the update
    check couldn't read it. Raises if there's no usable checksum: an installer is
    never downloaded as "verified", or run, without one."""
    sha = (info.sha256 or "").strip().lower()
    if not _is_sha256(sha) and info.sha256_url:
        sha = _fetch_sha256(info.sha256_url) or ""
        if sha:
            info.sha256 = sha
    if not _is_sha256(sha):
        raise RuntimeError(_NO_CHECKSUM_MSG)
    return sha


def _total_from_content_range(value: str | None) -> int | None:
    """'bytes 0-99/1234' or 'bytes */1234' -> 1234 (None if unknown)."""
    if value and "/" in value:
        tail = value.rsplit("/", 1)[-1].strip()
        if tail.isdigit():
            return int(tail)
    return None


def download(info: UpdateInfo, dest_dir: str | None = None,
             progress=None, is_cancelled=None) -> str:
    """Download the installer (resumable) and verify its SHA-256.

    The checksum is mandatory: if it is unknown and can't be (re)fetched this
    raises before downloading anything. The download survives a flaky/variable
    connection: it writes to a ``.part`` file in ``dest_dir`` (default: the stable
    updates_dir(), so a Retry resumes) and, on a stall, drop, or a sustained-slow
    window, reconnects with an HTTP ``Range`` request to resume from where it left
    off (and to grab a faster CDN edge). ``progress(done, total)`` and
    ``is_cancelled() -> bool`` are optional. Returns the final, verified file
    path; raises on cancellation, missing checksum or checksum failure.
    """
    expected = _require_sha256(info)
    dest_dir = dest_dir or updates_dir()
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, info.asset_name)
    part = path + ".part"
    meta = part + ".sha256"      # which file the .part belongs to

    # Already downloaded and intact (e.g. the installer didn't get to run)?
    if os.path.exists(path):
        try:
            if _sha256_file(path) == expected:
                _mark_verified(path, expected)
                if progress:
                    size = os.path.getsize(path)
                    progress(size, size)
                return path
        except OSError:
            pass
        _safe_remove(path)
    # Only resume a .part of the SAME file; one from another build is discarded.
    if os.path.exists(part):
        prev = _read_token(meta)
        if prev and prev != expected:
            _safe_remove(part)
    try:
        with open(meta, "w", encoding="ascii") as fh:
            fh.write(expected)
    except OSError:
        pass

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
        eof = False           # this round's body ended cleanly (server closed it)
        try:
            req = urllib.request.Request(info.url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                ranged = getattr(resp, "status", 200) == 206
                if existing and not ranged:      # server ignored Range → restart
                    existing = 0
                if total is None:
                    total = _total_from_content_range(resp.headers.get("Content-Range"))
                    if total is None:
                        length = int(resp.headers.get("Content-Length") or 0)
                        total = (existing + length) if length else None
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
                            eof = True
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
            # Keep the .part (and its marker) so Retry resumes; stale partials
            # are swept by cleanup_downloads() after a later check.
            raise RuntimeError("Update cancelled.")
        except urllib.error.HTTPError as exc:
            eof = False
            if exc.code == 416 and existing:
                # Range not satisfiable: the .part is already complete (the app
                # stopped before verifying it) — or it's longer than the file.
                full = _total_from_content_range(
                    exc.headers.get("Content-Range") if exc.headers else None)
                if full and existing == full:
                    total = full
                    break
                _safe_remove(part)               # bogus partial → start clean
                continue
            if exc.code in (404, 410):           # the asset isn't there — no retry
                raise RuntimeError(
                    "The update file wasn't found on the server. Please download "
                    "it from the Releases page.")
        except Exception:                        # network blip → resume & retry
            eof = False

        new_size = os.path.getsize(part) if os.path.exists(part) else 0
        if total and new_size >= total:
            break
        if total is None and eof and new_size > 0:
            # No Content-Length: the only end-of-file signal is the server
            # closing the body cleanly. The checksum below still guards it.
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

    if _sha256_file(part) != expected:
        _safe_remove(part)
        _safe_remove(meta)
        raise RuntimeError("The downloaded update failed its integrity check "
                           "and was discarded. Please try again later.")
    os.replace(part, path)
    _safe_remove(meta)
    _mark_verified(path, expected)
    return path


def apply_and_exit(setup_path: str, sha256: str | None = None) -> None:
    """Start installing the downloaded update, then let the app quit.

    Refuses (raises) unless ``setup_path`` passed its SHA-256 check — verified by
    download() in this session, or against ``sha256`` — so an unverified
    installer is never launched.

    * Windows — run the Inno Setup installer silently; it closes the running app,
      upgrades in place, and relaunches it. The user approves the standard UAC
      prompt.
    * macOS — open the downloaded ``.dmg`` so the user can drag the new app into
      Applications (the standard, signing-free update flow).
    """
    if not is_verified(setup_path, sha256):
        raise RuntimeError("The installer hasn't passed its checksum check, so it "
                           "won't be started. Please download the update again.")
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
