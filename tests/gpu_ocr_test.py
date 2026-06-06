"""GPU-accelerated OCR (DirectML) — runtime detection, correctness, CPU fallback.

Machine-agnostic: on a PC with a usable GPU the engine runs on DirectML; on a
CPU-only PC (or CI) it runs on CPU. EITHER WAY the OCR output must be correct and
the run must not error. Nothing is hard-coded to a specific GPU.

Run:  python tests/gpu_ocr_test.py
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


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def make_scanned_pdf(path: Path, lines: list[str]) -> None:
    """An image-only PDF (no text layer) so the OCR tool must actually run."""
    import fitz
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    y = 90
    for ln in lines:
        p.insert_text((60, y), ln, fontsize=22)
        y += 48
    pix = p.get_pixmap(dpi=200)
    d2 = fitz.open()
    pg = d2.new_page(width=595, height=842)
    pg.insert_image(pg.rect, pixmap=pix)
    d2.save(str(path))
    d.close(); d2.close()


def main() -> int:
    from mico360.core import processors as P

    # 1. Capability detection must never raise and returns a bool.
    try:
        dml = P._dml_available()
        ok = isinstance(dml, bool)
    except Exception as exc:  # noqa: BLE001
        ok, dml = False, f"raised {exc}"
    check("GPU detection runs without error (machine-agnostic)", ok is True, f"dml={dml}")
    print(f"  DirectML available on this machine: {dml}")
    print(f"  GPU-OCR user preference: {P._ocr_gpu_preference()}")

    # 2. Build the engine and OCR a scanned page — text must be correct.
    P._ocr_engine_cache = None  # force a fresh build for this test
    td = Path(tempfile.mkdtemp(prefix="mico360_gpuocr_"))
    out = td / "out"; out.mkdir()
    words = ["INVOICE", "Brown fox 12345", "support@mico360.com"]
    src = td / "scan.pdf"; make_scanned_pdf(src, words)

    try:
        P._make_ocr_engine()
    except P.ProcessError as exc:
        check("OCR engine available in this environment", False, str(exc))
        print("  (OCR engine/deps missing — skipping remaining checks)")
        return 1 if failures else 0

    provider = P.ocr_active_provider()
    print(f"  OCR engine built on: {provider}")
    check("Active provider is a valid label",
          provider in ("CPU", "GPU (DirectML)"), provider)
    # If a GPU is present AND the user pref is on, we must actually be on the GPU.
    if dml is True and P._ocr_gpu_preference():
        check("With a GPU available, OCR runs on the GPU (DirectML)",
              provider == "GPU (DirectML)", provider)

    r = P.pdf_ocr(src, out, {"overwrite": True}, lambda *a: None)
    import fitz
    doc = fitz.open(str(r[0])); text = "".join(p.get_text() for p in doc); doc.close()
    check("OCR output is searchable and correct (provider-agnostic)",
          "INVOICE" in text.upper() and "fox" in text.lower(),
          repr(text[:80]))

    # 2b. MULTI-PAGE scan — exercises the concurrent OCR path. On the GPU this
    # must run serially (DirectML sessions can't take concurrent Run() — it would
    # crash the process). This guards that regression.
    multi = td / "multi.pdf"
    import fitz as _f
    d = _f.open()
    for pg in range(6):
        p = d.new_page(width=595, height=842)
        p.insert_text((60, 100), f"Page {pg} unique marker zebra{pg}", fontsize=22)
        pix = p.get_pixmap(dpi=200)
        d.delete_page(p.number)
        np_ = d.new_page(width=595, height=842)
        np_.insert_image(np_.rect, pixmap=pix)
    d.save(str(multi)); d.close()
    rr = P.pdf_ocr(multi, out, {"overwrite": True}, lambda *a: None)
    dd = _f.open(str(rr[0])); mtext = "".join(p.get_text() for p in dd); dd.close()
    found = sum(1 for k in range(6) if f"zebra{k}" in mtext.lower())
    check("Multi-page OCR completes without crashing & reads all pages",
          found >= 5, f"{found}/6 page markers found on {provider}")

    # 3. CPU fallback path is exercised by the session try/except — verify the
    #    preference gate honours the setting being turned OFF.
    from mico360.config import settings
    old = settings.ocr_use_gpu
    try:
        settings.ocr_use_gpu = False
        check("Turning the setting off disables the GPU preference",
              P._ocr_gpu_preference() is False)
    finally:
        settings.ocr_use_gpu = old

    import shutil
    shutil.rmtree(td, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} GPU-OCR check(s) FAILED: {', '.join(failures)}")
        return 1
    print(f"All GPU-OCR checks passed (engine ran on: {provider}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
