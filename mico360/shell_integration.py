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
# A single top-level "just open it" verb that opens the target in the app and
# lets it auto-route by file type (no specific tool preselected).
OPEN_KEY = "MICO360Open"
OPEN_TITLE = "Open with MICO360 Toolkit"
DEFAULT_BASE = r"Software\Classes\SystemFileAssociations"

# Curated, ordered actions per file family — the tools a user most often wants
# straight from a right-click. (Every tool is still reachable inside the app.)
_PDF = ["pdf_compress", "pdf_merge", "pdf_split", "pdf_organize", "pdf_protect",
        "pdf_watermark", "pdf_ocr", "pdf_convert", "pdf_metadata"]
_IMAGE = ["image_compress", "image_resize", "image_convert", "image_to_pdf",
          "pdf_ocr", "image_watermark", "image_to_svg"]
_OFFICE = ["office_to_pdf", "to_markdown"]
_SVG = ["svg_to_image"]

# Curated actions for a right-clicked *folder* (and the folder background): the
# common "apply this to everything in here" batch jobs. Each opens the tool with
# the folder loaded — the app expands it to the matching files for that tool.
_FOLDER = ["pdf_compress", "pdf_merge", "pdf_convert",
           "image_compress", "image_to_pdf", "office_to_pdf"]

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


def folder_actions() -> list[str]:
    """Ordered tool ids for the folder / folder-background menu (existing only)."""
    from mico360.core.tools import TOOLS_BY_ID
    return [tid for tid in _FOLDER if tid in TOOLS_BY_ID]


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


def _tool_icon(tool_id: str) -> str:
    """Icon string for a tool's submenu verb — its own bundled ``.ico`` if
    present, else the generic app icon so the menu still works."""
    try:
        from mico360.paths import resource_path
        p = resource_path("menu_icons", f"{tool_id}.ico")
        if p.exists():
            return f'"{p}"'
    except Exception:
        pass
    return _icon()


def launch_command(tool_id: str, launch_prefix: str | None = None,
                   arg: str = "%1") -> str:
    """The registry command line for a tool: start the app, open the tool, and
    load the right-clicked target. ``arg`` is ``%1`` for a file verb or ``%V``
    for a folder / folder-background verb (the app expands a folder to the
    tool's matching files)."""
    prefix = launch_prefix if launch_prefix is not None else _launch_prefix()
    # "--" ends the options, so a file named e.g. "-draft.pdf" is still a file.
    return f'{prefix} --tool {tool_id} -- "{arg}"'


def open_command(launch_prefix: str | None = None, arg: str = "%1") -> str:
    """Command for the top-level "Open with MICO360 Toolkit" verb: open the
    target with no tool preselected so the app auto-routes by file type (for a
    folder, by what's inside it). ``arg`` is ``%1`` (file) or ``%V`` (folder)."""
    prefix = launch_prefix if launch_prefix is not None else _launch_prefix()
    return f'{prefix} -- "{arg}"'


# =====================================================================
# Registry (Windows only)
# =====================================================================
def _available() -> bool:
    return sys.platform.startswith("win")


def _classes_root(base: str) -> str:
    """The ``Software\\Classes`` root implied by ``base`` (which normally ends in
    ``\\SystemFileAssociations``). Keeps folder keys in the same sandbox as the
    per-extension keys during tests."""
    suffix = r"\SystemFileAssociations"
    return base[:-len(suffix)] if base.endswith(suffix) else base


def _dir_menu_parents(base: str) -> list[str]:
    """The two folder verbs: right-clicking a folder, and the folder background."""
    root = _classes_root(base)
    return [rf"{root}\Directory\shell\{PARENT_KEY}",
            rf"{root}\Directory\Background\shell\{PARENT_KEY}"]


def register(base: str = DEFAULT_BASE, launch_prefix: str | None = None) -> bool:
    """Create the cascading menu for every supported extension, and for folders
    (a right-clicked folder and the folder background). Returns True on success,
    False if unavailable (non-Windows) or on error."""
    if not _available():
        return False
    import winreg
    from mico360.core.tools import TOOLS_BY_ID
    icon = _icon()

    def setval(path: str, name: str, value: str) -> None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    def write_cascade(parent: str, tool_ids: list[str], arg: str) -> None:
        # Start from an empty submenu: child keys are "<index><tool_id>", so a
        # release that adds, removes or reorders tools would otherwise leave old
        # entries beside the new ones (a removed tool still launching).
        _delete_tree(winreg.HKEY_CURRENT_USER, rf"{parent}\shell")
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
            # Each submenu item shows its own tool icon (falls back to the app
            # icon if the per-tool .ico isn't bundled for some reason).
            tool_icon = _tool_icon(tid)
            if tool_icon:
                setval(verb, "Icon", tool_icon)
            setval(rf"{verb}\command", "",
                   launch_command(tid, launch_prefix, arg=arg))

    def write_open(shell_base: str, arg: str) -> None:
        # A single top-level verb: "Open with MICO360 Toolkit" (auto-route).
        key = rf"{shell_base}\{OPEN_KEY}"
        setval(key, "MUIVerb", OPEN_TITLE)
        if icon:
            setval(key, "Icon", icon)
        setval(rf"{key}\command", "", open_command(launch_prefix, arg))

    try:
        for ext, tool_ids in ext_actions().items():
            shell_base = rf"{base}\{ext}\shell"
            write_open(shell_base, "%1")
            write_cascade(rf"{shell_base}\{PARENT_KEY}", tool_ids, "%1")
        # Folder + folder-background: pass %V (the folder path); the app expands
        # it to the tool's matching files (and, for "Open with", auto-routes by
        # what's inside).
        fa = folder_actions()
        if fa:
            for parent in _dir_menu_parents(base):
                shell_base = parent.rsplit("\\", 1)[0]   # ...\shell
                write_open(shell_base, "%V")
                write_cascade(parent, fa, "%V")
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


def _our_extensions(base: str) -> set[str]:
    """Every extension under *base* that carries one of our verbs — including
    ones a previous release registered but this one no longer lists."""
    import winreg
    found: set[str] = set()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base, 0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    ext = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                for verb in (PARENT_KEY, OPEN_KEY):
                    try:
                        winreg.CloseKey(winreg.OpenKey(
                            winreg.HKEY_CURRENT_USER, rf"{base}\{ext}\shell\{verb}"))
                        found.add(ext)
                    except OSError:
                        pass
    except OSError:
        pass
    return found


def unregister(base: str = DEFAULT_BASE) -> bool:
    """Remove the menu from every extension we might have registered."""
    if not _available():
        return False
    import winreg
    # The static list plus a sweep for our keys anywhere under base, so
    # extensions dropped by a newer release are cleaned up too.
    exts = {".pdf", ".svg"} | _IMAGE_EXTS | _OFFICE_EXTS | _our_extensions(base)
    for ext in exts:
        _delete_tree(winreg.HKEY_CURRENT_USER,
                     rf"{base}\{ext}\shell\{PARENT_KEY}")
        _delete_tree(winreg.HKEY_CURRENT_USER,
                     rf"{base}\{ext}\shell\{OPEN_KEY}")
    for parent in _dir_menu_parents(base):        # folder + folder-background
        _delete_tree(winreg.HKEY_CURRENT_USER, parent)
        shell_base = parent.rsplit("\\", 1)[0]
        _delete_tree(winreg.HKEY_CURRENT_USER, rf"{shell_base}\{OPEN_KEY}")
    return True


def registered_command(base: str = DEFAULT_BASE) -> str:
    """The command line our PDF "Open with" verb currently runs ('' if none)."""
    if not _available():
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"{base}\.pdf\shell\{OPEN_KEY}\command") as k:
            return str(winreg.QueryValueEx(k, "")[0])
    except OSError:
        return ""


def self_heal(base: str = DEFAULT_BASE, launch_prefix: str | None = None) -> str:
    """Keep a registered menu pointing at *this* app. If the install moved (or
    an older build registered different entries) the menu is rewritten; menus
    the user turned off are left alone. Returns 'ok', 'rewritten' or 'off'."""
    if not _available() or not is_registered(base):
        return "off"
    want = open_command(launch_prefix, "%1")
    if registered_command(base) == want:
        return "ok"
    register(base, launch_prefix)
    return "rewritten"


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
