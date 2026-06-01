# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MICO360 Doc Toolkit (single-file build).

Build:
    pyinstaller build/mico360_onefile.spec --noconfirm

Produces a single self-contained dist/MICO360DocToolkit.exe. Slower first launch
than the onedir build (it unpacks to a temp dir at startup) but it is one file
you can copy and run anywhere. Bundled vendor/ binaries (if present) are packed
inside.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(os.getcwd())
RES = ROOT / "mico360" / "resources"

datas = [
    (str(RES / "logo.png"), "mico360/resources"),
    (str(RES / "logo-w.png"), "mico360/resources"),
    (str(RES / "app.ico"), "mico360/resources"),
]
binaries = []
hiddenimports = [
    "fitz", "pypdf", "pptx", "PIL", "pdf2docx", "img2pdf",
    # Word -> PDF engine chain
    "docx", "reportlab", "docx2pdf",
    "win32com", "win32com.client", "pythoncom", "pywintypes",
    # OCR
    "rapidocr_onnxruntime", "onnxruntime", "cv2", "numpy", "shapely", "pyclipper",
    # AES-256 PDF password protection (pypdf -> cryptography)
    "cryptography",
]

# Bundle tricky packages completely (data files, submodules).
for pkg in ("pdf2docx", "fontTools", "pptx", "reportlab", "docx", "docx2pdf",
            "rapidocr_onnxruntime", "onnxruntime", "cryptography"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

datas += collect_data_files("img2pdf")

# Bundle vendored binaries into the frozen app if present (optional).
vendor = ROOT / "vendor"
if vendor.exists():
    for path in vendor.rglob("*"):
        if path.is_file():
            datas.append((str(path), str(Path("vendor") / path.parent.relative_to(vendor))))


block_cipher = None

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Single-file: pack binaries/zipfiles/datas straight into the EXE (no COLLECT).
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MICO360DocToolkit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon=str(RES / "app.ico"),
)
