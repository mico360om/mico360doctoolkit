"""v5.4 UI tests: Dashboard home, drop routing, favourites, recent-files data,
Light/Dark/System theme mode, and the Toast widget.

Run:  python tests/v54_ui_test.py   (offscreen)
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
    from PySide6.QtCore import Qt
    app = QApplication.instance() or QApplication([])

    from mico360.config import settings
    from mico360.theme import stylesheet
    app.setStyleSheet(stylesheet("dark"))

    # --- drop routing ---------------------------------------------------
    from mico360.ui.dashboard_page import route_for
    check("route .pdf -> pdf_compress", route_for(["a.pdf"]) == "pdf_compress")
    check("route .docx -> word_to_pdf", route_for(["a.docx"]) == "word_to_pdf")
    check("route .xlsx -> excel_to_pdf", route_for(["a.xlsx"]) == "excel_to_pdf")
    check("route .pptx -> pptx_to_pdf", route_for(["a.pptx"]) == "pptx_to_pdf")
    check("route .png -> image_compress", route_for(["a.png"]) == "image_compress")
    check("route unknown -> None", route_for(["a.zzz"]) is None)

    # --- theme mode (system/light/dark) --------------------------------
    saved_mode = settings._s.value("ui/theme_mode", None)
    settings.theme_mode = "system"
    from mico360.theme import system_theme
    check("system mode resolves to effective theme",
          settings.theme == system_theme(), settings.theme)
    settings.theme_mode = "light"
    check("light mode pins light", settings.theme == "light")
    settings.theme_mode = "dark"
    check("dark mode pins dark", settings.theme == "dark")

    # --- favourites toggle ---------------------------------------------
    saved_favs = settings.favorite_tools
    settings.favorite_tools = []
    on = settings.toggle_favorite("pdf_merge")
    check("toggle adds favourite", on and "pdf_merge" in settings.favorite_tools)
    off = settings.toggle_favorite("pdf_merge")
    check("toggle removes favourite", not off and "pdf_merge" not in settings.favorite_tools)
    settings.favorite_tools = saved_favs

    # --- recent files + activity ---------------------------------------
    settings._set_json("home/recent_files", [])
    settings.add_recent_files(["X:/out/a.pdf", "X:/out/b.pdf"])
    settings.add_recent_files(["X:/out/a.pdf"])   # dedup -> moves to front
    rf = settings.recent_files
    check("recent files recorded + deduped", rf[:2] == ["X:/out/a.pdf", "X:/out/b.pdf"],
          str(rf[:3]))
    settings.add_activity("Compress PDF — 3 file(s) done")
    check("activity recorded", settings.recent_activity[0].startswith("Compress PDF"))

    # --- output_dir guard (rejects invalid / corrupted values) ----------
    import os
    saved_out = settings._s.value("io/output_dir", None)
    settings._s.setValue("io/output_dir", "saved 602.0 B (19%)"); settings._s.sync()
    check("output_dir ignores a non-absolute/corrupted stored value",
          os.path.isabs(settings.output_dir), repr(settings.output_dir))
    settings.output_dir = "not/absolute"
    check("output_dir setter rejects a non-absolute path",
          os.path.isabs(settings.output_dir))
    if saved_out is not None:
        settings._s.setValue("io/output_dir", saved_out)
    else:
        settings._s.remove("io/output_dir")
    settings._s.sync()

    # --- Dashboard builds + refresh ------------------------------------
    from mico360.ui.dashboard_page import DashboardPage
    dash = DashboardPage()
    opened = {}
    dash.openTool.connect(lambda t: opened.__setitem__("tool", t))
    dash.openToolWithFiles.connect(lambda t, f: opened.update(tool2=t, files=f))
    dash.refresh()
    check("dashboard builds", dash is not None)

    # --- MainWindow: Home is default, open_tool works, toast -----------
    from mico360.ui.main_window import MainWindow
    w = MainWindow()
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.show(); app.processEvents()
    check("Home is the landing page (index 0 built first)",
          0 in w._widgets and w._titles[0] == "Home")
    w.open_tool("pdf_merge")
    app.processEvents()
    idx = w._tool_index["pdf_merge"]
    check("open_tool navigates to the tool", w.stack.currentWidget() is w._widgets[idx])

    # open_tool with files preloads them into the page (use real files)
    import tempfile
    import fitz
    td = Path(tempfile.mkdtemp())
    reals = []
    for nm in ("one.pdf", "two.pdf"):
        p = td / nm
        doc = fitz.open(); doc.new_page(); doc.save(str(p)); doc.close()
        reals.append(str(p))
    w.open_tool("pdf_merge", reals)
    app.processEvents()
    from PySide6.QtWidgets import QScrollArea
    wrap = w._widgets[idx]
    page = wrap.widget() if isinstance(wrap, QScrollArea) else wrap
    check("open_tool preloads dropped files", len(page.files) == 2, str(len(page.files)))

    w.show_toast("Test toast", "ok")
    check("toast shown", len(w._toasts) >= 1)

    if saved_mode is not None:
        settings._s.setValue("ui/theme_mode", saved_mode); settings._s.sync()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v5.4 UI checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
