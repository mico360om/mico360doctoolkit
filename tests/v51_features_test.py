"""v5.1 feature tests: improved OCR (engine caching, confidence filtering,
visual-row reconstruction) and the expanded Help (OCR / Updates / shortcuts).

Run:  python tests/v51_features_test.py   (offscreen; no GUI shown)
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
rep = lambda m: None  # noqa: E731


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _scanned_pdf(path: Path) -> Path:
    """A PDF whose page is an image of text (no text layer) — like a scan."""
    import fitz
    src = fitz.open()
    pg = src.new_page(width=612, height=320)
    pg.insert_text((60, 90), "Strategic Leadership Course", fontsize=26)
    pg.insert_text((60, 150), "Module One Overview", fontsize=20)
    pix = pg.get_pixmap(dpi=150)
    src.close()
    img = path.with_suffix(".png")
    pix.save(str(img))
    flat = fitz.open()
    fp = flat.new_page(width=612, height=320)
    fp.insert_image(fp.rect, filename=str(img))
    flat.save(str(path))
    flat.close()
    return path


class _FakeEngine:
    """Stand-in OCR engine: returns canned (box, text, score) detections so we
    can test filtering/scaling without loading the real ONNX models."""
    def __call__(self, img):
        result = [
            ([[300, 150], [500, 150], [500, 180], [300, 180]], "Keep", 0.95),
            ([[300, 220], [500, 220], [500, 250], [300, 250]], "Drop", 0.20),
            ([[300, 290], [500, 290], [500, 320], [300, 320]], "   ", 0.99),
        ]
        return result, None


def main() -> int:
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication([])

    from mico360 import __version__
    from mico360.core import processors as P

    # --- version --------------------------------------------------------
    check("version is 5.1.x", __version__.startswith("5.1."), __version__)

    # --- _ocr_rows groups fragments into visual rows --------------------
    lines = [
        ("World", (100, 50, 140, 62)),
        ("Hello", (50, 50, 90, 62)),      # same row as "World", to its left
        ("Second", (50, 90, 110, 102)),   # next row down
    ]
    rows = P._ocr_rows(lines)
    check("_ocr_rows merges same-line fragments L→R",
          len(rows) == 2 and rows[0][0] == "Hello World",
          str([r[0] for r in rows]))
    check("_ocr_rows orders rows top→bottom", rows[1][0] == "Second")
    check("_ocr_rows handles empty input", P._ocr_rows([]) == [])

    # --- confidence filtering + DPI clamp via a fake engine -------------
    import fitz
    pg = fitz.open(); pg.new_page(width=612, height=320)
    got = P._ocr_page_lines(_FakeEngine(), pg[0], dpi=10_000)  # dpi clamped
    pg.close()
    texts = [t for t, _ in got]
    check("OCR drops low-confidence detections", "Drop" not in texts, str(texts))
    check("OCR keeps high-confidence text", "Keep" in texts, str(texts))
    check("OCR skips blank detections", len(got) == 1, str(texts))

    # --- engine is cached (built once, reused) --------------------------
    try:
        e1 = P._make_ocr_engine()
        e2 = P._make_ocr_engine()
        check("OCR engine is cached/reused", e1 is e2)
        ocr_available = True
    except P.ProcessError as exc:
        print(f"[INFO] OCR engine unavailable, skipping live OCR checks: {exc}")
        ocr_available = False

    # --- full scanned OCR → docx with clean rows ------------------------
    if ocr_available:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"; out.mkdir()
            scanned = _scanned_pdf(Path(td) / "scan.pdf")
            rw = P.pdf_to_word(scanned, out, {"ocr": True, "overwrite": True}, rep)
            import docx
            doc = docx.Document(str(rw[0]))
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            body = " ".join(paras)
            check("OCR docx recovered the heading text",
                  "Strategic" in body, repr(body[:60]))
            check("OCR docx keeps a line's words in one paragraph",
                  any("Strategic" in p and "Leadership" in p for p in paras),
                  str(paras[:3]))

    # --- Help page expanded ---------------------------------------------
    from mico360.ui.help_page import _HELP_HTML
    for needle in ("OCR", "Staying up to date", "Settings → Updates",
                   "Keyboard", "SHA-256"):
        check(f"Help mentions '{needle}'", needle in _HELP_HTML)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All v5.1 feature checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
