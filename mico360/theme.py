"""MICO360 design system — brand tokens and Qt stylesheets (v3).

A premium refresh built on the MICO360 brand: near-black charcoal surfaces,
crisp white text, and refined red accents drawn from the logo. Each theme is a
flat dict of design tokens; ``stylesheet()`` turns the active theme into a
single Qt Style Sheet applied app-wide, so every screen shares one look.
"""
from __future__ import annotations

# --- Brand: a refined, vivid red drawn from the MICO360 logo -------------
BRAND_RED = "#E1222E"
BRAND_RED_HOVER = "#F0333F"
BRAND_RED_PRESSED = "#BE1621"
BRAND_RED_SOFT = "#F06A72"        # lighter accent for dark surfaces

RADIUS = 14
RADIUS_SM = 10
RADIUS_XS = 8


def system_theme() -> str:
    """Return the OS appearance — 'light' or 'dark'. Used only when the user
    explicitly picks 'System' in Settings. Falls back to 'light'."""
    import sys
    if sys.platform == "darwin":          # macOS
        try:
            import subprocess
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=3)
            # The key exists (value "Dark") only in dark mode; absent ⇒ light.
            return "dark" if "dark" in out.stdout.lower() else "light"
        except Exception:
            return "light"
    try:                                  # Windows
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
        return "light"


DARK = {
    "name": "dark",
    # surfaces (low -> high elevation), neutral near-black charcoal
    "bg": "#0C0C0E",
    "sidebar": "#0F0F12",
    "surface": "#161619",
    "surface_2": "#1C1C21",
    "input": "#141417",
    "hover": "#212128",
    "selected": "#2A2A32",
    # lines
    "border": "#242429",
    "border_strong": "#34343C",
    "divider": "#1C1C21",
    # text
    "text": "#F4F5F7",
    "text_muted": "#9AA0A9",
    "text_faint": "#787E88",
    # brand
    "primary": "#E5323C",          # a touch brighter so it sings on black
    "primary_hover": "#F04A54",
    "primary_pressed": "#C21E28",
    "on_primary": "#FFFFFF",
    "accent_soft": BRAND_RED_SOFT,
    # nav
    "nav_text": "#C4C8D0",
    "nav_hover": "#1A1A1F",
    "nav_active_bg": "#E1222E",
    "nav_active_text": "#FFFFFF",
    "section": "#787E88",
    # status
    "success": "#3DBE74",
    "success_bg": "#12241A",
    "warn": "#E0A93A",
    "error": "#EF6259",
    "error_bg": "#241413",
    "info": "#5B9BE0",
    # drop zone
    "drop": "#141417",
    "drop_active": "#1F1416",
    "scrollbar": "#33333B",
    "scrollbar_hover": "#474751",
    # icon chip behind dashboard glyphs
    "chip_bg": "#1E1E24",
}

LIGHT = {
    "name": "light",
    "bg": "#F3F4F6",
    "sidebar": "#FFFFFF",
    "surface": "#FFFFFF",
    "surface_2": "#F6F7F9",
    "input": "#F3F5F8",
    "hover": "#EDEFF2",
    "selected": "#E8EAEF",
    "border": "#E3E5EA",
    "border_strong": "#CDD1D8",
    "divider": "#EBEDF0",
    "text": "#16171A",
    "text_muted": "#585E67",
    "text_faint": "#828892",
    "primary": "#D81E28",          # a touch deeper for contrast on white
    "primary_hover": "#EC2C37",
    "primary_pressed": "#B5141D",
    "on_primary": "#FFFFFF",
    "accent_soft": "#B5141D",
    "nav_text": "#3A3F47",
    "nav_hover": "#EFF1F4",
    "nav_active_bg": "#D81E28",
    "nav_active_text": "#FFFFFF",
    "section": "#828892",
    "success": "#1E9E55",
    "success_bg": "#E7F6ED",
    "warn": "#B07D12",
    "error": "#C8372E",
    "error_bg": "#FBEAE8",
    "info": "#2D74C4",
    "drop": "#F8F9FB",
    "drop_active": "#FDF0F1",
    "scrollbar": "#CCD0D6",
    "scrollbar_hover": "#ABB0B8",
    "chip_bg": "#F1F2F5",
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
    border: 1px solid {c['border_strong']}; border-radius: {RADIUS_XS}px;
    padding: 6px 9px;
}}

