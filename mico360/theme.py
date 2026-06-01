"""MICO360 design system — brand tokens and Qt stylesheets (v2).

A modern, responsive refresh built on the MICO360 brand (maroon / black / white).
Each theme is a flat dict of design tokens; ``stylesheet()`` turns the active
theme into a single Qt Style Sheet applied app-wide.
"""
from __future__ import annotations

# --- Brand ---------------------------------------------------------------
BRAND_MAROON = "#A0201F"
BRAND_MAROON_HOVER = "#B83532"
BRAND_MAROON_PRESSED = "#7E1719"
BRAND_MAROON_SOFT = "#C8514F"   # lighter accent for dark surfaces

RADIUS = 12
RADIUS_SM = 8


def system_theme() -> str:
    """Return the OS appearance — 'light' or 'dark'. Used as the default theme
    on first run when the user hasn't picked one yet. Falls back to 'dark'."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        try:
            apps_use_light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return "light" if apps_use_light else "dark"
    except Exception:
        return "dark"


DARK = {
    "name": "dark",
    # surfaces (low -> high elevation)
    "bg": "#101113",
    "sidebar": "#16181B",
    "surface": "#1B1D21",
    "surface_2": "#22252A",
    "input": "#191B1F",
    "hover": "#2A2E35",
    "selected": "#2E333B",
    # lines
    "border": "#2C3036",
    "border_strong": "#3B4047",
    "divider": "#23262B",
    # text
    "text": "#F3F4F6",
    "text_muted": "#A2A8B0",
    "text_faint": "#8B929B",   # raised for WCAG contrast on dark surfaces
    # brand
    "primary": BRAND_MAROON,
    "primary_hover": BRAND_MAROON_HOVER,
    "primary_pressed": BRAND_MAROON_PRESSED,
    "on_primary": "#FFFFFF",
    "accent_soft": BRAND_MAROON_SOFT,
    # nav
    "nav_text": "#C7CCD3",
    "nav_hover": "#23262C",
    "nav_active_bg": BRAND_MAROON,
    "nav_active_text": "#FFFFFF",
    "section": "#8B929B",
    # status
    "success": "#41C078",
    "success_bg": "#15281D",
    "warn": "#E3A93A",
    "error": "#EC5B52",
    "error_bg": "#2A1614",
    "info": "#4D9BE0",
    # drop zone
    "drop": "#191B1F",
    "drop_active": "#221A1A",
    "scrollbar": "#363B42",
    "scrollbar_hover": "#4A5058",
}

LIGHT = {
    "name": "light",
    "bg": "#EEF0F4",
    "sidebar": "#FFFFFF",
    "surface": "#FFFFFF",
    "surface_2": "#F5F7FA",
    "input": "#F5F7FA",
    "hover": "#ECEFF3",
    "selected": "#E7EBF1",
    "border": "#DCDFE6",
    "border_strong": "#C4CAD3",
    "divider": "#E8EBF0",
    "text": "#1A1D21",
    "text_muted": "#586069",
    "text_faint": "#6E7783",   # darkened for WCAG contrast on light surfaces
    "primary": BRAND_MAROON,
    "primary_hover": BRAND_MAROON_HOVER,
    "primary_pressed": BRAND_MAROON_PRESSED,
    "on_primary": "#FFFFFF",
    "accent_soft": "#7E1719",
    "nav_text": "#3C434C",
    "nav_hover": "#EFF1F5",
    "nav_active_bg": BRAND_MAROON,
    "nav_active_text": "#FFFFFF",
    "section": "#6E7783",
    "success": "#1E9E55",
    "success_bg": "#E7F6ED",
    "warn": "#B07D12",
    "error": "#C8372E",
    "error_bg": "#FBEAE8",
    "info": "#2D74C4",
    "drop": "#F7F9FC",
    "drop_active": "#FBF1F1",
    "scrollbar": "#C7CCD4",
    "scrollbar_hover": "#A7AEB8",
}


def palette(theme: str) -> dict:
    return DARK if theme == "dark" else LIGHT


def stylesheet(theme: str) -> str:
    c = palette(theme)
    return f"""
* {{
    font-family: 'Segoe UI Variable', 'Segoe UI', 'Inter', Arial, sans-serif;
    font-size: 13px;
    outline: none;
}}

