"""Filesystem path helpers that work both from source and from a PyInstaller bundle."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_root() -> Path:
    """Directory containing bundled resources / the executable."""
    if is_frozen():
        # PyInstaller extracts to sys._MEIPASS at runtime; data files live there.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource (icons, logo, etc.)."""
    return app_root().joinpath("mico360", "resources", *parts)


def vendor_path(*parts: str) -> Path:
    """Resolve a bundled third-party binary (Ghostscript / LibreOffice)."""
    return app_root().joinpath("vendor", *parts)


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    d = Path(base) / "MICO360" / "DocToolkit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = user_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_output_dir() -> Path:
    """The default output folder path. NOTE: this only computes the path; it does
    NOT create it. Creating it eagerly at startup could block for seconds if
    Documents is redirected to a syncing/offline OneDrive folder — the actual
    directory is created lazily by the processors when the first file is written.
    """
    return Path.home() / "Documents" / "MICO360 Doc Toolkit"
