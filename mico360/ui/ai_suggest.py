"""AI metadata suggestions panel for the Edit Metadata page.

Suggestions are always *shown first* and never applied on their own: each row
has the AI's value in an editable box with its own Apply, plus Apply all and
Dismiss for the whole set. Generation runs on a worker thread so the window
never freezes.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
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

    def __init__(self, path: Path, cfg):
        super().__init__()
        self._path = path
        self._cfg = cfg

    def run(self) -> None:
        try:
            from mico360.core.ai_metadata import suggest_metadata
            self.done.emit(suggest_metadata(self._path, self._cfg))
        except Exception as exc:      # noqa: BLE001 - reported, never fatal
            self.failed.emit(str(exc))


class AiSuggestPanel(Card):
    """Generate + review AI metadata suggestions.

    ``applyField(key, value)`` is emitted when the user accepts one value; the
    tool page writes it into the matching option control.
    """

    applyField = Signal(str, str)
    openSettings = Signal()

    def __init__(self, get_selected_path, parent: QWidget | None = None):
        super().__init__(parent)
        self._get_path = get_selected_path
        self._rows: dict[str, tuple] = {}
        self._current: dict[str, str] = {}   # fields currently suggested
        self._thread = None
        self._worker = None

        self.add(section_label("AI suggestions"))

        self.status = QLabel("")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        self.status.setOpenExternalLinks(False)
        self.add(self.status)

        row = QHBoxLayout()
        self.btn_suggest = QPushButton("Suggest with AI")
        self.btn_suggest.setObjectName("Ghost")
        self.btn_suggest.setCursor(Qt.PointingHandCursor)
        tip(self.btn_suggest,
            "Read the selected document and suggest its properties. Nothing is "
            "changed until you apply a suggestion.")
        self.btn_suggest.clicked.connect(self._suggest)
        row.addWidget(self.btn_suggest)

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

        # --- suggestion rows (hidden until we have some) ------------------
        self.results = QWidget()
        grid = QGridLayout(self.results)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        for r, key in enumerate(FIELDS):
            lbl = QLabel(FIELD_LABELS[key])
            lbl.setObjectName("Hint")
            edit = QLineEdit()
            edit.setPlaceholderText("—")
            edit.setAccessibleName(f"AI suggestion for {FIELD_LABELS[key]}")
            tip(edit, "Edit the suggestion before applying it if you want.")
            btn = QPushButton("Apply")
            btn.setObjectName("Subtle")
            btn.setCursor(Qt.PointingHandCursor)
            tip(btn, f"Use this value for {FIELD_LABELS[key]}.")
            btn.clicked.connect(lambda _=False, k=key: self._apply_one(k))
            grid.addWidget(lbl, r, 0)
            grid.addWidget(edit, r, 1)
            grid.addWidget(btn, r, 2)
            self._rows[key] = (lbl, edit, btn)
        self.add(self.results)

        actions = QHBoxLayout()
        self.btn_apply_all = QPushButton("Apply all")
        self.btn_apply_all.setObjectName("Primary")
        self.btn_apply_all.setCursor(Qt.PointingHandCursor)
        tip(self.btn_apply_all, "Use every suggested value above.")
        self.btn_apply_all.clicked.connect(self._apply_all)
        self.btn_dismiss = QPushButton("Dismiss")
        self.btn_dismiss.setObjectName("Ghost")
        self.btn_dismiss.setCursor(Qt.PointingHandCursor)
        tip(self.btn_dismiss, "Ignore these suggestions and hide them.")
        self.btn_dismiss.clicked.connect(self.clear)
        actions.addWidget(self.btn_apply_all)
        actions.addWidget(self.btn_dismiss)
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
        self.status.setObjectName("Hint")
        self.status.setText(("⚠  " if warn else "") + text)

    def clear(self) -> None:
        """Hide the suggestion rows (nothing pending)."""
        self._current = {}
        for _lbl, edit, _btn in self._rows.values():
            edit.clear()
        self.results.setVisible(False)
        self.actions_row.setVisible(False)

    def _show(self, values: dict) -> None:
        self._current = {k: v for k, v in values.items() if v}
        any_row = False
        for key, (lbl, edit, btn) in self._rows.items():
            val = values.get(key, "")
            edit.setText(val)
            visible = bool(val)
            lbl.setVisible(visible)
            edit.setVisible(visible)
            btn.setVisible(visible)
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

        self.btn_suggest.setEnabled(False)
        self.btn_suggest.setText("Analysing…")
        self._set_status(f"Reading '{Path(path).name}' and asking the AI… "
                         "(the first request can take up to a minute)")

        self._thread = QThread(self)
        self._worker = _SuggestWorker(Path(path), cfg)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _finish_thread(self) -> None:
        self.btn_suggest.setEnabled(True)
        self.btn_suggest.setText("Suggest with AI")
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread = None
            self._worker = None

    def _on_done(self, values: dict) -> None:
        self._finish_thread()
        self._show(values)
        self._set_status(f"{len(values)} suggestion(s) — review, edit if you "
                         "like, then apply.")

    def _on_failed(self, message: str) -> None:
        self._finish_thread()
        self.clear()
        self._set_status(message, warn=True)
        if "not configured" in message.lower() or "api key" in message.lower():
            self.btn_configure.setVisible(True)

    # -----------------------------------------------------------------
    def _apply_one(self, key: str) -> None:
        _lbl, edit, _btn = self._rows[key]
        value = edit.text().strip()
        if value:
            self.applyField.emit(key, value)
            self._set_status(f"Applied {FIELD_LABELS[key]}.")

    def _apply_all(self) -> None:
        n = 0
        for key in self._current:
            edit = self._rows[key][1]
            value = edit.text().strip()     # the EDITED text, if the user changed it
            if value:
                self.applyField.emit(key, value)
                n += 1
        self._set_status(f"Applied {n} field(s). Click Start to write them "
                         "into the document.")
