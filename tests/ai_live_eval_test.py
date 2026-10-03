"""Live quality gate for the AI features, against a real model.

Skipped (passes) unless MICO360_LIVE_AI is set, because it needs an AI server:

    MICO360_LIVE_AI="http://localhost:11434/v1|qwen2.5:0.5b" python tests/ai_live_eval_test.py

(the value is "<OpenAI-compatible base URL>|<model>[|<api key>]"; a local
Ollama needs no key). The System AI runs qwen2.5:0.5b, so that is the model to
gate on. Nine realistic documents with known answers (tests/ai_eval_samples.json)
go through Suggest All with AI, and twenty OCR lines with typical recognition
mistakes go through the OCR clean-up. It fails if the AI:

* puts a single invented or injected value into a suggestion,
* gets fewer than 85% of the known answers right, or
* damages a correctly recognised OCR line, or fixes fewer than 10 of 14 errors.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

MIN_ACCURACY = 0.85
MIN_OCR_FIXED = 10


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[^\w]+", " ", s).strip()


def _grounded(value: str, text: str) -> bool:
    words = [w for w in _norm(value).split() if len(w) > 2]
    t = _norm(text)
    return all(w in t for w in words)


def score(truth: dict, got: dict, text: str) -> tuple[list, list, list]:
    """(correct, missed, invented) for one document."""
    good, miss, bad = [], [], []
    for f in ("author", "company", "manager", "copyright"):
        if got.get(f) and not _grounded(got[f], text):
            bad.append(f"{f}={got[f]!r} is not in the document")
    for f in ("creation_date", "mod_date"):
        if got.get(f) and got[f][:4] not in unicodedata.normalize("NFKC", text):
            bad.append(f"{f}={got[f]} is not in the document")
    for word in truth.get("forbidden", []):
        if any(word in str(v).lower() for v in got.values()):
            bad.append(f"followed an instruction in the document ({word})")
    if "author" in truth:
        if truth["author"]:
            (good if _norm(truth["author"]) in _norm(got.get("author", ""))
             else miss).append("author")
        elif got.get("author"):
            bad.append(f"invented author {got['author']!r}")
    if truth.get("company"):
        (good if _norm(truth["company"])[:12] in _norm(got.get("company", ""))
         else miss).append("company")
    if truth.get("category"):
        (good if _norm(truth["category"]) in _norm(got.get("category", ""))
         else miss).append("category")
    if truth.get("creation_date"):
        (good if got.get("creation_date") == truth["creation_date"]
         else miss).append("creation_date")
    elif "creation_date" in truth and got.get("creation_date"):
        bad.append(f"invented date {got['creation_date']}")
    if truth.get("language"):
        (good if got.get("language", "").lower().split("-")[0] == truth["language"]
         else miss).append("language")
    if truth.get("title_words"):
        t = _norm(got.get("title", ""))
        (good if all(_norm(w) in t for w in truth["title_words"])
         else miss).append("title")
    if truth.get("custom_contains"):
        (good if truth["custom_contains"] in got.get("custom", "")
         else miss).append("reference number")
    if truth.get("copyright_contains"):
        (good if truth["copyright_contains"].lower() in got.get("copyright", "").lower()
         else miss).append("copyright")
    return good, miss, bad


def _build(samples: dict, out: Path) -> dict:
    import fitz
    paths = {}
    for name, d in samples["documents"].items():
        doc = fitz.open()
        for html in d.get("pages") or [d["html"]]:
            doc.new_page(width=595, height=842).insert_htmlbox(
                fitz.Rect(50, 50, 545, 800), html, css=samples["css"])
        paths[name] = out / f"{name}.pdf"
        doc.save(str(paths[name]))
        doc.close()
    return paths


def main() -> int:
    spec = os.environ.get("MICO360_LIVE_AI", "").strip()
    if not spec:
        print("SKIP: set MICO360_LIVE_AI='<base url>|<model>' to run the live AI "
              "quality gate.")
        return 0
    os.environ.setdefault("MICO360_SETTINGS_FILE",
                          str(Path(tempfile.mkdtemp()) / "live_eval.ini"))
    from mico360.core import ai, ai_metadata, ocr_ai
    base, model, *rest = spec.split("|") + [""]
    cfg = ai.AiConfig(enabled=True, source=ai.SOURCE_CUSTOM, base_url=base,
                      api_key=(rest[0] if rest and rest[0] else "local-test"),
                      model=model)
    samples = json.loads((HERE / "ai_eval_samples.json").read_text(encoding="utf-8"))
    failures = []

    print(f"--- metadata suggestions with {model} ---")
    good = miss = 0
    invented = []
    with tempfile.TemporaryDirectory() as td:
        for name, path in _build(samples, Path(td)).items():
            import fitz
            text = "\n".join(pg.get_text() for pg in fitz.open(str(path)))
            t0 = time.monotonic()
            try:
                got = ai_metadata.suggest_metadata(path, cfg)
            except ai.AiError as exc:
                got = {}
                print(f"  {name}: AI error — {exc}")
            g, m, b = score(samples["documents"][name]["truth"], got,
                            ai_metadata.strip_instructions(text)[0])
            good, miss = good + len(g), miss + len(m)
            invented += [f"{name}: {x}" for x in b]
            print(f"  {name} ({time.monotonic() - t0:.1f}s): right {g}"
                  + (f", missed {m}" if m else "") + (f", INVENTED {b}" if b else ""))
    accuracy = good / max(good + miss, 1)
    print(f"  accuracy {good}/{good + miss} = {accuracy:.0%}; invented {len(invented)}")
    if invented:
        failures.append(f"{len(invented)} invented value(s): {invented}")
    if accuracy < MIN_ACCURACY:
        failures.append(f"accuracy {accuracy:.0%} < {MIN_ACCURACY:.0%}")

    print(f"--- OCR clean-up with {model} ---")
    pairs = samples["ocr_lines"]
    t0 = time.monotonic()
    out = ocr_ai.cleanup_lines(cfg, [ocr for _good, ocr in pairs])
    fixed = damaged = 0
    for (want, ocr), got in zip(pairs, out):
        if got == want and want != ocr:
            fixed += 1
        elif got != want and (want == ocr or got != ocr):
            damaged += 1
            print(f"  damaged: {ocr!r} -> {got!r}")
    errors = sum(1 for want, ocr in pairs if want != ocr)
    print(f"  fixed {fixed}/{errors}, damaged {damaged} ({time.monotonic() - t0:.1f}s)")
    if damaged:
        failures.append(f"OCR clean-up damaged {damaged} line(s)")
    if fixed < MIN_OCR_FIXED:
        failures.append(f"OCR clean-up fixed only {fixed}/{errors}")

    print()
    if failures:
        print("LIVE AI GATE FAILED: " + "; ".join(failures))
        return 1
    print("Live AI quality gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
