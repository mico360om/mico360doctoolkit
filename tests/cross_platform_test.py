"""Cross-platform behaviour: the updater picks the right installer per OS
(.dmg on macOS, .exe on Windows) and the file-manager commands are correct for
each platform. Pure logic — runs anywhere.

Run:  python tests/cross_platform_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


class as_platform:
    """Temporarily pretend we're on another OS (functions read sys.platform live)."""
    def __init__(self, plat):
        self.plat = plat

    def __enter__(self):
        self._old = sys.platform
        sys.platform = self.plat

    def __exit__(self, *a):
        sys.platform = self._old


def main() -> int:
    from mico360 import updater
    from mico360.core import platform_utils as pu

    assets = [
        {"name": "MICO360-DocToolkit-Setup-6.1.1.exe", "browser_download_url": "u/win"},
        {"name": "MICO360-DocToolkit-Setup-Latest.exe", "browser_download_url": "u/winL"},
        {"name": "MICO360-DocToolkit-6.1.1.dmg", "browser_download_url": "u/mac"},
        {"name": "MICO360-DocToolkit-Latest.dmg", "browser_download_url": "u/macL"},
    ]

    # --- installer selection per OS -------------------------------------
    with as_platform("win32"):
        check("Windows installs .exe", updater._installer_ext() == ".exe")
        pick = updater._pick_installer(assets)
        check("Windows picks the versioned .exe (not Latest)",
              pick and pick["name"].endswith(".exe") and "latest" not in pick["name"].lower(),
              pick and pick["name"])
    with as_platform("darwin"):
        check("macOS installs .dmg", updater._installer_ext() == ".dmg")
        pick = updater._pick_installer(assets)
        check("macOS picks the versioned .dmg (not Latest)",
              pick and pick["name"].endswith(".dmg") and "latest" not in pick["name"].lower(),
              pick and pick["name"])

    # falls back to the -Latest copy when no versioned asset exists
    latest_only = [a for a in assets if "latest" in a["name"].lower()]
    with as_platform("darwin"):
        check("macOS falls back to -Latest.dmg if that's all there is",
              updater._pick_installer(latest_only)["name"].endswith("Latest.dmg"))

    # --- file-manager commands per OS -----------------------------------
    f = Path(__file__)                         # an existing file
    d = f.parent                               # an existing dir
    with as_platform("win32"):
        check("Windows reveal selects the file in Explorer",
              pu.reveal_command(f)[:2] == ["explorer", "/select,"])
        check("Windows open uses os.startfile (cmd is None)",
              pu.open_command(d) is None)
    with as_platform("darwin"):
        check("macOS reveal uses `open -R` for a file",
              pu.reveal_command(f)[:2] == ["open", "-R"])
        check("macOS open uses `open`", pu.open_command(d)[0] == "open")
    with as_platform("linux"):
        check("Linux uses xdg-open", pu.open_command(d)[0] == "xdg-open"
              and pu.reveal_command(f)[0] == "xdg-open")

    # --- checksum sidecar must match the picked installer per OS --------
    # (regression guard: a release with BOTH a .exe and a .dmg sidecar must not
    #  cross-wire the hashes, or the integrity check would block valid updates.)
    # Mirrors the real release layout: the macOS checksum uses a .sha256.TXT
    # extension so it can't be mistaken for the Windows installer's by an older
    # "grab any .sha256" updater — but our updater accepts either extension.
    rel = {
        "tag_name": "v9.9.9", "html_url": "x", "body": "",
        "assets": [
            {"name": "MICO360-DocToolkit-macos-9.9.9.dmg", "browser_download_url": "u/dmg"},
            {"name": "MICO360-DocToolkit-macos-9.9.9.dmg.sha256.txt", "browser_download_url": "u/dmgsha"},
            {"name": "MICO360-DocToolkit-Setup-9.9.9.exe", "browser_download_url": "u/exe"},
            {"name": "MICO360-DocToolkit-Setup-9.9.9.exe.sha256", "browser_download_url": "u/exesha"},
        ],
    }
    # An OLD "grab any .sha256" updater on Windows must only ever see the .exe's
    # checksum (the dmg's is .sha256.txt) — otherwise it cross-wires the hashes.
    only_sha256 = [a for a in rel["assets"] if a["name"].lower().endswith(".sha256")]
    check("only the .exe ships a bare .sha256 (old Windows updaters stay correct)",
          len(only_sha256) == 1 and only_sha256[0]["name"].endswith(".exe.sha256"),
          [a["name"] for a in only_sha256])
    real_newer, real_get = updater.is_newer, updater._get
    updater.is_newer = lambda *a, **k: True
    updater._get = lambda url, timeout=20: (
        ("a" * 64 + "  file") if "exesha" in url else ("b" * 64 + "  file")).encode()
    try:
        with as_platform("win32"):
            i = updater.check_for_update(json_fetcher=lambda url: rel)
            check("Windows update verifies against the .exe's own sha256",
                  i and i.asset_name.endswith(".exe") and i.sha256 == "a" * 64, i and i.sha256)
        with as_platform("darwin"):
            i = updater.check_for_update(json_fetcher=lambda url: rel)
            check("macOS update verifies against the .dmg's own sha256",
                  i and i.asset_name.endswith(".dmg") and i.sha256 == "b" * 64, i and i.sha256)
    finally:
        updater.is_newer, updater._get = real_newer, real_get

    # --- theme detection returns a valid value on this OS ---------------
    from mico360.theme import system_theme
    check("system_theme() returns light/dark", system_theme() in ("light", "dark"),
          system_theme())

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All cross-platform checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
