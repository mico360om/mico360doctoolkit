"""Optional AI clean-up for OCR: the line-corrector (ocr_ai.cleanup_lines), the
pdf_ocr AI pass (text correction + metadata embedding, all mocked so no real OCR
engine or network is needed), the tool option, and the UI gating that defaults
the toggle on only when AI is configured.

Run:  python tests/ocr_ai_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

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


def _image_only_pdf(path: Path) -> None:
    """A one-page PDF with no extractable text (a drawn box) → OCR would run."""
    import fitz
    d = fitz.open()
    pg = d.new_page()
    pg.draw_rect(fitz.Rect(60, 60, 500, 760), color=(0, 0, 0))
    d.save(str(path))
    d.close()


class _Rep:
    def __init__(self):
        self.msgs = []

    def __call__(self, m):
        self.msgs.append(m)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from mico360.core import ai as ai_core
    from mico360.core import ai_metadata, ocr_ai, processors
    from mico360.core.tools import TOOLS_BY_ID

    usable_cfg = ai_core.AiConfig(enabled=True, source=ai_core.SOURCE_CUSTOM,
                                  base_url="http://127.0.0.1:9/v1", api_key="k",
                                  model="m")
    off_cfg = ai_core.AiConfig(enabled=False)

    # ================= cleanup_lines =================
    print("--- cleanup_lines ---")
    orig_chat = ocr_ai.chat

    def _fix_chat(cfg, msgs, **k):
        # Echo back each "i<TAB>text" line with a couple of fixes applied.
        out = []
        for raw in msgs[-1]["content"].splitlines():
            num, _, text = raw.partition("\t")
            text = text.replace("teh", "the").replace("0CR", "OCR")
            out.append(f"{num}\t{text}")
        return "\n".join(out)
    ocr_ai.chat = _fix_chat
    try:
        got = ocr_ai.cleanup_lines(usable_cfg, ["teh cat", "0CR text"])
        check("corrects lines, same length", got == ["the cat", "OCR text"], str(got))
        check("empty input returns empty", ocr_ai.cleanup_lines(usable_cfg, []) == [])
    finally:
        ocr_ai.chat = orig_chat

    # count mismatch → keep raw
    ocr_ai.chat = lambda cfg, msgs, **k: "1\tonly one line back"
    try:
        raw = ["aaa", "bbb", "ccc"]
        check("shape mismatch keeps raw lines",
              ocr_ai.cleanup_lines(usable_cfg, raw) == raw)
    finally:
        ocr_ai.chat = orig_chat

    # exception → keep raw
    def _boom(*a, **k):
        raise RuntimeError("network down")
    ocr_ai.chat = _boom
    try:
        raw = ["x", "y"]
        check("AI error keeps raw lines (never raises)",
              ocr_ai.cleanup_lines(usable_cfg, raw) == raw)
    finally:
        ocr_ai.chat = orig_chat

    # never blank out a non-empty line
    ocr_ai.chat = lambda cfg, msgs, **k: "1\t\n2\tkept"
    try:
        check("won't blank a non-empty line (and won't take a rewrite)",
              ocr_ai.cleanup_lines(usable_cfg, ["keepme", "two"]) == ["keepme", "two"])
    finally:
        ocr_ai.chat = orig_chat

    # H-13: only plausible OCR fixes are accepted — never a changed number or
    # a rewritten phrase (e.g. steered by text in the scan).
    ocr_ai.chat = lambda cfg, msgs, **k: ("1\tInvoice total: 9,000 USD\n"
                                           "2\tEVIL Corp\n3\tThe quick brown fox\n"
                                           "4\tDated 2026-09-26")
    try:
        raw = ["Invoice total: 1,000 USD", "ACME Ltd", "Tbe quick brown f0x",
               "Dated 2O26-09-26"]
        got = ocr_ai.cleanup_lines(usable_cfg, raw)
        check("a changed amount is rejected (raw kept)", got[0] == raw[0], got[0])
        check("a rewritten name is rejected (raw kept)", got[1] == raw[1], got[1])
        check("a genuine OCR fix is accepted", got[2] == "The quick brown fox", got[2])
        check("an O/0 misread inside a date is fixed", got[3] == "Dated 2026-09-26", got[3])
    finally:
        ocr_ai.chat = orig_chat

    # list numbering in the text itself survives parsing
    ocr_ai.chat = lambda cfg, msgs, **k: "1\t1. Introduction\n2\t2. Scope"
    try:
        check("real list numbering is kept ('1. Introduction')",
              ocr_ai.cleanup_lines(usable_cfg, ["1. Introduction", "2. Scope"])
              == ["1. Introduction", "2. Scope"])
    finally:
        ocr_ai.chat = orig_chat

    # cancel → remaining lines left raw (big input, cancel immediately)
    ocr_ai.chat = lambda cfg, msgs, **k: "\n".join(
        f"{i+1}\tX" for i in range(ocr_ai.MAX_LINES_PER_CALL))
    try:
        big = [f"line{i}" for i in range(ocr_ai.MAX_LINES_PER_CALL * 2)]
        out = ocr_ai.cleanup_lines(usable_cfg, big, is_cancelled=lambda: True)
        check("cancel keeps everything raw", out == big)
    finally:
        ocr_ai.chat = orig_chat

    # ================= tool option =================
    print("--- tool option ---")
    ocr = TOOLS_BY_ID["pdf_ocr"]
    opt = next((o for o in ocr.options if o.key == "ocr_use_ai"), None)
    check("pdf_ocr has an ocr_use_ai bool option",
          opt is not None and opt.kind == "bool" and opt.default is False)

    # ================= pdf_ocr AI pass (mocked) =================
    print("--- pdf_ocr AI pass ---")
    td = Path(tempfile.mkdtemp(prefix="mico_ocrai_"))
    src = td / "scan.pdf"
    _image_only_pdf(src)
    canned = {0: [("teh quick", (72.0, 700.0, 260.0, 720.0)),
                  ("brovvn fox", (72.0, 676.0, 260.0, 696.0))]}

    o_engine, o_conc = processors._make_ocr_engine, processors._ocr_pages_concurrent
    o_load = ai_core.load_config
    o_clean, o_meta = ocr_ai.cleanup_lines, ai_metadata.suggest_metadata
    processors._make_ocr_engine = lambda *a, **k: None
    processors._ocr_pages_concurrent = lambda *a, **k: {0: list(canned[0])}

    def _run(use_ai, cfg):
        ai_core.load_config = lambda: cfg
        rep = _Rep()
        outs = processors.pdf_ocr(src, td / f"out_{use_ai}_{cfg.enabled}",
                                  {"ocr_lang": "latin", "quality": "fast",
                                   "ocr_use_ai": use_ai, "overwrite": True}, rep)
        return outs[0], rep

    try:
        # AI on + usable → corrected text + metadata embedded
        ocr_ai.cleanup_lines = lambda cfg, lines, is_cancelled=None, budget=None: \
            [s.replace("teh", "the").replace("brovvn", "brown") for s in lines]
        ai_metadata.suggest_metadata = lambda path, cfg, excerpt=None, cancel=None: \
            {"title": "The Quick Brown Fox", "subject": "pangram"}
        import fitz
        out, rep = _run(True, usable_cfg)
        txt = fitz.open(str(out))[0].get_text()
        meta = fitz.open(str(out)).metadata
        check("AI cleanup reaches the searchable text layer",
              "the quick" in txt and "brown fox" in txt and "teh" not in txt, repr(txt[:40]))
        check("AI metadata written to the output PDF",
              meta.get("title") == "The Quick Brown Fox" and meta.get("subject") == "pangram",
              str({k: meta.get(k) for k in ('title', 'subject')}))

        # AI on but not configured → skipped cleanly, raw text, no title
        out, rep = _run(True, off_cfg)
        txt = fitz.open(str(out))[0].get_text()
        check("unconfigured AI is skipped (raw text kept)", "teh quick" in txt)
        check("skip reason is reported to the user",
              any("skipped" in m.lower() for m in rep.msgs), str(rep.msgs[-2:]))
        check("no metadata written when AI unavailable",
              not fitz.open(str(out)).metadata.get("title"))

        # AI off → cleanup never invoked
        called = {"n": 0}
        ocr_ai.cleanup_lines = lambda *a, **k: called.__setitem__("n", called["n"] + 1) or a[1]
        out, _ = _run(False, usable_cfg)
        check("AI off → cleanup not called at all", called["n"] == 0)
        check("AI off → raw text in output", "teh quick" in fitz.open(str(out))[0].get_text())
    finally:
        processors._make_ocr_engine, processors._ocr_pages_concurrent = o_engine, o_conc
        ai_core.load_config = o_load
        ocr_ai.cleanup_lines, ai_metadata.suggest_metadata = o_clean, o_meta

    # ================= UI gating =================
    print("--- UI gating ---")
    from PySide6.QtWidgets import QCheckBox
    from mico360.ui.tool_page import ToolPage
    from mico360.config import settings
    settings.set_tool_options("pdf_ocr", {})       # no saved preference
    saved_load = ai_core.load_config
    try:
        ai_core.load_config = lambda: off_cfg      # AI not configured
        tp = ToolPage(TOOLS_BY_ID["pdf_ocr"])
        chk = tp.options_widget._controls.get("ocr_use_ai")
        check("checkbox present on OCR tool", isinstance(chk, QCheckBox))
        check("AI not configured → toggle off & disabled",
              chk is not None and not chk.isChecked() and not chk.isEnabled())

        ai_core.load_config = lambda: usable_cfg   # AI configured
        settings.set_tool_options("pdf_ocr", {})
        tp2 = ToolPage(TOOLS_BY_ID["pdf_ocr"])
        chk2 = tp2.options_widget._controls.get("ocr_use_ai")
        check("AI configured → toggle defaults on & enabled",
              chk2 is not None and chk2.isChecked() and chk2.isEnabled())

        settings.set_tool_options("pdf_ocr", {"ocr_use_ai": False})   # user chose off
        tp3 = ToolPage(TOOLS_BY_ID["pdf_ocr"])
        chk3 = tp3.options_widget._controls.get("ocr_use_ai")
        check("a saved 'off' choice is respected even when AI is configured",
              chk3 is not None and not chk3.isChecked())
    finally:
        ai_core.load_config = saved_load
        settings.set_tool_options("pdf_ocr", {})

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("OCR AI: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc if isinstance(_rc, int) else 0)
