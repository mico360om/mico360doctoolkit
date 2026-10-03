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


# Office formats that are ZIP packages inside (an older or password-protected
# one is an OLE file instead, and is left for the conversion engine to judge).
_ZIP_DOCS = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
_OLE_MAGIC = b"\xd0\xcf\x11\xe0"


def source_problem(path, any_file: bool = False) -> str:
    """Why a source file can't be processed, or "" when it looks fine.

    Checked before a tool runs, so a missing, empty or mislabelled file gets
    one clear sentence instead of whatever the PDF / image / Office library
    happens to raise. ``any_file`` is for tools that take every kind of file
    (Edit File Properties), where only "it must exist" applies.
    """
    p = Path(path)
    name = p.name
    try:
        if not p.is_file():
            return (f"'{name}' can't be found — it was moved, renamed or deleted "
                    "after you added it.")
        size = p.stat().st_size
    except OSError as exc:
        return f"'{name}' can't be opened ({exc.strerror or type(exc).__name__})."
    if any_file:
        return ""
    if size == 0:
        return f"'{name}' is empty (0 bytes), so there is nothing to process."
    ext = p.suffix.lower()
    if ext != ".pdf" and ext not in _ZIP_DOCS:
        return ""
    try:
        with open(p, "rb") as fh:
            head = fh.read(1024)
    except PermissionError:
        return (f"'{name}' can't be read — it is open in another program, or you "
                "don't have permission to open it.")
    except OSError as exc:
        return f"'{name}' can't be read ({exc.strerror or type(exc).__name__})."
    if ext == ".pdf":
        if b"%PDF-" not in head:
            return (f"'{name}' isn't a PDF inside — it is damaged, or it is another "
                    "kind of file that was renamed to .pdf.")
        return ""
    if head.startswith(_OLE_MAGIC):
        return ""
    import zipfile
    if not zipfile.is_zipfile(p):
        return (f"'{name}' isn't a valid {ext} document — it is damaged or "
                "incomplete, or it is another kind of file that was renamed.")
    return ""


def tidy_message(message: str, sources=()) -> str:
    """A failure message with the sources' full paths shortened to file names.
    Library errors quote the whole path (often with doubled backslashes), which
    buries the actual reason in the results list."""
    out = str(message)
    for s in sources or []:
        p = Path(s)
        full = str(p)
        for form in (full.replace("\\", "\\\\"), full, p.as_posix()):
            if form and form != p.name:
                out = out.replace(form, p.name)
    return out


def explain_failure(exc: BaseException, sources=()) -> str:
    """A plain-language reason for a known kind of technical failure, or ""
    when the error isn't one we recognise (the caller then reports it as
    unexpected). Lets a locked, damaged or vanished file read as that, rather
    than as "ValueError: document closed or encrypted"."""
    names = [Path(s).name for s in (sources or [])]
    raw = str(exc)
    named = next((n for n in names if n and n in raw), None)
    if named or len(names) == 1:
        subject = f"'{named or names[0]}'"
    else:
        subject = "One of the files"
    text = f"{type(exc).__name__}: {raw}".lower()
    if isinstance(exc, FileNotFoundError):
        return (f"{subject} can't be found — it was moved, renamed or deleted "
                "after you added it.")
    if isinstance(exc, PermissionError):
        return (f"{subject} can't be read or written — it is open in another "
                "program, or you don't have permission for that folder.")
    if isinstance(exc, MemoryError):
        return (f"{subject} is too large to process with the memory available. "
                "Close other apps, or try a lower quality setting.")
    if "decompressionbomb" in text:
        return f"{subject} has too many pixels to process safely."
    if "password" in text or "encrypted" in text:
        return (f"{subject} is password-protected. Remove the password first "
                "(Protect PDF → Remove the password), then try again.")
    if any(k in text for k in ("is no pdf", "filedataerror", "emptyfileerror",
                               "failed to open file", "broken document",
                               "cannot open broken", "no objects found")):
        return (f"{subject} isn't a valid PDF — it is damaged, or it is another "
                "kind of file that was renamed to .pdf.")
    if any(k in text for k in ("unidentifiedimageerror", "cannot identify image",
                               "image file is truncated", "broken data stream",
                               "broken png", "not a jpeg")):
        return (f"{subject} isn't a valid image — it is damaged or incomplete, "
                "or it is another kind of file that was renamed.")
    if "badzipfile" in text or "not a zip file" in text or "packagenotfound" in text:
        return (f"{subject} isn't a valid Office document — it is damaged or "
                "incomplete.")
    return ""