/* Bare containers stay transparent so they reveal the surface behind them.
   Widgets that need a fill (cards, inputs, buttons…) opt back in below. */
QWidget {{ background: transparent; color: {c['text']}; }}
QMainWindow, QDialog, QStackedWidget {{ background-color: {c['bg']}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{
    background-color: {c['surface_2']}; color: {c['text']};
    border: 1px solid {c['border_strong']}; border-radius: {RADIUS_SM}px;
    padding: 6px 9px;
}}

/* =================== Sidebar =================== */
#Sidebar {{
    background-color: {c['sidebar']};
    border-right: 1px solid {c['divider']};
}}
#Brand {{ color: {c['text']}; font-size: 16px; font-weight: 800; }}
#BrandSub {{ color: {c['text_faint']}; font-size: 10px; font-weight: 600; letter-spacing: 1px; }}
#NavSection {{
    color: {c['text_muted']}; font-size: 11px; font-weight: 800;
    letter-spacing: 1.3px; padding: 10px 8px 4px 8px;
    background: transparent; border: none; text-align: left;
}}
#NavSection:hover {{ color: {c['text']}; }}
QLineEdit#NavSearch {{
    background-color: {c['input']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px;
    padding: 6px 10px;
    color: {c['text']};
    font-size: 12px;
}}
QLineEdit#NavSearch:focus {{ border: 1px solid {c['primary']}; }}

QPushButton#NavItem {{
    background: transparent;
    color: {c['nav_text']};
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#NavItem:hover {{ background-color: {c['nav_hover']}; }}
QPushButton#NavItem:checked {{
    background-color: {c['nav_active_bg']};
    color: {c['nav_active_text']};
    font-weight: 600;
}}
QPushButton#IconButton {{
    background: transparent; border: none; border-radius: {RADIUS_SM}px;
    color: {c['text_muted']}; padding: 6px;
}}
QPushButton#IconButton:hover {{ background-color: {c['hover']}; color: {c['text']}; }}
QPushButton#IconButton:checked {{ background-color: {c['hover']}; color: {c['primary']}; }}

/* =================== Top bar =================== */
#TopBar {{ background-color: {c['bg']}; border-bottom: 1px solid {c['divider']}; }}
#TopTitle {{ font-size: 15px; font-weight: 700; color: {c['text']}; }}

/* =================== Cards =================== */
#Card {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS}px;
}}
#CardFlat {{ background-color: {c['surface_2']}; border: 1px solid {c['border']}; border-radius: {RADIUS}px; }}

#PageTitle {{ font-size: 24px; font-weight: 800; color: {c['text']}; }}
#PageSubtitle {{ font-size: 13px; color: {c['text_muted']}; }}
#SectionLabel {{ font-size: 11px; font-weight: 700; color: {c['text_faint']}; letter-spacing: 0.6px; }}
#Hint {{ color: {c['text_muted']}; font-size: 12px; }}
#Muted {{ color: {c['text_faint']}; font-size: 12px; }}
#ToolIcon {{ font-size: 24px; }}

/* =================== Buttons =================== */
QPushButton {{
    background-color: {c['surface_2']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px;
    padding: 8px 14px;
    font-weight: 500;
}}
QPushButton:hover {{ background-color: {c['hover']}; border-color: {c['border_strong']}; }}
QPushButton:pressed {{ background-color: {c['selected']}; }}
QPushButton:disabled {{ color: {c['text_faint']}; background-color: {c['surface_2']}; border-color: {c['border']}; }}

QPushButton#Primary {{
    background-color: {c['primary']};
    color: {c['on_primary']};
    border: none;
    font-weight: 700;
    padding: 11px 22px;
    font-size: 13px;
}}
QPushButton#Primary:hover {{ background-color: {c['primary_hover']}; }}
QPushButton#Primary:pressed {{ background-color: {c['primary_pressed']}; }}
QPushButton#Primary:disabled {{ background-color: {c['border_strong']}; color: {c['text_faint']}; }}

