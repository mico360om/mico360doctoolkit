"""Low-resource resilience: RAM-aware worker scaling, the free-disk-space guard
(unit + through the real batch engine), and the page organizer's progressive,
memory-bounded thumbnail rendering.

Run:  python tests/low_resource_test.py
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


def _make_pdf(path: Path, pages: int) -> None:
    import fitz
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 100), f"PAGE {i + 1}")
    d.save(str(path))
    d.close()


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEventLoop, QTimer
    app = QApplication.instance() or QApplication([])

    from mico360.core import util
    from mico360.core.util import (ProcessError, auto_worker_count,
                                   available_memory_bytes, free_disk_bytes,
                                   require_free_space)
    td = Path(tempfile.mkdtemp(prefix="mico_lowres_"))

    # ================= worker scaling =================
    print("--- worker scaling ---")
    check("always at least 1 worker", auto_worker_count(cpu=1, avail_mem_bytes=None) >= 1)
    check("low RAM (1 GB) caps to 1 worker",
          auto_worker_count(cpu=8, avail_mem_bytes=1_000_000_000) == 1,
          str(auto_worker_count(cpu=8, avail_mem_bytes=1_000_000_000)))
    check("2 GB free → 1 worker",
          auto_worker_count(cpu=8, avail_mem_bytes=2_000_000_000) == 1)
    check("ample RAM uses cores-1",
          auto_worker_count(cpu=5, avail_mem_bytes=64_000_000_000) == 4,
          str(auto_worker_count(cpu=5, avail_mem_bytes=64_000_000_000)))
    check("hard cap on many-core boxes",
          auto_worker_count(cpu=64, avail_mem_bytes=256_000_000_000) == 8)
    check("no RAM reading → CPU-based only",
          auto_worker_count(cpu=4, avail_mem_bytes=None) == 3)
    live = available_memory_bytes()
    check("available_memory_bytes: positive or None", live is None or live > 0, str(live))
    check("live auto_worker_count is sane (1..64)", 1 <= auto_worker_count() <= 64,
          str(auto_worker_count()))
    # macOS has no cheap "available" reading → the auto path must fall back to
    # total RAM so scaling still engages there (this is the Mac-readiness fix).
    from mico360.core.util import total_memory_bytes
    check("total_memory_bytes: positive or None",
          total_memory_bytes() is None or total_memory_bytes() > 0, str(total_memory_bytes()))
    _av, _tot = util.available_memory_bytes, util.total_memory_bytes
    util.available_memory_bytes = lambda: None          # simulate macOS
    util.total_memory_bytes = lambda: 2_000_000_000     # 2 GB total (small Mac)
    try:
        check("macOS-style (no avail; 2 GB total) still caps workers to 1",
              auto_worker_count(cpu=8) == 1, str(auto_worker_count(cpu=8)))
    finally:
        util.available_memory_bytes, util.total_memory_bytes = _av, _tot

    # ================= disk-space guard (unit) =================
    print("--- disk guard (unit) ---")
    check("free_disk_bytes is positive for a real dir", (free_disk_bytes(td) or 0) > 0)
    check("free_disk_bytes tolerates a non-existent path",
          free_disk_bytes(td / "no" / "such" / "dir") is not None)
    try:
        require_free_space(td, 10 ** 18, "the output")   # ~1 EB — never available
        check("impossible need raises ProcessError", False)
    except ProcessError as e:
        check("impossible need raises ProcessError", "disk space" in str(e).lower())
    try:
        require_free_space(td, 1)                         # trivially fits
        check("a tiny need does not raise", True)
    except ProcessError:
        check("a tiny need does not raise", False)
    _orig = util.free_disk_bytes
    util.free_disk_bytes = lambda _p: None               # unknown → must not block
    try:
        require_free_space(td, 10 ** 18)
        check("unknown free space never blocks work", True)
    except ProcessError:
        check("unknown free space never blocks work", False)
    finally:
        util.free_disk_bytes = _orig

    # ================= disk-space guard (through the engine) =================
    print("--- disk guard (engine e2e) ---")
    from mico360.core.engine import BatchController
    from mico360.core.tools import TOOLS_BY_ID
    src = td / "d.pdf"
    _make_pdf(src, 3)
    opts = {"operation": "rotate", "angle": 90, "pages": "all", "overwrite": True}

    def run_once(out):
        res = {}
        c = BatchController(max_workers=1)
        loop = QEventLoop()
        c.finished.connect(lambda s: (res.update(s), loop.quit()))
        QTimer.singleShot(30000, loop.quit)
        c.start(TOOLS_BY_ID["pdf_organize"], [src], out, opts)
        loop.exec()
        return res

    util.free_disk_bytes = lambda _p: 1000               # pretend the disk is full
    try:
        s = run_once(td / "full")
    finally:
        util.free_disk_bytes = _orig
    check("full disk → the unit fails (not a crash)", s.get("failed") == 1, str(s))
    errs = " ".join(m for _, m in s.get("errors", []))
    check("full-disk error message mentions disk space", "disk space" in errs.lower(), errs[:80])
    check("full disk → nothing written",
          not list((td / "full").glob("*.pdf")) if (td / "full").exists() else True)

    s = run_once(td / "ok")
    check("with space, the same job succeeds", s.get("ok") == 1 and s.get("failed") == 0,
          str(s))

    # ================= page organizer: progressive + bounded =================
    print("--- organizer: progressive/bounded render ---")
    import mico360.ui.page_organizer as po
    big = td / "big.pdf"
    _make_pdf(big, 60)
    import time
    t0 = time.monotonic()
    dlg = po.PageOrganizerDialog(big)
    dt = time.monotonic() - t0
    check("60-page dialog opens instantly (no eager render)", dt < 1.5, f"{dt:.2f}s")
    check("all pages are present as tiles immediately", dlg.grid.count() == 60)
    check("nothing rendered yet right after construct (progressive)",
          dlg._thumbs == {}, str(len(dlg._thumbs)))
    dlg.render_all_now()
    check("progressive render fills every thumbnail", len(dlg._thumbs) == 60)
    dlg._close_doc()

    # memory cap: pages past MAX_THUMBS stay placeholders but remain editable
    saved_cap = po.MAX_THUMBS
    po.MAX_THUMBS = 2
    try:
        dlg2 = po.PageOrganizerDialog(big)
        check("render queue is capped at MAX_THUMBS", len(dlg2._render_queue) == 2,
              str(len(dlg2._render_queue)))
        dlg2.render_all_now()
        check("only capped pages are rendered (memory bound)",
              set(dlg2._thumbs.keys()) == {0, 1}, str(sorted(dlg2._thumbs)))
        # a page beyond the cap (placeholder) is still fully editable
        dlg2.grid.item(40).setSelected(True)
        dlg2._rotate_cw()
        pg = dlg2.plan()["groups"][0]
        check("an un-rendered (placeholder) page still rotates in the plan",
              pg[40]["src"] == 40 and pg[40]["rotate"] == 90, str(pg[40]))
        check("plan still covers every page despite the render cap",
              len(pg) == 60)
        dlg2._close_doc()
    finally:
        po.MAX_THUMBS = saved_cap

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Low-resource: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc if isinstance(_rc, int) else 0)
