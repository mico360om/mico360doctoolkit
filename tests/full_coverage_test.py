"""Broad coverage test: every tool, edge cases, and helper utilities.

Complements smoke_test (happy path) by hitting the less-travelled branches:
all split modes + bad ranges, every image output format, resize, non-combined
image->pdf, output-name collisions, the LibreOffice-missing error path, and the
file_collector / util helpers.

Run:  python tests/full_coverage_test.py   (offscreen; no GUI shown)
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


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"[PASS] {name}")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}: {exc!r}")
        failures.append(name)


def expect_error(fn, needle: str = "") -> None:
    from mico360.core.util import ProcessError
    try:
        fn()
    except ProcessError as exc:
        assert needle.lower() in str(exc).lower(), f"wrong message: {exc}"
        return
    raise AssertionError("expected ProcessError, none raised")


def files_ok(result, expected: int | None = None):
    paths = list(result)
    assert paths, "no output produced"
    for p in paths:
        assert Path(p).exists() and Path(p).stat().st_size > 0, f"bad output {p}"
    if expected is not None:
        assert len(paths) == expected, f"expected {expected}, got {len(paths)}"
    return paths


def _pdf(path: Path, pages: int = 4) -> Path:
    import fitz
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page()
        pg.insert_text((72, 72), f"Page {i + 1}")
    doc.save(str(path))
    doc.close()
    return path


def _img(path: Path, size=(900, 600), mode="RGB") -> Path:
    from PIL import Image
    img = Image.new(mode, size, (160, 32, 31) if mode == "RGB" else (160, 32, 31, 255))
    img.save(path)
    return path


def main() -> int:
    from mico360.core import processors as P
    from mico360.core.util import build_output_path, human_size
    from mico360.ui.file_collector import collect_files

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        out = tmp / "out"; out.mkdir()
        pdf = _pdf(tmp / "doc.pdf", 4)
        pdf2 = _pdf(tmp / "doc2.pdf", 2)
        png = _img(tmp / "a.png")
        rgba = _img(tmp / "rgba.png", mode="RGBA")

        # --- split: every mode + bad input -----------------------------
        check("split each (4)", lambda: files_ok(
            P.pdf_split(pdf, out, {"mode": "each"}, rep), 4))
        check("split every_n=2 (2)", lambda: files_ok(
            P.pdf_split(pdf, out, {"mode": "every_n", "every_n": 2, "overwrite": True}, rep), 2))
        check("split ranges '1-2,4' (2)", lambda: files_ok(
            P.pdf_split(pdf, out, {"mode": "ranges", "ranges": "1-2, 4", "overwrite": True}, rep), 2))
        check("split bad ranges -> error",
              lambda: expect_error(lambda: P.pdf_split(
                  pdf, out, {"mode": "ranges", "ranges": "zzz"}, rep), "no valid"))

        # --- merge: happy + too-few ------------------------------------
        check("merge 2 -> 1", lambda: files_ok(
            P.pdf_merge([pdf, pdf2], out, {"output_name": "m"}, rep), 1))
        check("merge 1 -> error",
              lambda: expect_error(lambda: P.pdf_merge([pdf], out, {}, rep), "at least two"))

        # --- pdf -> image: all formats ---------------------------------
        for fmt, n in (("png", 4), ("jpg", 4), ("webp", 4), ("tiff", 4), ("bmp", 4)):
            check(f"pdf->image {fmt}", lambda fmt=fmt, n=n: files_ok(
                P.pdf_to_image(pdf, out, {"format": fmt, "dpi": 72,
                                          "jpeg_quality": 85, "overwrite": True}, rep), n))

        # --- image -> pdf: combined + per-file + rgba flatten ----------
        check("image->pdf combined", lambda: files_ok(
            P.image_to_pdf([png, rgba], out, {"combine": True, "output_name": "c"}, rep), 1))
        check("image->pdf per-file (2)", lambda: files_ok(
            P.image_to_pdf([png, rgba], out, {"combine": False, "overwrite": True}, rep), 2))
        check("image->pdf no images -> error",
              lambda: expect_error(lambda: P.image_to_pdf([], out, {}, rep), "no supported"))

        # --- image compress: formats + resize --------------------------
        check("img compress keep", lambda: files_ok(
            P.image_compress(png, out, {"level": "medium", "format": "keep", "overwrite": True}, rep)))
        check("img compress -> webp", lambda: files_ok(
            P.image_compress(png, out, {"level": "high", "format": "webp", "overwrite": True}, rep)))
        check("img compress -> png", lambda: files_ok(
            P.image_compress(rgba, out, {"level": "low", "format": "png", "overwrite": True}, rep)))

        def resize_check():
            res = P.image_compress(png, out, {"level": "medium", "format": "jpg",
                                              "max_dimension": 300, "overwrite": True}, rep)
            from PIL import Image
            w, h = Image.open(res[0]).size
            assert max(w, h) == 300, f"resize failed: {w}x{h}"
        check("img compress resize to 300px", resize_check)

        check("img compress bad type -> error",
              lambda: expect_error(lambda: P.image_compress(
                  tmp / "x.gif", out, {}, rep), "unsupported"))

        # --- convert: pptx + word --------------------------------------
        check("pdf->pptx", lambda: files_ok(P.pdf_to_pptx(pdf, out, {"dpi": 96}, rep)))
        check("pdf->word", lambda: files_ok(P.pdf_to_word(pdf, out, {}, rep)))

        # word->pdf now works via an engine chain (LibreOffice / MS Word /
        # built-in fallback) — no external program required.
        def word_pdf_works():
            import docx
            dp = tmp / "mini.docx"
            d = docx.Document()
            d.add_paragraph("Hello world from a Word document.")
            d.save(str(dp))
            r = P.word_to_pdf(dp, out, {}, rep)
            assert r[0].exists() and r[0].suffix == ".pdf", str(r)
            import fitz
            doc = fitz.open(r[0])
            txt = "".join(pg.get_text() for pg in doc)
            doc.close()
            assert "Hello world" in txt, repr(txt[:60])
        check("word->pdf works via engine chain", word_pdf_works)
        # A missing/invalid file still raises a clean ProcessError.
        check("word->pdf bad input -> error",
              lambda: expect_error(lambda: P.word_to_pdf(
                  tmp / "nope.docx", out, {}, rep), "failed"))

        # --- output-path collision handling ----------------------------
        def collision():
            a = build_output_path(pdf, out, ".pdf", name_suffix="_x", overwrite=False)
            a.write_bytes(b"1")
            b = build_output_path(pdf, out, ".pdf", name_suffix="_x", overwrite=False)
            assert b != a and "(1)" in b.name, f"no unique variant: {b.name}"
            c = build_output_path(pdf, out, ".pdf", name_suffix="_x", overwrite=True)
            assert c == a, "overwrite should reuse the base name"
        check("output collision -> ' (1)'", collision)

        # --- numbered naming for "save next to source" -----------------
        def numbered_path():
            # Ignores name_suffix/overwrite; always next free " (n)".
            p1 = build_output_path(pdf, out, ".pdf", name_suffix="_compressed",
                                   numbered=True)
            assert p1.name == "doc (1).pdf", p1.name
            p1.write_bytes(b"1")
            p2 = build_output_path(pdf, out, ".pdf", numbered=True)
            assert p2.name == "doc (2).pdf", p2.name
        check("numbered build_output_path -> 'doc (1).pdf', 'doc (2).pdf'", numbered_path)

        def numbered_compress_keeps_original():
            # Simulate "save next to source": source + output share a folder.
            src_dir = tmp / "beside"; src_dir.mkdir()
            s = _img(src_dir / "pic.jpg")
            before = s.read_bytes()
            r1 = P.image_compress(s, src_dir, {"level": "high", "format": "keep",
                                               "same_as_source": True}, rep)
            r2 = P.image_compress(s, src_dir, {"level": "high", "format": "keep",
                                               "same_as_source": True}, rep)
            assert r1[0].name == "pic (1).jpg", r1[0].name
            assert r2[0].name == "pic (2).jpg", r2[0].name
            assert s.exists() and s.read_bytes() == before, "original was modified!"
        check("same-as-source numbering keeps original untouched",
              numbered_compress_keeps_original)

        def chosen_folder_keeps_suffix():
            # Without same_as_source, keep the descriptive suffix as before.
            r = P.image_compress(png, out, {"level": "high", "format": "jpg",
                                            "overwrite": True}, rep)
            assert r[0].name == "a_compressed.jpg", r[0].name
        check("chosen-folder naming unchanged (_compressed)", chosen_folder_keeps_suffix)

        # --- helpers ---------------------------------------------------
        check("human_size", lambda: (
            _eq(human_size(0), "0.0 B"), _eq(human_size(1536), "1.5 KB"),
            _eq(human_size(1048576), "1.0 MB")))

        def collector():
            root = tmp / "tree" / "sub"
            root.mkdir(parents=True)
            _img(root / "p1.png"); _img(tmp / "tree" / "p2.jpg")
            (tmp / "tree" / "note.txt").write_text("x")
            got = collect_files([str(tmp / "tree")], {".png", ".jpg"})
            assert len(got) == 2, f"expected 2, got {len(got)}"
            # de-dup when the same file is passed twice
            again = collect_files([str(root / "p1.png"), str(root / "p1.png")], {".png"})
            assert len(again) == 1, f"dedup failed: {len(again)}"
        check("collect_files recursion + dedup + filter", collector)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All coverage checks passed.")
    return 0


def _eq(a, b):
    assert a == b, f"{a!r} != {b!r}"


if __name__ == "__main__":
    raise SystemExit(main())
