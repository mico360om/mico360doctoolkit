"""Shared helpers for processors: output-path resolution, byte formatting."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

# Output-name allocation runs on multiple QThreadPool workers writing to a shared
# directory. A plain "does it exist? then use it" is a TOCTOU race — two workers
# can pick the same free name and clobber each other. We allocate atomically:
# under a lock we *reserve* the chosen name by creating an empty placeholder
# file (O_EXCL), which the processor then overwrites. This guarantees uniqueness.
_alloc_lock = threading.Lock()


class ProcessError(Exception):
    """Raised when a processing operation fails for a user-actionable reason."""


def _reserve(path: Path) -> bool:
    """Atomically create *path* as an empty placeholder. False if it exists."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        # Fall back to a non-atomic check if the FS rejects O_EXCL.
        if path.exists():
            return False
        return True


def unique_path(path: Path, overwrite: bool) -> Path:
    """Return ``path`` or, if it exists and overwrite is off, a ' (n)' variant.

    Reserves the chosen name atomically so parallel workers never collide.
    """
    if overwrite:
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    with _alloc_lock:
        if _reserve(path):
            return path
        i = 1
        while True:
            cand = parent / f"{stem} ({i}){suffix}"
            if _reserve(cand):
                return cand
            i += 1


def unique_dir(base: Path) -> Path:
    """Create and return *base* as a fresh directory, or a ' (n)' variant if it
    already exists — so per-source output subfolders never collide."""
    with _alloc_lock:
        try:
            base.mkdir(parents=True, exist_ok=False)
            return base
        except FileExistsError:
            pass
        i = 1
        while True:
            cand = base.parent / f"{base.name} ({i})"
            try:
                cand.mkdir(parents=True, exist_ok=False)
                return cand
            except FileExistsError:
                i += 1


def build_output_path(
    src: Path,
    out_dir: Path,
    new_suffix: str,
    *,
    name_suffix: str = "",
    overwrite: bool = False,
    numbered: bool = False,
) -> Path:
    """Compute an output path inside *out_dir* for a given source file.

    new_suffix: target extension, e.g. ".pdf" (leading dot required).
    name_suffix: text inserted before the extension, e.g. "_compressed".
    numbered:   when True (used for "save next to the original files"), keep the
                original name and append " (n)" with the smallest free n >= 1 —
                e.g. ``report (1).pdf`` — so the original is never overwritten and
                no descriptive suffix is added. ``name_suffix`` is ignored.

    The chosen name is reserved atomically (parallel-worker safe).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if numbered:
        with _alloc_lock:
            i = 1
            while True:
                cand = out_dir / f"{src.stem} ({i}){new_suffix}"
                if _reserve(cand):
                    return cand
                i += 1
    target = out_dir / f"{src.stem}{name_suffix}{new_suffix}"
    return unique_path(target, overwrite)


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def run_subprocess(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    """Run a child process without flashing a console window on Windows."""
    creationflags = 0
    startupinfo = None
    if sys.platform.startswith("win"):
        creationflags = 0x08000000  # CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )
