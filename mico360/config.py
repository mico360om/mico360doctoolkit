"""Persistent application settings backed by QSettings."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QSettings

from mico360.paths import default_output_dir

ORG = "MICO360"
APP = "DocToolkit"


class Settings:
    """Thin typed wrapper around QSettings."""

    def __init__(self) -> None:
        self._s = QSettings(QSettings.IniFormat, QSettings.UserScope, ORG, APP)

    # --- generic helpers -------------------------------------------------
    def _get(self, key: str, default, cast):
        val = self._s.value(key, default)
        if cast is bool:
            if isinstance(val, str):
                return val.lower() in ("1", "true", "yes", "on")
            return bool(val)
        try:
            return cast(val)
        except (TypeError, ValueError):
            return default

    def _set(self, key: str, value) -> None:
        self._s.setValue(key, value)
        self._s.sync()

    # --- per-tool remembered options -------------------------------------
    def tool_options(self, tool_id: str) -> dict:
        """Return the last-used option values for a tool (empty if none)."""
        raw = self._get(f"tool_opts/{tool_id}", "", str)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    def set_tool_options(self, tool_id: str, values: dict) -> None:
        try:
            self._set(f"tool_opts/{tool_id}", json.dumps(values))
        except (TypeError, ValueError):
            pass

    # --- JSON helpers ----------------------------------------------------
    def _get_json(self, key: str, default):
        raw = self._get(key, "", str)
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return default

    def _set_json(self, key: str, value) -> None:
        try:
            self._set(key, json.dumps(value))
        except (TypeError, ValueError):
            pass

    # --- typed properties ------------------------------------------------
    @property
    def theme_mode(self) -> str:
        """'system' | 'light' | 'dark'. Defaults to 'system' on first run; an
        older saved ui/theme is migrated to an explicit light/dark pin."""
        if self._s.contains("ui/theme_mode"):
            return self._get("ui/theme_mode", "system", str)
        if self._s.contains("ui/theme"):
            return self._get("ui/theme", "dark", str)
        return "system"

    @theme_mode.setter
    def theme_mode(self, value: str) -> None:
        self._set("ui/theme_mode", value if value in ("system", "light", "dark")
                  else "system")

    @property
    def theme(self) -> str:
        """The *effective* theme ('light' or 'dark'), resolving 'system'."""
        mode = self.theme_mode
        if mode == "system":
            from mico360.theme import system_theme
            return system_theme()
        return mode if mode in ("light", "dark") else "dark"

    @theme.setter
    def theme(self, value: str) -> None:
        # Setting an explicit theme pins light/dark (e.g. the top-bar toggle).
        self.theme_mode = value

    @property
    def output_dir(self) -> str:
        val = self._get("io/output_dir", "", str)
        # Guard against a blank / non-absolute / invalid stored value (a deleted
        # folder, a removed drive, or a stale/corrupted setting): fall back to
        # the default so the UI never shows garbage and runs never target it.
        if not val or not os.path.isabs(val):
            return str(default_output_dir())
        return val

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        # Only persist real, absolute folder paths.
        if value and os.path.isabs(str(value)):
            self._set("io/output_dir", str(value))

    @property
    def same_as_source(self) -> bool:
        return self._get("io/same_as_source", False, bool)

    @same_as_source.setter
    def same_as_source(self, value: bool) -> None:
        self._set("io/same_as_source", value)

    @property
    def overwrite(self) -> bool:
        return self._get("io/overwrite", False, bool)

    @overwrite.setter
    def overwrite(self, value: bool) -> None:
        self._set("io/overwrite", value)

    @property
    def max_workers(self) -> int:
        return self._get("perf/max_workers", 0, int)  # 0 = auto

    @max_workers.setter
    def max_workers(self, value: int) -> None:
        self._set("perf/max_workers", int(value))

    @property
    def ocr_use_gpu(self) -> bool:
        """Use the GPU (DirectML, any DX12 GPU) for OCR when one is available.
        Default on; the engine silently falls back to CPU on machines without a
        usable GPU, so this is safe to leave enabled everywhere."""
        return self._get("perf/ocr_use_gpu", True, bool)

    @ocr_use_gpu.setter
    def ocr_use_gpu(self, value: bool) -> None:
        self._set("perf/ocr_use_gpu", bool(value))

    @property
    def auto_check_updates(self) -> bool:
        return self._get("update/auto_check", True, bool)

    @auto_check_updates.setter
    def auto_check_updates(self, value: bool) -> None:
        self._set("update/auto_check", bool(value))

    @property
    def pending_update(self) -> dict:
        """Set just before an update installer is launched: {version, started}.
        Read on next startup to show the 'updated successfully' confirmation."""
        v = self._get_json("update/pending", {})
        return v if isinstance(v, dict) else {}

    @pending_update.setter
    def pending_update(self, value) -> None:
        self._set_json("update/pending", dict(value or {}))

    @property
    def open_output_when_done(self) -> bool:
        return self._get("ui/open_output_when_done", True, bool)

    @open_output_when_done.setter
    def open_output_when_done(self, value: bool) -> None:
        self._set("ui/open_output_when_done", value)

    @property
    def ghostscript_path(self) -> str:
        return self._get("deps/ghostscript", "", str)

    @ghostscript_path.setter
    def ghostscript_path(self, value: str) -> None:
        self._set("deps/ghostscript", value)

    @property
    def libreoffice_path(self) -> str:
        return self._get("deps/libreoffice", "", str)

    @libreoffice_path.setter
    def libreoffice_path(self, value: str) -> None:
        self._set("deps/libreoffice", value)

    # --- dashboard / home data ------------------------------------------
    _DEFAULT_FAVS = ["pdf_compress", "pdf_merge", "pdf_convert", "image_compress"]

    @property
    def favorite_tools(self) -> list:
        v = self._get_json("home/favorites", None)
        return v if isinstance(v, list) else list(self._DEFAULT_FAVS)

    @favorite_tools.setter
    def favorite_tools(self, value) -> None:
        self._set_json("home/favorites", list(value))

    def toggle_favorite(self, tool_id: str) -> bool:
        """Pin/unpin a tool. Returns the new pinned state."""
        favs = self.favorite_tools
        if tool_id in favs:
            favs.remove(tool_id)
            pinned = False
        else:
            favs.append(tool_id)
            pinned = True
        self.favorite_tools = favs
        return pinned

    @property
    def recent_files(self) -> list:
        v = self._get_json("home/recent_files", [])
        return v if isinstance(v, list) else []

    def add_recent_files(self, paths, cap: int = 12) -> None:
        cur = self.recent_files
        for p in paths:
            p = str(p)
            if p in cur:
                cur.remove(p)
            cur.insert(0, p)
        self._set_json("home/recent_files", cur[:cap])

    def clear_recent(self) -> None:
        self._set_json("home/recent_files", [])
        self._set_json("home/recent_activity", [])

    @property
    def collapsed_groups(self) -> list:
        v = self._get_json("ui/collapsed_groups", [])
        return v if isinstance(v, list) else []

    @collapsed_groups.setter
    def collapsed_groups(self, value) -> None:
        self._set_json("ui/collapsed_groups", list(value))

    @property
    def recent_activity(self) -> list:
        v = self._get_json("home/recent_activity", [])
        return v if isinstance(v, list) else []

    def add_activity(self, line: str, cap: int = 10) -> None:
        cur = self.recent_activity
        cur.insert(0, str(line))
        self._set_json("home/recent_activity", cur[:cap])


settings = Settings()
