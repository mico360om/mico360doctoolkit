"""Sidebar search + collapsible categories.

Run:  python tests/sidebar_test.py   (offscreen)
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


def visible_items(sb):
    return [it for it in sb._items if it.isVisible()]


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    app = QApplication.instance() or QApplication([])
    from mico360.config import settings
    from mico360.theme import stylesheet
    app.setStyleSheet(stylesheet("dark"))

    # reset persisted collapse state for a deterministic run
    saved = settings.collapsed_groups
    settings.collapsed_groups = []

    from mico360.ui.main_window import MainWindow
    w = MainWindow()
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.show()
    # Use a wide window so the sidebar starts expanded (this test drives the
    # expanded search/collapse behaviour); the app otherwise auto-collapses the
    # sidebar on narrow/small screens.
    w.resize(1180, 760)
    app.processEvents()
    sb = w.sidebar

    # --- search filters by label ----------------------------------------
    sb._search.setText("merge")
    app.processEvents()
    vis = visible_items(sb)
    check("search 'merge' shows only matching tools",
          all("merge" in it._label.lower() for it in vis) and len(vis) >= 1,
          f"{[it._label for it in vis]}")
    check("non-matching group headers hidden during search",
          any(not g["header"].isVisible() for g in sb._groups))

    sb._search.setText("pdf")
    app.processEvents()
    vis = visible_items(sb)
    check("search 'pdf' matches several tools", len(vis) >= 5, str(len(vis)))

    sb._search.setText("")            # clear restores everything
    app.processEvents()
    check("clearing search restores all items",
          len(visible_items(sb)) == len(sb._items), str(len(visible_items(sb))))
    check("all section headers visible again",
          all(g["header"].isVisible() for g in sb._groups))

    # --- collapsible categories -----------------------------------------
    # Tools are grouped by job; "Organize" holds Merge/Split/Organize PDF.
    pdf_grp = next(g for g in sb._groups if g["name"] == "Organize")
    n_pdf = len(pdf_grp["items"])
    sb._toggle_group(pdf_grp)
    app.processEvents()
    check("collapsing 'Organize' hides its items",
          all(not it.isVisible() for it in pdf_grp["items"]), str(n_pdf))
    check("collapse chevron shown (▸)", "▸" in pdf_grp["header"].text())
    check("collapse persisted to settings", "Organize" in settings.collapsed_groups)

    sb._toggle_group(pdf_grp)
    app.processEvents()
    check("expanding 'Organize' shows its items again",
          all(it.isVisible() for it in pdf_grp["items"]))
    check("expand removes from persisted collapse",
          "Organize" not in settings.collapsed_groups)

    # --- select() expands a collapsed group -----------------------------
    sb._toggle_group(pdf_grp)         # collapse again
    app.processEvents()
    merge_idx = w._tool_index["pdf_merge"]
    sb.select(merge_idx)
    app.processEvents()
    check("navigating to a tool expands its collapsed group",
          not pdf_grp["collapsed"] and
          all(it.isVisible() for it in pdf_grp["items"]))

    # --- search ignores collapse + icon mode shows all ------------------
    sb._toggle_group(pdf_grp)         # collapse
    sb._search.setText("split")
    app.processEvents()
    check("search reveals a match inside a collapsed group",
          any(it._label.lower() == "split pdf" and it.isVisible()
              for it in pdf_grp["items"]))
    sb._search.setText("")
    app.processEvents()

    # icon-only mode: every tool visible regardless of collapse
    sb.set_collapsed(True)
    app.processEvents()
    check("icon-only sidebar shows every tool",
          len(visible_items(sb)) == len(sb._items),
          str(len(visible_items(sb))))
    check("search box hidden when collapsed", not sb._search_wrap.isVisible())
    sb.set_collapsed(False)
    app.processEvents()

    settings.collapsed_groups = saved
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All sidebar checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
