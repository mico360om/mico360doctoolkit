"""Dashboard / home page: quick actions, favourites, recent files & activity.

Accepts file drops anywhere and routes them to a sensible tool.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mico360 import __app_name__
from mico360.config import settings
from mico360.core.tools import TOOLS_BY_ID
from mico360.ui.widgets import Card, section_label

QUICK_ACTIONS = ["pdf_compress", "pdf_merge", "pdf_to_word", "pdf_to_excel",
                 "excel_to_pdf", "pdf_ocr", "image_compress", "pdf_organize"]

# Route a dropped file extension to a sensible default tool.
_ROUTES = [
    ({".pdf"}, "pdf_compress"),
    ({".doc", ".docx", ".odt", ".rtf"}, "word_to_pdf"),
    ({".xlsx", ".xls", ".ods", ".csv"}, "excel_to_pdf"),
    ({".pptx", ".ppt", ".odp"}, "pptx_to_pdf"),
    ({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}, "image_compress"),
]


def route_for(paths) -> str | None:
    for p in paths:
        ext = Path(p).suffix.lower()
        for exts, tool in _ROUTES:
            if ext in exts:
                return tool
    return None


class Tile(QPushButton):
    """A clickable tool tile (icon + name)."""

    def __init__(self, tool_id: str, parent: QWidget | None = None):
        super().__init__(parent)
        tool = TOOLS_BY_ID.get(tool_id)
        self.tool_id = tool_id
        self.setObjectName("DashTile")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(74)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)
        icon = QLabel(tool.icon if tool else "•")
        icon.setObjectName("DashTileIcon")
        name = QLabel(tool.name if tool else tool_id)
        name.setObjectName("DashTileName")
        name.setWordWrap(True)
        lay.addWidget(icon)
        lay.addWidget(name)
        if tool:
            self.setToolTip(tool.tagline)


class DashboardPage(QWidget):
    openTool = Signal(str)              # tool_id
    openToolWithFiles = Signal(str, list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        self.root = QVBoxLayout(body)
        self.root.setContentsMargins(28, 22, 28, 22)
        self.root.setSpacing(16)

        greeting = QLabel(f"Welcome to {__app_name__}")
        greeting.setObjectName("DashGreeting")
        self.root.addWidget(greeting)
        sub = QLabel("Pick a quick action, drop files anywhere, or choose a tool "
                     "from the sidebar.")
        sub.setObjectName("PageSubtitle")
        self.root.addWidget(sub)

        self.root.addWidget(self._quick_card())
        self._fav_card = Card()
        self.root.addWidget(self._fav_card)
        self._recent_card = Card()
        self.root.addWidget(self._recent_card)
        self._activity_card = Card()
        self.root.addWidget(self._activity_card)
        self.root.addStretch(1)

        self.refresh()

    # ------------------------------------------------------------------
    def _quick_card(self) -> Card:
        card = Card()
        card.add(section_label("Quick actions"))
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, tid in enumerate(QUICK_ACTIONS):
            if tid not in TOOLS_BY_ID:
                continue
            tile = Tile(tid)
            tile.clicked.connect(lambda _=False, t=tid: self.openTool.emit(t))
            grid.addWidget(tile, i // 4, i % 4)
        holder = QWidget()
        holder.setLayout(grid)
        card.add(holder)
        return card

    def _fill_card(self, card: Card, title: str) -> QVBoxLayout:
        # Clear and re-add a section label; return the card's layout for content.
        while card.layout().count():
            item = card.layout().takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)   # detach now so it can't paint over new content
                w.deleteLater()
        card.add(section_label(title))
        return card.layout()

    def refresh(self) -> None:
        self._build_favorites()
        self._build_recent()
        self._build_activity()

    def _build_favorites(self) -> None:
        self._fill_card(self._fav_card, "Favourite tools")
        favs = [t for t in settings.favorite_tools if t in TOOLS_BY_ID]
        if not favs:
            hint = QLabel("No favourites yet — open a tool and click ☆ to pin it.")
            hint.setObjectName("Hint")
            self._fav_card.add(hint)
            return
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, tid in enumerate(favs):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(2)
            tile = Tile(tid)
            tile.clicked.connect(lambda _=False, t=tid: self.openTool.emit(t))
            h.addWidget(tile, 1)
            grid.addWidget(row, i // 4, i % 4)
        holder = QWidget()
        holder.setLayout(grid)
        self._fav_card.add(holder)

    def _build_recent(self) -> None:
        self._fill_card(self._recent_card, "Recent files")
        recents = [p for p in settings.recent_files if Path(p).exists()]
        if not recents:
            hint = QLabel("Files you create will appear here.")
            hint.setObjectName("Hint")
            self._recent_card.add(hint)
            return
        lst = QListWidget()
        lst.setObjectName("FileList")
        lst.setMaximumHeight(180)
        for p in recents[:10]:
            it = QListWidgetItem(f"📄  {Path(p).name}")
            it.setToolTip(p)
            it.setData(Qt.UserRole, p)
            lst.addItem(it)
        lst.itemActivated.connect(self._open_recent)
        lst.itemDoubleClicked.connect(self._open_recent)
        self._recent_card.add(lst)
        clear = QPushButton("Clear recent")
        clear.setObjectName("Ghost")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(lambda: (settings.clear_recent(), self.refresh()))
        self._recent_card.add(clear)

    def _build_activity(self) -> None:
        self._fill_card(self._activity_card, "Last activity")
        acts = settings.recent_activity
        if not acts:
            hint = QLabel("Your recent actions will be listed here.")
            hint.setObjectName("Hint")
            self._activity_card.add(hint)
            return
        for line in acts[:8]:
            lbl = QLabel(f"•  {line}")
            lbl.setObjectName("Hint")
            lbl.setWordWrap(True)
            self._activity_card.add(lbl)

    def _open_recent(self, item) -> None:
        p = item.data(Qt.UserRole)
        if not p:
            return
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(Path(p).parent)])
        except Exception:
            pass

    # --- drag & drop anywhere -----------------------------------------
    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if not paths:
            return
        tool = route_for(paths) or "pdf_compress"
        self.openToolWithFiles.emit(tool, paths)
        event.acceptProposedAction()
