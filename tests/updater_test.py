"""Tests for the GitHub-manifest auto-updater (mico360.updater).

Covers version parsing/compare, release-manifest parsing with an injected JSON
fetcher (no network), installer-asset selection, and download + SHA-256
verification over a local file:// URL (also no network).

Run:  python tests/updater_test.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mico360 import updater
from mico360.updater import UpdateInfo

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _fake_release(tag: str, assets: list[dict]) -> dict:
    return {"tag_name": tag, "name": tag, "body": "## Notes\n- thing",
            "html_url": "https://example/releases/tag/" + tag, "assets": assets}


def _asset(name: str, url: str = "http://x/none") -> dict:
    return {"name": name, "browser_download_url": url}


def main() -> int:
    # --- version helpers ------------------------------------------------
    check("clean_version strips v", updater.clean_version("v5.1.0") == "5.1.0")
    check("parse_version pads", updater.parse_version("5") == (5, 0, 0))
    check("parse_version 3 parts", updater.parse_version("v5.2.3") == (5, 2, 3))
    check("is_newer patch", updater.is_newer("5.0.1", "5.0.0") is True)
    check("is_newer minor", updater.is_newer("5.1.0", "5.0.9") is True)
    check("is_newer major", updater.is_newer("6.0.0", "5.9.9") is True)
    check("not newer equal", updater.is_newer("5.0.0", "5.0.0") is False)
    check("not newer older", updater.is_newer("4.9.9", "5.0.0") is False)

    # --- check_for_update: up to date -----------------------------------
    same = _fake_release("v5.0.0", [_asset("MICO360-DocToolkit-Setup-5.0.0.exe")])
    check("up-to-date returns None",
          updater.check_for_update(lambda url: same) is None)

    # --- check_for_update: newer, picks Setup exe over onefile ----------
    # Use a far-future tag so this stays "newer" regardless of the app version.
    newer = _fake_release("v9.9.9", [
        _asset("MICO360DocToolkit.exe", "http://x/onefile.exe"),
        _asset("MICO360-DocToolkit-Setup-9.9.9.exe", "http://x/setup.exe"),
    ])
    info = updater.check_for_update(lambda url: newer)
    check("newer returns UpdateInfo", isinstance(info, UpdateInfo))
    check("version parsed", info and info.version == "9.9.9", str(info and info.version))
    check("prefers Setup installer", info and info.url == "http://x/setup.exe",
          str(info and info.url))
    check("notes carried", info and "thing" in info.notes)
    check("no sidecar -> sha None", info and info.sha256 is None)

    # --- newer but no exe asset -> None ---------------------------------
    noexe = _fake_release("v9.9.9", [_asset("notes.txt")])
    check("no installer asset returns None",
          updater.check_for_update(lambda url: noexe) is None)

    # --- size + release date + note categorisation ----------------------
    rich = {
        "tag_name": "v9.9.9", "name": "v9.9.9",
        "published_at": "2026-06-07T12:00:00Z", "html_url": "https://x",
        "body": ("**New features**\n- Cool new thing\n- Another feature\n"
                 "**Bugs fixed**\n- Fixed the resize crash\n"
                 "**Security improvements**\n- Signed the installer"),
        "assets": [{"name": "MICO360-DocToolkit-Setup-9.9.9.exe",
                    "browser_download_url": "http://x/s.exe", "size": 12345678}],
    }
    info3 = updater.check_for_update(lambda url: rich)
    check("UpdateInfo carries the asset size", info3 and info3.size == 12345678,
          str(info3 and info3.size))
    check("UpdateInfo carries the release date",
          info3 and info3.published_at.startswith("2026-06-07"))
    check("format_release_date is friendly",
          updater.format_release_date("2026-06-07T12:00:00Z") == "June 07, 2026",
          updater.format_release_date("2026-06-07T12:00:00Z"))
    cats = updater.categorize_notes(rich["body"])
    check("categorize: 2 new features", cats["features"] == ["Cool new thing", "Another feature"],
          str(cats["features"]))
    check("categorize: bug fix", cats["fixes"] == ["Fixed the resize crash"],
          str(cats["fixes"]))
    check("categorize: security", cats["security"] == ["Signed the installer"],
          str(cats["security"]))

    # --- Atom fallback when the GitHub API is unreachable ---------------
    # (rate-limited / firewalled api.github.com). The check must still work via
    # the Atom feed + stable releases/latest/download URLs.
    import urllib.error
    atom = (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
        '<entry><id>tag:github.com,2008:Repository/1/v9.9.9</id>'
        '<link rel="alternate" type="text/html" '
        'href="https://github.com/mico360om/mico360doctoolkit/releases/tag/v9.9.9"/>'
        '</entry></feed>')
    real_get = updater._get

    def fake_get(url, timeout=20):
        if "api.github.com" in url:
            raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)
        if url.endswith("releases.atom"):
            return atom.encode("utf-8")
        if url.endswith(".sha256") or url.endswith(".sha256.txt"):
            return (b"f" * 64) + b"  MICO360-DocToolkit-Setup-Latest.exe"
        raise urllib.error.URLError("unexpected url " + url)

    updater._get = fake_get
    try:
        info2 = updater.check_for_update()   # default fetcher -> hits fake_get
    finally:
        updater._get = real_get
    check("API failure falls back to Atom feed", isinstance(info2, UpdateInfo))
    check("Atom fallback parses the latest tag",
          info2 and info2.version == "9.9.9", str(info2 and info2.version))
    check("Atom fallback uses the stable download URL",
          info2 and info2.url == updater.DOWNLOAD_BASE + info2.asset_name,
          str(info2 and info2.url))
    check("Atom fallback reads the checksum sidecar",
          info2 and info2.sha256 == "f" * 64, str(info2 and info2.sha256))

    # An injected (test) fetcher that raises must NOT trigger the network fallback.
    def boom(url):
        raise RuntimeError("boom")
    raised_passthrough = False
    try:
        updater.check_for_update(boom)
    except RuntimeError:
        raised_passthrough = True
    check("injected fetcher errors propagate (no surprise network)",
          raised_passthrough)

    # --- download + sha256 verify (file:// URL, no network) -------------
    payload = b"PRETEND INSTALLER BYTES" * 5000
    src = Path(tempfile.mkdtemp(prefix="mico360_src_")) / "Setup.exe"
    src.write_bytes(payload)
    good_sha = hashlib.sha256(payload).hexdigest()
    file_url = src.as_uri()

    seen = {"max": 0}
    di = UpdateInfo("5.1.0", file_url, "Setup.exe", good_sha, "", "http://x")
    out = updater.download(di, progress=lambda d, t: seen.__setitem__("max", d))
    check("download wrote file", os.path.exists(out))
    check("download size matches", os.path.getsize(out) == len(payload))
    check("progress reported", seen["max"] == len(payload), str(seen["max"]))

    # bad hash -> raises and removes file
    bad = UpdateInfo("5.1.0", file_url, "Setup.exe", "deadbeef" * 8, "", "http://x")
    raised = False
    try:
        updater.download(bad, dest_dir=tempfile.mkdtemp(prefix="mico360_bad_"))
    except RuntimeError:
        raised = True
    check("bad checksum raises", raised)

    # cancellation -> raises
    cancelled = False
    try:
        updater.download(di, dest_dir=tempfile.mkdtemp(prefix="mico360_cxl_"),
                         is_cancelled=lambda: True)
    except RuntimeError:
        cancelled = True
    check("cancellation raises", cancelled)

    # --- config setting round-trips -------------------------------------
    from mico360.config import settings
    prev = settings.auto_check_updates
    settings.auto_check_updates = False
    check("auto_check_updates persists", settings.auto_check_updates is False)
    settings.auto_check_updates = prev

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All updater checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
