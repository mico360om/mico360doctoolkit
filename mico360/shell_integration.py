"""Windows Explorer "MICO360 Toolkit" right-click menu.

Registers a cascading context-menu (per file type) so a user can right-click a
supported file, pick a tool, and have the app open that tool with the file
already loaded — no browsing.

Implementation notes
--------------------
* **Per-user, no admin.** Everything lives under ``HKCU\\Software\\Classes\\
  SystemFileAssociations\\<ext>``, which *adds* a verb to a file type without
  owning it or changing the default program.
* **Cascading without CommandStore.** The parent verb sets ``MUIVerb`` and an
  empty ``SubCommands`` value, which makes the shell build the submenu from a
  nested ``shell`` subkey — the documented per-user way to get a cascade without
  the HKLM CommandStore.
* **Driven by the tool registry.** The actions per file type come from the tool
  list, so the menu can't drift from the tools that actually exist.

The heavy lifting (``register`` / ``unregister``) is Windows-only; on other
platforms the functions are safe no-ops. ``base`` and ``launch_prefix`` are
injectable so tests exercise the real logic against a throwaway registry path.
"""
from __future__ import annotations

import sys
from pathlib import Path

MENU_TITLE = "MICO360 Toolkit"
PARENT_KEY = "MICO360Toolkit"                 # our verb key under <ext>\shell
DEFAULT_BASE = r"Software\Classes\SystemFileAssociations"

# Curated, ordered actions per file family — the tools a user most often wants
# straight from a right-click. (Every tool is still reachable inside the app.)
_PDF = ["pdf_compress", "pdf_merge", "pdf_split", "pdf_organize", "pdf_protect",
        "pdf_watermark", "pdf_ocr", "pdf_convert", "pdf_metadata"]
_IMAGE = ["image_compress", "image_resize", "image_convert", "image_to_pdf",
          "image_watermark", "image_to_svg"]
_OFFICE = ["office_to_pdf", "to_markdown"]
_SVG = ["svg_to_image"]

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
               ".heic", ".heif"}
_OFFICE_EXTS = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods",
                ".csv", ".ppt", ".pptx", ".odp"}


def ext_actions() -> dict[str, list[str]]:
    """Map every supported extension to its ordered list of tool ids, filtered
    to tools that actually exist in the registry."""
    from mico360.core.tools import TOOLS_BY_ID
    raw: dict[str, list[str]] = {".pdf": _PDF, ".svg": _SVG}
    for e in _IMAGE_EXTS:
        raw[e] = _IMAGE
    for e in _OFFICE_EXTS:
        raw[e] = _OFFICE
    out: dict[str, list[str]] = {}
    for ext, ids in raw.items():
        valid = [tid for tid in ids if tid in TOOLS_BY_ID]
        if valid:
            out[ext] = valid
    return out


def _launch_prefix() -> str:
    """The command that starts the app, quoted. Frozen: the exe. Source: the
    Python interpreter plus run.py — so the menu works in development too."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return f'"{exe}"'
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    return f'"{exe}" "{run_py}"'


def _icon() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}",0'
    try:
        from mico360.paths import resource_path
        ico = resource_path("app.ico")
        if ico.exists():
            return f'"{ico}"'
    except Exception:
        pass
    return ""


def launch_command(tool_id: str, launch_prefix: str | None = None) -> str:
    """The registry command line for a tool: start the app, open the tool, and
    load the right-clicked file (``%1``)."""
    prefix = launch_prefix if launch_prefix is not None else _launch_prefix()
    return f'{prefix} --tool {tool_id} "%1"'


# =====================================================================
# Registry (Windows only)
# =====================================================================
def _available() -> bool:
    return sys.platform.startswith("win")


def register(base: str = DEFAULT_BASE, launch_prefix: str | None = None) -> bool:
    """Create the cascading menu for every supported extension. Returns True on
    success, False if unavailable (non-Windows) or on error."""
    if not _available():
        return False
    import winreg
    from mico360.core.tools import TOOLS_BY_ID
    icon = _icon()

    def setval(path: str, name: str, value: str) -> None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    try:
        for ext, tool_ids in ext_actions().items():
            parent = rf"{base}\{ext}\shell\{PARENT_KEY}"
            setval(parent, "MUIVerb", MENU_TITLE)
            # Empty SubCommands => cascade built from the nested `shell` subkey.
            setval(parent, "SubCommands", "")
            if icon:
                setval(parent, "Icon", icon)
            for i, tid in enumerate(tool_ids):
                tool = TOOLS_BY_ID[tid]
                # Numeric prefix keeps the menu in our intended order (the shell
                # sorts child verb keys alphabetically).
                verb = rf"{parent}\shell\{i:02d}{tid}"
                setval(verb, "MUIVerb", tool.name)
                if icon:
                    setval(verb, "Icon", icon)
                setval(rf"{verb}\command", "",
                       launch_command(tid, launch_prefix))
        return True
    except Exception:
        return False


def _delete_tree(root, path: str) -> None:
    import winreg
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, path + "\\" + sub)
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def unregister(base: str = DEFAULT_BASE) -> bool:
    """Remove the menu from every extension we might have registered."""
    if not _available():
        return False
    import winreg
    # Use a static ext list (not ext_actions) so a stale tool set still cleans up.
    exts = {".pdf", ".svg"} | _IMAGE_EXTS | _OFFICE_EXTS
    for ext in exts:
        _delete_tree(winreg.HKEY_CURRENT_USER,
                     rf"{base}\{ext}\shell\{PARENT_KEY}")
    return True


def is_registered(base: str = DEFAULT_BASE) -> bool:
    if not _available():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"{base}\.pdf\shell\{PARENT_KEY}"):
            return True
    except OSError:
        return False
