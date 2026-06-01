"""Regression tests for the QA-audit fixes (v3.2):
atomic output-name reservation (no TOCTOU clobber), friendly error wrapping for
corrupt files, unique split/image subfolders, and per-source output for the
aggregate "save next to source" case.

Run:  python tests/qa_fixes_test.py   (offscreen; no GUI shown)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def _img(path: Path) -> Path:
    from PIL import Image
    Image.new("RGB", (320, 240), (160, 32, 31)).save(path)
    return path


def _pdf(path: Path, pages: int = 3) -> Path:
    import fitz
    d = fitz.open()
    for _ in range(pages):
        d.new_page().insert_text((72, 72), "x")
    d.save(str(path)); d.close()
    return path


def main() -> int:
    from mico360.core import processors as P
    from mico360.core.util import build_output_path, unique_path

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); out = tmp / "out"; out.mkdir()

        # --- atomic output-name reservation (TOCTOU fix) ----------------
        def reservation():
            base = out / "report.pdf"
            a = unique_path(base, overwrite=False)
            b = unique_path(base, overwrite=False)   # must NOT reuse 'a'
            c = unique_path(base, overwrite=False)
            names = {a.name, b.name, c.name}
            assert len(names) == 3, f"collision: {names}"
            assert a.exists() and b.exists() and c.exists(), "names not reserved"
            assert names == {"report.pdf", "report (1).pdf", "report (2).pdf"}, names
        check("unique_path reserves distinct names atomically", reservation)

        def numbered_reservation():
            src = tmp / "doc.pdf"; src.write_bytes(b"x")
            p1 = build_output_path(src, out, ".pdf", numbered=True)
            p2 = build_output_path(src, out, ".pdf", numbered=True)
            assert {p1.name, p2.name} == {"doc (1).pdf", "doc (2).pdf"}, (p1.name, p2.name)
            assert p1.exists() and p2.exists()
        check("numbered build_output_path reserves distinct names", numbered_reservation)

        # --- friendly error wrapping for corrupt inputs -----------------
        bad_pdf = tmp / "broken.pdf"; bad_pdf.write_bytes(b"%PDF-1.4 not really")
        good_pdf = _pdf(tmp / "ok.pdf")
        check("merge corrupt -> friendly ProcessError",
              lambda: expect_error(lambda: P.pdf_merge([bad_pdf, good_pdf], out, {}, rep),
                                   "couldn't read"))
        check("split corrupt -> friendly ProcessError",
              lambda: expect_error(lambda: P.pdf_split(bad_pdf, out, {"mode": "each"}, rep),
                                   "couldn't read"))
        bad_img = tmp / "broken.jpg"; bad_img.write_bytes(b"not an image")
        check("image_compress corrupt -> friendly ProcessError",
              lambda: expect_error(lambda: P.image_compress(bad_img, out, {"level": "medium"}, rep),
                                   "couldn't open"))

        # --- unique split subfolder for same-named PDFs -----------------
        def split_subfolders():
            d1 = tmp / "f1"; d1.mkdir(); d2 = tmp / "f2"; d2.mkdir()
            a = _pdf(d1 / "same.pdf", 2); b = _pdf(d2 / "same.pdf", 2)
            sout = tmp / "sout"; sout.mkdir()
            r1 = P.pdf_split(a, sout, {"mode": "each", "overwrite": True}, rep)
            r2 = P.pdf_split(b, sout, {"mode": "each", "overwrite": True}, rep)
            dirs = {r1[0].parent, r2[0].parent}
            assert len(dirs) == 2, f"both wrote into the same subfolder: {dirs}"
        check("split of same-named PDFs uses separate subfolders", split_subfolders)

        # --- aggregate save-next-to-source goes beside EACH image -------
        def aggregate_same_as_source():
            d1 = tmp / "a1"; d1.mkdir(); d2 = tmp / "a2"; d2.mkdir()
            i1 = _img(d1 / "p1.png"); i2 = _img(d2 / "p2.png")
            res = P.image_to_pdf([i1, i2], out, {"combine": False, "same_as_source": True}, rep)
            parents = {p.parent for p in res}
            assert d1 in parents and d2 in parents, f"outputs not beside sources: {parents}"
        check("aggregate same-as-source writes beside each source", aggregate_same_as_source)

        # --- mid-loop cancellation stops a multi-page job early ---------
        def mid_loop_cancel():
            from mico360.core.processors import _check_cancel

            def cancelling_report(_m):
                pass
            cancelling_report.cancelled = lambda: True   # engine-style cancel flag
            # the helper raises so loops bail out promptly
            try:
                _check_cancel(cancelling_report)
            except Exception as exc:
                assert "cancel" in str(exc).lower(), exc
            else:
                raise AssertionError("_check_cancel did not raise when cancelled")
            # and a real processor honours it (bails before finishing the pages)
            deck = _pdf(tmp / "cdeck.pdf", 6)
            cout = tmp / "cout"; cout.mkdir()
            expect_error(lambda: P.pdf_to_image(
                deck, cout, {"format": "png", "dpi": 72}, cancelling_report), "cancel")
        check("mid-loop cancellation stops a job", mid_loop_cancel)

        # --- clamping guards out-of-range config values -----------------
        def clamping():
            from mico360.core.processors import _clampi
            assert _clampi(99999, 36, 600, 150) == 600
            assert _clampi(-5, 36, 600, 150) == 36
            assert _clampi("oops", 36, 600, 150) == 150
            # a hand-edited huge DPI must not blow up PDF->Image
            d = _pdf(tmp / "clamp.pdf", 1)
            cdir = tmp / "cl"; cdir.mkdir()
            r = P.pdf_to_image(d, cdir, {"format": "png", "dpi": 999999}, rep)
            assert r and r[0].exists()
        check("clamping guards out-of-range values", clamping)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All QA-fix checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
