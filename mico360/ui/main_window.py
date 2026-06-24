"""Main application window: responsive shell (collapsible sidebar + top bar)."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QIcon
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

# Preferred opening size (device-independent px); clamped to the screen at runtime.
PREF_W, PREF_H = 1180, 760
# Smallest window we allow. Kept low so it still fits comfortably on small or
# heavily-scaled displays (e.g. 1080p @ 250 % = 768×432 logical px); content
# scrolls inside rather than being clipped.
MIN_W, MIN_H = 480, 420

# Friendly section glyphs (fallback when a tool has none).
_SECTION_GLYPH = {"Home": "🏠", "Convert": "🔁", "Optimize": "🗜️", "Edit": "✏️",
                  "Organize": "🧩", "Secure": "🔒", "Recognize": "🔍",
                  "Files": "🗂️", "System": "⚙"}


def fit_window_size(pref_w: int, pref_h: int, min_w: int, min_h: int,
                    avail_w: int, avail_h: int, margin: int = 0) -> tuple[int, int]:
    """Clamp a preferred window size to the available screen area.

    Never larger than the screen (minus ``margin``) and never smaller than the
    minimum — so the window always opens fully on-screen, on a 1280×720 panel or
    a 4K display alike. Pure function (no Qt) so it is unit-testable."""
    w = max(min_w, min(pref_w, avail_w - margin))
    h = max(min_h, min(pref_h, avail_h - margin))
    return w, h


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__}  v{__version__}")
        self.setMinimumSize(MIN_W, MIN_H)
        self._geom_applied = False
        self._screen_hooked = False
        self._apply_initial_geometry()   # size + centre, clamped to the screen

        logo_png = resource_path("logo.png")
        if logo_png.exists():
            self.setWindowIcon(QIcon(str(logo_png)))

        self.setAcceptDrops(True)       # drag & drop anywhere routes to a tool
        self.stack = QStackedWidget()
        self.sidebar = Sidebar()
        self.sidebar.navigated.connect(self._navigate)
        self.log_page = LogPage()       # lightweight; shared by every tool page
        self.settings_page = None       # built lazily on first visit
        self.help_page = None
        self.dashboard = None           # built lazily on first visit
        self._toasts: list = []
        self._titles: dict[int, str] = {}
        self._factories: dict[int, object] = {}  # page_index -> builder
        self._widgets: dict[int, QWidget] = {}    # page_index -> built widget
        self._pinned: bool | None = None  # None=follow width; True/False=user pinned

        self._build_pages()
        self._build_layout()
        self._apply_visuals()
        self.sidebar.select_first()

        log.info("%s v%s started", __app_name__, __version__)

        # If we just installed an update, confirm it (installed version + time).
        QTimer.singleShot(800, self._confirm_update_if_just_installed)
        # Background update check (deferred so it never blocks startup).
        if settings.auto_check_updates:
            QTimer.singleShot(2500, self._auto_check_updates)

    # --- responsive window geometry / multi-monitor -------------------
    def _current_screen(self):
        return (QGuiApplication.screenAt(QCursor.pos())
                or self.screen() or QGuiApplication.primaryScreen())

    def _apply_initial_geometry(self) -> None:
        """Open at the preferred size but always fully on the current screen,
        centred. Works on a small 1280×720 laptop panel and a 4K monitor alike,
        and picks the monitor under the cursor on multi-monitor setups."""
        screen = self._current_screen()
        if screen is None:
            self.resize(PREF_W, PREF_H)
            return
        avail = screen.availableGeometry()
        w, h = fit_window_size(PREF_W, PREF_H, self.minimumWidth(),
                               self.minimumHeight(), avail.width(), avail.height())
        self.resize(w, h)
        frame = self.frameGeometry()
        frame.moveCenter(avail.center())
        # Keep the whole frame inside the available area.
        frame.moveLeft(max(avail.left(), min(frame.left(), avail.right() - frame.width())))
        frame.moveTop(max(avail.top(), min(frame.top(), avail.bottom() - frame.height())))
        self.move(frame.topLeft())

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        # Re-centre now that real frame margins are known, and listen for the
        # window being dragged to another (possibly smaller / differently-scaled)
        # monitor so it never ends up larger than that screen.
        if not self._geom_applied:
            self._apply_initial_geometry()
            self._geom_applied = True
        handle = self.windowHandle()
        if handle is not None and not self._screen_hooked:
            handle.screenChanged.connect(self._on_screen_changed)
            self._screen_hooked = True

    def _on_screen_changed(self, screen) -> None:
        if screen is None or self.isMaximized() or self.isFullScreen():
            return
        avail = screen.availableGeometry()
        w = min(self.width(), avail.width())
        h = min(self.height(), avail.height())
        if w != self.width() or h != self.height():
            self.resize(max(self.minimumWidth(), w), max(self.minimumHeight(), h))

    def bring_to_front(self) -> None:
        """Restore, raise and focus the window — called when the user tries to
        launch a second copy, so the existing window comes to the foreground."""
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized)
                            | Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        if sys.platform.startswith("win"):
            try:    # nudge Windows to allow the foreground change
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _confirm_update_if_just_installed(self) -> None:
        try:
            from mico360.ui.update_ui import maybe_show_update_completed
            maybe_show_update_completed(self)
        except Exception:
            log.exception("update-completed check failed")

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
        from mico360.core.tools import GROUP_ORDER
        groups: dict[str, list] = {}
        for tool in TOOLS:
            groups.setdefault(tool.group, []).append(tool)
        # Order groups by job (GROUP_ORDER); anything new falls to the end A→Z.
        order = {g: i for i, g in enumerate(GROUP_ORDER)}
        groups = dict(sorted(groups.items(),
                             key=lambda kv: (order.get(kv[0], len(order)), kv[0])))

        self._tool_index: dict[str, int] = {}   # tool_id -> page index

        # Home / Dashboard (the default landing page).
        self.sidebar.add_section("Home")
        self._factories[0] = self._build_dashboard
        self.sidebar.add_item("🏠", "Home", 0)
        self._titles[0] = "Home"
        page_index = 1

        for group_name, tools in groups.items():
            self.sidebar.add_section(group_name)
            for tool in tools:
                self._factories[page_index] = (lambda t=tool: self._build_tool_page(t))
                self.sidebar.add_item(tool.icon, tool.name, page_index)
                self._titles[page_index] = tool.name
                self._tool_index[tool.id] = page_index
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

    def _build_dashboard(self) -> QWidget:
        from mico360.ui.dashboard_page import DashboardPage
        self.dashboard = DashboardPage()
        self.dashboard.openTool.connect(lambda tid: self.open_tool(tid))
        self.dashboard.openToolWithFiles.connect(self.open_tool)
        return self.dashboard

    def _build_tool_page(self, tool) -> QWidget:
        page = ToolPage(tool)
        page.activity.connect(self.log_page.append)
        page.toast.connect(self.show_toast)
        return self._scrollable(page)

    def open_tool(self, tool_id: str, files=None) -> None:
        """Navigate to a tool by id, optionally pre-loading dropped files."""
        idx = self._tool_index.get(tool_id)
        if idx is None:
            return
        self.sidebar.select(idx)          # builds + shows the page
        if files:
            from pathlib import Path
            wrap = self._widgets.get(idx)
            page = wrap.widget() if isinstance(wrap, QScrollArea) else wrap
            if hasattr(page, "add_paths"):
                page.add_paths([Path(f) for f in files])

    # --- toast notifications ------------------------------------------
    def show_toast(self, message: str, kind: str = "ok") -> None:
        from mico360.ui.widgets import Toast
        if not hasattr(self, "_toasts"):
            self._toasts = []
        self._toasts = [t for t in self._toasts if t.isVisible()]
        toast = Toast(self, message, kind)
        # Stack above any existing toasts using their real heights (+ a gap).
        offset = sum(t.height() + 8 for t in self._toasts)
        toast.show_at(offset=offset)
        self._toasts.append(toast)

    def _build_settings_page(self) -> QWidget:
        self.settings_page = SettingsPage()
        self.settings_page.themeChanged.connect(self.apply_theme)
        return self._scrollable(self.settings_page)

    def _build_help_page(self) -> QWidget:
        self.help_page = HelpPage()
        return self.help_page

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        """Wrap a page so it scrolls vertically on short windows.

        The vertical scrollbar is always reserved (``ScrollBarAlwaysOn``) so the
        usable content width is identical on every page — otherwise the bar
        appearing only on taller tools would shift the layout by ~17px each time
        you switch tools, which reads as the panel "changing width"."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        # Horizontal bar only appears if a very narrow / highly-scaled window
        # can't fit the content — so it scrolls instead of clipping. The vertical
        # bar is always reserved so the usable width is identical on every page
        # (no shift when switching tools).
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
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
        if page_index == 0 and getattr(self, "dashboard", None) is not None:
            self.dashboard.refresh()    # show the latest recents / favourites

    # --- drag & drop anywhere -----------------------------------------
    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        from pathlib import Path

        from mico360.ui.dashboard_page import route_for
        from mico360.ui.tool_page import ToolPage
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if not paths:
            return
        # If we're already on a tool page that accepts these files, add them
        # there instead of jumping to a different default tool.
        cur = self.stack.currentWidget()
        page = cur.widget() if isinstance(cur, QScrollArea) else cur
        if isinstance(page, ToolPage):
            accepted = [p for p in paths if Path(p).suffix.lower() in page.tool.accept]
            if accepted:
                page.add_paths([Path(p) for p in accepted])
                event.acceptProposedAction()
                return
        tool = route_for(paths)
        if tool:
            self.open_tool(tool, paths)
            event.acceptProposedAction()

    def _toggle_sidebar(self) -> None:
        self.sidebar.set_collapsed(not self.sidebar.collapsed)
        self._pinned = self.sidebar.collapsed  # remember the explicit choice

    def _theme_glyph(self) -> str:
        return "☀" if settings.theme == "dark" else "🌙"

    def _toggle_theme(self) -> None:
        # The top-bar button pins an explicit light/dark (overriding 'system').
        self.apply_theme("light" if settings.theme == "dark" else "dark")
        if self.settings_page is not None:
            self.settings_page.sync_theme_combo()

    def apply_theme(self, mode: str) -> None:
        """Persist the theme *mode* ('system'|'light'|'dark') and repaint."""
        settings.theme_mode = mode
        self._apply_visuals()

    def _apply_visuals(self) -> None:
        theme = settings.theme  # effective light/dark (resolves 'system')
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
