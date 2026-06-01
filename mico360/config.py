"""Persistent application settings backed by QSettings."""
from __future__ import annotations

import json

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

    # --- typed properties ------------------------------------------------
    @property
    def theme(self) -> str:
        # Default to the OS appearance on first run; once the user picks a theme
        # it is remembered (saved) and used from then on.
        if not self._s.contains("ui/theme"):
            from mico360.theme import system_theme
            return system_theme()
        return self._get("ui/theme", "dark", str)

    @theme.setter
    def theme(self, value: str) -> None:
        self._set("ui/theme", value)

    @property
    def output_dir(self) -> str:
        return self._get("io/output_dir", str(default_output_dir()), str)

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        self._set("io/output_dir", value)

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
    def auto_check_updates(self) -> bool:
        return self._get("update/auto_check", True, bool)

    @auto_check_updates.setter
    def auto_check_updates(self, value: bool) -> None:
        self._set("update/auto_check", bool(value))

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


settings = Settings()
