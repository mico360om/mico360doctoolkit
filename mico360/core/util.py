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


# =========================================================================
# Low-resource guards: disk space + memory-aware concurrency
# =========================================================================
# Headroom kept free on the output volume so a job doesn't fill the disk to the
# brim (leaving room for the OS, temp files and filesystem metadata). Kept small
# so it never blocks a modest job on a low-storage device — the check adds this
# to the input size, and most tools produce output no larger than their input.
DISK_MARGIN = 20 * 1024 * 1024        # 20 MB


def free_disk_bytes(path) -> int | None:
    """Free bytes on the volume that would hold *path* (walking up to the first
    existing ancestor). None if it can't be determined."""
    import shutil
    try:
        p = Path(path)
        for _ in range(40):
            if p.exists():
                break
            if p.parent == p:
                break
            p = p.parent
        return int(shutil.disk_usage(str(p)).free)
    except Exception:
        return None


def require_free_space(out_dir, need_bytes: int, label: str = "") -> None:
    """Raise ProcessError if the output volume has less than *need_bytes* free
    (plus a safety margin). A no-op when free space can't be measured, so it
    never blocks work on exotic filesystems."""
    free = free_disk_bytes(out_dir)
    if free is None:
        return
    need = int(need_bytes) + DISK_MARGIN
    if free < need:
        what = f" for {label}" if label else ""
        raise ProcessError(
            f"Not enough free disk space{what}: about {human_size(need)} is "
            f"needed but only {human_size(free)} is free on the output drive. "
            f"Free up space or pick another output folder.")


def available_memory_bytes() -> int | None:
    """Best-effort available physical RAM in bytes (no third-party deps).
    None if it can't be determined."""
    try:
        if sys.platform.startswith("win"):
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            m = _MemStatus()
            m.dwLength = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return int(m.ullAvailPhys)
        elif hasattr(os, "sysconf"):
            names = getattr(os, "sysconf_names", {})
            if "SC_AVPHYS_PAGES" in names and "SC_PAGE_SIZE" in names:
                return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except Exception:
        return None
    return None


def auto_worker_count(cpu: int | None = None, avail_mem_bytes: int | None = -1,
                      per_worker_bytes: int = 1_100_000_000,
                      hard_max: int = 8) -> int:
    """Pick a sensible worker count for parallel file processing, scaling down
    on low-RAM machines so heavy tools (OCR, big PDFs/images) don't thrash or
    hit MemoryError. Never returns less than 1.

    ``avail_mem_bytes`` defaults to a live reading; pass an explicit value (or
    None to skip the RAM cap) in tests.
    """
    cpu = cpu or os.cpu_count() or 4
    n = min(max(1, cpu - 1), hard_max)
    mem = available_memory_bytes() if avail_mem_bytes == -1 else avail_mem_bytes
    if mem is not None and mem > 0:
        n = min(n, max(1, int(mem // per_worker_bytes)))
    return max(1, n)


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
