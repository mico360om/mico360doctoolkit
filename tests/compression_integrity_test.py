"""Content-integrity guarantees.

* Lossless compression (PDF + image) must change ZERO content and be verified
  identical; a tampered file must be detected.
* Lossy compression must still preserve text / links / bookmarks / attachments.
* The other tools must not silently lose content (merge/split keep every page's
  text & images; watermark/page-numbers/sign/metadata/protect keep the original
  text & images; organize reorder keeps the same page set).

Run:  python tests/compression_integrity_test.py
"""
from __future__ import annotations

import io
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
REP = lambda *_: None  # noqa: E731


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def rich_pdf(path, pages=3):
    import fitz
    from PIL import Image
    d = fitz.open()
    for i in range(pages):
        p = d.new_page(width=420, height=560)
        p.insert_text((40, 80), f"Confidential page {i + 1}. fox 12345 unique{i}.",
                      fontsize=12)
        buf = io.BytesIO()
        Image.new("RGB", (500, 400), (i * 60 % 255, 90, 160)).save(buf, "PNG")
        p.insert_image(__import__("fitz").Rect(40, 120, 360, 420), stream=buf.getvalue())
        p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(40, 440, 200, 460),
                       "uri": "https://mico360.com"})
    d.set_metadata({"title": "Secret", "author": "QA", "subject": "S",
                    "keywords": "k", "creator": "C", "producer": "Pr"})
    d.set_toc([[1, "Chapter 1", 1]])
    d.save(str(path)); d.close()
    return path


def page_text(path, i):
    import fitz
    d = fitz.open(str(path)); t = d[i].get_text("text"); d.close(); return t


def all_text(path):
    import fitz
    d = fitz.open(str(path)); t = "".join(p.get_text() for p in d); d.close(); return t


def image_count(path):
    import fitz
    d = fitz.open(str(path)); n = sum(len(p.get_images()) for p in d); d.close(); return n


