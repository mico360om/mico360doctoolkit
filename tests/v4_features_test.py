"""v4 feature tests: system-theme default, lazy page construction (startup hang
fix), theme-aware logo, legal documents, and lazy default_output_dir.

Run:  python tests/v4_features_test.py   (offscreen; no GUI shown)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication([])

    from mico360.theme import system_theme, stylesheet
    from mico360.config import settings

    # --- system theme detection + default-on-first-run ------------------
    st = system_theme()
    check("system_theme returns light/dark", st in ("light", "dark"), st)

    saved = settings._s.value("ui/theme", None)
    saved_mode = settings._s.value("ui/theme_mode", None)
    settings._s.remove("ui/theme"); settings._s.remove("ui/theme_mode")
    settings._s.sync()
    check("theme mode defaults to 'system' on first run",
          settings.theme_mode == "system", settings.theme_mode)
    check("theme defaults to the system mode on first run",
          settings.theme == system_theme(), f"{settings.theme} vs {system_theme()}")
    settings.theme = "light"
    check("explicit theme is remembered (not overridden by system)",
          settings.theme == "light")
    if saved is None:
        settings._s.remove("ui/theme")
    else:
        settings._s.setValue("ui/theme", saved)
    if saved_mode is None:
        settings._s.remove("ui/theme_mode")
    else:
        settings._s.setValue("ui/theme_mode", saved_mode)
    settings._s.sync()

    # --- borderless checkbox in the stylesheet --------------------------
    css = stylesheet("dark")
    import re
    m = re.search(r"QCheckBox::indicator \{([^}]*)\}", css)
    check("checkbox indicator has no border",
          bool(m) and "border: none" in m.group(1), m.group(1) if m else "no rule")

    # --- lazy page construction (startup hang fix) ----------------------
    from mico360.ui.main_window import MainWindow
    app = QApplication.instance()
    app.setStyleSheet(stylesheet(settings.theme))
    w = MainWindow()
    check("startup builds only the first page (lazy)", len(w._widgets) == 1,
          f"{len(w._widgets)} pages built at startup")
    from mico360.core.tools import TOOLS
    check("nav entries = Home + tools + 3 system pages",
          len(w._titles) == len(TOOLS) + 4, str(len(w._titles)))
    # settings/help not built until visited
    check("settings page not built until opened", w.settings_page is None)

    # --- theme-aware logo swap ------------------------------------------
    w.apply_theme("dark")
    dark_pix = w.sidebar._pix
    w.apply_theme("light")
    light_pix = w.sidebar._pix
    check("sidebar uses a different logo per theme",
          (not dark_pix.isNull()) and (dark_pix.cacheKey() != light_pix.cacheKey()
                                       if not light_pix.isNull() else True))

    # --- default_output_dir is path-only (no eager mkdir) ---------------
    from mico360.paths import default_output_dir
    d = default_output_dir()
    check("default_output_dir returns a path", isinstance(d, Path) and "MICO360" in str(d))

    # --- legal documents -------------------------------------------------
    from mico360 import legal
    for name, fn in (("About Us", legal.about_us),
                     ("Terms", legal.terms_and_conditions),
                     ("Privacy", legal.privacy_policy)):
        html = fn()
        check(f"legal doc '{name}' has content + contact",
              len(html) > 200 and "info@mico360.com" in html and "mico360.com" in html,
              f"{len(html)} chars")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v4 feature checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
