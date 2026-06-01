"""Multi-threaded batch execution built on QThreadPool.

A :class:`BatchController` turns a tool + a list of inputs into work units and
runs them concurrently, emitting Qt signals the UI binds to for live progress.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from mico360.core.tools import AGGREGATE, Tool
from mico360.core.util import ProcessError
from mico360.logging_setup import get_logger

log = get_logger("mico360.engine")


@dataclass
class UnitResult:
    label: str
    ok: bool
    outputs: list[Path] = field(default_factory=list)
    message: str = ""
    skipped: bool = False
    sources: list[Path] = field(default_factory=list)   # input file(s) this unit covered
    index: int = -1                                      # position in the batch


class _WorkerSignals(QObject):
    log = Signal(str, str)            # (unit label, message)
    progress = Signal(int, float)     # (unit index, fraction 0..1) — sub-unit progress
    finished = Signal(object)         # UnitResult


class _Worker(QRunnable):
    def __init__(self, tool: Tool, item, out_dir: Path, options: dict,
                 cancel: threading.Event, index: int = 0):
        super().__init__()
        self.tool = tool
        self.item = item             # Path (per-file) or list[Path] (aggregate)
        self.out_dir = out_dir
        self.options = options
        self.cancel = cancel
        self.index = index
        self.signals = _WorkerSignals()
        if isinstance(item, list):
            self.label = f"{len(item)} files"
        else:
            self.label = item.name

    def _make_report(self):
        """A report callable that also carries ``.progress(current, total)`` and
        ``.cancelled()`` attributes so processors can report fine-grained progress
        and bail out promptly when the user cancels mid-run."""
        sig, label, idx, cancel = self.signals, self.label, self.index, self.cancel

        def report(message):
            sig.log.emit(label, message)

        def progress(current, total):
            frac = (current / total) if total else 0.0
            sig.progress.emit(idx, max(0.0, min(1.0, frac)))

        report.progress = progress           # functions allow attribute assignment
        report.cancelled = cancel.is_set     # processors poll this in long loops
        return report

    def run(self) -> None:
        srcs = list(self.item) if isinstance(self.item, list) else [self.item]
        if self.cancel.is_set():
            self.signals.finished.emit(UnitResult(self.label, False, skipped=True,
                                                  message="Cancelled", sources=srcs,
                                                  index=self.index))
            return
        report = self._make_report()
        try:
            outputs = self.tool.runner(self.item, self.out_dir, self.options, report)
            self.signals.finished.emit(UnitResult(self.label, True, outputs or [],
                                                  sources=srcs, index=self.index))
        except ProcessError as exc:
            if self.cancel.is_set():   # cancelled mid-loop -> skipped, not failed
                self.signals.finished.emit(UnitResult(self.label, False, skipped=True,
                                                      message="Cancelled", sources=srcs,
                                                      index=self.index))
                return
            log.warning("%s failed: %s", self.label, exc)
            self.signals.finished.emit(UnitResult(self.label, False, message=str(exc),
                                                  sources=srcs, index=self.index))
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Unexpected error processing %s", self.label)
            self.signals.finished.emit(UnitResult(self.label, False,
                                                  message=f"Unexpected error: {exc}",
                                                  sources=srcs, index=self.index))


class BatchController(QObject):
    """Owns a run: dispatches workers, tracks progress, aggregates results."""

    started = Signal(int)                       # total units
    unit_started = Signal(str)                  # label
    unit_finished = Signal(object)              # UnitResult
    progress = Signal(int, int)                 # done, total
    fine_progress = Signal(float)               # overall percent 0..100 (sub-unit aware)
    log = Signal(str, str)                      # (label, message)
    finished = Signal(dict)                     # summary

    def __init__(self, max_workers: int = 0, parent: QObject | None = None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        cpu = os.cpu_count() or 4
        self.pool.setMaxThreadCount(max_workers if max_workers > 0 else max(2, cpu - 1))
        self._cancel = threading.Event()
        self._total = 0
        self._done = 0
        self._results: list[UnitResult] = []
        self._start_time = 0.0
        self._outputs: list[Path] = []
        self._unit_frac: dict[int, float] = {}   # per-unit completion fraction

    @property
    def output_paths(self) -> list[Path]:
        return self._outputs

    def cancel(self) -> None:
        self._cancel.set()

    def start(self, tool: Tool, inputs: list[Path], out_dir: Path, options: dict,
              same_as_source: bool = False) -> None:
        self._cancel.clear()   # never inherit a prior cancellation
        units: list = [inputs] if tool.mode == AGGREGATE else list(inputs)
        self._total = len(units)
        self._done = 0
        self._results = []
        self._outputs = []
        self._unit_frac = {}
        self._start_time = time.monotonic()
        self.started.emit(self._total)
        if self._total == 0:
            self._emit_summary()
            return
        # Let processors adjust output naming when writing next to the source.
        options = {**options, "same_as_source": same_as_source}
        for i, item in enumerate(units):
            if same_as_source:
                base = item.parent if isinstance(item, Path) else item[0].parent
            else:
                base = out_dir
            worker = _Worker(tool, item, base, dict(options), self._cancel, index=i)
            worker.signals.log.connect(self.log)
            worker.signals.progress.connect(self._on_unit_progress)
            worker.signals.finished.connect(self._on_unit_done)
            label = item.name if isinstance(item, Path) else f"{len(item)} files"
            self.unit_started.emit(label)
            self.pool.start(worker)

    def _emit_fine(self) -> None:
        if self._total:
            pct = 100.0 * sum(self._unit_frac.values()) / self._total
            self.fine_progress.emit(max(0.0, min(100.0, pct)))

    def _on_unit_progress(self, index: int, frac: float) -> None:
        # Ignore late ticks for an already-finished unit.
        if self._unit_frac.get(index, 0.0) < 1.0:
            self._unit_frac[index] = frac
            self._emit_fine()

    def _on_unit_done(self, result: UnitResult) -> None:
        self._done += 1
        self._unit_frac[result.index] = 1.0
        self._emit_fine()
        self._results.append(result)
        self._outputs.extend(result.outputs)
        self.unit_finished.emit(result)
        self.progress.emit(self._done, self._total)
        if self._done >= self._total:
            self._emit_summary()

    def _emit_summary(self) -> None:
        ok = sum(1 for r in self._results if r.ok)
        failed = sum(1 for r in self._results if not r.ok and not r.skipped)
        skipped = sum(1 for r in self._results if r.skipped)
        summary = {
            "total": self._total,
            "ok": ok,
            "failed": failed,
            "skipped": skipped,
            "elapsed": time.monotonic() - self._start_time,
            "outputs": list(self._outputs),
            "errors": [(r.label, r.message) for r in self._results
                       if not r.ok and not r.skipped],
            "cancelled": self._cancel.is_set(),
        }
        self.finished.emit(summary)