def main() -> int:
    from mico360.core import processors as P
    td = Path(tempfile.mkdtemp(prefix="mico360_integ_"))
    out = td / "o"; out.mkdir()

    def o(d=None):
        x = {"overwrite": True}; x.update(d or {}); return x

    src = rich_pdf(td / "src.pdf")

    # 1. Lossless compression — strictly identical
    r = P.pdf_compress(src, out, o({"level": "lossless"}), REP)
    ok, diffs = P.verify_pdf_integrity(src, r[0], mode="strict")
    check("LOSSLESS compress: content 100% identical (text/images/fonts/links/meta/render)",
          ok, "; ".join(diffs[:3]))
    check("LOSSLESS compress: not larger than original",
          r[0].stat().st_size <= src.stat().st_size,
          f"{src.stat().st_size} -> {r[0].stat().st_size}")

    # 1b. Progress is reported and strictly ascending (so the bar never "sticks"
    #     on a large file mid‑compression).
    class _ProgRep:
        def __init__(self):
            self.ticks = []

        def __call__(self, *a):
            pass

        def progress(self, c, t):
            self.ticks.append(c / t if t else 0)

        cancelled = staticmethod(lambda: False)

    pr = _ProgRep()
    P.pdf_compress(src, out, o({"level": "lossless"}), pr)
    check("LOSSLESS compress reports ascending progress (bar moves)",
          len(pr.ticks) >= 3 and pr.ticks == sorted(pr.ticks) and pr.ticks[-1] >= 0.99,
          f"{len(pr.ticks)} ticks {pr.ticks[:1]}..{pr.ticks[-1:]}")

    # 2. Lossy compression — text/links/bookmarks/attachments still preserved
    r = P.pdf_compress(src, out, o({"level": "high"}), REP)
    ok, diffs = P.verify_pdf_integrity(src, r[0], mode="structural")
    check("LOSSY compress: text / links / bookmarks / attachments preserved",
          ok, "; ".join(diffs[:3]))

    # 3. Integrity check actually catches changes (no false negatives)
    import fitz
    d = fitz.open(str(src)); d[0].insert_text((40, 240), "INJECTED", fontsize=9)
    tam = td / "tampered.pdf"; d.save(str(tam)); d.close()
    ok, _ = P.verify_pdf_integrity(src, tam, mode="structural")
    check("integrity check DETECTS injected text (no false 'identical')", not ok)
    d = fitz.open(str(src)); d.delete_page(0); short = td / "short.pdf"; d.save(str(short)); d.close()
    ok, _ = P.verify_pdf_integrity(src, short, mode="strict")
    check("integrity check DETECTS a removed page", not ok)

    # 4. Lossless image — pixels identical
    from PIL import Image
    png = td / "pic.png"; Image.new("RGB", (800, 600), (150, 40, 40)).save(png)
    r = P.image_compress(png, out, o({"level": "lossless"}), REP)
    check("LOSSLESS image: pixels identical", P.verify_image_identical(png, r[0]),
          f"{png.stat().st_size} -> {r[0].stat().st_size}")

    # ---- other tools must not lose content ----
    # Merge keeps every page's text + all images
    a, b = rich_pdf(td / "a.pdf", 2), rich_pdf(td / "b.pdf", 2)
    r = P.pdf_merge([a, b], out, o({"output_name": "m"}), REP)
    check("Merge: keeps all pages' text", all_text(a) + all_text(b) == all_text(r[0]) or
          (all_text(a) in all_text(r[0]) and all_text(b) in all_text(r[0])))
    check("Merge: keeps all images", image_count(r[0]) == image_count(a) + image_count(b))

    # Split: each output page text == source page text
    r = P.pdf_split(src, out, o({"mode": "each"}), REP)
    check("Split: each page preserves its exact text",
          all(page_text(r[i], 0) == page_text(src, i) for i in range(len(r))))

    # Watermark keeps the original text + images (adds, never replaces)
    r = P.pdf_watermark(src, out, o({"wm_type": "text", "text": "WM", "opacity": 20,
                                     "position": "center"}), REP)
    check("Watermark: original text still present",
          "unique0" in all_text(r[0]) and "unique2" in all_text(r[0]))
    check("Watermark: original images kept", image_count(r[0]) >= image_count(src))

    # Page numbers keep original text + images
    r = P.pdf_page_numbers(src, out, o({"position": "bottom-center", "format": "n",
                                        "start": 1, "font_size": 11}), REP)
    check("Page numbers: original text preserved", "unique1" in all_text(r[0]))
    check("Page numbers: images preserved", image_count(r[0]) == image_count(src))

    # Metadata edit changes ONLY metadata — text & images untouched
    r = P.pdf_metadata(src, out, o({"title": "New", "author": "Me",
                                    "subject": "", "keywords": ""}), REP)
    check("Edit metadata: page text unchanged", all_text(r[0]) == all_text(src))
    check("Edit metadata: images unchanged", image_count(r[0]) == image_count(src))
    d = fitz.open(str(r[0])); newtitle = d.metadata.get("title"); d.close()
    check("Edit metadata: title actually updated", newtitle == "New")

    # Protect → Unlock round-trip preserves text & images
    prot = P.pdf_protect(src, out, o({"operation": "protect", "password": "p@ss",
                                      "confirm_password": "p@ss"}), REP)
    unl = P.pdf_protect(prot[0], out, o({"operation": "unlock", "password": "p@ss"}), REP)
    check("Protect→Unlock: text identical to original", all_text(unl[0]) == all_text(src))
    check("Protect→Unlock: images preserved", image_count(unl[0]) == image_count(src))

    # Organize reorder keeps the SAME set of page texts
    r = P.pdf_organize(src, out, o({"operation": "reorder", "order": "3,1,2"}), REP)
    check("Organize reorder: same set of page texts (no loss)",
          sorted(page_text(r[0], i) for i in range(3)) ==
          sorted(page_text(src, i) for i in range(3)))

    import shutil
    shutil.rmtree(td, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All content-integrity checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
