"""Progress bar: a multi-page job must emit REAL intermediate progress (not jump
0 -> 100), and a multi-file batch must advance smoothly. Drives the actual
BatchController + processors so the engine wiring is exercised end to end.

Run:  python tests/progress_test.py   (offscreen; no GUI shown)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from mico360.core.engine import BatchController
from mico360.core.tools import TOOLS_BY_ID

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _pdf(path: Path, pages: int) -> Path:
    import fitz
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 72), f"page {i + 1}")
    d.save(str(path)); d.close()
    return path


def run_batch(tool_id, inputs, out_dir, options) -> list[float]:
    """Run a batch, collecting every fine_progress value emitted."""
    if QApplication.instance() is None:
        QApplication([])
    seen: list[float] = []
    c = BatchController(max_workers=1)
    c.fine_progress.connect(lambda p: seen.append(p))
    loop = QEventLoop()
    c.finished.connect(lambda _s: loop.quit())
    t = QTimer(); t.setSingleShot(True); t.timeout.connect(loop.quit); t.start(30000)
    c.start(TOOLS_BY_ID[tool_id], list(inputs), out_dir, options, False)
    loop.exec()
    return seen


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()

        # --- single multi-page file: must show intermediate progress --------
        pdf = _pdf(tmp / "deck.pdf", 12)
        vals = run_batch("pdf_to_image", [pdf], out, {"format": "png", "dpi": 72})
        mids = [v for v in vals if 1.0 < v < 99.0]
        check("single multi-page job emits progress values", bool(vals), f"{len(vals)} values")
        check("progress has intermediate steps (not a 0->100 jump)",
              len(mids) >= 3, f"intermediate={sorted(set(round(m) for m in mids))}")
        check("progress reaches 100%", any(v >= 99.5 for v in vals), f"max={max(vals or [0]):.0f}")
        check("progress is non-decreasing", vals == sorted(vals),
              f"first few={[round(v) for v in vals[:6]]}")

        # --- multi-file batch: advances per file ----------------------------
        a = _pdf(tmp / "a.pdf", 2); b = _pdf(tmp / "b.pdf", 2); c = _pdf(tmp / "c.pdf", 2)
        out2 = tmp / "out2"; out2.mkdir()
        vals2 = run_batch("pdf_compress", [a, b, c], out2, {"level": "medium", "overwrite": True})
        mids2 = [v for v in vals2 if 1.0 < v < 99.0]
        check("multi-file batch emits intermediate progress", len(mids2) >= 1,
              f"values={[round(v) for v in vals2]}")
        check("multi-file reaches 100%", any(v >= 99.5 for v in vals2))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All progress checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
