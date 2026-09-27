"""Run a blocking call (a network request) off the UI thread, safely.

Results come back on the UI thread through a small relay QObject that lives
there, so the callbacks may touch widgets. The work runs on a *daemon* Python
thread: closing the app mid-request just ends the process — unlike a QThread,
which Qt aborts the whole process for if it is destroyed while still running
(an AI request can block for up to two minutes).

Callbacks are never invoked after their owner widget has been deleted.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class _Relay(QObject):
    ok = Signal(object)
    err = Signal(str)

    def __init__(self, parent, on_ok, on_err):
        super().__init__(parent)
        self._on_ok = on_ok
        self._on_err = on_err
        # Bound methods of an object living on the UI thread: emissions from
        # the worker thread are queued to the UI thread.
        self.ok.connect(self._deliver_ok)
        self.err.connect(self._deliver_err)

    def _deliver_ok(self, value) -> None:
        try:
            self._on_ok(value)
        finally:
            self.deleteLater()

    def _deliver_err(self, message: str) -> None:
        try:
            self._on_err(message)
        finally:
            self.deleteLater()


def run_in_background(owner: QObject, fn, on_ok, on_err) -> threading.Thread:
    """Call ``fn()`` on a daemon thread; then ``on_ok(result)`` or
    ``on_err(str(exc))`` on the UI thread. Returns the (started) thread."""
    relay = _Relay(owner, on_ok, on_err)

    def body() -> None:
        try:
            value = fn()
        except Exception as exc:          # noqa: BLE001 - reported to the UI
            try:
                relay.err.emit(str(exc))
            except RuntimeError:          # owner (and relay) already gone
                pass
            return
        try:
            relay.ok.emit(value)
        except RuntimeError:
            pass

    t = threading.Thread(target=body, name="mico360-bg", daemon=True)
    t.start()
    return t
