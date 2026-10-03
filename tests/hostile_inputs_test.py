"""Robustness: every tool against broken, empty, mislabelled and oddly named
files, run through the real engine worker (what the user actually sees).

For each of the 21 tools and each hostile input — 0 bytes, random bytes, a
truncated file, another file type renamed, a file deleted after it was added, a
password-protected PDF, extreme image shapes and colour modes, and valid files
with a long or non-English name — the result must be either a real output or
ONE readable sentence:

* never "Unexpected error: …" (a raw library exception),
* never a full path, error code or Python internals in the message,
* the source file is never modified, and no stray output is left behind,
* valid files with awkward names are processed normally.

Run:  python tests/hostile_inputs_test.py            (all tools, ~2 minutes)
      python tests/hostile_inputs_test.py pdf_sign   (just these tool ids)
"""
import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix="mico_fuzz_"))
os.environ.setdefault("MICO360_SETTINGS_FILE", str(WORK / "fuzz.ini"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication([])

import fitz  # noqa: E402
from PIL import Image  # noqa: E402

from mico360.core.tools import TOOLS  # noqa: E402

ONLY = set(sys.argv[1].split(",")) if len(sys.argv) > 1 and sys.argv[1] else None
SRC = WORK / "src dir – ünï"
SRC.mkdir()
ODD = "résumé (final) #1 & co – عربي 文件"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).exists() else None


# ---------------------------------------------------------------- valid samples
def make_pdf(p, pages=3, password=None, blank=False):
    d = fitz.open()
    for i in range(pages):
        pg = d.new_page()
        if not blank:
            pg.insert_text((60, 90), f"Quarterly report page {i + 1}", fontsize=18)
            pg.insert_text((60, 130), "Revenue rose 12% to OMR 48.2 million. " * 3,
                           fontsize=10)
    if password:
        d.save(str(p), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password,
               owner_pw=password)
    else:
        d.save(str(p))
    d.close()


def make_img(p, size=(640, 480), mode="RGB"):
    im = Image.new(mode, size, (200, 60, 60) if mode == "RGB" else None)
    if mode == "RGB":
        from PIL import ImageDraw
        ImageDraw.Draw(im).rectangle([40, 40, 300, 200], fill=(255, 255, 255))
    if p.suffix.lower() in (".jpg", ".jpeg") and mode not in ("RGB", "L", "CMYK"):
        im = im.convert("RGB")
    im.save(str(p))


def make_docx(p):
    import docx
    d = docx.Document()
    d.add_heading("Sample letter", 1)
    d.add_paragraph("Dear customer, thank you for your business. " * 5)
    d.save(str(p))


SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120">'
       '<rect width="200" height="120" fill="#821414"/>'
       '<circle cx="100" cy="60" r="40" fill="white"/></svg>')

good_pdf = SRC / "good.pdf"; make_pdf(good_pdf)
good_png = SRC / "good.png"; make_img(good_png)
good_jpg = SRC / "good.jpg"; make_img(good_jpg)
good_docx = SRC / "good.docx"; make_docx(good_docx)
good_svg = SRC / "good.svg"; good_svg.write_text(SVG, encoding="utf-8")
BYTES = {".pdf": good_pdf.read_bytes(), ".png": good_png.read_bytes(),
         ".jpg": good_jpg.read_bytes(), ".docx": good_docx.read_bytes(),
         ".svg": good_svg.read_bytes()}
WRONG = {".pdf": ".png", ".png": ".pdf", ".jpg": ".pdf", ".docx": ".pdf", ".svg": ".png"}


def cases_for(ext):
    """(case name, path, expect) — expect 'ok' or 'fail' or 'any'."""
    out = []

    def w(name, fname, data):
        p = SRC / fname
        p.write_bytes(data)
        out.append((name, p))

    good = BYTES[ext]
    w("valid, odd name", f"{ODD}{ext}", good)
    w("valid, 180-char name", "n" * 180 + ext, good)
    w("empty (0 bytes)", f"zero{ext}", b"")
    w("garbage bytes", f"garbage{ext}", os.urandom(4096))
    w("truncated", f"truncated{ext}", good[: max(8, int(len(good) * 0.4))])
    w("wrong type inside", f"wrongtype{ext}", BYTES[WRONG[ext]])
    out.append(("missing file", SRC / f"does_not_exist{ext}"))
    if ext == ".pdf":
        p = SRC / "locked.pdf"; make_pdf(p, password="s3cret!pw"); out.append(("password-protected", p))
        p = SRC / "blank.pdf"; make_pdf(p, pages=1, blank=True); out.append(("blank page, no text", p))
        p = SRC / "big.pdf"; make_pdf(p, pages=120); out.append(("120 pages", p))
    if ext in (".png", ".jpg"):
        p = SRC / f"tiny{ext}"; make_img(p, (1, 1)); out.append(("1x1 pixel", p))
        p = SRC / f"wide{ext}"; make_img(p, (6000, 8)); out.append(("6000x8 strip", p))
        if ext == ".png":
            p = SRC / "palette_alpha.png"
            im = Image.new("RGBA", (300, 200), (0, 0, 0, 0)); im.paste((255, 0, 0, 255), (50, 50, 200, 150))
            im.convert("P").save(str(p), transparency=0); out.append(("palette + transparency", p))
            p = SRC / "gray16.png"; Image.new("I;16", (200, 150), 30000).save(str(p)); out.append(("16-bit grey", p))
        else:
            p = SRC / "cmyk.jpg"; Image.new("CMYK", (300, 200), (0, 200, 200, 0)).save(str(p)); out.append(("CMYK", p))
    return out


