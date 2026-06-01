"""Collapsible brand sidebar with grouped navigation."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mico360 import __version__
from mico360.paths import resource_path
from mico360.ui.widgets import NavItem

EXPANDED_W = 236
COLLAPSED_W = 66


class Sidebar(QWidget):
    navigated = Signal(int)   # page index

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._collapsed = False
        self._items: list[NavItem] = []
        self._sections: list[QLabel] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.setFixedWidth(EXPANDED_W)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- brand header ---
        header = QWidget()
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 16, 14, 12)
        h.setSpacing(10)
        self._logo = QLabel()
        # Two logo variants: the white "logo-w.png" reads on the dark sidebar,
        # the normal "logo.png" on the light one. Loaded once, swapped on theme.
        light_png = resource_path("logo.png")
        dark_png = resource_path("logo-w.png")
        self._pix_light = QPixmap(str(light_png)) if light_png.exists() else QPixmap()
        self._pix_dark = QPixmap(str(dark_png)) if dark_png.exists() else self._pix_light
        self._pix = self._pix_dark   # default; main window calls set_theme()
        self._apply_logo()
        h.addWidget(self._logo)
        brand_box = QVBoxLayout()
        brand_box.setSpacing(0)
        self._brand = QLabel("MICO360")
        self._brand.setObjectName("Brand")
        self._brand_sub = QLabel("DOC TOOLKIT")
        self._brand_sub.setObjectName("BrandSub")
        brand_box.addWidget(self._brand)
        brand_box.addWidget(self._brand_sub)
        self._brand_box = brand_box
        h.addLayout(brand_box)
        h.addStretch(1)
        root.addWidget(header)

        # --- scrollable nav ---
        self._nav_host = QWidget()
        self._nav = QVBoxLayout(self._nav_host)
        self._nav.setContentsMargins(10, 6, 10, 6)
        self._nav.setSpacing(3)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self._nav_host)
        root.addWidget(scroll, 1)

        # --- footer ---
        self._ver = QLabel(f"  v{__version__}")
        self._ver.setObjectName("Muted")
        self._ver.setContentsMargins(8, 6, 8, 10)
        root.addWidget(self._ver)

    # -- building -----------------------------------------------------------
    def add_section(self, name: str) -> None:
        lbl = QLabel(name.upper())
        lbl.setObjectName("NavSection")
        lbl.setContentsMargins(2, 8, 0, 2)
        self._nav.addWidget(lbl)
        self._sections.append(lbl)

    def add_item(self, glyph: str, label: str, page_index: int) -> NavItem:
        item = NavItem(glyph, label)
        item.clicked.connect(lambda: self.navigated.emit(page_index))
        item._page_index = page_index  # type: ignore[attr-defined]
        self._group.addButton(item)
        self._nav.addWidget(item)
        self._items.append(item)
        return item

    def finish(self) -> None:
        self._nav.addStretch(1)

    def select(self, page_index: int) -> None:
        for it in self._items:
            if getattr(it, "_page_index", None) == page_index:
                it.setChecked(True)
                self.navigated.emit(page_index)
                break

    def select_first(self) -> None:
        if self._items:
            self._items[0].setChecked(True)
            self.navigated.emit(getattr(self._items[0], "_page_index", 0))

    # -- collapse -----------------------------------------------------------
    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(COLLAPSED_W if collapsed else EXPANDED_W)
        for it in self._items:
            it.set_collapsed(collapsed)
        for s in self._sections:
            s.setVisible(not collapsed)
        self._brand.setVisible(not collapsed)
        self._brand_sub.setVisible(not collapsed)
        self._ver.setVisible(not collapsed)
        self._apply_logo()

    def set_theme(self, theme: str) -> None:
        """Use the white logo on the dark sidebar, the normal logo on the light."""
        self._pix = self._pix_dark if theme == "dark" else self._pix_light
        self._apply_logo()

    def _apply_logo(self) -> None:
        if self._pix.isNull():
            self._logo.setText("M360")
            return
        h = 26 if self._collapsed else 30
        self._logo.setPixmap(self._pix.scaledToHeight(h, Qt.SmoothTransformation))
        self._logo.setFixedSize(QSize(self._pix.width() * h // max(1, self._pix.height()), h))
