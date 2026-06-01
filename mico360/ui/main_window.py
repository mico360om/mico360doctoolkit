"""Main application window: responsive shell (collapsible sidebar + top bar)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mico360 import __app_name__, __version__
from mico360.config import settings
from mico360.core.tools import TOOLS
from mico360.logging_setup import get_logger
from mico360.paths import resource_path
from mico360.theme import stylesheet
from mico360.ui.help_page import HelpPage
from mico360.ui.log_page import LogPage
from mico360.ui.settings_page import SettingsPage
from mico360.ui.sidebar import Sidebar
from mico360.ui.tool_page import ToolPage

log = get_logger("mico360.ui")

# Width thresholds for responsive sidebar auto-collapse / auto-expand.
NARROW = 860
WIDE = 1040

# Friendly section glyphs (fallback when a tool has none).
_SECTION_GLYPH = {"PDF": "📄", "Convert": "🔁", "Image": "🖼️", "System": "⚙"}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__}  v{__version__}")
        self.resize(1180, 760)
        self.setMinimumSize(560, 480)

        logo_png = resource_path("logo.png")
        if logo_png.exists():
            self.setWindowIcon(QIcon(str(logo_png)))

        self.stack = QStackedWidget()
        self.sidebar = Sidebar()
        self.sidebar.navigated.connect(self._navigate)
        self.log_page = LogPage()       # lightweight; shared by every tool page
        self.settings_page = None       # built lazily on first visit
        self.help_page = None
        self._titles: dict[int, str] = {}
        self._factories: dict[int, object] = {}  # page_index -> builder
        self._widgets: dict[int, QWidget] = {}    # page_index -> built widget
        self._pinned: bool | None = None  # None=follow width; True/False=user pinned

        self._build_pages()
        self._build_layout()
        self.apply_theme(settings.theme)
        self.sidebar.select_first()

        log.info("%s v%s started", __app_name__, __version__)

        # Background update check (deferred so it never blocks startup).
        if settings.auto_check_updates:
            QTimer.singleShot(2500, self._auto_check_updates)

    # ------------------------------------------------------------------
    def _auto_check_updates(self) -> None:
        """Silently check GitHub for a newer release; prompt only if one exists."""
        try:
            from mico360 import updater
            from mico360.ui.update_ui import UpdateDialog, start_check
        except Exception:
            return
        if not updater.is_configured():
            return

        def on_found(info):
            try:
                UpdateDialog(info, self).exec()
            except Exception:
                log.exception("update dialog failed")

        # On startup, stay silent when up to date or on network errors.
        start_check(self, on_found, None, lambda msg: log.info("update check: %s", msg))

    # ------------------------------------------------------------------
    def _build_pages(self) -> None:
        """Register the nav items and a *factory* per page. Pages are built
        lazily on first visit, so startup never blocks on building 12 pages or
        scanning the disk for external tools."""
        groups: dict[str, list] = {}
        for tool in TOOLS:
            groups.setdefault(tool.group, []).append(tool)

        page_index = 0
        for group_name, tools in groups.items():
            self.sidebar.add_section(group_name)
            for tool in tools:
                self._factories[page_index] = (lambda t=tool: self._build_tool_page(t))
                self.sidebar.add_item(tool.icon, tool.name, page_index)
                self._titles[page_index] = tool.name
                page_index += 1

        self.sidebar.add_section("System")
        self._factories[page_index] = self._build_settings_page
        self.sidebar.add_item("⚙", "Settings", page_index)
        self._titles[page_index] = "Settings"
        page_index += 1

        self._factories[page_index] = lambda: self.log_page
        self.sidebar.add_item("📜", "Activity", page_index)
        self._titles[page_index] = "Activity log"
        page_index += 1

        self._factories[page_index] = self._build_help_page
        self.sidebar.add_item("❔", "Help", page_index)
        self._titles[page_index] = "Help"
        page_index += 1

        self.sidebar.finish()

    def _build_tool_page(self, tool) -> QWidget:
        page = ToolPage(tool)
        page.activity.connect(self.log_page.append)
        return self._scrollable(page)

    def _build_settings_page(self) -> QWidget:
        self.settings_page = SettingsPage()
        self.settings_page.themeChanged.connect(self.apply_theme)
        return self._scrollable(self.settings_page)

    def _build_help_page(self) -> QWidget:
        self.help_page = HelpPage()
        return self.help_page

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        """Wrap a page so it scrolls vertically on short windows."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(page)
        return area

    def _build_layout(self) -> None:
        # --- top bar ---
        top = QWidget()
        top.setObjectName("TopBar")
        top.setFixedHeight(52)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 8, 14, 8)
        tl.setSpacing(10)

        self.btn_toggle = QPushButton("☰")
        self.btn_toggle.setObjectName("IconButton")
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setFixedSize(36, 36)
        self.btn_toggle.setToolTip("Collapse / expand menu")
        self.btn_toggle.setAccessibleName("Collapse or expand the menu")
        self.btn_toggle.clicked.connect(self._toggle_sidebar)
        tl.addWidget(self.btn_toggle)

        self.top_title = QLabel("")
        self.top_title.setObjectName("TopTitle")
        tl.addWidget(self.top_title)
        tl.addStretch(1)

        self.btn_theme = QPushButton(self._theme_glyph())
        self.btn_theme.setObjectName("IconButton")
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.setFixedSize(36, 36)
        self.btn_theme.setToolTip("Toggle light / dark theme")
        self.btn_theme.setAccessibleName("Toggle light or dark theme")
        self.btn_theme.clicked.connect(self._toggle_theme)
        tl.addWidget(self.btn_theme)

        # --- right side: top bar + stack ---
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(top)
        rl.addWidget(self.stack, 1)

        central = QWidget()
        cl = QHBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.sidebar)
        cl.addWidget(right, 1)
        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    def _navigate(self, page_index: int) -> None:
        widget = self._widgets.get(page_index)
        if widget is None:                       # build this page on first visit
            widget = self._factories[page_index]()
            self._widgets[page_index] = widget
            self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)
        self.top_title.setText(self._titles.get(page_index, ""))

    def _toggle_sidebar(self) -> None:
        self.sidebar.set_collapsed(not self.sidebar.collapsed)
        self._pinned = self.sidebar.collapsed  # remember the explicit choice

    def _theme_glyph(self) -> str:
        return "☀" if settings.theme == "dark" else "🌙"

    def _toggle_theme(self) -> None:
        self.apply_theme("light" if settings.theme == "dark" else "dark")
        if self.settings_page is not None:
            self.settings_page.sync_theme_combo()

    def apply_theme(self, theme: str) -> None:
        settings.theme = theme
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet(theme))
        self.sidebar.set_theme(theme)
        if hasattr(self, "btn_theme"):
            self.btn_theme.setText(self._theme_glyph())

    # --- responsive sidebar -------------------------------------------
    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        w = self.width()
        if w < NARROW:
            # Too narrow for an expanded sidebar — collapse for space, but keep
            # the user's pin so the choice is restored when there's room again.
            if not self.sidebar.collapsed:
                self.sidebar.set_collapsed(True)
        elif w >= WIDE:
            # Roomy: restore the desired state — the user's pin, or expanded when
            # following width automatically.
            want = self._pinned if self._pinned is not None else False
            if self.sidebar.collapsed != want:
                self.sidebar.set_collapsed(want)
