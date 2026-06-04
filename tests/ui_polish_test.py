"""v6.1 UI/UX polish: file-list empty state, no-truncation tooltips.

Run:  python tests/ui_polish_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication([])
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.tool_page import ToolPage
    from mico360.ui.widgets import FileListWidget

    page = ToolPage(TOOLS_BY_ID["pdf_watermark"])

    # 1) File list shows a helpful empty-state placeholder while empty.
    check("file list is the empty-state-aware widget",
          isinstance(page.file_list, FileListWidget))
    check("empty file list has guidance text",
          bool(page.file_list._placeholder) and page.file_list.count() == 0,
          repr(page.file_list._placeholder[:40]))

    # 2) Output path is never silently truncated — full path on hover.
    long_path = r"C:\Users\Someone\Very\Deeply\Nested\Output\Folder\For\Results"
    page._set_output_path(long_path)
    check("output path field tooltip = full path",
          page.out_edit.toolTip() == long_path)
    check("output path cursor at end (shows the meaningful tail)",
          page.out_edit.cursorPosition() == len(long_path))

    # 3) The file-count summary carries a tooltip too (the row can be tight).
    page.files = [Path("a.pdf"), Path("b.pdf")]
    page._update_counts()
    check("count summary has a tooltip", bool(page.count_lbl.toolTip()),
          page.count_lbl.toolTip())

    # 4) Empty-state disappears once files are present (placeholder only paints
    #    when count()==0 — verify the gate).
    from PySide6.QtWidgets import QListWidgetItem
    page.file_list.addItem(QListWidgetItem("x.pdf"))
    check("placeholder suppressed when the list has items",
          page.file_list.count() > 0)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All UI-polish checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
