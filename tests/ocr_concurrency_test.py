"""OCR crash regression: GPU inference must never run on two threads at once.

A DirectML ONNX session cannot be Run() concurrently — doing so faults the
process (a hard crash, not a Python exception). The batch engine happily runs
several files at the same time, all sharing one cached OCR engine, so the
serialisation has to be global, not per-file.

This reproduces the race with a fake engine that flags overlapping entry, so it
catches the regression on any machine (GPU or not).

Run:  python tests/ocr_concurrency_test.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


class OverlapDetectingEngine:
    """Stands in for RapidOCR. Records whether two threads were ever inside a
    call at the same time — i.e. whether a real DirectML session would have
    been Run() concurrently (and crashed the process)."""

    def __init__(self):
        self.inside = 0
        self.max_inside = 0
        self.calls = 0
        self._guard = threading.Lock()

    def __call__(self, img, **kwargs):
        with self._guard:
            self.inside += 1
            self.max_inside = max(self.max_inside, self.inside)
            self.calls += 1
        time.sleep(0.02)          # widen the window so a race is reliably seen
        with self._guard:
            self.inside -= 1
        return [], None           # (result, elapsed) — no detections


def hammer(engine, threads: int = 8, each: int = 4) -> None:
    from mico360.core import processors
    import numpy as np
    img = np.zeros((8, 8, 3), dtype=np.uint8)

    def worker():
        for _ in range(each):
            processors._ocr_image_lines(engine, img, dpi=72)

    ts = [threading.Thread(target=worker) for _ in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


def main() -> int:
    from mico360.core import processors

    # --- GPU active: inference MUST be serialised (the crash fix) ----------
    original = processors._ocr_active_provider
    try:
        processors._ocr_active_provider = "GPU (DirectML)"
        eng = OverlapDetectingEngine()
        hammer(eng)
        check("every OCR call ran (nothing dropped)", eng.calls == 32, str(eng.calls))
        check("GPU OCR never runs on two threads at once (no crash window)",
              eng.max_inside == 1, f"max concurrent = {eng.max_inside}")

        # --- CPU active: concurrency is allowed (and expected) -------------
        processors._ocr_active_provider = "CPU"
        eng_cpu = OverlapDetectingEngine()
        hammer(eng_cpu)
        check("CPU OCR still runs concurrently (no speed regression)",
              eng_cpu.max_inside > 1, f"max concurrent = {eng_cpu.max_inside}")
    finally:
        processors._ocr_active_provider = original

    # --- the lock exists and is a real lock --------------------------------
    check("a process-wide OCR inference lock exists",
          isinstance(processors._ocr_infer_lock, type(threading.Lock())))

    print()
    if failures:
        print(f"{len(failures)} OCR concurrency check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All OCR concurrency checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
