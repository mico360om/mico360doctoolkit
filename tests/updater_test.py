"""Tests for the GitHub-manifest auto-updater (mico360.updater).

Covers version parsing/compare (incl. pre-release ordering), release-manifest
parsing with an injected JSON fetcher (no network), installer-asset selection,
the Atom-feed fallback (pre-release skip + per-tag asset URLs), the mandatory
checksum, download + SHA-256 verification over a local file:// URL (also no
network), and the stable updates folder cleanup.

Isolation: the per-user updates folder is redirected to a temp dir and the app
settings to a temp INI, so running this never touches the real ones.

Run:  python tests/updater_test.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
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


class as_platform:
    def __init__(self, plat):
        self.plat = plat

    def __enter__(self):
        self._old = sys.platform
        sys.platform = self.plat

    def __exit__(self, *a):
        sys.platform = self._old


def _raises(fn, exc=RuntimeError) -> tuple[bool, str]:
    try:
        fn()
    except exc as e:
        return True, str(e)
    return False, ""


def main() -> int:
    # Never touch the real per-user updates folder from a test.
    tmp_updates = tempfile.mkdtemp(prefix="mico360_updates_")
    updater.updates_dir = lambda: tmp_updates

    # --- version helpers ------------------------------------------------
    check("clean_version strips v", updater.clean_version("v5.1.0") == "5.1.0")
    check("parse_version pads", updater.parse_version("5") == (5, 0, 0))
    check("parse_version 3 parts", updater.parse_version("v5.2.3") == (5, 2, 3))
    check("is_newer patch", updater.is_newer("5.0.1", "5.0.0") is True)
    check("is_newer minor", updater.is_newer("5.1.0", "5.0.9") is True)
    check("is_newer major", updater.is_newer("6.0.0", "5.9.9") is True)
    check("not newer equal", updater.is_newer("5.0.0", "5.0.0") is False)
    check("not newer older", updater.is_newer("4.9.9", "5.0.0") is False)

    # --- pre-release ordering (M-32) --------------------------------------
    check("parse_version ignores the rc number (7.4.0-rc2 -> 7.4.0)",
          updater.parse_version("7.4.0-rc2") == (7, 4, 0),
          str(updater.parse_version("7.4.0-rc2")))
    check("7.10.0 > 7.9.0", updater.is_newer("7.10.0", "7.9.0") is True
          and updater.is_newer("7.9.0", "7.10.0") is False)
    check("7.4.0-rc2 < 7.4.0", updater.is_newer("7.4.0", "7.4.0-rc2") is True
          and updater.is_newer("7.4.0-rc2", "7.4.0") is False)
    check("7.4.0 < 7.4.1", updater.is_newer("7.4.1", "7.4.0") is True)
    check("7.4.0-rc2 is newer than 7.3.9",
          updater.is_newer("7.4.0-rc2", "7.3.9") is True)
    check("rc2 < rc10 (numeric, not lexical)",
          updater.is_newer("7.4.0-rc10", "7.4.0-rc2") is True)
    check("alpha < beta < rc",
          updater.version_key("7.4.0-alpha") < updater.version_key("7.4.0-beta")
          < updater.version_key("7.4.0-rc1"))
    order = ["7.4.1", "7.4.0", "v7.4.0-rc2", "7.9.0", "7.10.0", "7.4.0-beta1"]
    want = ["7.4.0-beta1", "v7.4.0-rc2", "7.4.0", "7.4.1", "7.9.0", "7.10.0"]
    got = sorted(order, key=updater.version_key)
    check("full ordering beta < rc < final < patch < 7.9 < 7.10", got == want, str(got))
    check("+build metadata is not a pre-release",
          not updater.is_prerelease("7.4.0+win")
          and not updater.is_newer("7.4.0+win", "7.4.0"))
    check("is_prerelease flags -rc / -beta / -alpha",
          all(updater.is_prerelease(t) for t in ("v7.4.0-rc1", "7.4.0-beta", "7.4.0-alpha2"))
          and not updater.is_prerelease("v7.4.0"))
    check("a final release is not offered over the same final",
          updater.check_for_update(lambda url: _fake_release(
              "v" + updater.__version__, [_asset("MICO360-DocToolkit-Setup-x.exe")])) is None)

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
    check("no sidecar -> no checksum URL either", info and info.sha256_url == "")

    # --- newer but no exe asset -> None ---------------------------------
    noexe = _fake_release("v9.9.9", [_asset("notes.txt")])
    check("no installer asset returns None",
          updater.check_for_update(lambda url: noexe) is None)

    # --- sidecar fetch is retried once (M-30) ---------------------------
    real_get = updater._get
    calls = {"n": 0}

    def flaky_get(url, timeout=20):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient")
        return (b"a" * 64) + b"  MICO360-DocToolkit-Setup-9.9.9.exe"

    with_sidecar = _fake_release("v9.9.9", [
        _asset("MICO360-DocToolkit-Setup-9.9.9.exe", "http://x/setup.exe"),
        _asset("MICO360-DocToolkit-Setup-9.9.9.exe.sha256", "http://x/setup.sha256"),
    ])
    updater._get = flaky_get
    try:
        info_r = updater.check_for_update(lambda url: with_sidecar)
    finally:
        updater._get = real_get
    check("sidecar fetch retried once after a transient failure",
          info_r and info_r.sha256 == "a" * 64 and calls["n"] == 2,
          f"sha={info_r and info_r.sha256} calls={calls['n']}")
    check("sidecar URL is remembered for a later re-fetch",
          info_r and info_r.sha256_url == "http://x/setup.sha256")

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
    # the Atom feed + that tag's own releases/download/<tag>/ URLs, and must
    # skip pre-releases the feed also lists (M-31).
    import urllib.error

    def _entry(tag):
        return ('<entry><id>tag:github.com,2008:Repository/1/' + tag + '</id>'
                '<link rel="alternate" type="text/html" '
                'href="https://github.com/mico360om/mico360doctoolkit/releases/tag/'
                + tag + '"/></entry>')

    feed = {"xml": ""}
    fetched: list[str] = []

    def fake_get(url, timeout=20):
        fetched.append(url)
        if "api.github.com" in url:
            raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)
        if url.endswith("releases.atom"):
            return feed["xml"].encode("utf-8")
        if url.endswith(".sha256") or url.endswith(".sha256.txt"):
            return (b"f" * 64) + b"  " + url.rsplit("/", 1)[-1].encode()
        raise urllib.error.URLError("unexpected url " + url)

    def atom_check(entries, plat="win32"):
        feed["xml"] = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
                       + "".join(_entry(t) for t in entries) + '</feed>')
        fetched.clear()
        real_head = updater._head_size
        updater._get = fake_get
        updater._head_size = lambda url: (fetched.append("HEAD " + url), 4321)[1]
        try:
            with as_platform(plat):
                return updater.check_for_update()   # default fetcher -> fake_get
        finally:
            updater._get = real_get
            updater._head_size = real_head

    # The newest entry is a pre-release: it must be skipped for v9.9.9.
    info2 = atom_check(["v9.9.10-rc1", "v9.9.9", "v9.9.8"])
    check("API failure falls back to Atom feed", isinstance(info2, UpdateInfo))
    check("Atom fallback skips the pre-release and picks the stable tag",
          info2 and info2.version == "9.9.9", str(info2 and info2.version))
    tag_base = updater.DOWNLOAD_TAG_BASE + "v9.9.9/"
    check("Atom fallback downloads the asset OF THAT TAG (not releases/latest)",
          info2 and info2.url == tag_base + "MICO360-DocToolkit-Setup-9.9.9.exe"
          and info2.asset_name == "MICO360-DocToolkit-Setup-9.9.9.exe",
          str(info2 and info2.url))
    check("Atom fallback reads the matching sidecar",
          info2 and info2.sha256 == "f" * 64
          and info2.sha256_url == tag_base + "MICO360-DocToolkit-Setup-9.9.9.exe.sha256",
          str(info2 and info2.sha256_url))
    check("Atom fallback never touches the -Latest asset or releases/latest/download",
          not any("-latest" in u.lower() or "/latest/download/" in u.lower()
                  for u in fetched), str(fetched))
    check("Atom fallback sizes the tag's own asset",
          info2 and info2.size == 4321
          and "HEAD " + tag_base + "MICO360-DocToolkit-Setup-9.9.9.exe" in fetched,
          str(fetched))
    check("Atom fallback page is the tag's release page",
          info2 and info2.page.endswith("/releases/tag/v9.9.9"), str(info2 and info2.page))

    mac = atom_check(["v9.9.9"], plat="darwin")
    check("Atom fallback on macOS picks the tag's .dmg + .sha256.txt",
          mac and mac.url == tag_base + "MICO360-DocToolkit-macos-9.9.9.dmg"
          and mac.sha256_url == tag_base + "MICO360-DocToolkit-macos-9.9.9.dmg.sha256.txt",
          str(mac and mac.url))

    only_pre = atom_check(["v99.0.0-beta2", "v99.0.0-rc1"])
    check("Atom feed with only pre-releases offers no update", only_pre is None,
          str(only_pre and only_pre.version))

    # Highest stable wins even if an older line's hotfix is listed first.
    hot = atom_check(["v9.8.7", "v9.9.9"])
    check("Atom fallback picks the highest stable version",
          hot and hot.version == "9.9.9", str(hot and hot.version))

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
    check("download defaults to the stable updates folder",
          os.path.dirname(os.path.abspath(out)) == os.path.abspath(tmp_updates), out)
    check("download size matches", os.path.getsize(out) == len(payload))
    check("progress reported", seen["max"] == len(payload), str(seen["max"]))
    check("download marks the installer verified", updater.is_verified(out))
    check("no .part / marker left behind",
          not os.path.exists(out + ".part") and not os.path.exists(out + ".part.sha256"))

    # A second download of the same, intact installer is reused (no refetch).
    src.write_bytes(b"CHANGED" * 10)                 # source now differs...
    out_again = updater.download(di)
    check("an intact, already-downloaded installer is reused",
          out_again == out and os.path.getsize(out_again) == len(payload))
    src.write_bytes(payload)

    # bad hash -> raises and removes file
    bad = UpdateInfo("5.1.0", file_url, "Setup.exe", "deadbeef" * 8, "", "http://x")
    bad_dir = tempfile.mkdtemp(prefix="mico360_bad_")
    raised = False
    try:
        updater.download(bad, dest_dir=bad_dir)
    except RuntimeError:
        raised = True
    check("bad checksum raises", raised)
    check("bad checksum leaves no installer or partial",
          not any(n.lower().startswith("setup.exe") for n in os.listdir(bad_dir)),
          str(os.listdir(bad_dir)))

    # --- missing checksum is a hard failure (M-30) ----------------------
    nosha_dir = tempfile.mkdtemp(prefix="mico360_nosha_")
    nosha = UpdateInfo("5.1.0", file_url, "Setup.exe", None, "", "http://x")
    ok, msg = _raises(lambda: updater.download(nosha, dest_dir=nosha_dir))
    check("no checksum at all -> download refuses", ok and "checksum" in msg.lower(), msg)
    check("...and downloads nothing", os.listdir(nosha_dir) == [], str(os.listdir(nosha_dir)))

    sidecar_calls = {"n": 0}

    def dead_get(url, timeout=20):
        sidecar_calls["n"] += 1
        raise urllib.error.URLError("offline")
    unreachable = UpdateInfo("5.1.0", file_url, "Setup.exe", None, "", "http://x",
                             sha256_url="http://x/Setup.exe.sha256")
    updater._get = dead_get
    try:
        ok, msg = _raises(lambda: updater.download(unreachable, dest_dir=nosha_dir))
    finally:
        updater._get = real_get
    check("unfetchable checksum -> download refuses", ok and "checksum" in msg.lower(), msg)
    check("checksum re-fetch is retried once", sidecar_calls["n"] == 2,
          str(sidecar_calls["n"]))

    garbage = UpdateInfo("5.1.0", file_url, "Setup.exe", "not-a-hash", "", "http://x")
    ok, _ = _raises(lambda: updater.download(garbage, dest_dir=nosha_dir))
    check("a malformed checksum is treated as missing", ok)

    late_dir = tempfile.mkdtemp(prefix="mico360_late_")
    late = UpdateInfo("5.1.0", file_url, "Setup.exe", None, "", "http://x",
                      sha256_url="http://x/Setup.exe.sha256")
    updater._get = lambda url, timeout=20: good_sha.encode() + b"  Setup.exe"
    try:
        late_out = updater.download(late, dest_dir=late_dir)
    finally:
        updater._get = real_get
    check("download re-fetches a checksum the check couldn't read",
          os.path.exists(late_out) and late.sha256 == good_sha)

    # --- an unverified installer is never launched -----------------------
    rogue = Path(tempfile.mkdtemp(prefix="mico360_rogue_")) / "Setup.exe"
    rogue.write_bytes(b"not verified")
    ok, msg = _raises(lambda: updater.apply_and_exit(str(rogue)))
    check("apply_and_exit refuses an unverified installer", ok, msg)
    ok, _ = _raises(lambda: updater.apply_and_exit(str(rogue), "0" * 64))
    check("apply_and_exit refuses a hash mismatch", ok)
    check("is_verified accepts a matching explicit hash",
          updater.is_verified(str(rogue), hashlib.sha256(b"not verified").hexdigest()))
    rogue_verified = Path(out)
    rogue_verified.write_bytes(payload[:-1] + b"X")  # tampered after verification
    check("a verified installer modified afterwards is no longer verified",
          not updater.is_verified(str(rogue_verified)))

    # cancellation -> raises
    cancelled = False
    try:
        updater.download(di, dest_dir=tempfile.mkdtemp(prefix="mico360_cxl_"),
                         is_cancelled=lambda: True)
    except RuntimeError:
        cancelled = True
    check("cancellation raises", cancelled)

    # --- stale-download cleanup -------------------------------------------
    cdir = tempfile.mkdtemp(prefix="mico360_clean_")
    old = time.time() - 24 * 3600

    def _mk(name, age_old=True):
        p = os.path.join(cdir, name)
        with open(p, "wb") as fh:
            fh.write(b"x")
        if age_old:
            os.utime(p, (old, old))
        return p
    stale_exe = _mk("MICO360-DocToolkit-Setup-7.2.0.exe")
    stale_part = _mk("MICO360-DocToolkit-Setup-7.3.0.exe.part", age_old=False)
    stale_meta = _mk("MICO360-DocToolkit-Setup-7.3.0.exe.part.sha256", age_old=False)
    fresh_exe = _mk("MICO360-DocToolkit-Setup-7.3.1.exe", age_old=False)
    keep_part = _mk("MICO360-DocToolkit-Setup-9.9.9.exe.part")
    keep_meta = _mk("MICO360-DocToolkit-Setup-9.9.9.exe.part.sha256")
    n = updater.cleanup_downloads(keep_asset="MICO360-DocToolkit-Setup-9.9.9.exe",
                                  dest_dir=cdir)
    check("cleanup removes old installers and other versions' partials",
          not os.path.exists(stale_exe) and not os.path.exists(stale_part)
          and not os.path.exists(stale_meta) and n == 3, f"removed={n}")
    check("cleanup keeps the offered update's partial (so it can resume)",
          os.path.exists(keep_part) and os.path.exists(keep_meta))
    check("cleanup keeps a just-finished installer (may be installing now)",
          os.path.exists(fresh_exe))
    check("cleanup on a missing folder is a safe no-op",
          updater.cleanup_downloads(dest_dir=os.path.join(cdir, "nope")) == 0)

    # --- config setting round-trips (temp INI, never the real settings) ---
    from PySide6.QtCore import QSettings
    from mico360.config import settings
    real_s = settings._s
    settings._s = QSettings(os.path.join(tempfile.mkdtemp(prefix="mico360_ini_"),
                                         "t.ini"), QSettings.IniFormat)
    try:
        settings.auto_check_updates = False
        check("auto_check_updates persists", settings.auto_check_updates is False)
    finally:
        settings._s = real_s

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All updater checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    # Skip Qt's crash-prone offscreen teardown at interpreter shutdown
    # (a lingering C++ object can abort finalization with 0xC0000409,
    #  masking an otherwise-clean pass). Flush and exit with the result.
    import os as _os, sys as _sys
    _sys.stdout.flush(); _sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
