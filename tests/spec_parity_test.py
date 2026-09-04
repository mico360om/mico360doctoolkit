"""Guard: the macOS PyInstaller spec must bundle the same feature-critical bits as
the Windows spec, so features don't silently break on one platform.

This is what let Arabic OCR / HEIC / Image->SVG ship broken on macOS: the macOS
spec was never updated when those were added on Windows.

Run:  python tests/spec_parity_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
WIN = (ROOT / "build" / "mico360.spec").read_text(encoding="utf-8")
MAC = (ROOT / "build" / "mico360_macos.spec").read_text(encoding="utf-8")

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


# Feature-critical payload that must be present in BOTH specs.
REQUIRED = [
    ("ocr_data (Arabic OCR dictionary)", "ocr_data"),
    ("pillow_heif (HEIC support)", "pillow_heif"),
    ("vtracer (Image -> SVG)", "vtracer"),
    ("rapidocr (OCR engine)", "rapidocr_onnxruntime"),
    ("onnxruntime", "onnxruntime"),
    ("cryptography (PDF encryption)", "cryptography"),
    ("QtSvg (tintable line icons)", "PySide6.QtSvg"),
    ("mico360.ui.icons (icon set)", "mico360.ui.icons"),
    ("mico360.capabilities (Help gating)", "mico360.capabilities"),
    ("AI metadata modules", "mico360.core.ai_metadata"),
    ("AI suggest panel", "mico360.ui.ai_suggest"),
    ("square app icon (app.png)", "app.png"),
]

# Hidden imports that only make sense on Windows; the macOS spec may omit them.
WIN_ONLY = {
    "win32com", "win32com.client", "pythoncom", "pywintypes",
    "win32file", "win32con", "win32security", "ntsecuritycon",
    "docx2pdf",                  # drives Microsoft Word via COM
    "mico360.shell_integration",  # Explorer right-click menu (registry)
}


def _hidden_imports(spec_text: str) -> set[str]:
    import re
    m = re.search(r"hiddenimports\s*=\s*\[(.*?)\n\]", spec_text, re.S)
    return set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()


def main() -> int:
    check("Windows spec exists", bool(WIN))
    check("macOS spec exists", bool(MAC))
    for label, token in REQUIRED:
        check(f"Windows spec bundles {label}", token in WIN)
        check(f"macOS spec bundles {label}", token in MAC)

    # Every explicit hidden import on Windows must be on macOS too, unless it is
    # genuinely Windows-only. (This is the gap that lets lazily-imported modules
    # — icons, AI panel — silently vanish from the .app.)
    missing = sorted((_hidden_imports(WIN) - _hidden_imports(MAC)) - WIN_ONLY)
    check("macOS spec lists every non-Windows hidden import the Windows spec has",
          not missing, str(missing))

    # The bundled OCR dictionary file must actually exist on disk.
    keys = ROOT / "mico360" / "core" / "ocr_data" / "arabic_keys.txt"
    check("arabic_keys.txt is present in the tree", keys.exists(), str(keys))
    res = ROOT / "mico360" / "resources"
    check("app.png (square window icon) is present", (res / "app.png").exists())
    check("app.icns (macOS bundle icon) is present", (res / "app.icns").exists())
    check("app.ico (Windows icon) is present", (res / "app.ico").exists())

    print()
    if failures:
        print(f"{len(failures)} parity check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All spec-parity checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    # Skip Qt's crash-prone offscreen teardown at interpreter shutdown
    # (a lingering C++ object can abort finalization with 0xC0000409,
    #  masking an otherwise-clean pass). Flush and exit with the result.
    import os as _os, sys as _sys
    _sys.stdout.flush(); _sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
