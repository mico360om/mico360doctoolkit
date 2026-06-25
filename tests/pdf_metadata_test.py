"""Edit Metadata: every document property round-trips, untouched fields are
preserved, and 'Remove all' truly strips everything.

Run:  python tests/pdf_metadata_test.py
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


def _make_pdf(path: Path) -> None:
    import fitz
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


def _run(src: Path, out_dir: Path, opt: dict):
    from mico360.core import processors
    return processors.pdf_metadata(src, out_dir, opt, lambda *a, **k: None)


def main() -> int:
    from pypdf import PdfReader

    tmp = Path(tempfile.mkdtemp(prefix="mico360_meta_"))
    src = tmp / "src.pdf"
    out_dir = tmp / "out"
    out_dir.mkdir()
    _make_pdf(src)

    # --- set every field ----------------------------------------------------
    opt = {
        "title": "My Title", "author": "Jane Doe", "subject": "A subject",
        "keywords": "alpha,beta", "creator": "My Word App",
        "producer": "My Producer", "creation_date": "2021-03-04 09:10",
        "mod_date": "2022-05-06 11:12", "company": "MICO360",
        "manager": "The Boss", "category": "Reports", "comments": "hello world",
        "copyright": "© 2026 MICO360 <all rights>", "language": "en-US",
        "trapped": "Unknown", "show_title": True,
    }
    outs = _run(src, out_dir, opt)
    check("produces one output PDF", len(outs) == 1 and outs[0].exists())
    out = outs[0]
    r = PdfReader(str(out))
    m = r.metadata or {}

    expect = {
        "/Title": "My Title", "/Author": "Jane Doe", "/Subject": "A subject",
        "/Keywords": "alpha,beta", "/Creator": "My Word App",
        "/Producer": "My Producer", "/Company": "MICO360", "/Manager": "The Boss",
        "/Category": "Reports", "/Comments": "hello world",
    }
    for k, v in expect.items():
        check(f"info {k} round-trips", str(m.get(k)) == v, f"{m.get(k)!r}")
    check("creation date is a PDF date", str(m.get("/CreationDate", "")).startswith("D:2021"),
          str(m.get("/CreationDate")))
    check("mod date is a PDF date", str(m.get("/ModDate", "")).startswith("D:2022"),
          str(m.get("/ModDate")))
    check("trapped is set", "Unknown" in str(m.get("/Trapped")), str(m.get("/Trapped")))

    root = r.trailer["/Root"]
    check("document language /Lang is set", str(root.get("/Lang")) == "en-US",
          str(root.get("/Lang")))
    vp = root.get("/ViewerPreferences")
    vp = vp.get_object() if vp is not None else {}
    check("DisplayDocTitle viewer pref is on", bool(vp.get("/DisplayDocTitle")) is True,
          str(vp.get("/DisplayDocTitle")))

    raw = out.read_bytes()
    check("copyright stored in XMP (dc:rights)",
          b"dc:rights" in raw and "© 2026 MICO360".encode("utf-8") in raw)
    check("XMP marks the document as rights-managed", b"xmpRights:Marked" in raw)

    # --- preserve untouched fields -----------------------------------------
    out2 = _run(out, out_dir, {"title": "Renamed"})[0]
    m2 = PdfReader(str(out2)).metadata or {}
    check("changing only Title preserves Author", str(m2.get("/Author")) == "Jane Doe",
          str(m2.get("/Author")))
    check("changing only Title preserves Company", str(m2.get("/Company")) == "MICO360",
          str(m2.get("/Company")))
    check("Title was updated", str(m2.get("/Title")) == "Renamed", str(m2.get("/Title")))

    # --- bad date is reported clearly --------------------------------------
    from mico360.core.processors import ProcessError
    try:
        _run(src, out_dir, {"creation_date": "not-a-date"})
        check("invalid date raises a clear error", False, "no error raised")
    except ProcessError as exc:
        check("invalid date raises a clear error", "date" in str(exc).lower())

    # --- remove all ---------------------------------------------------------
    stripped = _run(out, out_dir, {"remove_all": True})[0]
    rs = PdfReader(str(stripped))
    ms = rs.metadata or {}
    nonempty = {k: v for k, v in ms.items() if str(v).strip()}
    check("remove_all clears the Info dictionary", not nonempty, str(nonempty))
    rroot = rs.trailer["/Root"]
    check("remove_all drops XMP + /Lang",
          "/Metadata" not in rroot and "/Lang" not in rroot)

    # cleanup
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} metadata check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All Edit-Metadata checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
