"""Help guides, Terms, Privacy, and the per-user capability/permission summary.

Verifies the docs cover every module (AI incl. cancel/retry, the Explorer
right-click menu, keyboard shortcuts, usability features), that the legal
sections are well-formed, and that the "Your setup & permissions" summary
reflects each user's actual access level.

Run:  python tests/help_legal_test.py
"""
from __future__ import annotations

import os
import re
import sys
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


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from mico360 import legal, capabilities as cap
    from mico360.config import settings
    from mico360.core import ai as ai_core

    # ================= legal docs =================================
    print("--- terms & privacy ---")
    terms = legal.terms_and_conditions()
    priv = legal.privacy_policy()
    about = legal.about_us()
    for name, doc in (("terms", terms), ("privacy", priv), ("about", about)):
        nums = [int(m) for m in re.findall(r"<h3>(\d+)\.", doc)]
        if nums:
            check(f"{name} sections are numbered sequentially",
                  nums == list(range(1, len(nums) + 1)), str(nums))
        check(f"{name} has the contact email", "info@mico360.com" in doc)

    check("Terms cover AI providers (System AI / your own API)",
          "AI features" in terms and "System AI" in terms
          and "your own" in terms.lower())
    check("Terms cover the optional Windows Explorer integration",
          "right-click" in terms.lower() and "registry" in terms.lower())
    # Collapse whitespace so line-wrapped HTML sentences still match as phrases.
    priv_n = re.sub(r"\s+", " ", priv.lower())
    check("Privacy covers the Explorer registry integration",
          "registry" in priv_n and "removed when you turn it off" in priv_n)
    check("Privacy documents AI: excerpt only + encrypted key + off by default",
          "off by default" in priv_n and "excerpt" in priv_n
          and "encrypted" in priv_n)
    check("Privacy has an 'access level' section",
          "access level" in priv.lower()
          and "your setup" in priv.lower())
    check("About Us highlights AI and the right-click menu",
          "AI" in about and "right-click" in about.lower())

    # ================= help guide coverage ========================
    print("--- help guide coverage ---")
    from mico360.ui import help_page
    h = help_page._HELP_HTML
    coverage = {
        "Explorer right-click menu": "MICO360 Toolkit" in h and "right-click" in h.lower(),
        "keyboard shortcuts (Ctrl+K/O/Enter/Esc)":
            all(k in h for k in ("Ctrl+K", "Ctrl+O", "Ctrl+Enter", "Esc")),
        "Ctrl+1..9 pinned tools": "Ctrl+1" in h,
        "F1 help": "F1" in h,
        "AI Suggest All + Auto apply + Cancel":
            "Suggest All with AI" in h and "Auto apply" in h and "Cancel" in h,
        "AI model dropdown + Test connection":
            "Test connection" in h and "Model" in h,
        "Retry N failed": "Retry" in h and "failed" in h,
        "Undo remove/clear": "Undo" in h,
        "running window title": "window title" in h.lower(),
        "search-everywhere (password/dpi)": "password" in h.lower() and "dpi" in h.lower(),
        "light is the default theme": "the default" in h.lower(),
    }
    for label, ok in coverage.items():
        check(f"help documents: {label}", ok)

    # ================= capability summary (access level) ==========
    print("--- per-user capability summary ---")
    st = cap.capability_state()
    for key in ("platform", "ai_state", "ai", "key_protection", "gpu_ocr",
                "engine", "ghostscript", "shell_menu", "platform_note"):
        check(f"capability_state has '{key}'", key in st)

    saved = (settings.ai_enabled, settings.ai_source, settings.ai_base_url,
             settings.ai_model, settings.ai_api_key_sealed)
    try:
        settings.ai_enabled = False
        s = cap.capability_state()
        check("AI shown as OFF when disabled",
              s["ai_state"] == "off" and "off" in s["ai"].lower())

        settings.ai_enabled = True
        settings.ai_source = ai_core.SOURCE_SYSTEM
        settings.ai_api_key_sealed = ai_core.seal_key("mico_key_abcdefghij")
        s = cap.capability_state()
        check("AI shown as System AI when configured to system",
              s["ai_state"] == "system" and "System AI" in s["ai"])

        settings.ai_source = ai_core.SOURCE_CUSTOM
        settings.ai_base_url = "http://ai.example.com:5310/v1"
        settings.ai_model = "qwen2.5:0.5b"
        s = cap.capability_state()
        check("AI shows your own endpoint host + model when custom",
              s["ai_state"] == "custom" and "ai.example.com:5310" in s["ai"]
              and "qwen2.5:0.5b" in s["ai"])

        htmlp = cap.capabilities_html()
        check("capabilities_html renders the live summary",
              "Your platform" in htmlp and "Explorer right-click menu" in htmlp
              and "AI suggestions" in htmlp)
    finally:
        (settings.ai_enabled, settings.ai_source, settings.ai_base_url,
         settings.ai_model, settings.ai_api_key_sealed) = saved

    # a stale/failed probe must never break the summary
    check("capability_state never raises", isinstance(cap.capability_state(), dict))

    # ================= Help page builds with the card =============
    print("--- Help page ---")
    from mico360.theme import stylesheet
    app.setStyleSheet(stylesheet(settings.theme))
    from mico360.ui.help_page import HelpPage
    hp = HelpPage()
    from PySide6.QtWidgets import QLabel
    labels = " ".join(lbl.text() for lbl in hp.findChildren(QLabel)).lower()
    # section_label() upper-cases its text, so match case-insensitively.
    check("Help page shows the 'Your setup & permissions' card",
          "your setup" in labels and "ai suggestions" in labels)
    hp.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Help & legal: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(_rc if isinstance(_rc, int) else 0)
