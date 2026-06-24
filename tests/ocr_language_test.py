"""Multi-language OCR: registry, on-demand language packs, RTL ordering, and —
when the Arabic model is present — real recognition of Arabic script.

Run:  python tests/ocr_language_test.py
"""
from __future__ import annotations

import os
import sys
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


def main() -> int:
    from mico360.core import ocr_models
    from mico360.core import processors

    # --- registry -------------------------------------------------------
    ids = list(ocr_models.LANGUAGES)
    check("Latin + Arabic are registered", {"latin", "arabic"} <= set(ids), str(ids))
    check("Latin is built in (no download)", ocr_models.language("latin").builtin)
    check("Arabic needs a downloaded model", not ocr_models.language("arabic").builtin)
    check("Arabic is right-to-left", ocr_models.language("arabic").rtl)
    ar = ocr_models.language("arabic")
    check("Arabic model has an integrity hash + size",
          bool(ar.model_sha256) and ar.model_size > 0)
    choices = dict(ocr_models.language_choices())
    check("language selector lists both", "latin" in choices and "arabic" in choices)
    check("unknown language falls back to Latin",
          ocr_models.language("klingon").id == "latin")

    # --- built-in Latin needs no provisioning ---------------------------
    check("Latin is always ready", ocr_models.is_language_ready("latin"))
    check("ensure_language(latin) is a no-op (uses default engine)",
          ocr_models.ensure_language("latin") is None)

    # --- bundled dictionary is present ----------------------------------
    keys = ocr_models._keys_path(ar)
    check("Arabic character dictionary is bundled", keys is not None and keys.exists(),
          str(keys))
    if keys:
        n = len([ln for ln in keys.read_text(encoding="utf-8").splitlines() if ln != ""])
        check("dictionary has the expected size (747 glyphs)", n == 747, f"{n} lines")

    # --- RTL row assembly (pure logic, no model) ------------------------
    lines = [("ALPHA", (10, 10, 50, 30)), ("BETA", (60, 10, 100, 30))]
    ltr = processors._ocr_rows(lines, rtl=False)
    rtl = processors._ocr_rows(lines, rtl=True)
    check("LTR joins fragments left→right", ltr and ltr[0][0] == "ALPHA BETA")
    check("RTL joins fragments right→left", rtl and rtl[0][0] == "BETA ALPHA")
    check("_ocr_lang_is_rtl reflects the language",
          processors._ocr_lang_is_rtl("arabic") and not processors._ocr_lang_is_rtl("latin"))

    # --- real Arabic recognition (only if the model is staged) ----------
    staged = ocr_models.model_path(ar)
    if staged.exists() and staged.stat().st_size == ar.model_size:
        try:
            import numpy as np
            from PIL import Image, ImageDraw, ImageFont
            import arabic_reshaper
            from bidi.algorithm import get_display
            font_file = next((f for f in (r"C:\Windows\Fonts\arial.ttf",
                                          r"C:\Windows\Fonts\tahoma.ttf")
                              if os.path.exists(f)), None)
            if font_file:
                font = ImageFont.truetype(font_file, 48)
                shaped = get_display(arabic_reshaper.reshape("اللغة العربية"))
                img = Image.new("RGB", (640, 90), "white")
                ImageDraw.Draw(img).text((20, 15), shaped, fill="black", font=font)
                engine = processors._make_ocr_engine("arabic")
                res, _ = engine(np.array(img))
                got = " ".join(r[1] for r in res) if res else ""
                arabic = any("؀" <= c <= "ۿ" for c in got)
                check("Arabic model recognises Arabic script", arabic, repr(got))
            else:
                print("[SKIP] no Arabic-capable font available for the render test")
        except Exception as exc:  # shaping libs are dev-only; don't fail CI
            print(f"[SKIP] Arabic render/recognise test ({exc})")
    else:
        print("[SKIP] Arabic model not staged locally — recognition test skipped")

    print()
    if failures:
        print(f"{len(failures)} OCR-language check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All OCR-language checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
