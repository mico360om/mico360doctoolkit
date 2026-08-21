"""Dashboard / home page: quick actions, favourites, recent files & activity.

Accepts file drops anywhere and routes them to a sensible tool.
"""
from __future__ import annotations

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
from mico360.core.tools import IMAGES, OFFICE, PDF, SVG, TOOLS_BY_ID
from mico360.ui.widgets import Card, section_label, tip

QUICK_ACTIONS = ["pdf_compress", "pdf_merge", "pdf_convert", "office_to_pdf",
                 "pdf_ocr", "image_compress", "pdf_organize", "to_markdown"]

# Route a dropped file extension to a sensible default tool. The extension sets
# come straight from the tool registry so this can never drift out of sync with
# what the tools actually accept (e.g. HEIC photos route to Compress Image).
_ROUTES = [
    (PDF, "pdf_compress"),
    (OFFICE, "office_to_pdf"),
    (IMAGES, "image_compress"),
    (SVG, "svg_to_image"),
]


def route_for(paths) -> str | None:
    for p in paths:
        ext = Path(p).suffix.lower()
        for exts, tool in _ROUTES:
            if ext in exts:
                return tool
    return None


class Tile(QPushButton):
    """A clickable tool tile: an icon chip, the tool name, and (optionally) a
    one-line description and a chevron — a horizontal card matching the brand
    design system. ``compact`` drops the description/chevron (used for the
    Favourites row, which carries a star instead)."""

    def __init__(self, tool_id: str, parent: QWidget | None = None,
                 compact: bool = False):
        super().__init__(parent)
        tool = TOOLS_BY_ID.get(tool_id)
        self.tool_id = tool_id
        from PySide6.QtWidgets import QSizePolicy
        self.setObjectName("DashTile")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(56 if compact else 88)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)

        icon = QLabel(tool.icon if tool else "•")
        icon.setObjectName("DashTileIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(40, 40)
        lay.addWidget(icon, 0, Qt.AlignTop if not compact else Qt.AlignVCenter)

        textbox = QVBoxLayout()
        textbox.setContentsMargins(0, 0, 0, 0)
        textbox.setSpacing(3)
        name = QLabel(tool.name if tool else tool_id)
        name.setObjectName("DashTileName")
        name.setWordWrap(True)
        textbox.addWidget(name)
        if not compact and tool and tool.tagline:
            desc = QLabel(tool.tagline)
            desc.setObjectName("DashTileDesc")
            desc.setWordWrap(True)
            textbox.addWidget(desc)
        textbox.addStretch(1)
        lay.addLayout(textbox, 1)

        if not compact:
            chev = QLabel("›")           # ›
            chev.setObjectName("DashChevron")
            lay.addWidget(chev, 0, Qt.AlignVCenter)

        if tool:
            self.setAccessibleName(tool.name)
            tip(self, tool.tagline)


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

        from mico360.theme import palette
        _accent = palette(settings.theme)["primary"]
        greeting = QLabel(f"Welcome to <span style='color:{_accent};'>"
                          f"{__app_name__}</span>")
        greeting.setObjectName("DashGreeting")
        greeting.setTextFormat(Qt.RichText)
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
            tile = Tile(tid, compact=True)
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
        lst.setAccessibleName("Recent files")
        for p in recents[:10]:
            it = QListWidgetItem(f"📄  {Path(p).name}")
            it.setToolTip(f"{p}\nDouble-click to show this file in its folder.")
            it.setData(Qt.UserRole, p)
            lst.addItem(it)
        lst.itemActivated.connect(self._open_recent)
        lst.itemDoubleClicked.connect(self._open_recent)
        self._recent_card.add(lst)
        clear = QPushButton("Clear recent")
        clear.setObjectName("Ghost")
        clear.setCursor(Qt.PointingHandCursor)
        tip(clear, "Clear the Recent files and Last activity lists. "
                   "No files are deleted.")
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
        from mico360.core.platform_utils import reveal
        reveal(p)

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