QPushButton#Ghost {{ background: transparent; border: 1px solid {c['border']}; color: {c['text']}; }}
QPushButton#Ghost:hover {{ background-color: {c['hover']}; }}
QPushButton#Subtle {{ background: transparent; border: none; color: {c['text_muted']}; padding: 7px 10px; }}
QPushButton#Subtle:hover {{ background-color: {c['hover']}; color: {c['text']}; }}
QPushButton#Danger {{ background: transparent; border: 1px solid {c['border']}; color: {c['error']}; }}
QPushButton#Danger:hover {{ background-color: {c['error_bg']}; border-color: {c['error']}; }}

/* Keyboard focus indicators (the global outline:none hides the default ring) */
QPushButton:focus {{ border: 1px solid {c['primary']}; }}
QPushButton#Primary:focus {{ border: 2px solid {c['text']}; }}
QPushButton#Subtle:focus, QPushButton#IconButton:focus {{
    border: 1px solid {c['primary']}; background-color: {c['hover']};
}}
QPushButton#NavItem:focus {{ border: 1px solid {c['primary']}; }}
QCheckBox:focus, QRadioButton:focus {{ color: {c['primary']}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {c['primary']}; }}

/* =================== Inputs =================== */
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {c['input']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px;
    padding: 8px 11px;
    color: {c['text']};
    selection-background-color: {c['primary']};
    selection-color: #FFFFFF;
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {c['border_strong']}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c['primary']}; }}
QComboBox:disabled, QLineEdit:disabled {{ color: {c['text_faint']}; background-color: {c['surface_2']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background-color: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: {RADIUS_SM}px;
    selection-background-color: {c['primary']};
    selection-color: #FFFFFF;
    padding: 4px;
    outline: none;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 18px; border: none; background: transparent;
}}

/* =================== Check / Radio (borderless) =================== */
QCheckBox, QRadioButton {{ spacing: 9px; color: {c['text']}; padding: 2px 0; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; }}
QCheckBox::indicator {{ border: none; border-radius: 5px; background: {c['surface_2']}; }}
QCheckBox::indicator:hover {{ background: {c['hover']}; }}
QCheckBox::indicator:checked {{ background: {c['primary']}; image: none; }}
QCheckBox::indicator:checked:hover {{ background: {c['primary_hover']}; }}
QRadioButton::indicator {{ border: none; border-radius: 9px; background: {c['surface_2']}; }}
QRadioButton::indicator:hover {{ background: {c['hover']}; }}
QRadioButton::indicator:checked {{ background: {c['primary']}; border: 5px solid {c['primary']}; }}

/* =================== Drop zone =================== */
#DropArea {{
    background-color: {c['drop']};
    border: 2px dashed {c['border_strong']};
    border-radius: {RADIUS}px;
}}
#DropArea:hover {{ border-color: {c['text_muted']}; }}
#DropArea[dragActive="true"] {{
    border: 2px dashed {c['primary']};
    background-color: {c['drop_active']};
}}
#DropTitle {{ font-size: 15px; font-weight: 700; color: {c['text']}; }}
#DropHint {{ color: {c['text_muted']}; font-size: 12px; }}
#DropFormats {{ color: {c['text_faint']}; font-size: 11px; }}
#DropGlyph {{ color: {c['primary']}; }}

/* =================== Toast notifications =================== */
#Toast {{
    background-color: {c['surface_2']};
    border: 1px solid {c['border']};
    border-left: 4px solid {c['primary']};
    border-radius: {RADIUS_SM}px;
}}
#Toast[toastKind="ok"] {{ border-left-color: {c['success']}; }}
#Toast[toastKind="error"] {{ border-left-color: {c['error']}; }}
#Toast[toastKind="info"] {{ border-left-color: {c['info']}; }}
#ToastText {{ color: {c['text']}; font-size: 13px; font-weight: 600; }}

/* =================== Dashboard =================== */
#DashTile {{
    background-color: {c['surface_2']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS}px;
}}
#DashTile:hover {{ border-color: {c['primary']}; }}
#DashTileIcon {{ font-size: 22px; }}
#DashTileName {{ color: {c['text']}; font-size: 13px; font-weight: 700; }}
#DashGreeting {{ color: {c['text']}; font-size: 22px; font-weight: 800; }}
#FavStar {{
    color: {c['text_muted']}; border: none; background: transparent;
    font-size: 20px; font-family: "Segoe UI Symbol", "Segoe UI Emoji", "Segoe UI";
}}
#FavStar:hover {{ color: #E8B54D; }}
#FavStar[pinned="true"] {{ color: #E8B54D; }}
#RecentLink {{ color: {c['text']}; }}

