"""Small cross-platform helpers (Windows / macOS / Linux).

Keeps OS-specific calls (revealing a file in the file manager, opening a folder,
launching an installer) in one place so the rest of the app stays portable.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MAC


def reveal_command(path) -> list[str] | None:
    """The argv to reveal ``path`` in the OS file manager (None ⇒ use os.startfile
    on Windows). Pure — no side effects — so it's easy to test."""
    p = Path(path)
    if sys.platform.startswith("win"):
        return ["explorer", "/select,", str(p)] if p.is_file() else ["explorer", str(p)]
    if sys.platform == "darwin":
        return ["open", "-R", str(p)] if p.is_file() else ["open", str(p)]
    return ["xdg-open", str(p if p.is_dir() else p.parent)]


def open_command(path) -> list[str] | None:
    """The argv to open ``path`` with its default app (None ⇒ os.startfile)."""
    if sys.platform.startswith("win"):
        return None
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    return [opener, str(Path(path))]


def reveal(path) -> None:
    """Show a file (or folder) in the OS file manager, selecting it when possible:
    Explorer on Windows, Finder on macOS, the default handler on Linux."""
    try:
        subprocess.Popen(reveal_command(path))
    except Exception:
        pass


def open_path(path) -> None:
    """Open a file or folder with its default application."""
    try:
        cmd = open_command(path)
        if cmd is None:
            os.startfile(str(Path(path)))  # type: ignore[attr-defined]  # noqa: S606
        else:
            subprocess.Popen(cmd)
    except Exception:
        pass
