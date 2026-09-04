"""A small, self-contained monochrome line-icon set (Lucide-style).

Every icon is a tiny inline SVG so it renders crisply at any DPI and can be
tinted to any colour (unlike the OS emoji we used before, which render
inconsistently and can't take the brand red). Rendered pixmaps are cached by
(name, size, colour, dpr).

Public API:
    tool_icon_name(tool_id) -> str
    pixmap(name, size, color, dpr=1.0) -> QPixmap
    icon(name, size, color, dpr=1.0) -> QIcon
    label_pixmap(name, size, color) -> QPixmap   # DPI from the app automatically
"""
from __future__ import annotations

# --- 24x24 line-icon shapes (inner SVG; stroke set by the wrapper) --------
_SHAPES: dict[str, str] = {
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
            '<path d="M14 3v5h5"/>',
    "file-text": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
                 '<path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "compress": '<path d="M4 12h16"/><path d="m8 8 4-4 4 4M8 16l4 4 4-4"/>',
    "layers": '<path d="M12 3 3 8l9 5 9-5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "scissors": '<circle cx="6" cy="6" r="2.6"/><circle cx="6" cy="18" r="2.6"/>'
                '<line x1="20" y1="4" x2="8.6" y2="15.4"/>'
                '<line x1="14.2" y1="14.2" x2="20" y2="20"/>'
                '<line x1="8.6" y1="8.6" x2="12" y2="12"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/>'
            '<rect x="14" y="3" width="7" height="7" rx="1"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1"/>'
            '<rect x="14" y="14" width="7" height="7" rx="1"/>',
    "lock": '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2"/>'
            '<path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>',
    "droplet": '<path d="M12 3s6 5.7 6 10a6 6 0 0 1-12 0c0-4.3 6-10 6-10z"/>',
    "list-ordered": '<path d="M10 6h10M10 12h10M10 18h10"/>'
                    '<path d="M4 5v5M3 10h2"/><path d="M4 15.5h2v1.5H4v1.5h2"/>',
    "hash": '<path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/>',
    "pen": '<path d="M12 20h9"/>'
           '<path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "tag": '<path d="M3 11.5 11.5 3H20a1 1 0 0 1 1 1v8.5L12.5 21a1 1 0 0 1-1.4 0'
           'l-7.1-7.1a1 1 0 0 1 0-1.4z"/><circle cx="16.5" cy="7.5" r="1.3"/>',
    "scan": '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2'
            'M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
    "repeat": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/>'
              '<path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/>'
             '<circle cx="8.5" cy="8.5" r="1.8"/><path d="m21 15-4.5-4.5L5 21"/>',
    "maximize": '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3'
                'M16 21h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3'
               'M1 14h6M9 8h6M17 16h6"/>',
    "spline": '<circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/>'
              '<path d="M5 17C5 9 9 5 17 5"/>',
    # UI / navigation
    "home": '<path d="M3 10.5 12 3l9 7.5"/>'
            '<path d="M5 9.4V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/>'
                '<path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1'
                'M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
    "activity": '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
    "help": '<circle cx="12" cy="12" r="9"/>'
            '<path d="M9.4 9.4a2.6 2.6 0 0 1 5 1c0 1.6-2.4 2-2.4 3.4"/>'
            '<circle cx="12" cy="17" r="0.6"/>',
    "sun": '<circle cx="12" cy="12" r="4"/>'
           '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
           'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "star": '<path d="M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6-5.4-3-5.4 3 1.2-6L3.3 9.3'
            'l6.1-.7z"/>',
    # "{c}" is replaced with the tint colour (for filled shapes).
    "star-filled": '<path fill="{c}" d="M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6-5.4-3'
                   '-5.4 3 1.2-6L3.3 9.3l6.1-.7z"/>',
    "inbox": '<path d="M12 3v11"/><path d="m8 10 4 4 4-4"/>'
             '<path d="M3 15v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3"/>',
    "eye": '<path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"/>'
           '<circle cx="12" cy="12" r="2.8"/>',
    "eye-off": '<path d="M3 3l18 18"/>'
               '<path d="M10.6 5.9A10.5 10.5 0 0 1 12 5.5c6.5 0 10 6.5 10 6.5'
               'a17.6 17.6 0 0 1-3.2 3.9M6.6 6.6C3.7 8.5 2 12 2 12s3.5 6.5 10 6.5'
               'c1.7 0 3.2-.4 4.5-1"/>'
               '<path d="M9.9 9.9a2.9 2.9 0 0 0 4.2 4.2"/>',
    "check": '<path d="m4.5 12.5 5 5 10-11"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/>'
            '<circle cx="12" cy="8" r="0.6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5'
              'a2 2 0 0 1-2-2z"/>',
    "bug": '<path d="M8 2l1.9 1.9M16 2l-1.9 1.9"/>'
           '<path d="M9 8a3 3 0 0 1 6 0v1H9z"/>'
           '<rect x="7" y="9" width="10" height="11" rx="5"/>'
           '<path d="M3 13h4M17 13h4M4 20l3.5-2M20 20l-3.5-2M4 7l3 2M20 7l-3 2'
           'M12 9v11"/>',
    "sparkles": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>'
                '<path d="M19 16v4M17 18h4M5 3v3M3.5 4.5h3"/>',
}

