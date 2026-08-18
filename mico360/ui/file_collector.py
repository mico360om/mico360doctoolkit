"""Expand a set of dropped/selected paths into a de-duplicated file list.

Import has to survive whatever the user drops on it: a folder with 100k files,
a network share that disappears mid-walk, permission-denied subfolders, symlink
loops, over-long paths. Nothing here may raise — problems are counted and
reported so the caller can tell the user what was skipped, and the import always
returns whatever it could collect.
"""
from __future__ import annotations

import os
from pathlib import Path

# Hard ceiling on one import. Far more than any real batch, but low enough that
# dropping a huge tree (or C:\ by accident) can't hang the UI or exhaust memory.
MAX_FILES = 20000


class CollectStats:
    """What happened during a collect: how many files were unsupported, how many
    were unreadable, and whether the cap was hit."""

    __slots__ = ("unsupported", "unreadable", "truncated")

    def __init__(self) -> None:
        self.unsupported = 0     # right there, wrong type for this tool
        self.unreadable = 0      # permission denied / vanished / bad path
        self.truncated = False   # stopped at MAX_FILES

    def summary(self) -> str:
        """A short, user-facing note about what was skipped (empty if nothing)."""
        bits = []
        if self.unsupported:
            bits.append(f"{self.unsupported} unsupported file(s) skipped")
        if self.unreadable:
            bits.append(f"{self.unreadable} unreadable file(s) skipped")
        if self.truncated:
            bits.append(f"stopped at the {MAX_FILES:,}-file limit")
        return "; ".join(bits)


def collect_files_detailed(paths, accept: set[str],
                           limit: int = MAX_FILES) -> tuple[list[Path], CollectStats]:
    """Walk files and folders, returning (files, stats).

    Folders are traversed recursively. Order is preserved; duplicates removed.
    Unreadable folders/files are skipped rather than raising.
    """
    accept = {e.lower() for e in accept}
    any_file = "*" in accept
    seen: set = set()
    result: list[Path] = []
    stats = CollectStats()

    def key_for(p: Path):
        """A stable identity for de-duplication that never raises."""
        try:
            return p.resolve()
        except OSError:
            return os.path.normcase(os.path.abspath(str(p)))

    def add(p: Path) -> bool:
        """Returns False once the cap is reached."""
        if len(result) >= limit:
            stats.truncated = True
            return False
        if not (any_file or p.suffix.lower() in accept):
            stats.unsupported += 1
            return True
        k = key_for(p)
        if k in seen:
            return True
        seen.add(k)
        result.append(p)
        return True

    for raw in paths:
        try:
            p = Path(raw)
            is_dir = p.is_dir()
            is_file = p.is_file()
        except OSError:          # bad path, dead network drive, name too long
            stats.unreadable += 1
            continue

        if is_dir:
            # os.walk with onerror=ignore never raises on protected folders, and
            # streams results instead of materialising the whole tree first.
            # followlinks=False keeps symlink loops from spinning forever.
            for root, dirs, files in os.walk(str(p), onerror=lambda _e: None,
                                             followlinks=False):
                dirs.sort()
                for name in sorted(files):
                    if not add(Path(root) / name):
                        return result, stats
        elif is_file:
            if not add(p):
                return result, stats
        else:
            stats.unreadable += 1     # vanished between drop and read
    return result, stats


def collect_files(paths, accept: set[str]) -> list[Path]:
    """Back-compatible wrapper: just the files (see collect_files_detailed)."""
    return collect_files_detailed(paths, accept)[0]
