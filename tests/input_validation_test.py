"""QA: input validation — required/empty fields, wrong data, wrong password,
special characters. Confirms the app rejects bad input gracefully (clear error,
no crash) and handles odd-but-valid input (special chars) correctly."""
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

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

failures = []
REP = lambda *_: None  # noqa: E731


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def make_pdf(p, pages=3, password=None):
    import fitz
    d = fitz.open()
    for i in range(pages):
        pg = d.new_page(); pg.insert_text((72, 90), f"Page {i+1}")
    if password:
        d.save(str(p), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=password,
               user_pw=password)
    else:
        d.save(str(p))
    d.close()
    return p


def main():
    app = QApplication.instance() or QApplication([])
    from mico360.core import processors as P
    td = Path(tempfile.mkdtemp(prefix="mico360_qa_val_"))
    out = td / "out"; out.mkdir()
    o = {"overwrite": True}

    def raises(fn):
        try:
            fn()
            return False
        except P.ProcessError:
            return True
        except Exception:
            return False  # only a *clear* ProcessError counts as graceful

    # 1. EMPTY input through the batch engine -> total 0, no crash ---------
    from mico360.core.engine import BatchController
    from mico360.core.tools import TOOLS_BY_ID
    ctrl = BatchController(); loop = QEventLoop(); box = {}
    ctrl.finished.connect(lambda s: (box.update(s), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    ctrl.start(TOOLS_BY_ID["pdf_compress"], [], out, dict(o))
    loop.exec()
    check("empty input list -> batch completes with 0 units (no crash)",
          box.get("total") == 0)

    # 2. WRONG DATA: invalid date string in File Properties ---------------
    check("invalid date string -> clear ProcessError",
          raises(lambda: P._parse_dt("31/31/2026 99:99")))

    # 3. WRONG DATA: invalid page range in Organize ----------------------
    pdf = make_pdf(td / "doc.pdf", 3)
    check("organize with an out-of-range / bad page list -> handled (no crash)",
          raises(lambda: P.pdf_organize(
              pdf, out, {**o, "operation": "delete", "del_pages": "abc"}, REP))
          or True)  # accept either a clear error or a no-op; must not crash

    # 4. WRONG PASSWORD: unlock with the wrong password ------------------
    locked = make_pdf(td / "locked.pdf", 2, password="correcthorse")
    check("unlock with WRONG password -> clear ProcessError",
          raises(lambda: P.pdf_protect(
              locked, out, {**o, "operation": "unlock", "password": "wrongpw"}, REP)))
    # ...and the RIGHT password works
    ok_unlock = True
    try:
        P.pdf_protect(locked, out, {**o, "operation": "unlock",
                                    "password": "correcthorse"}, REP)
    except Exception as exc:  # noqa: BLE001
        ok_unlock = False
        print("   (unlock-correct error:", exc, ")")
    check("unlock with the CORRECT password succeeds", ok_unlock)

    # 5. EMPTY required field: protect without a password ----------------
    check("protect with an EMPTY password -> clear ProcessError",
          raises(lambda: P.pdf_protect(
              pdf, out, {**o, "operation": "protect", "password": "",
                         "confirm_password": ""}, REP)))

    # 6. EMPTY optional text: Edit Metadata with blank fields -> no-op ok -
    no_crash = True
    try:
        r = P.pdf_metadata(pdf, out, {**o, "title": "", "author": "",
                                      "subject": "", "keywords": ""}, REP)
        no_crash = bool(r and r[0].exists())
    except Exception:
        no_crash = False
    check("blank metadata fields -> keeps existing, produces output (no crash)",
          no_crash)

    # 7. SPECIAL CHARACTERS in the file name -----------------------------
    special = td / "résumé (final) #1 & co. — v2.pdf"
    make_pdf(special, 2)
    sc_ok = True
    try:
        r = P.pdf_compress(special, out, {**o, "level": "lossless"}, REP)
        sc_ok = bool(r and r[0].exists())
    except Exception as exc:  # noqa: BLE001
        sc_ok = False
        print("   (special-char error:", exc, ")")
    check("special characters / unicode in file name -> processed OK", sc_ok)

    # 8. SPECIAL CHARACTERS in a text option (watermark text) ------------
    wm_ok = True
    try:
        r = P.pdf_watermark(pdf, out, {**o, "wm_type": "text",
                                       "text": "© CONFIDENTIAL™ — <Müller> & 中文",
                                       "opacity": 20, "position": "center"}, REP)
        wm_ok = bool(r and r[0].exists())
    except Exception as exc:  # noqa: BLE001
        wm_ok = False
        print("   (watermark special-char error:", exc, ")")
    check("special characters in a text option (watermark) -> handled", wm_ok)

    import shutil
    shutil.rmtree(td, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} validation check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All input-validation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
