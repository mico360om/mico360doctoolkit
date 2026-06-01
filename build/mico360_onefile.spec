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
    # PDF -> Excel (tables) and Excel handling
    "pdfplumber", "pdfminer", "openpyxl", "pypdfium2",
]

# Bundle tricky packages completely (data files, submodules).
for pkg in ("pdf2docx", "fontTools", "pptx", "reportlab", "docx", "docx2pdf",
            "rapidocr_onnxruntime", "onnxruntime", "cryptography",
            "pdfplumber", "pdfminer", "openpyxl", "pypdfium2"):
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
    excludes=["tkinter", "matplotlib", "pytest",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
              "PySide6.QtNetwork", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
              "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
              "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    cipher=block_cipher,
    noarchive=False,
)

# Drop unused bundled Qt modules + translations (see onedir spec). Saves ~20+ MB.
_QT_DROP = (
    "qt6quick", "qt6qml", "qt6qmlmodels", "qt6quickwidgets", "qt6quickcontrols2",
    "qt6quicktemplates2", "qt6virtualkeyboard", "qt6pdf", "qt6network",
    "qt6multimedia", "qt6charts", "qt6datavisualization", "qt6spatialaudio",
    "qtquick", "qtqml", "qtpdf", "qtnetwork", "qtmultimedia", "qtcharts",
)


def _qt_unused(entry) -> bool:
    n = str(entry[0]).lower().replace("\\", "/")
    if "/translations/" in n or n.startswith("pyside6/translations"):
        return True
    if "/qml/" in n:
        return True
    base = n.rsplit("/", 1)[-1]
    return any(base.startswith(d) for d in _QT_DROP)


a.binaries = [x for x in a.binaries if not _qt_unused(x)]
a.datas = [x for x in a.datas if not _qt_unused(x)]

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
