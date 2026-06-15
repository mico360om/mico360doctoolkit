"""Expand a set of dropped/selected paths into a de-duplicated file list."""
from __future__ import annotations

from pathlib import Path


def collect_files(paths: list[str | Path], accept: set[str]) -> list[Path]:
    """Walk files and folders, returning files whose suffix is in *accept*.

    Folders are traversed recursively. Order is preserved; duplicates removed.
    """
    accept = {e.lower() for e in accept}
    seen: set[Path] = set()
    result: list[Path] = []

    any_file = "*" in accept

    def add(p: Path) -> None:
        rp = p.resolve()
        if rp in seen:
            return
        if any_file or p.suffix.lower() in accept:
            seen.add(rp)
            result.append(p)

    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    add(child)
        elif p.is_file():
            add(p)
    return result
