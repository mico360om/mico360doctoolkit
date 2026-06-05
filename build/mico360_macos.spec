# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MICO360 Doc Toolkit — macOS .app bundle.

Build (must run ON macOS):
    pyinstaller build/mico360_macos.spec --noconfirm
Produces:
    dist/MICO360 Doc Toolkit.app   (then packaged into a .dmg by CI)

Windows-only bits (pywin32 / win32com) are simply absent here; the app's
Office-COM paths are guarded and fall back to LibreOffice on macOS.
"""
import os
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(os.getcwd())
RES = ROOT / "mico360" / "resources"

# Read the version straight from the package (no heavy imports).
_init = (ROOT / "mico360" / "__init__.py").read_text(encoding="utf-8")
VERSION = (re.search(r'__version__\s*=\s*"([^"]+)"', _init) or [None, "1.0.0"])[1]

datas = [
    (str(RES / "logo.png"), "mico360/resources"),
    (str(RES / "logo-w.png"), "mico360/resources"),
    (str(RES / "app.ico"), "mico360/resources"),
]
binaries = []
hiddenimports = [
    "PySide6.QtNetwork",   # QLocalServer/QLocalSocket — single-instance guard
    "fitz", "pypdf", "pptx", "PIL", "pdf2docx", "img2pdf",
    "docx", "reportlab",
    "rapidocr_onnxruntime", "onnxruntime", "cv2", "numpy", "shapely", "pyclipper",
    "cryptography",
    "pdfplumber", "pdfminer", "openpyxl", "pypdfium2",
]

for pkg in ("pdf2docx", "fontTools", "pptx", "reportlab", "docx",
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

vendor = ROOT / "vendor"
if vendor.exists():
    for path in vendor.rglob("*"):
        if path.is_file():
            datas.append((str(path), str(Path("vendor") / path.parent.relative_to(vendor))))


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
              "PySide6.QtPdf", "PySide6.QtPdfWidgets",
              "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
              "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    noarchive=False,
)

# Drop unused Qt modules / translations (Widgets-only app).
_QT_DROP = (
    "qtquick", "qtqml", "qtqmlmodels", "qtquickwidgets", "qtquickcontrols2",
    "qtquicktemplates2", "qtvirtualkeyboard", "qtpdf", "qtmultimedia",
    "qtcharts", "qtdatavisualization", "qtspatialaudio",
    "qt6quick", "qt6qml", "qt6pdf", "qt6multimedia", "qt6charts",
)


def _qt_unused(entry) -> bool:
    n = str(entry[0]).lower().replace("\\", "/")
    if "/translations/" in n or "/qml/" in n:
        return True
    base = n.rsplit("/", 1)[-1]
    return any(d in base for d in _QT_DROP)


def _heavy_unused(entry) -> bool:
    base = str(entry[0]).lower().replace("\\", "/").rsplit("/", 1)[-1]
    if "opencv_videoio_ffmpeg" in base:          # OpenCV video I/O (OCR = images)
        return True
    if base.startswith("_avif") and base.endswith((".so", ".pyd")):  # AVIF codec
        return True
    return False


a.binaries = [x for x in a.binaries if not _qt_unused(x) and not _heavy_unused(x)]
a.datas = [x for x in a.datas if not _qt_unused(x) and not _heavy_unused(x)]

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MICO360DocToolkit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name="MICO360DocToolkit",
)
app = BUNDLE(
    coll,
    name="MICO360 Doc Toolkit.app",
    icon=str(RES / "app.icns"),
    bundle_identifier="com.mico360.doctoolkit",
    version=VERSION,
    info_plist={
        "CFBundleName": "MICO360 Doc Toolkit",
        "CFBundleDisplayName": "MICO360 Doc Toolkit",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "© MICO360",
    },
)
