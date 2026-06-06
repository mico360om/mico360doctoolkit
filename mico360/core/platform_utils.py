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


# --- Recycle Bin / Trash --------------------------------------------------
def _trash_windows(p: Path) -> bool:
    """Send a file to the Recycle Bin via the Win32 shell (recoverable)."""
    import ctypes
    from ctypes import wintypes

    FO_DELETE = 3
    FOF_SILENT = 0x0004
    FOF_NOCONFIRMATION = 0x0010
    FOF_ALLOWUNDO = 0x0040          # the bit that routes to the Recycle Bin
    FOF_NOERRORUI = 0x0400

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = str(p) + "\0\0"      # path list is double-null terminated
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0


def _trash_mac(p: Path) -> bool:
    script = ('tell application "Finder" to delete POSIX file '
              f'"{p}"')
    return subprocess.run(["osascript", "-e", script],
                          capture_output=True).returncode == 0


def _trash_linux(p: Path) -> bool:
    for cmd in (["gio", "trash", "--", str(p)], ["trash", str(p)]):
        try:
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                return True
        except FileNotFoundError:
            continue
    return False


def move_to_trash(path) -> bool:
    """Send a file to the Recycle Bin / Trash (recoverable), returning True on
    success. Tries send2trash if present, then a per-OS fallback. Never raises."""
    p = Path(path)
    if not p.exists():
        return False
    try:
        from send2trash import send2trash
        send2trash(str(p))
        return True
    except Exception:
        pass
    try:
        if IS_WINDOWS:
            return _trash_windows(p)
        if IS_MAC:
            return _trash_mac(p)
        return _trash_linux(p)
    except Exception:
        return False