/* Context menus — must be opaque & theme-coloured (the global transparent
   QWidget rule above would otherwise leave the popup see-through / black). */
QMenu {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    border-radius: {RADIUS_SM}px;
    padding: 6px;
}}
QMenu::item {{
    background: transparent;
    color: {c['text']};
    padding: 7px 22px 7px 16px;
    border-radius: 6px;
    margin: 1px 2px;
}}
QMenu::item:selected {{ background-color: {c['primary']}; color: {c['on_primary']}; }}
QMenu::item:disabled {{ color: {c['text_faint']}; background: transparent; }}
QMenu::separator {{ height: 1px; background-color: {c['divider']}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 6px; }}

/* =================== Sidebar =================== */
#Sidebar {{
    background-color: {c['sidebar']};
    border-right: 1px solid {c['divider']};
}}
#Brand {{ color: {c['text']}; font-size: 16px; font-weight: 800; letter-spacing: 0.3px; }}
#BrandSub {{ color: {c['primary']}; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; }}
#NavSection {{
    color: {c['section']}; font-size: 10px; font-weight: 800;
    letter-spacing: 1.4px; padding: 12px 8px 4px 10px;
    background: transparent; border: none; text-align: left;
}}
#NavSection:hover {{ color: {c['text_muted']}; }}
QLineEdit#NavSearch {{
    background-color: {c['input']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px;
    padding: 8px 12px;
    color: {c['text']};
    font-size: 12px;
}}
QLineEdit#NavSearch:hover {{ border-color: {c['border_strong']}; }}
QLineEdit#NavSearch:focus {{ border: 1px solid {c['primary']}; }}

QPushButton#NavItem {{
    background: transparent;
    color: {c['nav_text']};
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 10px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#NavItem:hover {{ background-color: {c['nav_hover']}; color: {c['text']}; }}
QPushButton#NavItem:checked {{
    background-color: {c['nav_active_bg']};
    color: {c['nav_active_text']};
    font-weight: 700;
}}
QPushButton#IconButton {{
    background: transparent; border: none; border-radius: {RADIUS_SM}px;
    color: {c['text_muted']}; padding: 7px;
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

#PageTitle {{ font-size: 25px; font-weight: 800; color: {c['text']}; }}
#PageSubtitle {{ font-size: 13px; color: {c['text_muted']}; }}
/* Section headers carry a short red tick, echoing the brand throughout. */
#SectionLabel {{
    font-size: 12px; font-weight: 800; color: {c['text']};
    letter-spacing: 0.5px; padding: 1px 0 1px 10px;
    border-left: 3px solid {c['primary']};
}}
#Hint {{ color: {c['text_muted']}; font-size: 12px; }}
#Muted {{ color: {c['text_faint']}; font-size: 12px; }}
#ToolIcon {{ font-size: 24px; }}

