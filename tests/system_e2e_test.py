"""Whole-system end-to-end audit.

Covers what unit suites don't: that every button on every page is actually
wired (no dead controls) and wired exactly once (no duplicate actions), that
links are valid, that the visible numbers are computed correctly (sizes,
counts, savings %, ETA), that records display accurately, that pages are
properly interconnected, and that bad input fails safely instead of crashing.

Run:  python tests/system_e2e_test.py
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

failures: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="mico360_sys_"))


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _pdf(path: Path, pages: int = 2) -> Path:
    import fitz
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 100), f"page {i + 1}", fontsize=12)
    d.save(str(path))
    d.close()
    return path


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QPushButton
    app = QApplication.instance() or QApplication([])

    from mico360.core.tools import TOOLS, TOOLS_BY_ID
    from mico360.core.util import human_size
    from mico360.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1180, 760)
    win.show()
    app.processEvents()

    # =====================================================================
    # 1. Every page builds, and every button is wired exactly once
    # =====================================================================
    dead: list[str] = []
    doubled: list[str] = []
    for idx in sorted(win._titles):
        win.sidebar.select(idx)
        app.processEvents()
        w = win._widgets.get(idx)
        if w is None:
            dead.append(f"page {idx}: not built")
            continue
        for b in w.findChildren(QPushButton):
            # PySide6 wants the old SIGNAL() form ("2" prefix = signal).
            # Checkable buttons (e.g. the password eye) legitimately act on
            # toggled instead of clicked, so count both.
            n = b.receivers("2clicked()") + b.receivers("2toggled(bool)")
            label = f"{win._titles[idx]}:{b.text() or b.objectName() or 'button'}"
            if n == 0:
                dead.append(label)
            elif b.receivers("2clicked()") > 1:
                # >1 receiver on clicked means the action fires twice.
                doubled.append(f"{label}({n})")
    check("every page builds and no button is dead (all have a handler)",
          not dead, ", ".join(dead[:6]))
    check("no button triggers a duplicate action (single connection)",
          not doubled, ", ".join(doubled[:6]))

    # =====================================================================
    # 2. Links: well-formed and consistent with the repo constants
    # =====================================================================
    from mico360 import legal, updater
    urls = [legal.WEBSITE_URL, updater.REPO_URL, updater.RELEASES_PAGE,
            updater.API_LATEST, updater.ATOM_FEED, updater.DOWNLOAD_BASE]
    bad = [u for u in urls if not str(u).startswith("https://") or " " in str(u)]
    check("every built-in link is a well-formed https URL", not bad, str(bad))
    check("release/API/atom links all point at the configured repo",
          all(f"{updater.GITHUB_OWNER}/{updater.GITHUB_REPO}" in u
              for u in (updater.REPO_URL, updater.RELEASES_PAGE,
                        updater.API_LATEST, updater.ATOM_FEED,
                        updater.DOWNLOAD_BASE)))
    check("support email is consistent across legal + crash reporting",
          legal.EMAIL == __import__("mico360.core.crash", fromlist=["x"]).REPORT_EMAIL,
          legal.EMAIL)

    # =====================================================================
    # 3. Calculations shown to the user
    # =====================================================================
    check("human_size formats each unit correctly",
          human_size(0).endswith("B") and human_size(1536).startswith("1.5")
          and human_size(1024 ** 2).startswith("1.0")
          and human_size(1024 ** 3).endswith("GB"),
          f"{human_size(1536)} / {human_size(1024**3)}")

    idx = win._tool_index["pdf_compress"]
    win.sidebar.select(idx)
    app.processEvents()
    page = win._widgets[idx].widget()

    a, b = _pdf(TMP / "a.pdf"), _pdf(TMP / "b.pdf", 3)
    page.add_paths([str(a), str(b)])
    app.processEvents()
    n, done, failed, pending = page._counts()
    check("queue counts start correct (2 queued, none done/failed)",
          (n, done, failed, pending) == (2, 0, 0, 2), str((n, done, failed, pending)))

    # Sizes are cached and totalled — the summary must show real bytes.
    total = sum(it.size for it in page.items)
    check("queue rows cache their real size (no '?' rows)",
          all(it.size > 0 for it in page.items) and total == a.stat().st_size + b.stat().st_size)
    check("queue summary shows the file count and total size",
          "2 files" in page.count_lbl.text() and human_size(total) in page.count_lbl.text(),
          page.count_lbl.text())

    # Duplicate must carry the size across (regression: showed "?" + skewed total).
    page._duplicate([page.items[0]])
    app.processEvents()
    check("duplicated rows keep their size (accurate records)",
          len(page.items) == 3 and all(it.size > 0 for it in page.items),
          str([it.size for it in page.items]))
    check("'?' never shown for a real file", "?" not in page._sub_text(page.items[1]))

    # Mixed states → counts stay consistent.
    page.items[0].state = "done"
    page.items[1].state = "failed"
    n, done, failed, pending = page._counts()
    check("counts track done/failed/pending after state changes",
          (n, done, failed, pending) == (3, 1, 1, 1), str((n, done, failed, pending)))
    page._remove_finished()
    check("'Remove done' clears finished rows only", len(page.items) == 1,
          str(len(page.items)))

    # Savings maths: 1000 -> 250 bytes must read as 75%.
    page._clear()
    page.add_paths([str(a)])
    big = TMP / "big.bin"; big.write_bytes(b"x" * 1000)
    small = TMP / "small.bin"; small.write_bytes(b"x" * 250)
    page.items[0].path = big
    page.items[0].state, page.items[0].outputs = "done", [small]
    saved = page._total_saved()
    check("compression savings % is computed correctly (1000→250 = 75%)",
          "75%" in saved and "750" in saved.replace(" ", ""), saved)

    check("ETA formatting is human readable",
          page._fmt_eta(45) == "45s" and page._fmt_eta(125) == "2m 05s",
          f"{page._fmt_eta(45)} / {page._fmt_eta(125)}")
    page._clear()

    # =====================================================================
    # 4. Page interconnection: Home → tool, with files carried over
    # =====================================================================
    win.sidebar.select(0)
    app.processEvents()
    win.open_tool("pdf_merge", [str(a), str(b)])
    app.processEvents()
    mi = win._tool_index["pdf_merge"]
    mpage = win._widgets[mi].widget()
    check("opening a tool from Home navigates to that page",
          win.stack.currentWidget() is win._widgets[mi])
    check("files handed over from Home land in the target tool's queue",
          len(mpage.items) == 2, str(len(mpage.items)))
    mpage._clear()

    # Drop routing reaches a tool that accepts the file type.
    from mico360.ui.dashboard_page import route_for
    for ext, expect_accepts in ((".pdf", True), (".heic", True), (".svg", True),
                                (".docx", True)):
        tid = route_for([f"x{ext}"])
        tool = TOOLS_BY_ID.get(tid)
        ok = tool is not None and (ext in tool.accept or "*" in tool.accept)
        check(f"dropping {ext} on Home reaches a tool that accepts it", ok,
              f"{ext} -> {tid}")

    # =====================================================================
    # 5. Validation / permissions: bad input fails safely with a clear message
    # =====================================================================
    from mico360.core import processors
    from mico360.core.processors import ProcessError

    broken = TMP / "broken.pdf"
    broken.write_bytes(b"not a pdf at all")
    try:
        processors.pdf_compress(broken, TMP / "o", {}, lambda *a, **k: None)
        check("a corrupt PDF raises a clear error (no crash)", False, "no error")
    except ProcessError as exc:
        check("a corrupt PDF raises a clear error (no crash)",
              "couldn't" in str(exc).lower() or "corrupt" in str(exc).lower(),
              str(exc)[:70])
    except Exception as exc:  # noqa: BLE001
        check("a corrupt PDF raises a clear error (no crash)", False,
              f"{type(exc).__name__}: {exc}")

    # A password-protected PDF must be reported clearly, not silently mangled.
    enc = TMP / "locked.pdf"
    import fitz
    d = fitz.open(str(a))
    d.save(str(enc), encryption=fitz.PDF_ENCRYPT_AES_256,
           owner_pw="owner", user_pw="secret")
    d.close()
    try:
        processors.pdf_compress(enc, TMP / "o", {}, lambda *a, **k: None)
        check("a password-protected PDF is reported, not silently processed",
              False, "no error raised")
    except ProcessError as exc:
        check("a password-protected PDF is reported, not silently processed",
              "password" in str(exc).lower() or "protected" in str(exc).lower(),
              str(exc)[:70])

    # Empty queue must refuse to run rather than starting an empty batch.
    from PySide6.QtWidgets import QMessageBox
    _orig = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    try:
        page._clear()
        page.start()
        check("Start on an empty queue does nothing (no phantom run)",
              page.controller is None)
    finally:
        QMessageBox.information = _orig

    win.close()
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} system check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All system end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    # Skip Qt's crash-prone offscreen teardown at interpreter shutdown
    # (a lingering C++ object can abort finalization with 0xC0000409,
    #  masking an otherwise-clean pass). Flush and exit with the result.
    import os as _os, sys as _sys
    _sys.stdout.flush(); _sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
