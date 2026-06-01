"""Stress / concurrency test: a large batch and a big multi-page PDF through the
real engine, asserting completion, correct outputs, and no leaked processes.

Run:  python tests/stress_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from mico360.config import settings
from mico360.core.tools import TOOLS_BY_ID
from mico360.logging_setup import setup_logging
from mico360.theme import stylesheet
from mico360.ui.tool_page import ToolPage

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _img(p, size=(1600, 1200)):
    from PIL import Image
    im = Image.new("RGB", size)
    px = im.load()
    for y in range(0, size[1], 4):
        for x in range(0, size[0], 4):
            px[x, y] = ((x * 255) // size[0], (y * 255) // size[1], 90)
    im.save(p, quality=92)
    return p


def _bigpdf(p, pages=60):
    import fitz
    d = fitz.open()
    for i in range(pages):
        pg = d.new_page(width=595, height=842)
        pg.insert_text((72, 72), f"Stress page {i + 1} of {pages}", fontsize=14)
    d.save(str(p)); d.close()
    return p


def run(page, out, timeout_ms=120000):
    page.chk_same.setChecked(False)
    page.chk_overwrite.setChecked(True)
    page.out_edit.setText(str(out))
    res = {}
    loop = QEventLoop()
    page.start()
    if page.controller is None:
        return res
    page.controller.finished.connect(lambda s: (res.update(s), loop.quit()))
    g = QTimer(); g.setSingleShot(True); g.timeout.connect(loop.quit); g.start(timeout_ms)
    loop.exec()
    return res


def main() -> int:
    setup_logging()
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(stylesheet(settings.theme))
    saved_out = settings.output_dir
    saved_workers = settings.max_workers
    settings.max_workers = 0   # auto (all cores) — exercise concurrency

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()
        settings.output_dir = str(out)

        # --- large concurrent batch: 20 images compressed in parallel ----
        imgs = [str(_img(tmp / f"p{i}.jpg")) for i in range(20)]
        page = ToolPage(TOOLS_BY_ID["image_compress"])
        page.add_paths(imgs)
        t0 = time.monotonic()
        s = run(page, out)
        dt = time.monotonic() - t0
        check("batch of 20 all succeeded",
              s.get("ok") == 20 and s.get("failed") == 0,
              f"ok={s.get('ok')} failed={s.get('failed')}")
        check("batch produced 20 outputs", len(s.get("outputs") or []) == 20,
              str(len(s.get("outputs") or [])))
        outs = s.get("outputs") or []
        check("all 20 outputs exist and are non-empty",
              all(Path(o).exists() and Path(o).stat().st_size > 0 for o in outs))
        print(f"      (20-image batch took {dt:.1f}s on {os.cpu_count()} cores)")

        # --- big PDF: 60 pages, split every page -> 60 outputs -----------
        big = _bigpdf(tmp / "big.pdf", 60)
        sp = ToolPage(TOOLS_BY_ID["pdf_split"])
        sp.add_paths([str(big)])
        sp.options_widget._controls["mode"].setCurrentIndex(
            sp.options_widget._controls["mode"].findData("each"))
        s = run(sp, out)
        check("60-page split: 1 unit ok", s.get("ok") == 1 and s.get("failed") == 0,
              f"ok={s.get('ok')}")
        check("60-page split: 60 page files", len(s.get("outputs") or []) == 60,
              str(len(s.get("outputs") or [])))

        # --- repeated runs don't leak the controller --------------------
        cp = ToolPage(TOOLS_BY_ID["pdf_page_numbers"])
        cp.add_paths([str(_bigpdf(tmp / "n.pdf", 5))])
        for _ in range(5):
            cp._redo()
            run(cp, out)
        check("repeated runs settle (controller released)", cp.controller is None)
        check("repeated runs: start button re-enabled", cp.btn_start.isEnabled())

    # --- no leaked helper processes from a headless batch ---------------
    import subprocess
    try:
        tl = subprocess.run(["tasklist", "/FI", "IMAGENAME eq explorer.exe"],
                            capture_output=True, text=True, timeout=15).stdout
        # We only assert our own run didn't spawn a runaway count; explorer is
        # the shell, so a small number is normal. The headless guard means tools
        # never open Explorer in tests.
        n = tl.lower().count("explorer.exe")
        check("no explorer storm from headless batch (<=3)", n <= 3, f"{n} explorer")
    except Exception as exc:
        print(f"[INFO] explorer check skipped: {exc}")

    settings.output_dir = saved_out
    settings.max_workers = saved_workers
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All stress checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
