"""Scale & control robustness: many files, a very large file, cancel and retry.

The app must stay responsive and correct when a batch is big, when one file is
huge, when the user cancels mid-run, and when failed rows are retried.

Run:  python tests/stress_batch_test.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

from PySide6.QtCore import QEventLoop, QTimer                      # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox            # noqa: E402

from mico360.config import settings                                # noqa: E402
from mico360.core.tools import TOOLS_BY_ID                         # noqa: E402
from mico360.ui.tool_page import ToolPage                          # noqa: E402

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def make_pdf(p, pages=2, heavy=False):
    """A text PDF, or (heavy=True) a genuinely large one: each page carries a
    full-page photographic image, which is what makes real scans big."""
    import fitz
    d = fitz.open()
    for i in range(pages):
        pg = d.new_page(width=595, height=842)
        if heavy:
            # A DIFFERENT photographic image per page — one shared image would be
            # stored once and the file would not actually be large.
            import numpy as np
            from PIL import Image
            arr = np.random.randint(0, 255, (1400, 1000, 3), dtype=np.uint8)
            buf = io.BytesIO()
            Image.fromarray(arr).save(buf, format="JPEG", quality=92)
            pg.insert_image(pg.rect, stream=buf.getvalue())
        pg.insert_text((60, 90), f"Page {i+1} " + ("x" * 60), fontsize=11)
    d.save(str(p), deflate=True)
    d.close()
    return p


def run(page, out, timeout_ms=180000, cancel_after_ms=0):
    page.chk_same.setChecked(False)
    page.chk_overwrite.setChecked(True)
    page.out_edit.setText(str(out))
    res = {}
    loop = QEventLoop()
    page.start()
    if page.controller is None:
        return {"_nostart": True}
    page.controller.finished.connect(lambda s: (res.update(s), loop.quit()))
    if cancel_after_ms:
        c = QTimer(); c.setSingleShot(True)
        c.timeout.connect(page._cancel)
        c.start(cancel_after_ms)
    g = QTimer(); g.setSingleShot(True); g.timeout.connect(loop.quit)
    g.start(timeout_ms)
    loop.exec()
    res["_timeout"] = not g.isActive()
    g.stop()
    return res


def main() -> int:
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    saved = settings.output_dir

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        out = tmp / "out"
        out.mkdir()
        settings.output_dir = str(out)

        # ---------- many files -------------------------------------------
        N = 200
        many = tmp / "many"
        many.mkdir()
        for i in range(N):
            make_pdf(many / f"doc{i:03d}.pdf", pages=1)

        page = ToolPage(TOOLS_BY_ID["pdf_metadata"])
        t0 = time.monotonic()
        page.add_paths([str(many)])
        import_s = time.monotonic() - t0
        check(f"importing {N} files is fast (no UI freeze)",
              len(page.items) == N and import_s < 15,
              f"{len(page.items)} files in {import_s:.1f}s")

        page.options_widget._controls["title"].setText("Batch")
        s = run(page, out)
        check(f"batch of {N} files completes",
              not s.get("_timeout") and s.get("ok", 0) == N
              and s.get("failed", 0) == 0,
              f"ok={s.get('ok')} failed={s.get('failed')} timeout={s.get('_timeout')}")
        check("queue counts match the result after a big batch",
              sum(1 for it in page.items if it.state == "done") == N)

        # ---------- one very large file -----------------------------------
        big = make_pdf(tmp / "big.pdf", pages=25, heavy=True)
        mb = big.stat().st_size / 1048576
        page = ToolPage(TOOLS_BY_ID["pdf_compress"])
        page.add_paths([str(big)])
        s = run(page, out, timeout_ms=300000)
        check(f"a very large PDF ({mb:.1f} MB, 25 image pages) processes without hanging",
              not s.get("_timeout") and s.get("ok", 0) == 1,
              f"ok={s.get('ok')} failed={s.get('failed')}")

        # ---------- cancel mid-run ----------------------------------------
        page = ToolPage(TOOLS_BY_ID["pdf_compress"])
        page.add_paths([str(p) for p in sorted(many.glob("*.pdf"))])
        s = run(page, out, cancel_after_ms=250)
        check("cancelling mid-run ends the batch cleanly",
              not s.get("_timeout"), f"timeout={s.get('_timeout')}")
        check("cancel is reported and nothing is left running",
              s.get("cancelled") or s.get("skipped", 0) > 0,
              f"cancelled={s.get('cancelled')} skipped={s.get('skipped')}")
        check("the UI returns to an idle state after cancel",
              page.controller is None and page.btn_start.isEnabled())

        # ---------- retry after failure -----------------------------------
        page = ToolPage(TOOLS_BY_ID["pdf_compress"])
        okp = make_pdf(tmp / "ok.pdf")
        badp = tmp / "bad.pdf"
        badp.write_bytes(os.urandom(2048))
        page.add_paths([str(okp), str(badp)])
        s = run(page, out)
        check("mixed batch: one ok, one failed",
              s.get("ok") == 1 and s.get("failed") == 1,
              f"ok={s.get('ok')} failed={s.get('failed')}")
        failed_items = [it for it in page.items if it.state == "failed"]
        check("failed row carries the reason", failed_items
              and bool(failed_items[0].msg), str(failed_items[:1]))

        page._retry(failed_items)
        check("retry resets failed rows to pending",
              all(it.state == "pending" for it in failed_items))
        s2 = run(page, out)
        check("retrying a still-bad file fails cleanly again (no crash)",
              not s2.get("_timeout") and s2.get("failed", 0) == 1,
              f"failed={s2.get('failed')}")
        check("already-done rows are skipped on the retry run",
              s2.get("total", 0) == 1, f"total={s2.get('total')}")

    settings.output_dir = saved
    print()
    if failures:
        print(f"{len(failures)} stress check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All stress/scale checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