# --- tool_id -> icon name -------------------------------------------------
TOOL_ICON: dict[str, str] = {
    "pdf_compress": "compress",
    "pdf_merge": "layers",
    "pdf_split": "scissors",
    "pdf_organize": "grid",
    "pdf_protect": "lock",
    "pdf_watermark": "droplet",
    "pdf_page_numbers": "list-ordered",
    "pdf_sign": "pen",
    "pdf_metadata": "tag",
    "pdf_ocr": "scan",
    "pdf_convert": "repeat",
    "office_to_pdf": "file-text",
    "to_markdown": "hash",
    "image_to_pdf": "image",
    "image_compress": "compress",
    "image_resize": "maximize",
    "image_convert": "repeat",
    "image_watermark": "droplet",
    "svg_to_image": "image",
    "image_to_svg": "spline",
    "file_properties": "sliders",
}


def tool_icon_name(tool_id: str) -> str:
    return TOOL_ICON.get(tool_id, "file")


def svg(name: str, color: str = "#000000", stroke: float = 1.8) -> str:
    inner = (_SHAPES.get(name) or _SHAPES["file"]).replace("{c}", color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</svg>'
    )


_cache: dict = {}


def pixmap(name: str, size: int, color: str, dpr: float = 1.0):
    """A tinted icon pixmap, cached and DPI-aware."""
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    key = (name, int(size), color, round(dpr, 3))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    data = QByteArray(svg(name, color).encode("utf-8"))
    renderer = QSvgRenderer(data)
    px = max(1, int(round(size * dpr)))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm


def _dpr() -> float:
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            return float(app.devicePixelRatio())
    except Exception:
        pass
    return 1.0


def label_pixmap(name: str, size: int, color: str):
    """Pixmap for a QLabel, using the app's current device-pixel ratio."""
    return pixmap(name, size, color, _dpr())


def icon(name: str, size: int, color: str):
    from PySide6.QtGui import QIcon
    return QIcon(pixmap(name, size, color, _dpr()))


def theme_color(role: str) -> str:
    """Current theme's colour for a palette role (falls back to text)."""
    from mico360.config import settings
    from mico360.theme import palette
    c = palette(settings.theme)
    return c.get(role, c["text"])


_IconLabelClass = None


def _icon_label_class():
    """Build the concrete QLabel subclass once, on first use. Defining it here
    (rather than at module top) keeps this module import-light — it pulls in
    QtWidgets only when an icon label is actually created — while still giving
    every IconLabel a single shared type, so isinstance()/findChildren() work
    and we don't churn out a throwaway class per icon."""
    global _IconLabelClass
    if _IconLabelClass is not None:
        return _IconLabelClass
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    class _IconLabel(QLabel):
        def __init__(self, name, size, role, parent=None):
            super().__init__(parent)
            self._icon_name = name
            self._icon_size = size
            self._icon_role = role
            self.setFixedSize(size, size)
            self.setAlignment(Qt.AlignCenter)
            self.refresh_icon()

        def set_icon(self, name=None, role=None):
            if name is not None:
                self._icon_name = name
            if role is not None:
                self._icon_role = role
            self.refresh_icon()

        def refresh_icon(self):
            self.setPixmap(label_pixmap(self._icon_name, self._icon_size,
                                        theme_color(self._icon_role)))

    _IconLabelClass = _IconLabel
    return _IconLabelClass


class IconLabel:
    """A QLabel that shows a tinted line icon and re-tints itself when the theme
    changes. Constructing one returns a shared ``_IconLabel`` subclass instance;
    use :func:`icon_label_type` for isinstance()/findChildren() checks."""

    def __new__(cls, name: str, size: int = 20, role: str = "text",
                parent=None):
        return _icon_label_class()(name, size, role, parent)


def icon_label_type():
    """The concrete QLabel subclass produced by :class:`IconLabel` (for
    isinstance / findChildren)."""
    return _icon_label_class()


_IconButtonClass = None


def _icon_button_class():
    """A QPushButton that shows a tinted line icon (optionally a different one
    when checked) and re-tints itself on theme change. Built once, lazily —
    same reasoning as :func:`_icon_label_class`."""
    global _IconButtonClass
    if _IconButtonClass is not None:
        return _IconButtonClass
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QPushButton

    class _IconButton(QPushButton):
        def __init__(self, name, size, role, parent=None,
                     checked_name=None, checked_role=None):
            super().__init__(parent)
            self._icon_name = name
            self._icon_size = size
            self._icon_role = role
            self._checked_name = checked_name
            self._checked_role = checked_role
            self.setIconSize(QSize(size, size))
            self.toggled.connect(lambda _on: self.refresh_icon())
            self.refresh_icon()

        def set_icon(self, name=None, role=None, checked_name=None,
                     checked_role=None):
            if name is not None:
                self._icon_name = name
            if role is not None:
                self._icon_role = role
            if checked_name is not None:
                self._checked_name = checked_name
            if checked_role is not None:
                self._checked_role = checked_role
            self.refresh_icon()

        def refresh_icon(self):
            on = self.isCheckable() and self.isChecked()
            name = (self._checked_name if on and self._checked_name
                    else self._icon_name)
            role = (self._checked_role if on and self._checked_role
                    else self._icon_role)
            self.setIcon(icon(name, self._icon_size, theme_color(role)))

    _IconButtonClass = _IconButton
    return _IconButtonClass


def IconButton(name: str, size: int = 18, role: str = "text_muted", parent=None,
               checked_name: str | None = None, checked_role: str | None = None):
    """Factory: a QPushButton carrying a tinted line icon. When the button is
    checkable, ``checked_name``/``checked_role`` swap the icon while checked
    (e.g. eye → eye-off, star → star-filled)."""
    return _icon_button_class()(name, size, role, parent, checked_name,
                                checked_role)


def icon_button_type():
    return _icon_button_class()


def refresh_all(root) -> None:
    """Re-tint every icon-bearing widget under ``root`` (call on theme change)."""
    from PySide6.QtWidgets import QWidget
    for w in root.findChildren(QWidget):
        fn = getattr(w, "refresh_icon", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