/* =================== Settings tabs =================== */
QTabWidget#SettingsTabs::pane {{ border: none; top: -1px; }}
QTabWidget#SettingsTabs > QTabBar {{ qproperty-drawBase: 0; }}
#SettingsTabs QTabBar::tab {{
    background: transparent; border: none; color: {c['text_muted']};
    padding: 8px 16px; margin-right: 6px; font-size: 13px; font-weight: 600;
    border-bottom: 2px solid transparent;
}}
#SettingsTabs QTabBar::tab:hover {{ color: {c['text']}; }}
#SettingsTabs QTabBar::tab:selected {{
    color: {c['primary']}; border-bottom: 2px solid {c['primary']};
}}

/* =================== Password eye + position grid =================== */
QPushButton#EyeToggle {{
    background-color: {c['input']}; border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px; padding: 4px;
}}
QPushButton#EyeToggle:hover {{ border-color: {c['border_strong']}; }}
QPushButton#EyeToggle:checked {{ border-color: {c['primary']}; color: {c['primary']}; }}
QRadioButton#PosDot {{ spacing: 0px; }}
QRadioButton#PosDot::indicator {{
    width: 18px; height: 18px; border-radius: 9px;
    border: 2px solid {c['border_strong']}; background: {c['surface_2']};
}}
QRadioButton#PosDot::indicator:hover {{ border-color: {c['primary']}; }}
QRadioButton#PosDot::indicator:checked {{
    border: 2px solid {c['primary']}; background: {c['primary']};
}}

/* =================== Lists / tables =================== */
QListWidget#FileList {{
    background-color: {c['input']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px;
    padding: 5px;
}}
QListWidget#FileList::item {{ padding: 8px 10px; border-radius: 6px; color: {c['text']}; }}
QListWidget#FileList::item:hover {{ background-color: {c['hover']}; }}
QListWidget#FileList::item:selected {{ background-color: {c['selected']}; color: {c['text']}; }}

/* =================== Progress =================== */
QProgressBar {{
    background-color: {c['surface_2']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    height: 18px; text-align: center; color: {c['text']};
    font-size: 11px; font-weight: 600;
}}
QProgressBar::chunk {{ background-color: {c['primary']}; border-radius: 7px; }}

/* =================== Log / text =================== */
QPlainTextEdit#Log, QTextEdit {{
    background-color: {c['input']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px;
    color: {c['text']};
    font-family: 'Cascadia Mono', 'Consolas', monospace;
    font-size: 12px;
    padding: 9px;
    selection-background-color: {c['primary']};
    selection-color: #FFFFFF;
}}
QLabel#HelpBody {{ color: {c['text']}; font-size: 13px; }}

/* =================== Status chip =================== */
#Chip {{
    border-radius: 9px; padding: 4px 11px; font-size: 11px; font-weight: 700;
    background-color: {c['surface_2']}; color: {c['text_muted']};
}}
#Chip[chipState="ready"] {{ background-color: {c['surface_2']}; color: {c['text_muted']}; }}
#Chip[chipState="run"] {{ background-color: {c['info']}; color: #FFFFFF; }}
#Chip[chipState="ok"] {{ background-color: {c['success_bg']}; color: {c['success']}; }}
#Chip[chipState="err"] {{ background-color: {c['error_bg']}; color: {c['error']}; }}

/* =================== Scrollbars =================== */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
QScrollBar::handle:vertical {{ background: {c['scrollbar']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_hover']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
QScrollBar::handle:horizontal {{ background: {c['scrollbar']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {c['scrollbar_hover']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* =================== Misc =================== */
QStatusBar {{ background-color: {c['sidebar']}; color: {c['text_muted']}; border-top: 1px solid {c['divider']}; }}
QSplitter::handle {{ background: transparent; }}
#Divider {{ background-color: {c['divider']}; max-height: 1px; min-height: 1px; border: none; }}
#VDivider {{ background-color: {c['divider']}; max-width: 1px; min-width: 1px; border: none; }}
"""
