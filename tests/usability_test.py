"""Usability features: keyboard shortcuts, running window title, failed-item
recovery, first-run hints, teaching empty state, search-everywhere, recent-file
actions, undo, and keyboard accessibility.

Run:  python tests/usability_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QShortcut
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    app = QApplication.instance() or QApplication([])
    # Never let a real dialog block the test; count Browse invocations.
    browse_calls = {"n": 0}

    def _fake_open(*a, **k):
        browse_calls["n"] += 1
        return ([], "")
    QFileDialog.getOpenFileNames = staticmethod(_fake_open)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)

    from mico360.config import settings
    from mico360.theme import stylesheet
    app.setStyleSheet(stylesheet(settings.theme))
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.main_window import MainWindow
    from mico360.ui.widgets import Toast, DropArea

    # keep and restore the persisted flag we flip
    saved_hint = settings.first_run_hints_shown
    saved_favs = list(settings.favorite_tools)

    w = MainWindow()
    w.resize(1300, 850)
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.show()
    for _ in range(6):
        app.processEvents()

    scmap = {s.key().toString(): s for s in w.findChildren(QShortcut)}

    # ================= 1. shortcuts exist ==========================
    print("--- keyboard shortcuts ---")
    for key in ("Ctrl+K", "Ctrl+O", "Ctrl+Return", "Ctrl+Enter", "Esc",
                "Ctrl+V", "F1", "Ctrl+1", "Ctrl+9"):
        check(f"shortcut {key} is registered", key in scmap)

    # F1 -> Help
    scmap["F1"].activated.emit()
    for _ in range(3):
        app.processEvents()
    check("F1 opens the Help page", w.top_title.text() == "Help",
          w.top_title.text())

    # Ctrl+K -> search box focused/visible
    scmap["Ctrl+K"].activated.emit()
    for _ in range(3):
        app.processEvents()
    check("Ctrl+K reveals the tool search box",
          w.sidebar._search_wrap.isVisibleTo(w.sidebar))

    # Ctrl+1 -> first pinned tool
    settings.favorite_tools = ["pdf_merge"]
    scmap["Ctrl+1"].activated.emit()
    for _ in range(3):
        app.processEvents()
    check("Ctrl+1 jumps to the first pinned tool",
          w.top_title.text() == TOOLS_BY_ID["pdf_merge"].name, w.top_title.text())

    # tool-scoped shortcuts route to the CURRENT tool page
    w.open_tool("pdf_compress")
    tp = w._current_tool_page()
    calls = {"start": 0, "browse": 0, "paste": 0, "cancel": 0}
    tp.start = lambda: calls.__setitem__("start", calls["start"] + 1)
    tp._browse_files = lambda: calls.__setitem__("browse", calls["browse"] + 1)
    tp.paste_from_clipboard = lambda: calls.__setitem__("paste", calls["paste"] + 1)
    tp.cancel_if_running = lambda: calls.__setitem__("cancel", calls["cancel"] + 1)
    scmap["Ctrl+Return"].activated.emit()
    scmap["Ctrl+O"].activated.emit()
    scmap["Ctrl+V"].activated.emit()
    scmap["Esc"].activated.emit()
    for _ in range(3):
        app.processEvents()
    check("Ctrl+Enter routes to the current tool's Start", calls["start"] == 1)
    check("Ctrl+O routes to Add files", calls["browse"] == 1)
    check("Ctrl+V routes to Paste", calls["paste"] == 1)
    check("Esc routes to Cancel", calls["cancel"] == 1)

    # ================= 2. running window title =====================
    print("--- running window title ---")
    base = w._base_title
    tp.runStatus.emit("Compress PDF: 37 of 200 · ~4m 00s left · 2 failed")
    check("window title shows batch progress while running",
          "37 of 200" in w.windowTitle() and "2 failed" in w.windowTitle(),
          w.windowTitle())
    tp.runStatus.emit("")
    check("title resets to the app name when idle", w.windowTitle() == base,
          w.windowTitle())

    # ================= 3. failed-item recovery =====================
    print("--- retry failed ---")
    from mico360.ui.tool_page import QueueItem, ToolPage
    page = ToolPage(TOOLS_BY_ID["pdf_compress"])
    page.items = [QueueItem(path=Path("a.pdf"), state="failed"),
                  QueueItem(path=Path("b.pdf"), state="failed"),
                  QueueItem(path=Path("c.pdf"), state="done")]
    page._update_counts()
    check("Retry-failed button appears with the count",
          page.btn_retry_failed.isVisibleTo(page)
          and "2 failed" in page.btn_retry_failed.text(),
          page.btn_retry_failed.text())
    # clicking it resets the failed rows to pending and starts
    started = {"n": 0}
    page.start = lambda: started.__setitem__("n", started["n"] + 1)
    page._retry_failed()
    check("Retry-failed resets failed rows to pending and runs",
          started["n"] == 1
          and all(it.state != "failed" for it in page.items[:2]))

    # ================= 4. first-run hints ==========================
    print("--- first-run hints ---")
    from mico360.ui.dashboard_page import DashboardPage
    settings.first_run_hints_shown = False
    d1 = DashboardPage()
    hints = d1._build_first_run_hints()
    check("first-run hints are shown when the flag is unset", hints is not None)
    settings.first_run_hints_shown = True
    d2 = DashboardPage()
    check("first-run hints do NOT show once dismissed",
          d2._build_first_run_hints() is None)

    # ================= 5. teaching empty state =====================
    print("--- empty state ---")
    empty_page = ToolPage(TOOLS_BY_ID["pdf_compress"])
    check("queue empty state mentions paste (Ctrl+V)",
          "Ctrl+V" in empty_page.file_list._placeholder)
    before = browse_calls["n"]
    empty_page.file_list.emptyClicked.emit()   # wired to _browse_files
    check("clicking the empty queue asks to browse (opens file picker)",
          browse_calls["n"] == before + 1)

    # real clipboard paste adds the copied file(s) to the queue
    with tempfile.TemporaryDirectory() as td:
        import fitz
        f = Path(td) / "pasted.pdf"
        doc = fitz.open(); doc.new_page(); doc.save(str(f)); doc.close()
        from PySide6.QtCore import QMimeData, QUrl
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(str(f))])
        QApplication.clipboard().setMimeData(md)
        paste_page = ToolPage(TOOLS_BY_ID["pdf_compress"])
        n0 = len(paste_page.items)
        paste_page.paste_from_clipboard()
        for _ in range(3):
            app.processEvents()
        check("Ctrl+V paste actually adds the copied file to the queue",
              len(paste_page.items) == n0 + 1, f"{len(paste_page.items)} items")

    # ================= 6. search everywhere ========================
    print("--- search everywhere ---")
    def visible_labels():
        return {it._label for it in w.sidebar._items if it.isVisibleTo(w.sidebar)}
    w.sidebar.set_collapsed(False)
    w.sidebar._search.setText("password")
    for _ in range(2):
        app.processEvents()
    vis = visible_labels()
    check("searching an option word ('password') surfaces Protect PDF",
          "Protect PDF" in vis, str(sorted(vis))[:80])
    w.sidebar._search.setText("dpi")
    for _ in range(2):
        app.processEvents()
    vis = visible_labels()
    check("searching 'dpi' surfaces a compression tool",
          any("Compress" in v for v in vis), str(sorted(vis))[:80])
    w.sidebar._search.setText("")

    # ================= 7. recent-file actions ======================
    print("--- recent-file right-click ---")
    check("dashboard has a recent-file context menu handler",
          hasattr(DashboardPage, "_recent_menu"))

    # ================= 8. undo ====================================
    print("--- undo remove/clear ---")
    up = ToolPage(TOOLS_BY_ID["pdf_compress"])
    up.items = [QueueItem(path=Path(f"{i}.pdf")) for i in range(3)]
    up._refresh_list()
    captured = {}
    up.toastAction.connect(lambda m, k, a, cb: captured.update(
        msg=m, action=a, cb=cb))
    up._clear()
    check("clearing the queue offers an Undo toast",
          captured.get("action") == "Undo" and up.items == [])
    captured["cb"]()          # invoke Undo
    check("Undo restores the cleared rows", len(up.items) == 3)

    # ================= 9. accessibility ============================
    print("--- accessibility ---")
    check("drop area is keyboard-focusable",
          up.drop.focusPolicy() == Qt.StrongFocus)
    fired = {"n": 0}
    up.drop.browseFiles.connect(lambda: fired.__setitem__("n", fired["n"] + 1))
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    up.drop.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    check("Enter on the drop area triggers Browse", fired["n"] == 1)

    t = Toast(w, "Removed 2 rows.", "info", action_text="Undo",
              on_action=lambda: None)
    check("an actionable toast builds an action button", hasattr(t, "_btn"))

    # restore persisted state
    settings.first_run_hints_shown = saved_hint
    settings.favorite_tools = saved_favs
    w.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Usability: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(_rc if isinstance(_rc, int) else 0)