EXPECT_OK = {"valid, odd name", "valid, 180-char name", "blank page, no text", "120 pages",
             "1x1 pixel", "6000x8 strip", "palette + transparency", "16-bit grey", "CMYK"}
OVERRIDES = {
    "pdf_protect": {"password": "Passw0rd!x", "confirm_password": "Passw0rd!x"},
    "pdf_sign": {"image_path": str(good_png)},
    "file_properties": {"date_modified": "2026-01-02 03:04"},
}


def primary_ext(tool):
    a = tool.accept
    for e in (".pdf", ".png", ".svg", ".docx"):
        if e in a or "*" in a:
            return e
    return sorted(a)[0]


class Rep:
    def __init__(self):
        self.msgs = []

    def __call__(self, m):
        self.msgs.append(str(m))

    def progress(self, c, t):
        pass

    def cancelled(self):
        return False


rows = []
for tool in TOOLS:
    if ONLY and tool.id not in ONLY:
        continue
    exts = [primary_ext(tool)]
    if tool.id == "pdf_ocr":
        exts.append(".png")
    if ".jpg" in tool.accept and tool.id != "pdf_ocr":
        exts.append(".jpg")
    for ext in exts:
        for name, path in cases_for(ext):
            opt = {o.key: o.default for o in tool.options}
            opt.update(OVERRIDES.get(tool.id, {}))
            opt.update(overwrite=False, same_as_source=False)
            out_dir = WORK / "out" / tool.id / f"{ext[1:]}_{len(rows)}"
            out_dir.mkdir(parents=True)
            before = sha(path)
            item = [path, {".pdf": good_pdf, ".png": good_png, ".jpg": good_jpg}.get(ext, path)] \
                if tool.mode == "aggregate" else path
            print(f"… {tool.id} [{ext}] {name}", flush=True)
            t0 = time.monotonic()
            # Through the real engine worker: exactly what the user would see.
            import threading
            from mico360.core.engine import _Worker
            got = []
            wk = _Worker(tool, item, out_dir, opt, threading.Event(), 0)
            wk.signals.finished.connect(got.append)
            wk.run()
            res = got[0]
            if res.ok:
                outs = res.outputs
                kind = "OK" if outs else "OK?"
                detail = ", ".join(Path(o).name[:40] for o in outs[:2]) or "no outputs"
            elif res.message.startswith("Unexpected error"):
                kind, detail = "RAW", res.message
            else:
                kind, detail = "CLEAN", res.message
            # A readable message never shows Python internals or a full path.
            if kind == "CLEAN" and any(k in detail for k in (
                    "Traceback", "Error:", "Exception", "Errno", "WinError",
                    ":\\", "\\\\", "0x", "-2147")):
                kind = "UGLY"
            dt = time.monotonic() - t0
            flags = []
            if before is not None and sha(path) != before and tool.id != "file_properties":
                flags.append("SOURCE MODIFIED")
            if kind in ("CLEAN", "RAW", "UGLY"):
                left = [f.name for f in out_dir.rglob("*") if f.is_file()]
                if left:
                    flags.append(f"left behind: {left[:3]}")
            want_ok = name in EXPECT_OK
            verdict = "ok"
            if kind in ("RAW", "UGLY") or flags:
                verdict = "PROBLEM"
            elif want_ok and kind != "OK":
                # a valid file was refused — only OCR may (text PDFs need no OCR)
                verdict = "check" if (tool.id == "pdf_ocr" and ext == ".pdf") else "PROBLEM"
            elif not want_ok and kind == "OK" and name != "wrong type inside":
                verdict = "check"          # a broken file "succeeded"
            rows.append((verdict, tool.id, ext, name, kind, dt, detail, flags))

print("\n================ RESULTS ================")
problems = [r for r in rows if r[0] == "PROBLEM"]
for r in problems:
    print(f"[FAIL] {r[1]} [{r[2]}] {r[3]} -> {r[4]}: {r[6][:260]} {' | '.join(r[7])}")
by_tool = {}
for r in rows:
    by_tool.setdefault(r[1], []).append(r)
for tid, rs in by_tool.items():
    bad = sum(1 for r in rs if r[0] == "PROBLEM")
    print(f"[{'FAIL' if bad else 'PASS'}] {tid}: {len(rs)} hostile-input cases, "
          f"{sum(1 for r in rs if r[4] == 'OK')} processed, "
          f"{sum(1 for r in rs if r[4] == 'CLEAN')} refused with a clear message"
          + (f", {bad} PROBLEM(S)" if bad else ""))
import shutil
shutil.rmtree(WORK, ignore_errors=True)
print()
if problems:
    print(f"{len(problems)} of {len(rows)} robustness case(s) FAILED.")
    sys.exit(1)
print(f"All {len(rows)} robustness cases passed.")
sys.exit(0)
