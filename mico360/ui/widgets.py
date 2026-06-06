"""Reusable UI building blocks for the v2 design system.

Card / DropArea / Chip / Divider / NavItem plus a ResponsiveRow container that
reflows its two children from side-by-side to stacked as width changes.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter)
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

# Item-data roles for the queue rows (read by QueueRowDelegate).
ROLE_ID = Qt.UserRole            # unique row id (also used by tool_page)
ROLE_NAME = Qt.UserRole + 11     # file name
ROLE_STATE = Qt.UserRole + 12    # pending | running | done | failed
ROLE_SUB = Qt.UserRole + 13      # secondary line: "size · message"


class QueueRowDelegate(QStyledItemDelegate):
    """Two-line queue row: a coloured status dot, the file name (middle-elided so
    long names keep their start AND extension), a muted size/message line, and a
    right-aligned status label. Theme-aware via a palette getter."""

    _DOT = {"pending": "text_faint", "running": "info",
            "done": "success", "failed": "error"}
    _LABEL = {"pending": "Queued", "running": "Working…",
              "done": "Done", "failed": "Failed"}

    def __init__(self, theme_getter, parent=None):
        super().__init__(parent)
        self._theme = theme_getter

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 48)

    def paint(self, painter, option, index):
        c = self._theme()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect

        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, QColor(c["selected"]))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, QColor(c["hover"]))

        state = index.data(ROLE_STATE) or "pending"
        name = index.data(ROLE_NAME) or index.data(Qt.DisplayRole) or ""
        sub = index.data(ROLE_SUB) or ""
        dot = QColor(c.get(self._DOT.get(state, "text_faint"), c["text_faint"]))

        # Status dot (left).
        cy = rect.center().y()
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot)
        painter.drawEllipse(rect.left() + 14, cy - 4, 9, 9)

        # Status label (right), bold, in the status colour.
        label = self._LABEL.get(state, state)
        sf = QFont(option.font)
        sf.setBold(True)
        sf.setPointSizeF(max(8.0, option.font.pointSizeF() - 0.5))
        fm_s = QFontMetrics(sf)
        label_w = fm_s.horizontalAdvance(label)
        painter.setFont(sf)
        painter.setPen(dot)
        painter.drawText(QRect(rect.right() - label_w - 14, rect.top(),
                               label_w, rect.height()),
                         int(Qt.AlignRight | Qt.AlignVCenter), label)

        text_left = rect.left() + 34
        text_w = max(40, rect.right() - 14 - label_w - 14 - text_left)

        # File name (line 1) — middle-elided so the extension stays visible.
        nf = QFont(option.font)
        fm = QFontMetrics(nf)
        elided = fm.elidedText(str(name), Qt.ElideMiddle, text_w)
        painter.setFont(nf)
        painter.setPen(QColor(c["text"]))
        painter.drawText(QRect(text_left, rect.top() + 7, text_w, fm.height()),
                         int(Qt.AlignLeft | Qt.AlignVCenter), elided)

        # Secondary line (size · message) — muted.
        if sub:
            subf = QFont(option.font)
            subf.setPointSizeF(max(8.0, option.font.pointSizeF() - 1.0))
            fms = QFontMetrics(subf)
            painter.setFont(subf)
            painter.setPen(QColor(c["error"] if state == "failed"
                                  else c["text_faint"]))
            painter.drawText(
                QRect(text_left, rect.bottom() - fms.height() - 6, text_w,
                      fms.height()),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                fms.elidedText(str(sub), Qt.ElideRight, text_w))
        painter.restore()


class FileListWidget(QListWidget):
    """A file list that paints a friendly, centred empty-state message while no
    files have been added — instead of leaving a blank box."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._placeholder = placeholder

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.viewport().update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if self.count() or not self._placeholder:
            return
        from mico360.config import settings
        from mico360.theme import palette
        c = palette(settings.theme)
        painter = QPainter(self.viewport())
        rect = self.viewport().rect().adjusted(24, 18, -24, -18)
        f = QFont(self.font())
        f.setPointSizeF(max(9.0, f.pointSizeF() + 1.0))
        painter.setFont(f)
        painter.setPen(QColor(c["text_faint"]))
        painter.drawText(rect, int(Qt.AlignCenter | Qt.TextWordWrap), self._placeholder)
        painter.end()


