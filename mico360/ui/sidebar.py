"""Collapsible brand sidebar with grouped navigation."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mico360 import __version__
from mico360.config import settings
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
        self._sections: list[QPushButton] = []
        self._groups: list[dict] = []     # {name, header, items, collapsed}
        self._cur_group: dict | None = None
        self._searching = False
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

        # --- search ---
        self._search_wrap = QWidget()
        sw = QHBoxLayout(self._search_wrap)
        sw.setContentsMargins(12, 0, 12, 8)
        self._search = QLineEdit()
        self._search.setObjectName("NavSearch")
        self._search.setPlaceholderText("Search tools…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search)
        sw.addWidget(self._search)
        root.addWidget(self._search_wrap)

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
        btn = QPushButton()
        btn.setObjectName("NavSection")
        btn.setCursor(Qt.PointingHandCursor)
        grp = {"name": name, "header": btn, "items": [], "collapsed": False}
        btn.clicked.connect(lambda _=False, g=grp: self._toggle_group(g))
        self._groups.append(grp)
        self._cur_group = grp
        self._sections.append(btn)
        self._update_section_text(grp)
        self._nav.addWidget(btn)

    def add_item(self, glyph: str, label: str, page_index: int) -> NavItem:
        item = NavItem(glyph, label)
        item.clicked.connect(lambda: self.navigated.emit(page_index))
        item._page_index = page_index  # type: ignore[attr-defined]
        item._group = self._cur_group  # type: ignore[attr-defined]
        self._group.addButton(item)
        self._nav.addWidget(item)
        self._items.append(item)
        if self._cur_group is not None:
            self._cur_group["items"].append(item)
        return item

    def finish(self) -> None:
        self._nav.addStretch(1)
        # Restore the user's collapsed sections.
        for name in settings.collapsed_groups:
            for grp in self._groups:
                if grp["name"] == name:
                    grp["collapsed"] = True
                    for it in grp["items"]:
                        it.setVisible(False)
                    self._update_section_text(grp)

    def select(self, page_index: int) -> None:
        for it in self._items:
            if getattr(it, "_page_index", None) == page_index:
                self._expand_group_of(it)
                it.setChecked(True)
                self.navigated.emit(page_index)
                break

    def select_first(self) -> None:
        if self._items:
            self._items[0].setChecked(True)
            self.navigated.emit(getattr(self._items[0], "_page_index", 0))

    # -- search & collapsible groups ---------------------------------------
    def _update_section_text(self, grp: dict) -> None:
        name = (grp["name"] or "").upper()
        if self._searching:
            chevron = ""
        else:
            chevron = "▸  " if grp["collapsed"] else "▾  "
        grp["header"].setText(f"{chevron}{name}")

    def _toggle_group(self, grp: dict) -> None:
        if self._searching:
            return
        grp["collapsed"] = not grp["collapsed"]
        for it in grp["items"]:
            it.setVisible(not grp["collapsed"])
        self._update_section_text(grp)
        settings.collapsed_groups = [g["name"] for g in self._groups if g["collapsed"]]

    def _expand_group_of(self, item: NavItem) -> None:
        grp = getattr(item, "_group", None)
        if grp and grp.get("collapsed") and not self._searching:
            self._toggle_group(grp)

    def _on_search(self, text: str) -> None:
        q = (text or "").strip().lower()
        self._searching = bool(q)
        for grp in self._groups:
            any_match = False
            for it in grp["items"]:
                if q:
                    match = q in it._label.lower()
                    it.setVisible(match)
                    any_match = any_match or match
                else:
                    it.setVisible(not grp["collapsed"])
            # During a search, hide empty sections; otherwise always show headers.
            grp["header"].setVisible(any_match if q else True)
            self._update_section_text(grp)

    # -- collapse -----------------------------------------------------------
    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(COLLAPSED_W if collapsed else EXPANDED_W)
        self._search_wrap.setVisible(not collapsed)
        for it in self._items:
            it.set_collapsed(collapsed)
        for s in self._sections:
            s.setVisible(not collapsed)
        if collapsed:
            # Icon-only mode shows every tool, ignoring group-collapse/search.
            for it in self._items:
                it.setVisible(True)
        else:
            self._reapply_visibility()
        self._brand.setVisible(not collapsed)
        self._brand_sub.setVisible(not collapsed)
        self._ver.setVisible(not collapsed)
        self._apply_logo()

    def _reapply_visibility(self) -> None:
        self._on_search(self._search.text())

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