# Placeholders reserved by the current worker thread, so the engine can remove
# the ones a failed / cancelled unit never filled (a 0-byte file with a real-
# looking name is worse than no file at all).
_tls = threading.local()


def begin_reservations() -> None:
    """Start tracking placeholders reserved on this thread (engine, per unit)."""
    _tls.paths = []


def discard_empty_reservations() -> int:
    """Delete this thread's reserved placeholders that are still empty. Called
    when a unit fails or is cancelled. Returns how many were removed."""
    removed = 0
    for p in getattr(_tls, "paths", None) or []:
        try:
            if p.exists() and p.stat().st_size == 0:
                p.unlink()
                removed += 1
        except OSError:
            pass
    _tls.paths = []
    return removed


def is_nonempty(path) -> bool:
    """True if *path* exists and has content (a reserved placeholder is 0 bytes,
    so ``exists()`` alone can't tell "produced" from "never written")."""
    try:
        return Path(path).stat().st_size > 0
    except OSError:
        return False


def _reserve(path: Path) -> bool:
    """Atomically create *path* as an empty placeholder. False if it exists."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        tracked = getattr(_tls, "paths", None)
        if tracked is not None:
            tracked.append(path)
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
    if not name_suffix and _same_file(target, src):
        # Never hand back the SOURCE itself as the output: e.g. converting a
        # JPEG to JPEG into its own folder with Overwrite on would silently
        # replace the original with the re-encoded copy.
        target = out_dir / f"{src.stem}_new{new_suffix}"
    return unique_path(target, overwrite)


def _same_file(a, b) -> bool:
    try:
        return (os.path.normcase(os.path.abspath(str(a)))
                == os.path.normcase(os.path.abspath(str(b))))
    except Exception:
        return False


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


def _win_mem_status():
    """The Win32 MEMORYSTATUSEX struct, or None off Windows / on failure."""
    if not sys.platform.startswith("win"):
        return None
    try:
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
            return m
    except Exception:
        return None
    return None


def available_memory_bytes() -> int | None:
    """Best-effort *available* physical RAM in bytes (no third-party deps).
    None if it can't be determined — notably on macOS, where the OS keeps most
    RAM as reclaimable cache so a cheap "free" reading is misleading; callers
    fall back to :func:`total_memory_bytes` there."""
    try:
        m = _win_mem_status()
        if m is not None:
            return int(m.ullAvailPhys)
        names = getattr(os, "sysconf_names", {})
        if "SC_AVPHYS_PAGES" in names and "SC_PAGE_SIZE" in names:   # Linux
            return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except Exception:
        return None
    return None


def total_memory_bytes() -> int | None:
    """Best-effort *total* physical RAM in bytes (no third-party deps). Works on
    Windows, macOS and Linux. None if it can't be determined."""
    try:
        m = _win_mem_status()
        if m is not None:
            return int(m.ullTotalPhys)
        names = getattr(os, "sysconf_names", {})
        if "SC_PHYS_PAGES" in names and "SC_PAGE_SIZE" in names:     # macOS + Linux
            return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
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
    if avail_mem_bytes == -1:                       # auto-detect
        mem = available_memory_bytes()
        if mem is None:                             # macOS has no cheap "avail"
            mem = total_memory_bytes()              # → scale by total RAM instead
    else:
        mem = avail_mem_bytes
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