def clamp_to_screen(widget, pref_w: int, pref_h: int, margin: int = 48) -> None:
    """Size a top-level widget (e.g. a dialog) to its preferred size but never
    larger than the screen it's on — so it can't open partly off-screen on small
    or heavily-scaled displays. Content inside should scroll if it doesn't fit."""
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if screen is None:
        widget.resize(pref_w, pref_h)
        return
    avail = screen.availableGeometry()
    w = max(320, min(pref_w, avail.width() - margin))
    h = max(240, min(pref_h, avail.height() - margin))
    widget.resize(w, h)


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

    # Effective "no maximum" for a widget width (Qt's QWIDGETSIZE_MAX).
    _WIDE = 16777215

    def __init__(self, primary: QWidget, secondary: QWidget,
                 threshold: int = 820, stretch=(3, 2),
                 secondary_width: tuple[int, int] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._threshold = threshold
        self._stretch = stretch
        self._primary = primary
        self._secondary = secondary
        # Optional (min, max) width clamp applied to the secondary pane *only*
        # when side-by-side, so the options column is the same width on every
        # tool (a stable split) and never sprawls on very wide windows.
        self._secondary_width = secondary_width
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
            if self._secondary_width:
                lo, hi = self._secondary_width
                self._secondary.setMinimumWidth(lo)
                self._secondary.setMaximumWidth(hi)
        else:
            self._lay.setDirection(QBoxLayout.TopToBottom)
            self._lay.setStretch(0, 0)
            self._lay.setStretch(1, 0)
            if self._secondary_width:
                # Stacked: let the pane fill the column width again.
                self._secondary.setMinimumWidth(0)
                self._secondary.setMaximumWidth(self._WIDE)

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

    def __init__(self, parent: QWidget | None = None, compact: bool = False):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
        self._compact = compact
        if compact:
            self._build_compact()
        else:
            self._build_full()

    def _build_full(self) -> None:
        # MinimumExpanding (vertical): the area grows to fill spare space but is
        # never squeezed below its own content, so the Browse buttons can't be
        # clipped — if room is tight the page scrolls instead.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.setMinimumHeight(160)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(8)

        glyph = QLabel("⬇")
        glyph.setObjectName("DropGlyph")
        glyph.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(30)
        glyph.setFont(f)
        lay.addWidget(glyph)

        title = QLabel("Drag & drop files or folders")
        title.setObjectName("DropTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        lay.addWidget(title)

        hint = QLabel("Folders are scanned recursively for supported files")
        hint.setObjectName("DropHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
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

    def _build_compact(self) -> None:
        """A short, single-band drop zone — leaves the vertical space for the
        queue. Glyph + prompt on the left, Browse buttons on the right."""
        self.setProperty("compact", True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(58)
        self.setMaximumHeight(76)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 12, 8)
        lay.setSpacing(12)

        glyph = QLabel("⬇")
        glyph.setObjectName("DropGlyph")
        gf = QFont()
        gf.setPointSize(18)
        glyph.setFont(gf)
        lay.addWidget(glyph, 0, Qt.AlignVCenter)

        title = QLabel("Drag & drop files or folders here")
        title.setObjectName("DropTitle")
        title.setWordWrap(True)
        lay.addWidget(title, 1, Qt.AlignVCenter)

        b_files = QPushButton("Browse files")
        b_files.setObjectName("Ghost")
        b_files.setCursor(Qt.PointingHandCursor)
        b_files.clicked.connect(self.browseFiles.emit)
        b_folder = QPushButton("Browse folder")
        b_folder.setObjectName("Ghost")
        b_folder.setCursor(Qt.PointingHandCursor)
        b_folder.clicked.connect(self.browseFolder.emit)
        lay.addWidget(b_files, 0, Qt.AlignVCenter)
        lay.addWidget(b_folder, 0, Qt.AlignVCenter)

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


# --------------------------------------------------------------------------
# Toast notification
# --------------------------------------------------------------------------
class Toast(QFrame):
    """A small auto-dismissing notification, overlaid on its parent window."""

    def __init__(self, parent: QWidget, message: str, kind: str = "ok",
                 duration: int = 3400):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setProperty("toastKind", kind)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 16, 10)
        lay.setSpacing(8)
        glyph = {"ok": "✓", "error": "✗", "info": "ℹ"}.get(kind, "✓")
        text = QLabel(f"{glyph}  {message}")
        text.setObjectName("ToastText")
        text.setWordWrap(False)            # single line → consistent height
        lay.addWidget(text)
        self.setMaximumWidth(460)
        QTimer.singleShot(duration, self.close)

    def show_at(self, offset: int = 0, margin: int = 22) -> None:
        p = self.parentWidget()
        self.adjustSize()
        if p is not None:
            x = p.width() - self.width() - margin
            y = p.height() - self.height() - margin - offset
            self.move(max(margin, x), max(margin, y))
        self.show()
        self.raise_()
