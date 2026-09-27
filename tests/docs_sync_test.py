"""The user-facing text stays correct: update notes, Help, Terms and Privacy.

* build/RELEASE_NOTES.md (the GitHub release body = what the in-app update
  dialog shows) is for the current version only, and every bullet comes out
  whole and in the right section — including in app versions that are already
  installed, whose notes parser keeps only the FIRST line of a bullet.
* Help covers every tool, every Settings section and the key features.
* Terms & Privacy carry a real "Last updated" date and the required disclosures.

Run:  python tests/docs_sync_test.py   (or via tests/run_suite.py)
"""
from __future__ import annotations

import datetime
import html
import os
import re
import sys
import tempfile
from pathlib import Path

if not os.environ.get("MICO360_SETTINGS_FILE"):
    os.environ["MICO360_SETTINGS_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="mico360_docs_"), "DocToolkit.ini")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


# Section headers the update dialog understands (and what each maps to).
SECTIONS = {"New features": "features", "Bugs fixed": "fixes",
            "Security improvements": "security", "Improvements": "other"}
FOOTER = "_Windows: the installer updates in place"


def plain(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    return re.sub(r"[*_`]", "", s).strip()


def test_release_notes() -> None:
    from mico360 import __version__
    from mico360.updater import categorize_notes
    notes = (ROOT / "build" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    lines = notes.splitlines()
    heads = [ln for ln in lines if ln.startswith("## ")]
    check("notes: exactly one version section, for the current version",
          heads == [f"## MICO360 Doc Toolkit v{__version__}"], str(heads))
    check("notes: no older releases or separators appended",
          not any(ln.strip() in ("---", "***") or ln.startswith("### ") for ln in lines))

    # Every bullet must be ONE line: installed apps drop continuation lines.
    wrapped = [n for n, ln in enumerate(lines, 1)
               if ln[:1] in (" ", "\t") and ln.strip()]
    check("notes: no wrapped (continuation) lines — each bullet is one line",
          not wrapped, f"lines {wrapped[:8]}")

    # Every bullet sits under a known section header.
    current, placed, stray, unknown = None, [], [], []
    for ln in lines:
        s = ln.strip()
        if s.startswith("**") and s.rstrip(":").endswith("**") and not s.startswith("- "):
            name = s.strip("*").rstrip(":").strip()
            current = name if name in SECTIONS else None
            if current is None and not name.endswith("."):   # the one-line summary is allowed
                unknown.append(name)
            continue
        m = re.match(r"^- (.*)$", ln)
        if m:
            (placed if current else stray).append((current, plain(m.group(1))))
    check("notes: only the standard section headers are used",
          not unknown, f"unknown: {unknown} — use one of {list(SECTIONS)}")
    check("notes: every bullet is under a section header", not stray and placed,
          f"stray: {[t for _, t in stray][:3]}")

    got = categorize_notes(notes)
    for sec, text in placed:
        bucket = SECTIONS[sec]
        check(f"notes: shown whole under '{sec}': {text[:50]}…", text in got[bucket],
              f"dialog has: {got[bucket]}")
    total = sum(len(v) for v in got.values())
    check("notes: the dialog shows exactly the bullets in the file",
          total == len(placed), f"{total} shown vs {len(placed)} written")
    check("notes: end with the install/update footer", FOOTER in notes)


def help_text() -> str:
    src = (ROOT / "mico360" / "ui" / "help_page.py").read_text(encoding="utf-8")
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", src)).split()).lower()


def test_help() -> None:
    from mico360.core.tools import TOOLS
    text = help_text()
    missing = [t.name for t in TOOLS if t.name.lower() not in text]
    check("help: every tool is described", not missing, str(missing))
    sp = (ROOT / "mico360" / "ui" / "settings_page.py").read_text(encoding="utf-8")
    sections = re.findall(r'section_label\("([^"]+)"\)', sp)
    miss_sec = [s for s in sections if html.unescape(s).lower() not in text]
    check("help: every Settings section is covered", not miss_sec, str(miss_sec))
    # Features that must stay documented (add new user-visible features here).
    features = ["redo ocr on pages that already have text", "use ai", "visual organizer",
                "run them all again", "retry", "undo", "right-click", "recognition quality",
                "privacy", "scrub", "save beside", "watermark"]
    miss_f = [f for f in features if f not in text]
    check("help: key features are documented", not miss_f, str(miss_f))
    # Every tool option's hint is shown in the app; Help must not describe options
    # that no longer exist (spot-check the OCR ones by their real labels).
    from mico360.core.tools import TOOLS_BY_ID
    ocr_labels = [o.label for o in TOOLS_BY_ID["pdf_ocr"].options]
    check("help: the OCR tool's option labels match the app",
          all(any(w in text for w in (lab.lower(), lab.lower().split(" (")[0]))
              for lab in ocr_labels if lab != "Use AI to clean up text & fill title/subject"),
          str(ocr_labels))


def test_legal() -> None:
    from mico360 import legal
    try:
        d = datetime.datetime.strptime(legal.LEGAL_UPDATED, "%d %B %Y").date()
        ok = d <= datetime.date.today() + datetime.timedelta(days=1)
    except ValueError:
        d, ok = None, False
    check("legal: LEGAL_UPDATED is a real date, not in the future", ok, legal.LEGAL_UPDATED)
    terms, privacy = legal.terms_and_conditions(), legal.privacy_policy()
    check("legal: Terms and Privacy both show the Last updated date",
          f"Last updated {legal.LEGAL_UPDATED}" in terms
          and f"Last updated {legal.LEGAL_UPDATED}" in privacy)
    check("legal: Privacy discloses what the AI features send (every page for OCR)",
          "every page" in privacy and "short excerpt" in privacy)
    check("legal: Privacy lists every kind of network activity",
          all(k in privacy for k in ("Updates", "Optional engines", "AI features", "Error reports")))
    check("legal: Terms warn that automated results (OCR/AI) can contain mistakes",
          "can contain mistakes" in terms)
    from mico360 import __version__
    check("legal: pages show the current version",
          f"v{__version__}" in terms and f"v{__version__}" in privacy)


def main() -> int:
    test_release_notes()
    test_help()
    test_legal()
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Docs are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
