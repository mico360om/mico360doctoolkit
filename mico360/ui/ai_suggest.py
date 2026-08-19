"""AI metadata suggestions panel for the Edit Metadata page.

Suggestions cover every metadata field the tool supports. They are shown for
review first — each row has a tick box (for bulk selection), an editable value
and its own Apply — plus Apply all, Apply selected and Dismiss. Turning on
*Auto apply* accepts them as soon as they arrive.

Two rules protect existing metadata:
  * a blank / low-confidence suggestion is never applied, so a useful value is
    never overwritten with nothing;
  * a field left at "Keep current" (and the whole panel under a Privacy preset)
    is left alone.

Generation runs on a worker thread so the window never freezes.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from mico360.core import ai as ai_core
from mico360.core.ai_metadata import FIELD_LABELS, FIELDS
from mico360.logging_setup import get_logger
from mico360.ui.widgets import Card, section_label, tip

log = get_logger("mico360.ui.ai")


class _SuggestWorker(QObject):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, path: Path, cfg, cancel=None):
        super().__init__()
        self._path = path
        self._cfg = cfg
        self._cancel = cancel

    def run(self) -> None:
        try:
            from mico360.core.ai_metadata import suggest_metadata
            self.done.emit(suggest_metadata(self._path, self._cfg,
                                            cancel=self._cancel))
        except Exception as exc:      # noqa: BLE001 - reported, never fatal
            self.failed.emit(str(exc))


class AiSuggestPanel(Card):
    """Generate + review AI metadata suggestions for every field.

    ``applyField(key, value)`` is emitted per accepted value; the tool page
    writes it into the matching option control.
    """

    applyField = Signal(str, str)
    openSettings = Signal()

    def __init__(self, get_selected_path, parent: QWidget | None = None,
                 field_count: int | None = None):
        super().__init__(parent)
        self._get_path = get_selected_path
        self._rows: dict[str, tuple] = {}
        self._current: dict[str, str] = {}     # fields currently suggested
        self._total_fields = field_count or len(FIELDS)
        self._thread = None
        self._worker = None
        self._active_token = 0        # bumped each run; a stale result is ignored
        self._cancel_event = None     # threading.Event for the running request
        self._pending: set = set()    # threads awaiting non-blocking reap

        self.add(section_label("AI suggestions"))

        self.status = QLabel("")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        self.add(self.status)

        # --- actions -----------------------------------------------------
        row = QHBoxLayout()
        self.btn_suggest = QPushButton("Suggest All with AI")
        self.btn_suggest.setObjectName("Ghost")
        self.btn_suggest.setCursor(Qt.PointingHandCursor)
        tip(self.btn_suggest,
            "Read the selected document and suggest a value for every metadata "
            "field it can. Nothing changes until you apply — unless Auto apply "
            "is on.")
        self.btn_suggest.clicked.connect(self._suggest)
        row.addWidget(self.btn_suggest)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("Ghost")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        tip(self.btn_cancel,
            "Stop waiting for the AI. Any answer still on its way is discarded.")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setVisible(False)
        row.addWidget(self.btn_cancel)

        self.btn_configure = QPushButton("Configure AI…")
        self.btn_configure.setObjectName("Ghost")
        self.btn_configure.setCursor(Qt.PointingHandCursor)
        tip(self.btn_configure, "Open Settings to choose an AI provider and "
                                "enter your API key.")
        self.btn_configure.clicked.connect(self.openSettings.emit)
        self.btn_configure.setVisible(False)
        row.addWidget(self.btn_configure)
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        self.add(holder)

        self.chk_auto = QCheckBox("Auto apply AI suggestions")
        tip(self.chk_auto,
            "Fill the fields as soon as the suggestions arrive, without "
            "confirming each one. You can still edit anything afterwards.")
        self.chk_auto.setChecked(_auto_apply_setting())
        self.chk_auto.toggled.connect(self._on_auto_toggled)
        self.add(self.chk_auto)

        # --- one row per field -------------------------------------------
        self.results = QWidget()
        grid = QGridLayout(self.results)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        for r, key in enumerate(FIELDS):
            pick = QCheckBox()
            pick.setChecked(True)
            pick.setAccessibleName(f"Include {FIELD_LABELS[key]} in bulk update")
            tip(pick, "Tick to include this field in Apply selected.")
            lbl = QLabel(FIELD_LABELS[key])
            lbl.setObjectName("Hint")
            edit = QLineEdit()
            edit.setPlaceholderText("—")
            edit.setAccessibleName(f"AI suggestion for {FIELD_LABELS[key]}")
            tip(edit, "Review or edit the suggested value before applying it.")
            btn = QPushButton("Apply")
            btn.setObjectName("Subtle")
            btn.setCursor(Qt.PointingHandCursor)
            tip(btn, f"Use this value for {FIELD_LABELS[key]}.")
            btn.clicked.connect(lambda _=False, k=key: self._apply_one(k))
            grid.addWidget(pick, r, 0)
            grid.addWidget(lbl, r, 1)
            grid.addWidget(edit, r, 2)
            grid.addWidget(btn, r, 3)
            self._rows[key] = (pick, lbl, edit, btn)
        grid.setColumnStretch(2, 1)
        self.add(self.results)

        actions = QHBoxLayout()
        self.btn_apply_all = QPushButton("Apply all")
        self.btn_apply_all.setObjectName("Primary")
        self.btn_apply_all.setCursor(Qt.PointingHandCursor)
        tip(self.btn_apply_all, "Use every suggested value above.")
        self.btn_apply_all.clicked.connect(self._apply_all)

        self.btn_apply_sel = QPushButton("Apply selected")
        self.btn_apply_sel.setObjectName("Ghost")
        self.btn_apply_sel.setCursor(Qt.PointingHandCursor)
        tip(self.btn_apply_sel,
            "Bulk update: apply only the ticked fields, leaving the rest alone.")
        self.btn_apply_sel.clicked.connect(self._apply_selected)

        self.btn_select_all = QPushButton("Select all")
        self.btn_select_all.setObjectName("Ghost")
        self.btn_select_all.setCursor(Qt.PointingHandCursor)
        tip(self.btn_select_all, "Tick or untick every suggested field.")
        self.btn_select_all.clicked.connect(self._toggle_select_all)

        self.btn_dismiss = QPushButton("Dismiss")
        self.btn_dismiss.setObjectName("Ghost")
        self.btn_dismiss.setCursor(Qt.PointingHandCursor)
        tip(self.btn_dismiss, "Ignore these suggestions and hide them.")
        self.btn_dismiss.clicked.connect(self.clear)

        for b in (self.btn_apply_all, self.btn_apply_sel, self.btn_select_all,
                  self.btn_dismiss):
            actions.addWidget(b)
        actions.addStretch(1)
        self.actions_row = QWidget()
        self.actions_row.setLayout(actions)
        self.add(self.actions_row)

        self.clear()
        self.refresh_availability()

    # -----------------------------------------------------------------
    def refresh_availability(self) -> None:
        """Reflect the current AI configuration in the panel."""
        cfg = ai_core.load_config()
        ok, why = cfg.is_usable()
        self.btn_suggest.setEnabled(ok)
        self.btn_configure.setVisible(not ok)
        if ok:
            where = ("System AI" if cfg.source == ai_core.SOURCE_SYSTEM
                     else "your AI API")
            self._set_status(f"Ready — using {where} ({cfg.effective_model}).")
        else:
            self._set_status("AI API not configured. " + why, warn=True)

    def _set_status(self, text: str, warn: bool = False) -> None:
        self.status.setText(("⚠  " if warn else "") + text)

    def _on_auto_toggled(self, on: bool) -> None:
        try:
            from mico360.config import settings
            settings.ai_auto_apply = bool(on)
        except Exception:              # noqa: BLE001
            pass

    def clear(self) -> None:
        """Hide the suggestion rows (nothing pending)."""
        self._current = {}
        for pick, _lbl, edit, _btn in self._rows.values():
            edit.clear()
            pick.setChecked(True)
        self.results.setVisible(False)
        self.actions_row.setVisible(False)

    def _show(self, values: dict) -> None:
        """Display only the fields the AI could actually fill."""
        self._current = {k: v for k, v in values.items() if v}
        any_row = False
        for key, (pick, lbl, edit, btn) in self._rows.items():
            val = values.get(key, "")
            edit.setText(val)
            visible = bool(val)
            for w in (pick, lbl, edit, btn):
                w.setVisible(visible)
            pick.setChecked(visible)
            any_row = any_row or visible
        self.results.setVisible(any_row)
        self.actions_row.setVisible(any_row)

    # -----------------------------------------------------------------
    def _suggest(self) -> None:
        path = self._get_path()
        if path is None:
            self._set_status("Select a file in the queue first.", warn=True)
            return
        cfg = ai_core.load_config()
        ok, why = cfg.is_usable()
        if not ok:
            self._set_status("AI API not configured. " + why, warn=True)
            self.btn_configure.setVisible(True)
            return

        import threading
        self._active_token += 1
        token = self._active_token
        self._cancel_event = threading.Event()

        self.btn_suggest.setEnabled(False)
        self.btn_suggest.setText("Analysing…")
        self.btn_cancel.setVisible(True)
        self._set_status(f"Reading '{Path(path).name}' and asking the AI for all "
                         f"{self._total_fields} fields… (the first request can "
                         "take up to a minute — Cancel to stop waiting)")

        thread = QThread(self)
        worker = _SuggestWorker(Path(path), cfg, self._cancel_event)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(lambda v, t=token: self._on_done(v, t))
        worker.failed.connect(lambda m, t=token: self._on_failed(m, t))
        # Non-blocking self-reap: the thread quits and deletes itself when the
        # worker finishes, so a cancelled run cleans up on its own without the UI
        # ever calling wait() on a still-blocked network read.
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda th=thread: self._pending.discard(th))
        self._pending.add(thread)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _cancel(self) -> None:
        """Stop waiting for the current suggestion and free the panel now.

        A blocking network read can't be truly aborted, so the pending answer is
        marked stale (its result is discarded when it eventually arrives) and the
        request's retry-backoff wait is interrupted immediately.
        """
        self._active_token += 1               # any result in flight is now stale
        if self._cancel_event is not None:
            self._cancel_event.set()
        if self._thread is not None:
            self._thread.requestInterruption()
        self._thread = None
        self._worker = None
        self._reset_idle()
        self._set_status("Cancelled.")

    def _reset_idle(self) -> None:
        self.btn_suggest.setEnabled(True)
        self.btn_suggest.setText("Suggest All with AI")
        self.btn_cancel.setVisible(False)

    def closeEvent(self, event):        # noqa: N802
        """Never let a running suggestion thread outlive the panel — Qt aborts
        the process if a QThread is destroyed while still running."""
        self._teardown_threads()
        super().closeEvent(event)

    def _teardown_threads(self) -> None:
        self._active_token += 1
        if self._cancel_event is not None:
            self._cancel_event.set()
        for th in list(self._pending):
            # A thread may already have self-reaped (deleteLater) by the time we
            # get here; touching a deleted QThread would raise and, at shutdown,
            # crash the app. Guard every call.
            try:
                th.requestInterruption()
                th.quit()
                th.wait(3000)
            except RuntimeError:
                pass
        self._pending.clear()
        self._thread = None
        self._worker = None

    def _on_done(self, values: dict, token=None) -> None:
        if token is not None and token != self._active_token:
            return                            # cancelled or superseded — ignore
        self._thread = None
        self._worker = None
        self._reset_idle()
        self._show(values)
        n = len(self._current)
        if self.chk_auto.isChecked():
            self._apply_all()
        else:
            self._set_status(
                f"{n} of {self._total_fields} fields suggested — review, edit "
                "if you like, then apply. Fields the AI wasn't sure about were "
                "left out so your existing values stay put.")

    def _on_failed(self, message: str, token=None) -> None:
        if token is not None and token != self._active_token:
            return                            # cancelled or superseded — ignore
        self._thread = None
        self._worker = None
        self._reset_idle()
        self.clear()
        self._set_status(message, warn=True)
        if "not configured" in message.lower() or "api key" in message.lower():
            self.btn_configure.setVisible(True)

    # -----------------------------------------------------------------
    def _emit(self, keys) -> int:
        """Apply the given fields; blanks are skipped so nothing is wiped."""
        n = 0
        for key in keys:
            edit = self._rows[key][2]
            value = edit.text().strip()      # the EDITED text, if changed
            if value:
                self.applyField.emit(key, value)
                n += 1
        return n

    def _summary(self, n: int) -> None:
        self._set_status(f"{n} of {self._total_fields} fields updated by AI. "
                         "Click Start to write them into the document.")

    def _apply_one(self, key: str) -> None:
        if self._emit([key]):
            self._set_status(f"Applied {FIELD_LABELS[key]}.")

    def _apply_all(self) -> None:
        self._summary(self._emit(list(self._current)))

    def _apply_selected(self) -> None:
        keys = [k for k in self._current if self._rows[k][0].isChecked()]
        if not keys:
            self._set_status("Tick at least one field to bulk update.", warn=True)
            return
        self._summary(self._emit(keys))

    def _toggle_select_all(self) -> None:
        shown = [k for k in self._current]
        turn_on = not all(self._rows[k][0].isChecked() for k in shown)
        for k in shown:
            self._rows[k][0].setChecked(turn_on)


def _auto_apply_setting() -> bool:
    try:
        from mico360.config import settings
        return bool(settings.ai_auto_apply)
    except Exception:                  # noqa: BLE001
        return False
