"""End-to-end UI test: drive a real ToolPage through a full processing run.

Builds the actual Compress Image page, adds a generated image, clicks Start, and
waits for the batch (multi-threaded via QThreadPool) to finish — verifying the
UI -> engine -> processor -> output wiring, the progress/status updates and the
header status chip. Runs offscreen; no window is shown.

Run:  python tests/functional_ui_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from mico360.config import settings
from mico360.core.tools import TOOLS_BY_ID
from mico360.logging_setup import setup_logging
from mico360.theme import stylesheet
from mico360.ui.tool_page import ToolPage

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _sample_image(path: Path) -> Path:
    from PIL import Image
    img = Image.new("RGB", (1400, 1000))
    px = img.load()
    for y in range(1000):
        for x in range(1400):
            px[x, y] = (x * 255 // 1400, y * 255 // 1000, 128)
    img.save(path, quality=95)
    return path


def run_to_completion(page: ToolPage, timeout_ms: int = 30000) -> dict:
    """Click Start and block (spinning the event loop) until finished."""
    result: dict = {}
    loop = QEventLoop()

    def on_finished(summary: dict) -> None:
        result.update(summary)
        loop.quit()

    # The controller is created inside start(); connect after it exists.
    page.start()
    assert page.controller is not None, "controller was not created"
    page.controller.finished.connect(on_finished)

    guard = QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(loop.quit)
    guard.start(timeout_ms)
    loop.exec()
    return result


def main() -> int:
    setup_logging()
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(stylesheet(settings.theme))

    saved_output_dir = settings.output_dir   # restore so tests don't pollute QSettings
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        out = tmp / "out"
        out.mkdir()
        settings.output_dir = str(out)

        img = _sample_image(tmp / "photo.jpg")

        page = ToolPage(TOOLS_BY_ID["image_compress"])
        page.chk_same.setChecked(False)
        page.out_edit.setText(str(out))

        # Pick the "High" preset via the real combo so we exercise the widget.
        level_cb = page.options_widget._controls["level"]
        level_cb.setCurrentIndex(level_cb.findData("high"))

        # Add a file the way a drop would.
        page.add_paths([str(img)])
        check("file added to list", len(page.files) == 1, f"{len(page.files)} files")

        summary = run_to_completion(page)
        check("run finished", bool(summary), "no finished signal")
        check("one file ok", summary.get("ok") == 1 and summary.get("failed") == 0,
              f"ok={summary.get('ok')} failed={summary.get('failed')}")

        outputs = summary.get("outputs") or []
        produced_ok = bool(outputs) and Path(outputs[0]).exists() and Path(outputs[0]).stat().st_size > 0
        check("output file produced", produced_ok, str(outputs[:1]))

        check("progress bar completed",
              page.progress.value() == page.progress.maximum() and page.progress.maximum() > 0,
              f"{page.progress.value()}/{page.progress.maximum()}")
        check("status chip shows done",
              page.header_chip.property("chipState") == "ok",
              str(page.header_chip.property("chipState")))
        check("start re-enabled after run", page.btn_start.isEnabled())

        # --- aggregate-mode flow (Image -> PDF, combined) -------------
        i1 = _sample_image(tmp / "one.jpg")
        i2 = _sample_image(tmp / "two.jpg")
        agg = ToolPage(TOOLS_BY_ID["image_to_pdf"])
        agg.chk_same.setChecked(False)
        agg.out_edit.setText(str(out))
        agg.add_paths([str(i1), str(i2)])
        check("aggregate: 2 files added", len(agg.files) == 2, f"{len(agg.files)}")
        agg_summary = run_to_completion(agg)
        # AGGREGATE mode = one work unit producing one combined PDF.
        check("aggregate: single combined output",
              agg_summary.get("ok") == 1 and len(agg_summary.get("outputs", [])) == 1,
              f"ok={agg_summary.get('ok')} outs={len(agg_summary.get('outputs', []))}")
        combined = (agg_summary.get("outputs") or [None])[0]
        check("aggregate: combined PDF exists",
              combined and Path(combined).suffix == ".pdf" and Path(combined).exists(),
              str(combined))

        # --- "save next to source" -> numbered output, original kept ----
        src_dir = tmp / "beside"
        src_dir.mkdir()
        beside = _sample_image(src_dir / "photo.jpg")
        original_bytes = beside.read_bytes()
        sp = ToolPage(TOOLS_BY_ID["image_compress"])
        sp.chk_same.setChecked(True)          # save next to source
        sp.add_paths([str(beside)])
        sp_summary = run_to_completion(sp)
        produced = (sp_summary.get("outputs") or [None])[0]
        check("save-next-to-source: numbered name in source folder",
              produced and Path(produced).name == "photo (1).jpg"
              and Path(produced).parent == src_dir, str(produced))
        check("save-next-to-source: original untouched",
              beside.exists() and beside.read_bytes() == original_bytes)

    settings.output_dir = saved_output_dir
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All functional UI checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
