"""Locate external binaries (Ghostscript, LibreOffice).

Resolution order:
  1. An explicit path saved in Settings.
  2. A copy bundled with the app under ``vendor/``.
  3. The system PATH / well-known install locations.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from mico360.config import settings
from mico360.paths import vendor_path


# --- Ghostscript ---------------------------------------------------------
_GS_NAMES = ["gswin64c.exe", "gswin32c.exe", "gs"]


def find_ghostscript() -> str | None:
    saved = settings.ghostscript_path
    if saved and Path(saved).exists():
        return saved

    # Bundled
    for name in _GS_NAMES:
        cand = vendor_path("ghostscript", "bin", name)
        if cand.exists():
            return str(cand)

    # PATH
    for name in _GS_NAMES:
        found = shutil.which(name)
        if found:
            return found

    # Well-known install dirs
    for base in (r"C:\Program Files\gs", r"C:\Program Files (x86)\gs"):
        p = Path(base)
        if p.exists():
            for sub in sorted(p.glob("gs*/bin/gswin64c.exe"), reverse=True):
                return str(sub)
            for sub in sorted(p.glob("gs*/bin/gswin32c.exe"), reverse=True):
                return str(sub)
    return None


# --- LibreOffice ---------------------------------------------------------
def find_libreoffice() -> str | None:
    saved = settings.libreoffice_path
    if saved and Path(saved).exists():
        return saved

    cand = vendor_path("libreoffice", "program", "soffice.exe")
    if cand.exists():
        return str(cand)

    for name in ("soffice.exe", "soffice.com", "soffice"):
        found = shutil.which(name)
        if found:
            return found

    for base in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if os.path.exists(base):
            return base
    return None


def dependency_status() -> dict[str, str | None]:
    return {
        "ghostscript": find_ghostscript(),
        "libreoffice": find_libreoffice(),
    }