/* =================== Buttons =================== */
QPushButton {{
    background-color: {c['surface_2']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px;
    padding: 9px 15px;
    font-weight: 600;
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

QPushButton#Ghost {{ background: transparent; border: 1px solid {c['border_strong']}; color: {c['text']}; }}
QPushButton#Ghost:hover {{ background-color: {c['hover']}; border-color: {c['text_faint']}; }}
QPushButton#Subtle {{ background: transparent; border: none; color: {c['text_muted']}; padding: 7px 10px; }}
QPushButton#Subtle:hover {{ background-color: {c['hover']}; color: {c['text']}; }}
QPushButton#Danger {{ background: transparent; border: 1px solid {c['border_strong']}; color: {c['error']}; }}
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
    padding: 9px 12px;
    color: {c['text']};
    selection-background-color: {c['primary']};
    selection-color: #FFFFFF;
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {c['border_strong']}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c['primary']}; }}
QComboBox:disabled, QLineEdit:disabled {{ color: {c['text_faint']}; background-color: {c['surface_2']}; }}
/* NOTE: do NOT style ::drop-down or ::down-arrow here. Touching either moves Qt
   onto the stylesheet painting path, where it stops drawing the native arrow —
   and a ::down-arrow with only a size paints nothing at all, which made every
   dropdown in the app look like a plain text box. Left alone, the style draws a
   proper chevron in the palette's colour. (Covered by tests/combobox_arrow_test.py) */
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
QCheckBox::indicator {{ border: 1px solid {c['border_strong']}; border-radius: 5px; background: {c['surface_2']}; }}
QCheckBox::indicator:hover {{ border-color: {c['primary']}; }}
QCheckBox::indicator:checked {{ background: {c['primary']}; border-color: {c['primary']}; image: none; }}
QCheckBox::indicator:checked:hover {{ background: {c['primary_hover']}; border-color: {c['primary_hover']}; }}
QRadioButton::indicator {{ border: 1px solid {c['border_strong']}; border-radius: 9px; background: {c['surface_2']}; }}
QRadioButton::indicator:hover {{ border-color: {c['primary']}; }}
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
/* Compact drop band (a slim row above the queue) */
#DropArea[compact="true"] #DropTitle {{ font-size: 13px; font-weight: 600;
    color: {c['text_muted']}; }}

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
#DashTile:hover {{ border-color: {c['primary']}; background-color: {c['hover']}; }}
#DashTileIcon {{
    font-size: 20px; color: {c['primary']};
    background-color: {c['chip_bg']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS_SM}px;
    padding: 8px;
}}
#DashTileName {{ color: {c['text']}; font-size: 13px; font-weight: 700; }}
#DashTileDesc {{ color: {c['text_muted']}; font-size: 11px; }}
#DashChevron {{ color: {c['text_faint']}; font-size: 20px; font-weight: 700; }}
#DashTile:hover #DashChevron {{ color: {c['primary']}; }}
#DashGreeting {{ color: {c['text']}; font-size: 30px; font-weight: 800; }}
#FavStar {{
    color: {c['text_faint']}; border: none; background: transparent;
    font-size: 20px; font-family: "Segoe UI Symbol", "Segoe UI Emoji", "Segoe UI";
}}
#FavStar:hover {{ color: {c['primary']}; }}
#FavStar[pinned="true"] {{ color: {c['primary']}; }}
#RecentLink {{ color: {c['text']}; }}

/* =================== Settings tabs =================== */
QTabWidget#SettingsTabs::pane {{ border: none; top: -1px; }}
QTabWidget#SettingsTabs > QTabBar {{ qproperty-drawBase: 0; }}
#SettingsTabs QTabBar::tab {{
    background: transparent; border: none; color: {c['text_muted']};
    padding: 9px 16px; margin-right: 4px; font-size: 13px; font-weight: 600;
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
QListWidget#FileList::item {{ padding: 9px 10px; border-radius: {RADIUS_XS}px; color: {c['text']}; }}
QListWidget#FileList::item:hover {{ background-color: {c['hover']}; }}
QListWidget#FileList::item:selected {{ background-color: {c['selected']}; color: {c['text']}; }}
#ThumbPreview {{ background-color: {c['surface_2']}; border: 1px solid {c['border']};
    border-radius: {RADIUS_XS}px; color: {c['text_faint']}; font-size: 12px; }}

/* =================== Progress =================== */
QProgressBar {{
    background-color: {c['surface_2']};
    border: 1px solid {c['border']};
    border-radius: 9px;
    min-height: 22px; text-align: center; color: {c['text']};
    font-size: 12px; font-weight: 700;
}}
QProgressBar::chunk {{ background-color: {c['primary']}; border-radius: 8px; }}
#ProgressCaption {{ color: {c['text_muted']}; font-size: 12px; }}

/* =================== Update dialog =================== */
#UpdVersions {{ font-size: 17px; font-weight: 800; color: {c['text']}; }}
#UpdMetaCap {{ color: {c['text_faint']}; font-size: 12px; }}
#UpdMetaVal {{ color: {c['text']}; font-size: 12px; font-weight: 700; }}
#UpdSectionHead {{ color: {c['text']}; font-size: 13px; font-weight: 700;
    margin-top: 4px; }}
#UpdBullet {{ color: {c['text_muted']}; font-size: 12px; }}
#UpdError {{ color: {c['error']}; font-size: 12px; font-weight: 600; }}
#UpdRepoLink {{ color: {c['text_faint']}; font-size: 12px; }}

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
