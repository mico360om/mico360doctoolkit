"""Queue management UI — model, selection ops, context actions, result mapping.

Headless (offscreen Qt). Verifies the new queue behaves correctly: empty/populated
counts, add/dedupe, duplicate (same file twice, independent status), move to
top/bottom, retry, remove selected/finished/clear, delete-from-disk row removal,
and result mapping by submission index (robust to duplicates).

Run:  python tests/queue_management_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtWidgets import QApplication  # noqa: E402

from mico360.core import platform_utils  # noqa: E402
from mico360.core.engine import UnitResult  # noqa: E402
from mico360.core.tools import TOOLS_BY_ID  # noqa: E402
from mico360.ui.tool_page import ToolPage  # noqa: E402

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def select_rows(page, rows):
    page.file_list.clearSelection()
    for r in rows:
        page.file_list.item(r).setSelected(True)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    td = Path(tempfile.mkdtemp(prefix="mico360_queue_"))
    pdfs = []
    for i in range(4):
        p = td / f"f{i}.pdf"
        p.write_bytes(b"%PDF-1.4\n%%EOF\n")
        pdfs.append(p)

    page = ToolPage(TOOLS_BY_ID["pdf_compress"])

    # 1. Empty state
    check("Empty state shows '0 files'", page.count_lbl.text() == "0 files",
          page.count_lbl.text())

    # 2. Add + dedupe
    page.add_paths([str(p) for p in pdfs])
    page.add_paths([str(pdfs[0])])  # duplicate add is ignored
    check("Add files populates the queue (dedupe on add)", len(page.items) == 4,
          str(len(page.items)))
    check("Populated count shows item count + pending",
          "4 files" in page.count_lbl.text() and "4 pending" in page.count_lbl.text(),
          page.count_lbl.text())
    check("List view row count matches model", page.file_list.count() == 4)

    # 3. Duplicate row(s): same path appears twice with independent ids
    select_rows(page, [1])
    page._duplicate(page._selected_items())
    check("Duplicate adds a row (same file twice)", len(page.items) == 5)
    same_path = [it for it in page.items if it.path == pdfs[1]]
    check("Duplicated rows share the path but have distinct ids",
          len(same_path) == 2 and same_path[0].id != same_path[1].id)

    # 4. Move to top / bottom
    select_rows(page, [3])
    moved_id = page.items[3].id
    page._move_selected(to_top=True)
    check("Move to top puts the row first", page.items[0].id == moved_id)
    select_rows(page, [0])
    page._move_selected(to_top=False)
    check("Move to bottom puts the row last", page.items[-1].id == moved_id)

    # 5. Result mapping by index — duplicates get independent status
    page.items = [it for it in page.items if it.path in (pdfs[0], pdfs[1])][:1]
    page.add_paths([str(pdfs[1])])
    # Build a queue: [f0, f1] then duplicate f1 -> [f0, f1, f1b]
    page._clear()
    page.add_paths([str(pdfs[0]), str(pdfs[1])])
    select_rows(page, [1])
    page._duplicate(page._selected_items())          # -> f0, f1, f1b
    page._run_items = list(page.items)               # simulate a run submission
    # f1 (index 1) fails; its duplicate f1b (index 2) succeeds — independent.
    page._on_unit_finished(UnitResult("f1.pdf", ok=False, message="boom",
                                      sources=[pdfs[1]], index=1))
    page._on_unit_finished(UnitResult("f1.pdf", ok=True, outputs=[td / "out.pdf"],
                                      sources=[pdfs[1]], index=2))
    check("Result maps by index (duplicate rows get independent status)",
          page.items[1].state == "failed" and page.items[2].state == "done",
          f"{page.items[1].state}/{page.items[2].state}")

    # 6. Retry failed/done
    select_rows(page, [1, 2])
    page._retry(page._selected_items())
    check("Retry resets finished rows to pending",
          all(page.items[r].state == "pending" for r in (1, 2)))

    # 7. Remove finished (mark one done, one failed, then remove)
    page.items[0].state = "done"
    page.items[1].state = "failed"
    page._refresh_list()
    page._remove_finished()
    check("Remove finished drops done+failed rows", len(page.items) == 1,
          str(len(page.items)))

    # 8. Remove selected
    select_rows(page, [0])
    page._remove_selected()
    check("Remove selected drops the selection", len(page.items) == 0)
    check("Back to empty state '0 files'", page.count_lbl.text() == "0 files")

    # 9. Delete from disk -> removes rows for trashed paths (trash mocked)
    page.add_paths([str(p) for p in pdfs])
    real = platform_utils.move_to_trash
    trashed_calls = []
    platform_utils.move_to_trash = lambda p: (trashed_calls.append(Path(p)) or True)
    try:
        select_rows(page, [0, 2])
        page._delete_from_disk(page._selected_items())
    finally:
        platform_utils.move_to_trash = real
    check("Delete from disk trashes the selected sources", len(trashed_calls) == 2,
          str(len(trashed_calls)))
    check("Delete from disk removes those rows from the queue", len(page.items) == 2)

    # 10. AGGREGATE tool: one result applies to all submitted rows
    apage = ToolPage(TOOLS_BY_ID["pdf_merge"])
    apage.add_paths([str(p) for p in pdfs[:3]])
    apage._run_items = list(apage.items)
    apage._on_unit_finished(UnitResult("3 files", ok=True, outputs=[td / "m.pdf"],
                                       sources=list(pdfs[:3]), index=0))
    check("AGGREGATE result marks every submitted row done",
          all(it.state == "done" for it in apage.items))

    import shutil
    shutil.rmtree(td, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} queue check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All queue-management checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
