"""Global activity log page, fed by the logging bridge and tool pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mico360.logging_setup import bridge
from mico360.paths import logs_dir
from mico360.ui.widgets import Card


class LogPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Activity log")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        btn_open = QPushButton("Open logs folder"); btn_open.setObjectName("Ghost")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.clicked.connect(self._open_logs)
        btn_clear = QPushButton("Clear"); btn_clear.setObjectName("Ghost")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(lambda: self.view.clear())
        header.addWidget(btn_open); header.addWidget(btn_clear)
        root.addLayout(header)

        card = Card()
        self.view = QPlainTextEdit()
        self.view.setObjectName("Log")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(5000)
        card.add(self.view)
        root.addWidget(card, 1)

        bridge.record.connect(self._on_record)

    def _on_record(self, level: str, message: str) -> None:
        self.view.appendPlainText(f"{level:<7} {message}")
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append(self, text: str) -> None:
        self.view.appendPlainText(text)

    def _open_logs(self) -> None:
        from mico360.core.platform_utils import open_path
        open_path(logs_dir())
