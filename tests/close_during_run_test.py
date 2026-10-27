"""Closing the window (or pressing Cancel) while a big batch runs.

Reported on a laptop as "the app crashed while compressing 200+ files": the
window had gone but the process kept working through the whole queue invisibly
for minutes, and a relaunch said the app was already running.

Checks, with a 120-file Ghostscript run (the slowest common tool):
* closing the main window cancels the batch: it winds down within seconds, not
  after the remaining 100+ files;
* queued files are reported as skipped (not failed), running ones stop at their
  next check, and no half-written output is left behind;
* helper processes (Ghostscript) are killed on cancel, so a long conversion
  doesn't keep the process alive;
* native-crash capture (faulthandler) is on, writing to the logs folder.

Run:  python tests/close_during_run_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _make_pdfs(folder: Path, n: int) -> list[Path]:
    import fitz
    from PIL import Image
    folder.mkdir(parents=True, exist_ok=True)
    photo = folder / "photo.jpg"
    Image.radial_gradient("L").resize((1400, 1000)).convert("RGB").save(photo, quality=90)
    out = []
    for i in range(n):
        d = fitz.open()
        for p in range(6):
            pg = d.new_page()
            pg.insert_image(pg.rect, filename=str(photo))
            pg.insert_text((50, 60), f"Document {i} page {p}", fontsize=10)
        path = folder / f"doc_{i:03}.pdf"
        d.save(str(path), deflate=True)
        d.close()
        out.append(path)
    return out


def main() -> int:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from mico360 import logging_setup
    from mico360.config import settings
    from mico360.core import util
    from mico360.core.processors import find_ghostscript
    from mico360.ui.main_window import MainWindow

    logging_setup.setup_logging()
    import faulthandler
    check("native-crash capture is on", faulthandler.is_enabled())
    check("…writing to the logs folder",
          logging_setup._native_crash_file is not None
          and Path(logging_setup._native_crash_file.name).name == logging_setup.NATIVE_CRASH_LOG)

    work = Path(tempfile.mkdtemp(prefix="mico_close_"))
    srcs = _make_pdfs(work / "src", 120)
    out_dir = work / "out"
    out_dir.mkdir()
    saved = (settings.max_workers, settings.output_dir)
    settings.max_workers = 2
    settings.output_dir = str(out_dir)
    level = "medium" if find_ghostscript() else "lossless"
    print(f"--- 120 files, {level}, 2 workers, window closed after 2 s ---")
    try:
        win = MainWindow()
        win.show()
        win.open_tool("pdf_compress", [str(p) for p in srcs])
        for _ in range(20):
            app.processEvents()
        page = win._current_tool_page()
        check("the tool page holds the 120 files", page is not None
              and page.file_list.count() == 120, str(page and page.file_list.count()))
        ctl = page.options_widget._controls["level"]
        ctl.setCurrentIndex(ctl.findData(level))
        page.chk_same.setChecked(False)
        page.start()
        controller = page.controller
        check("the batch is running", controller is not None and controller.running)

        t0 = time.monotonic()
        QTimer.singleShot(2000, win.close)
        loop = QEventLoop()
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(loop.quit)
        guard.start(60_000)
        controller.finished.connect(lambda _s: loop.quit())
        loop.exec()
        elapsed = time.monotonic() - t0
        for _ in range(20):
            app.processEvents()
        results = controller._results
        done = sum(1 for r in results if r.ok)
        skipped = sum(1 for r in results if r.skipped)
        failed = sum(1 for r in results if not r.ok and not r.skipped)
        check("closing the window stops the batch within seconds",
              elapsed < 15, f"{elapsed:.1f}s")
        check("the queue was cancelled, not left to run (most files skipped)",
              skipped >= 80 and len(results) == 120,
              f"done={done} skipped={skipped} failed={failed} of {len(results)}")
        check("cancelled files are skipped, never 'failed'", failed == 0, str(failed))
        check("Ghostscript helper processes were stopped",
              not any(p.poll() is None for p in list(util._children)))
        outs = sorted(out_dir.glob("*.pdf"))
        bad = [o.name for o in outs if o.stat().st_size == 0]
        check("no empty or half-written output is left behind",
              not bad and len(outs) == done, f"{len(outs)} files for {done} done; empty={bad}")
        for o in outs:
            try:
                import fitz
                fitz.open(str(o)).close()
            except Exception as exc:              # noqa: BLE001
                bad.append(f"{o.name}: {exc}")
        check("every output left is a readable PDF", not bad, str(bad[:3]))
    finally:
        settings.max_workers, settings.output_dir = saved

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All close-during-run checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
