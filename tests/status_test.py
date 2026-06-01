"""Per-file status: files are marked done, skipped on re-run, and Redo re-arms.

Run:  python tests/status_test.py   (offscreen; no GUI shown)
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

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from mico360.config import settings
from mico360.core.tools import TOOLS_BY_ID
from mico360.logging_setup import setup_logging
from mico360.theme import stylesheet
from mico360.ui.tool_page import ToolPage

# Don't let the "already done" modal block the headless test.
QMessageBox.information = staticmethod(lambda *a, **k: None)

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _img(path: Path) -> Path:
    from PIL import Image
    Image.new("RGB", (600, 400), (160, 32, 31)).save(path)
    return path


def run(page: ToolPage, timeout=30000) -> dict:
    res: dict = {}
    loop = QEventLoop()
    page.start()
    if page.controller is None:           # start() short-circuited (all done)
        return res
    page.controller.finished.connect(lambda s: (res.update(s), loop.quit()))
    t = QTimer(); t.setSingleShot(True); t.timeout.connect(loop.quit); t.start(timeout)
    loop.exec()
    return res


def main() -> int:
    setup_logging()
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(stylesheet(settings.theme))
    saved = settings.output_dir

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        settings.output_dir = str(out)
        a, b = _img(tmp / "a.png"), _img(tmp / "b.png")

        page = ToolPage(TOOLS_BY_ID["image_compress"])
        page.chk_same.setChecked(False)
        page.out_edit.setText(str(out))
        page.add_paths([str(a), str(b)])
        check("new files start pending",
              all(page._st(p)["state"] == "pending" for p in page.files))

        run(page)
        states = [page._st(p)["state"] for p in page.files]
        check("all files done after run", states == ["done", "done"], str(states))
        outs1 = [page._st(p)["outputs"][0] for p in page.files]
        check("each file recorded an output", all(o.exists() for o in outs1))
        check("list shows done glyph", page.file_list.item(0).text().startswith("✓"),
              repr(page.file_list.item(0).text()[:3]))

        # total-saved summary (compress tool) is a non-empty, sensible string
        saved = page._total_saved()
        check("total-saved summary produced",
              bool(saved) and ("saved" in saved or "optimized" in saved), repr(saved))

        # Re-run: everything is done, so start() must skip (no reprocessing).
        mtimes = [o.stat().st_mtime_ns for o in outs1]
        run(page)
        check("re-run skips done files (start short-circuited)",
              page.btn_start.isEnabled() and page.controller is None)
        check("outputs were not rewritten",
              [o.stat().st_mtime_ns for o in outs1] == mtimes)

        # Redo re-arms the files, then they process again.
        page._redo()
        check("redo resets to pending",
              all(page._st(p)["state"] == "pending" for p in page.files))
        run(page)
        check("files done again after redo",
              all(page._st(p)["state"] == "done" for p in page.files))

        # A failed unit marks its source "failed" (deterministic: inject the
        # result the engine would emit, avoiding thread-pool timing).
        from mico360.core.engine import UnitResult
        f0 = page.files[0]
        page._on_unit_finished(UnitResult(f0.name, False, message="boom", sources=[f0]))
        check("failed unit marks file failed", page._st(f0)["state"] == "failed",
              page._st(f0)["state"])
        check("failed files are re-armed by start (not skipped)",
              f0 in [p for p in page.files if page._st(p)["state"] != "done"])

        # "Remove done" drops only finished files, keeps the rest.
        page._st(page.files[0]).update(state="done")   # f0 -> done
        before_n = len(page.files)
        n_done = sum(1 for p in page.files if page._st(p)["state"] == "done")
        page._remove_done()
        check("remove-done drops only finished files",
              len(page.files) == before_n - n_done and
              all(page._st(p)["state"] != "done" for p in page.files),
              f"{before_n}->{len(page.files)}, removed {n_done}")

    settings.output_dir = saved
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All status checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
