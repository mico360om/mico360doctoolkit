"""Reusable UI building blocks for the v2 design system.

Card / DropArea / Chip / Divider / NavItem plus a ResponsiveRow container that
reflows its two children from side-by-side to stacked as width changes.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# --------------------------------------------------------------------------
# Cards & simple labels
# --------------------------------------------------------------------------
class Card(QFrame):
    """A rounded surface container with a vertical layout."""

    def __init__(self, parent: QWidget | None = None, flat: bool = False,
                 margins: tuple[int, int, int, int] = (18, 16, 18, 16),
                 spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("CardFlat" if flat else "Card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(*margins)
        self._lay.setSpacing(spacing)

    def layout(self) -> QVBoxLayout:  # type: ignore[override]
        return self._lay

    def add(self, w: QWidget) -> None:
        self._lay.addWidget(w)

    def add_layout(self, lay) -> None:
        self._lay.addLayout(lay)


def section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("SectionLabel")
    return lbl


def hint_label(text: str, object_name: str = "Hint") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(object_name)
    lbl.setWordWrap(True)
    return lbl


class Divider(QFrame):
    """A 1px horizontal rule that follows the theme."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class Chip(QLabel):
    """A small status pill (Ready / Running / Done / Error).

    Geometry comes from ``#Chip`` and the colour from a dynamic ``chipState``
    property selector, so both combine in one rule set (see theme.py)."""

    def __init__(self, text: str = "Ready", state: str = "ready",
                 parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self.setAlignment(Qt.AlignCenter)
        self.set_state(state, text)

    def set_state(self, state: str, text: str | None = None) -> None:
        self.setProperty("chipState", state)
        if text is not None:
            self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)


# --------------------------------------------------------------------------
# Responsive container
# --------------------------------------------------------------------------
class ResponsiveRow(QWidget):
    """Holds two widgets side-by-side, stacking them vertically when the
    available width drops below ``threshold`` pixels."""

    def __init__(self, primary: QWidget, secondary: QWidget,
                 threshold: int = 820, stretch=(3, 2),
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._threshold = threshold
        self._stretch = stretch
        self._primary = primary
        self._secondary = secondary
        self._horizontal: bool | None = None

        self._lay = QBoxLayout(QBoxLayout.LeftToRight, self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(16)
        self._lay.addWidget(primary)
        self._lay.addWidget(secondary)
        self._apply(horizontal=True)

    def _apply(self, horizontal: bool) -> None:
        if horizontal == self._horizontal:
            return
        self._horizontal = horizontal
        if horizontal:
            self._lay.setDirection(QBoxLayout.LeftToRight)
            self._lay.setStretch(0, self._stretch[0])
            self._lay.setStretch(1, self._stretch[1])
        else:
            self._lay.setDirection(QBoxLayout.TopToBottom)
            self._lay.setStretch(0, 0)
            self._lay.setStretch(1, 0)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._apply(horizontal=self.width() >= self._threshold)


# --------------------------------------------------------------------------
# Drop area
# --------------------------------------------------------------------------
class DropArea(QFrame):
    """Drag-and-drop target with browse buttons for files and folders."""

    pathsAdded = Signal(list)   # list[str]
    browseFiles = Signal()
    browseFolder = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(150)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(8)

        glyph = QLabel("⬇")
        glyph.setObjectName("DropGlyph")
        glyph.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(28)
        glyph.setFont(f)
        lay.addWidget(glyph)

        title = QLabel("Drag & drop files or folders")
        title.setObjectName("DropTitle")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        hint = QLabel("Folders are scanned recursively for supported files")
        hint.setObjectName("DropHint")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)

        btns = QHBoxLayout()
        btns.setAlignment(Qt.AlignCenter)
        btns.setSpacing(8)
        b_files = QPushButton("Browse files")
        b_files.setObjectName("Ghost")
        b_files.setCursor(Qt.PointingHandCursor)
        b_files.clicked.connect(self.browseFiles.emit)
        b_folder = QPushButton("Browse folder")
        b_folder.setObjectName("Ghost")
        b_folder.setCursor(Qt.PointingHandCursor)
        b_folder.clicked.connect(self.browseFolder.emit)
        btns.addWidget(b_files)
        btns.addWidget(b_folder)
        lay.addSpacing(2)
        lay.addLayout(btns)

    # --- drag events -----------------------------------------------------
    def _set_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active(True)

    def dragLeaveEvent(self, event):  # noqa: N802
        self._set_active(False)

    def dropEvent(self, event):  # noqa: N802
        self._set_active(False)
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        if paths:
            self.pathsAdded.emit(paths)
            event.acceptProposedAction()


# --------------------------------------------------------------------------
# Sidebar nav item
# --------------------------------------------------------------------------
class NavItem(QPushButton):
    """A checkable sidebar entry that shows an icon + label, and collapses to
    an icon-only button when the sidebar is collapsed."""

    def __init__(self, glyph: str, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._glyph = glyph
        self._label = label
        self.setMinimumHeight(40)
        # Keep a stable screen-reader name even when collapsed to an icon.
        self.setAccessibleName(label)
        self.set_collapsed(False)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.setText(self._glyph)
            self.setToolTip(self._label)
            self.setStyleSheet("text-align: center;")
        else:
            self.setText(f"  {self._glyph}   {self._label}")
            self.setToolTip("")
            self.setStyleSheet("text-align: left;")
