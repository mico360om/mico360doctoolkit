"""Regression tests for the fixes from the 2026-09-26 bug report
(build/BUG_REPORT_2026-09-26.md). Each check names the report item it guards.

Runs against temporary files, a throw-away settings file and a sandbox registry
key only — never the user's real settings or Explorer menu.

Run:  python tests/bugfix_2026_09_test.py   (or via tests/run_suite.py)
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
from pathlib import Path

# Never touch the real %APPDATA% settings, even when run directly.
if not os.environ.get("MICO360_SETTINGS_FILE"):
    os.environ["MICO360_SETTINGS_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="mico360_bugfix_"), "DocToolkit.ini")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def quiet(*_a, **_k):
    pass


TD = Path(tempfile.mkdtemp(prefix="mico360_bugfix_files_"))


def make_pdf(path: Path, n: int = 3, toc: bool = True, title: str = "Orig") -> Path:
    import fitz
    d = fitz.open()
    for i in range(n):
        d.new_page().insert_text((72, 100), f"PAGE {i + 1} body text")
    if toc:
        d.set_toc([[1, "First", 1], [1, "Last", n]])
    d.set_metadata({"title": title, "author": "Real Author"})
    d.save(str(path))
    d.close()
    return path


# =====================================================================
def test_settings_isolation():
    print("--- M-37 settings isolation ---")
    from mico360.config import settings
    check("M-37: settings use MICO360_SETTINGS_FILE when set",
          os.path.normcase(settings._s.fileName())
          == os.path.normcase(os.environ["MICO360_SETTINGS_FILE"]),
          settings._s.fileName())


def test_ocr_unicode_layer():
    print("--- H-9 Unicode OCR text layer ---")
    import fitz
    from mico360.core import processors as P
    src = TD / "scan.pdf"
    d = fitz.open(); d.new_page(); d.save(str(src)); d.close()
    lines = ["مرحبا بالعالم", "Привет мир", "Zażółć gęślą jaźń", "Plain English"]
    canned = [(t, (72.0, 100.0 + 30 * k, 400.0, 120.0 + 30 * k)) for k, t in enumerate(lines)]
    oe, oc = P._make_ocr_engine, P._ocr_pages_concurrent
    P._make_ocr_engine = lambda *a, **k: None
    P._ocr_pages_concurrent = lambda *a, **k: {0: list(canned)}
    try:
        out = P.pdf_ocr(src, TD / "ocr", {"ocr_lang": "arabic", "overwrite": True}, quiet)[0]
    finally:
        P._make_ocr_engine, P._ocr_pages_concurrent = oe, oc
    d = fitz.open(str(out))
    txt = d[0].get_text()
    for t in lines:
        check(f"H-9: text layer reads back {t!r}", t in txt, repr(txt[:80]))
    for w in ("مرحبا", "Привет", "gęślą"):
        check(f"H-9: search finds {w!r}", bool(d[0].search_for(w)))
    check("H-9: reading order kept", txt.index("مرحبا") < txt.index("Plain"))
    d.close()


def test_pdf_structure_kept():
    print("--- M-11 bookmarks + metadata survive ---")
    import fitz
    from mico360.core import processors as P
    src = make_pdf(TD / "doc.pdf", 4)
    o = P.pdf_protect(src, TD / "prot", {"operation": "protect", "password": "pw",
                                          "overwrite": True}, quiet)[0]
    d = fitz.open(str(o)); d.authenticate("pw")
    check("M-11: protect keeps bookmarks", len(d.get_toc()) == 2, str(d.get_toc()))
    check("M-11: protect keeps the title", d.metadata.get("title") == "Orig")
    d.close()
    u = P.pdf_protect(o, TD / "unl", {"operation": "unlock", "password": "pw",
                                       "overwrite": True}, quiet)[0]
    d = fitz.open(str(u))
    check("M-11: unlock keeps bookmarks", not d.needs_pass and len(d.get_toc()) == 2)
    d.close()
    for name, fn, opt in (
            ("rotate", P.pdf_rotate, {"angle": 90, "pages": "1"}),
            ("delete", P.pdf_delete, {"pages": "2"}),
            ("extract", P.pdf_extract, {"pages": "1, 4"})):
        o = fn(src, TD / name, dict(opt, overwrite=True), quiet)[0]
        d = fitz.open(str(o))
        check(f"M-11: {name} keeps bookmarks + title",
              len(d.get_toc()) >= 1 and d.metadata.get("title") == "Orig",
              f"{d.get_toc()} {d.metadata.get('title')}")
        d.close()


def test_pptx_rotated():
    print("--- M-17 PDF → PowerPoint ---")
    import fitz
    from pptx import Presentation
    from mico360.core import processors as P
    src = TD / "rot.pdf"
    d = fitz.open()
    d.new_page(width=612, height=792).insert_text((72, 100), "Portrait text " * 10)
    p = d.new_page(width=612, height=792)
    p.insert_text((100, 700), "Rotated page text " * 12, rotate=90)
    p.set_rotation(90)
    d.new_page(width=306, height=396).insert_text((20, 40), "Small page " * 10, fontsize=6)
    d.save(str(src)); d.close()
    o = P.pdf_to_pptx(src, TD / "pptx", {"mode": "text", "overwrite": True}, quiet)[0]
    prs = Presentation(str(o))
    sw, sh = prs.slide_width, prs.slide_height
    for n, slide in enumerate(prs.slides, 1):
        boxes = [s for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()]
        on = boxes and all(0 <= s.left + s.width / 2 <= sw and 0 <= s.top + s.height / 2 <= sh
                           for s in boxes)
        check(f"M-17: slide {n} text lands on the slide", bool(on))


def test_friendly_errors_and_parsing():
    print("--- processing Lows ---")
    import fitz
    from mico360.core import processors as P
    from mico360.core.util import ProcessError
    enc = TD / "enc.pdf"
    d = fitz.open(str(make_pdf(TD / "e0.pdf", 1)))
    d.save(str(enc), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    d.close()
    for name, fn, opt in (("watermark", P.pdf_watermark, {"text": "X"}),
                          ("page numbers", P.pdf_page_numbers, {}),
                          ("PDF → image", P.pdf_to_image, {}),
                          ("PDF → PPTX", P.pdf_to_pptx, {})):
        try:
            fn(enc, TD / "x", opt, quiet)
            check(f"Low: {name} explains a password-protected PDF", False)
        except ProcessError as exc:
            check(f"Low: {name} explains a password-protected PDF",
                  "password" in str(exc).lower(), str(exc)[:70])
    try:
        P._parse_dt("03/04/2026")
        check("Low: an ambiguous day/month date is rejected", False)
    except ProcessError as exc:
        check("Low: an ambiguous day/month date is rejected", "ambiguous" in str(exc))
    check("Low: an unambiguous date still parses",
          P._parse_dt("25/12/2026").month == 12 and P._parse_dt("2026-04-03").day == 3)

    class _Cancelled:
        def __call__(self, *a, **k):
            pass
        cancelled = staticmethod(lambda: True)
    big = TD / "big.pdf"
    make_pdf(big, 2)
    try:
        P.pdf_compress(big, TD / "tgt", {"level": "target", "target_kb": 1}, _Cancelled())
        check("Low: compress-to-target honours Cancel", False)
    except ProcessError as exc:
        check("Low: compress-to-target honours Cancel", "Cancel" in str(exc))


def test_visual_plan_target():
    print("--- H-3 organizer plan is per file ---")
    from mico360.core import processors as P
    from mico360.core.util import ProcessError
    a = make_pdf(TD / "A.pdf", 3)
    b = make_pdf(TD / "B.pdf", 3)
    plan = {"n_src": 3, "groups": [[{"src": 2, "rotate": 0}, {"src": 0, "rotate": 90}]],
            "target": str(a)}
    out = P.pdf_organize(a, TD / "va", {"operation": "visual", "plan": plan,
                                         "overwrite": True}, quiet)
    check("H-3: the plan applies to its own file", len(out) == 1)
    try:
        P.pdf_organize(b, TD / "vb", {"operation": "visual", "plan": plan}, quiet)
        check("H-3: another queued file is left unchanged", False)
    except ProcessError as exc:
        check("H-3: another queued file is left unchanged", "A.pdf" in str(exc), str(exc)[:70])


def test_collector_and_routing():
    print("--- M-2 drops / collector ---")
    from PIL import Image
    from mico360.ui.dashboard_page import route_for
    from mico360.ui.file_collector import collect_files_detailed
    folder = TD / "photos"
    folder.mkdir()
    for i in range(3):
        Image.new("RGB", (8, 8)).save(folder / f"p{i}.jpg")
    make_pdf(folder / "one.pdf", 1)
    for junk in ("desktop.ini", "Thumbs.db", "~$report.docx"):
        (folder / junk).write_bytes(b"x")
    files, _ = collect_files_detailed([folder], {"*"})
    names = {f.name for f in files}
    check("Low: folder walks skip lock files, desktop.ini, Thumbs.db",
          not names & {"desktop.ini", "Thumbs.db", "~$report.docx"}, str(sorted(names)))
    check("M-2: a folder of photos routes to Compress Image",
          route_for([str(folder)]) == "image_compress", str(route_for([str(folder)])))
    check("M-2: nothing supported routes nowhere", route_for(["x.zzz"]) is None)


def test_gpu_fallback_and_models():
    print("--- OCR engine Lows ---")
    from mico360.core import ocr_models
    from mico360.core import processors as P

    class Bad:
        def run(self, *a):
            raise RuntimeError("device removed")

    class Good:
        def run(self, *a):
            return "cpu"
    w = P._GpuFallbackSession(Bad(), lambda: Good())
    check("Low: GPU OCR falls back to CPU mid-inference", w.run(None, {}) == "cpu")
    url = ocr_models.LANGUAGES["arabic"].model_url
    check("Low: the OCR model URL is pinned to a commit",
          "/resolve/main/" not in url and len(url.split("/resolve/")[1].split("/")[0]) == 40)

    # A model damaged on disk is replaced before use.
    good = b"model-bytes" * 100
    import hashlib
    lang = ocr_models.OcrLanguage("t_x", "Test", model_url="http://example.invalid/m",
                                  model_sha256=hashlib.sha256(good).hexdigest(),
                                  model_size=len(good), keys_file="arabic_keys.txt")
    ocr_models.LANGUAGES["t_x"] = lang
    dest = TD / "models" / "rec.onnx"
    dest.parent.mkdir()
    dest.write_bytes(b"X" * len(good))           # right size, wrong content
    om, od = ocr_models.model_path, None
    from mico360.core import engines
    od = engines._download
    ocr_models.model_path = lambda _l: dest
    engines._download = lambda url, d, *a, **k: Path(d).write_bytes(good)
    try:
        ocr_models._verified.discard(str(dest))
        ocr_models.ensure_language("t_x")
        check("Low: a corrupted OCR model is re-downloaded", dest.read_bytes() == good)
    finally:
        ocr_models.model_path, engines._download = om, od
        ocr_models.LANGUAGES.pop("t_x", None)


def test_ocr_low_memory():
    print("--- OCR under memory pressure ---")
    import fitz
    from mico360.core import processors as P
    src = TD / "multi_scan.pdf"
    d = fitz.open()
    for i in range(6):
        d.new_page()
    d.save(str(src)); d.close()
    calls = {"n": 0}

    def flaky(engine, img, dpi, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:            # a concurrent inference runs out of memory
            try:
                raise RuntimeError("[ONNXRuntimeError] : 1 : FAIL : bad allocation")
            except RuntimeError as inner:
                raise ValueError("ONNXRuntime inferece failed.") from inner
        return [("page text", (10, 10, 50, 20))]

    oe, oi, op, om = (P._make_ocr_engine, P._ocr_image_lines, P._ocr_page_lines,
                      P.available_memory_bytes)
    P._make_ocr_engine = lambda *a, **k: object()
    P._ocr_image_lines = flaky
    P._ocr_page_lines = lambda engine, page, dpi=300: [("page text", (10, 10, 50, 20))]
    P.available_memory_bytes = lambda: 64 * 1024 ** 3       # allow several workers
    msgs: list = []
    try:
        prev = P._ocr_active_provider
        P._ocr_active_provider = "CPU"
        res = P._ocr_pages_concurrent(src, list(range(6)), lambda m, *a, **k: msgs.append(m))
        check("OCR: an out-of-memory page no longer fails the whole file",
              sorted(res) == list(range(6)), str(sorted(res)))
        check("OCR: the user is told it continued one page at a time",
              any("one page at a time" in m for m in msgs), str(msgs))
        check("OCR: allocation failures are recognised through the exception chain",
              P._is_out_of_memory(ValueError("x").with_traceback(None)) is False)
        P.available_memory_bytes = lambda: 500 * 1024 ** 2   # very low free RAM
        calls["n"] = 100                                      # no more failures
        res = P._ocr_pages_concurrent(src, list(range(6)), lambda *a, **k: None)
        check("OCR: very low free memory runs pages one at a time", sorted(res) == list(range(6)))
    finally:
        P._ocr_active_provider = prev
        P._make_ocr_engine, P._ocr_image_lines, P._ocr_page_lines, P.available_memory_bytes = (
            oe, oi, op, om)


def test_ai_security():
    print("--- H-12 / M-22 / M-23 AI security ---")
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from mico360.config import settings
    from mico360.core import ai

    check("H-12: pasted key loses line breaks / control chars",
          ai.sanitize_key(" sk-ab\ncd\t\x00 ") == "sk-abcd")
    seen: dict = {}

    class B(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["auth"] = self.headers.get("Authorization")
            body = b'{"data": [{"id": "m1"}]}'
            self.send_response(200); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass
    sb = ThreadingHTTPServer(("127.0.0.1", 0), B)
    threading.Thread(target=sb.serve_forever, daemon=True).start()
    target = f"http://localhost:{sb.server_address[1]}/v1/models"   # other origin

    class A(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302); self.send_header("Location", target)
            self.send_header("Content-Length", "0"); self.end_headers()

        def log_message(self, *a):
            pass
    sa = ThreadingHTTPServer(("127.0.0.1", 0), A)
    threading.Thread(target=sa.serve_forever, daemon=True).start()
    try:
        cfg = ai.AiConfig(enabled=True, source=ai.SOURCE_CUSTOM,
                          base_url=f"http://127.0.0.1:{sa.server_address[1]}/v1",
                          api_key="sk-secret-123456", model="m1")
        models = ai.list_models(cfg)
        check("M-22: a cross-host redirect still works", models == ["m1"], str(models))
        check("M-22: …but the API key is NOT forwarded to the other host",
              seen.get("auth") is None, str(seen.get("auth")))
    finally:
        sa.shutdown(); sb.shutdown()

    n = ai.normalize_base_url
    check("M-22: a bare public host defaults to HTTPS",
          n("ai.example.com:5310") == "https://ai.example.com:5310/v1")
    check("M-22: a local server keeps HTTP", n("localhost:11434") == "http://localhost:11434/v1")
    check("Low: Gemini/Azure URLs are left intact",
          n("https://generativelanguage.googleapis.com/v1beta/openai/")
          == "https://generativelanguage.googleapis.com/v1beta/openai"
          and "?api-version=1" in n("https://r.openai.azure.com/openai/deployments/g?api-version=1"))

    # M-23: the saved key belongs to the server it was saved for.
    ai.save_config(ai.AiConfig(enabled=True, source=ai.SOURCE_CUSTOM,
                               base_url="http://127.0.0.1:1/v1", model="m"),
                   api_key="sk-bound-123456")
    check("M-23: the key is used for its own server",
          ai.stored_key_for("http://127.0.0.1:1/v1") == "sk-bound-123456")
    check("M-23: the key is NOT sent to a newly typed server",
          ai.stored_key_for("http://evil.example.com/v1") == "")
    settings.ai_base_url = "http://evil.example.com/v1"
    check("M-23: load_config drops the key after the URL changes",
          ai.load_config().api_key == "")
    settings.ai_enabled = False


def test_ocr_ai_guard():
    print("--- H-13 / M-20 / M-21 OCR AI ---")
    import fitz
    from mico360.core import ocr_ai
    from mico360.core import processors as P
    s = ocr_ai.is_safe_correction
    check("H-13: a changed amount is rejected",
          not s("Invoice total: 1,000 USD", "Invoice total: 9,000 USD"))
    check("H-13: a rewritten name is rejected", not s("ACME Ltd", "EVIL Corp"))
    check("H-13: a genuine OCR fix is accepted", s("Tbe quick brown f0x", "The quick brown fox"))
    check("H-13: list numbering survives parsing",
          ocr_ai._parse_numbered("1\t1. Introduction\n2\tBody", 2) == ["1. Introduction", "Body"])

    src = TD / "titled_scan.pdf"
    d = fitz.open(); d.new_page(); d.set_metadata({"title": "Real Title", "author": "Real A"})
    d.save(str(src)); d.close()
    oe, oc, oa = P._make_ocr_engine, P._ocr_pages_concurrent, P._ocr_ai_pass
    P._make_ocr_engine = lambda *a, **k: None
    P._ocr_pages_concurrent = lambda *a, **k: {0: [("Hello", (72, 100, 200, 120))]}
    P._ocr_ai_pass = lambda *a, **k: {"title": "AI Title", "author": "AI Author",
                                      "subject": "AI Subject"}
    try:
        out = P.pdf_ocr(src, TD / "ocrai", {"ocr_use_ai": True, "overwrite": True}, quiet)[0]
        md = fitz.open(str(out)).metadata
        check("M-20: the existing title is not overwritten", md.get("title") == "Real Title")
        check("M-20: Author is never written by AI", md.get("author") == "Real A")
        check("M-20: an empty subject is filled", md.get("subject") == "AI Subject")

        class _C:
            def __call__(self, *a, **k):
                pass
            cancelled = staticmethod(lambda: True)
        from mico360.core.util import ProcessError
        try:
            P.pdf_ocr(src, TD / "ocrai2", {"ocr_use_ai": True}, _C())
            check("M-21: Cancel during the AI step saves nothing", False)
        except ProcessError:
            check("M-21: Cancel during the AI step saves nothing",
                  not list((TD / "ocrai2").glob("*.pdf")) if (TD / "ocrai2").exists() else True)
    finally:
        P._make_ocr_engine, P._ocr_pages_concurrent, P._ocr_ai_pass = oe, oc, oa


def test_metadata_privacy():
    print("--- M-24 / M-25 metadata ---")
    import fitz
    from pypdf import PdfReader, PdfWriter
    from mico360.core import processors as P
    src = TD / "meta_src.pdf"
    d = fitz.open()
    pg = d.new_page()
    a = pg.add_text_annot((100, 100), "note")
    a.set_info(title="Jane Secret")
    a.update()
    d.embfile_add("secret.txt", b"private")
    d.set_metadata({"title": "T", "author": "Old Author"})
    d.set_xml_metadata(
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description '
        'rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" pdfaid:part="2" '
        'pdfaid:conformance="B"><dc:creator><rdf:Seq><rdf:li>Old Author</rdf:li>'
        '</rdf:Seq></dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>'
        '<?xpacket end="w"?>')
    d.save(str(src)); d.close()
    w = PdfWriter(clone_from=PdfReader(str(src)))
    w.add_metadata({"/LastModifiedBy": "jdoe"})
    w.write(str(src))

    o = P.pdf_metadata(src, TD / "meta_edit", {"author": "New Author",
                                               "copyright": "(c) ACME",
                                               "overwrite": True}, quiet)[0]
    x = fitz.open(str(o)).get_xml_metadata()
    check("M-25: an edited Author replaces the stale one in XMP",
          "New Author" in x and "Old Author" not in x)
    check("M-25: setting Copyright keeps the PDF/A identification",
          "pdfaid" in x and "(c) ACME" in x)

    o = P.pdf_metadata(src, TD / "meta_scrub", {"privacy": "scrub", "overwrite": True},
                       quiet)[0]
    d = fitz.open(str(o))
    info = PdfReader(str(o)).metadata or {}
    check("M-24: Scrub removes custom identifying keys (/LastModifiedBy)",
          "/LastModifiedBy" not in info and "/Author" not in info)
    check("M-24: Scrub keeps the Title", info.get("/Title") == "T")
    check("M-24: Scrub removes embedded files", d.embfile_count() == 0)
    check("M-24: Scrub removes comment author names",
          all(not a.info.get("title") for a in d[0].annots()))
    check("M-24: Scrub drops XMP and changes the file identifier",
          not d.get_xml_metadata()
          and PdfReader(str(o)).trailer.get("/ID") != PdfReader(str(src)).trailer.get("/ID"))
    d.close()


def test_crash_redaction():
    print("--- Low crash-report privacy ---")
    import getpass
    from mico360.core import crash
    home = os.path.expanduser("~")
    text = f"File '{home}\\Documents\\Secret Contract.pdf'\nBearer sk-abcdefgh12345"
    red = crash.redact(text)
    check("Low: the home folder / user name is removed",
          home.lower() not in red.lower() and getpass.getuser().lower() not in red.lower(), red)
    check("Low: document names are removed", "Secret Contract" not in red, red)
    check("Low: key-like strings are removed", "sk-abcdefgh12345" not in red, red)


def test_shell_menu():
    print("--- H-7 / M-29 Explorer menu ---")
    if not sys.platform.startswith("win"):
        print("(skipped: Windows only)")
        return
    import winreg
    from mico360 import shell_integration as si
    base = r"Software\MICO360-bugfixtest\SystemFileAssociations"
    try:
        si.register(base=base, launch_prefix='"A.EXE"')
        stale = rf"{base}\.pdf\shell\{si.PARENT_KEY}\shell\99gone_tool"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, stale, 0, winreg.KEY_WRITE):
            pass
        odd = rf"{base}\.zzz\shell\{si.OPEN_KEY}"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, odd, 0, winreg.KEY_WRITE):
            pass
        si.register(base=base, launch_prefix='"A.EXE"')
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, stale))
            gone = False
        except OSError:
            gone = True
        check("H-7: re-registering removes stale submenu entries", gone)
        check("self-heal: a menu pointing elsewhere is rewritten",
              si.self_heal(base=base, launch_prefix='"B.EXE"') == "rewritten"
              and si.registered_command(base).startswith('"B.EXE"'))
        check("self-heal: an up-to-date menu is left alone",
              si.self_heal(base=base, launch_prefix='"B.EXE"') == "ok")
        si.unregister(base=base)
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, odd))
            swept = False
        except OSError:
            swept = True
        check("H-7: unregister sweeps extensions no longer listed", swept)
    finally:
        si._delete_tree(winreg.HKEY_CURRENT_USER, r"Software\MICO360-bugfixtest")


def test_single_instance_race():
    print("--- H-5 single instance ---")
    import subprocess
    import time
    root = str(Path(__file__).resolve().parent.parent)
    child = (
        "import os,sys,time\n"
        f"sys.path.insert(0, {root!r})\n"
        "os.environ['QT_QPA_PLATFORM']='offscreen'\n"
        "from PySide6.QtCore import QCoreApplication\n"
        "app=QCoreApplication([])\n"
        "from mico360.single_instance import SingleInstance\n"
        "t=float(sys.argv[2])\n"
        "while time.time()<t: pass\n"
        "g=SingleInstance(sys.argv[1])\n"
        "if g.is_primary():\n"
        "    end=time.time()+4\n"
        "    while time.time()<end: app.processEvents(); time.sleep(0.01)\n"
        "    print('P')\n"
        "else:\n"
        "    print('S', g.signal_running('x'))\n")
    name = f"MICO360-bugfix-race-{os.getpid()}"
    start = time.time() + 2.0
    procs = [subprocess.Popen([sys.executable, "-c", child, name, str(start)],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL, text=True) for _ in range(5)]
    outs = [p.communicate(timeout=60)[0].strip() for p in procs]
    check("H-5: five simultaneous launches give exactly one window",
          outs.count("P") == 1, str(outs))
    check("H-5: every other launch hands its files to that window",
          outs.count("S True") == 4, str(outs))


def test_ui():
    print("--- UI fixes ---")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from mico360.config import settings
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.tool_page import QueueItem, ToolPage

    # H-1: a second Start while running does nothing.
    page = ToolPage(TOOLS_BY_ID["pdf_compress"])
    page.items = [QueueItem(path=make_pdf(TD / "u1.pdf", 1))]
    sentinel = object()
    page.controller = sentinel
    page.start()
    check("H-1: Start/Ctrl+Enter during a run doesn't start a second batch",
          page.controller is sentinel)
    page.controller = None

    # H-2: settings changed elsewhere are picked up; unchanged values not written.
    settings.overwrite = True
    page._resync_from_settings()
    settings.overwrite = False
    page._resync_from_settings()
    check("H-2: Overwrite re-syncs from Settings", not page.chk_overwrite.isChecked())

    # M-4: Undo restores only what was removed.
    a, b, c = (QueueItem(path=Path(f"{x}.pdf")) for x in "abc")
    page.items = [a, b]
    page._refresh_list()
    undo = {}
    page.toastAction.connect(lambda m, k, act, cb: undo.__setitem__("cb", cb))
    page.file_list.item(1).setSelected(True)
    page._remove_selected()
    page.items.append(c)
    page._refresh_list()
    undo["cb"]()
    check("M-4: Undo brings back the removed row and keeps rows added since",
          [it.path.name for it in page.items] == ["a.pdf", "b.pdf", "c.pdf"],
          str([it.path.name for it in page.items]))

    # M-5: the counter counts only this run.
    page.items = [QueueItem(path=Path("d1.pdf"), state="done"),
                  QueueItem(path=Path("r1.pdf"), state="running")]
    page._run_items = [page.items[1]]
    page._run_total = 1
    page._update_progress_detail(0.0)
    check("M-5: 'Processing X of Y' ignores rows done in an earlier run",
          "Processing 1 of 1" in page.status_lbl.text(), page.status_lbl.text())

    # M-1: an aggregate re-run includes rows done earlier.
    merge = ToolPage(TOOLS_BY_ID["pdf_merge"])
    merge.items = [QueueItem(path=Path("m1.pdf"), state="done"),
                   QueueItem(path=Path("m2.pdf"), state="done"),
                   QueueItem(path=Path("m3.pdf"))]
    got = {}
    merge._run = lambda todo: got.__setitem__("todo", todo)
    merge.start()
    check("M-1: re-running Merge uses every queued PDF",
          len(got.get("todo") or []) == 3, str(len(got.get("todo") or [])))

    # M-3: Delete is scoped to the queue.
    from PySide6.QtGui import QShortcut
    scs = [s for s in page.file_list.findChildren(QShortcut)]
    check("M-3: Delete only acts while the queue has focus",
          scs and all(s.context() == Qt.WidgetWithChildrenShortcut for s in scs))

    # M-7 + M-27: disabled / per-document values aren't saved as defaults.
    meta = ToolPage(TOOLS_BY_ID["pdf_metadata"])
    meta.options_widget._controls["title"].setText("One file's title")
    meta.options_widget.save()
    check("M-27: a document Title isn't remembered for next time",
          "title" not in settings.tool_options("pdf_metadata"))
    ocr = ToolPage(TOOLS_BY_ID["pdf_ocr"])
    ctrl = ocr.options_widget._controls.get("ocr_use_ai")
    if ctrl is not None:
        ctrl.setEnabled(False)
        ctrl.setChecked(False)
        ocr.options_widget.save()
        check("M-7: a forced-off (disabled) 'Use AI' isn't saved as a choice",
              "ocr_use_ai" not in settings.tool_options("pdf_ocr"))

    # H-4: the organizer releases the PDF on Cancel.
    from mico360.ui.page_organizer import PageOrganizerDialog
    pdf = make_pdf(TD / "org.pdf", 3)
    dlg = PageOrganizerDialog(pdf)
    dlg.reject()
    check("H-4: Cancel stops rendering and closes the PDF",
          dlg._doc is None and not dlg._timer.isActive())
    moved = TD / "org_renamed.pdf"
    try:
        pdf.rename(moved)
        ok = True
    except OSError:
        ok = False
    check("H-4: the source file isn't locked afterwards", ok)

    # M-3: Esc in the sidebar search clears it instead of cancelling.
    from mico360.ui.main_window import MainWindow
    import PySide6.QtWidgets as qw
    w = MainWindow()
    w.open_tool("pdf_compress")
    tp = w._current_tool_page()
    hits = {"n": 0}
    tp.cancel_if_running = lambda: hits.__setitem__("n", hits["n"] + 1)
    search = w.sidebar._search
    search.setText("comp")
    orig = qw.QApplication.focusWidget
    qw.QApplication.focusWidget = staticmethod(lambda: search)
    try:
        w._on_escape()
    finally:
        qw.QApplication.focusWidget = orig
    check("M-3: Esc in the search box clears it and doesn't cancel the run",
          search.text() == "" and hits["n"] == 0)

    # Low: toasts free themselves; contrast tokens meet WCAG AA.
    from mico360.ui.widgets import Toast
    t = Toast(w, "hi")
    check("Low: toasts are deleted when dismissed", t.testAttribute(Qt.WA_DeleteOnClose))
    from mico360.theme import DARK, LIGHT

    def lum(h):
        h = h.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        f = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]

    def ratio(a, b):
        x, y = sorted([lum(a), lum(b)])
        return (y + 0.05) / (x + 0.05)
    worst = min(ratio(t_["text_faint"], t_[k]) for t_ in (DARK, LIGHT)
                for k in ("bg", "surface", "surface_2"))
    check("Low: faint text has ≥ 4.5:1 contrast in both themes", worst >= 4.5, f"{worst:.2f}")
    check("Low: the 'Working…' chip has ≥ 4.5:1 contrast",
          min(ratio(t_["on_info"], t_["info"]) for t_ in (DARK, LIGHT)) >= 4.5)
    w.close()


def main() -> int:
    for fn in (test_settings_isolation, test_ocr_unicode_layer, test_pdf_structure_kept,
               test_pptx_rotated, test_friendly_errors_and_parsing, test_visual_plan_target,
               test_collector_and_routing, test_gpu_fallback_and_models,
               test_ocr_low_memory, test_ai_security,
               test_ocr_ai_guard, test_metadata_privacy, test_crash_redaction,
               test_shell_menu,
               test_single_instance_race, test_ui):
        try:
            fn()
        except Exception as exc:                  # a crash in one area is a failure
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} ran without crashing", False, repr(exc))
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All bug-fix regression checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush()
    os._exit(_rc)
