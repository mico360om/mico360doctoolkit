# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MICO360 Doc Toolkit (onedir build).

Build:
    pyinstaller build/mico360.spec --noconfirm

Produces dist/MICO360DocToolkit/ which the Inno Setup script packages, along
with the bundled vendor/ binaries (Ghostscript, LibreOffice).
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
    "PySide6.QtNetwork",   # QLocalServer/QLocalSocket — single-instance guard
    "fitz", "pypdf", "pptx", "PIL", "pdf2docx", "img2pdf",
    # Word -> PDF engine chain
    "docx", "reportlab", "docx2pdf",
    "win32com", "win32com.client", "pythoncom", "pywintypes",
    # File-properties tool (Date Created / Owner) via the Win32 API
    "win32file", "win32con", "win32security", "ntsecuritycon",
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

# Ensure onnxruntime's native libraries ship — including DirectML.dll and the
# provider DLLs when the DirectML build is installed — so GPU OCR works in the
# frozen app (with CPU fallback). Harmless if only the CPU build is present.
try:
    from PyInstaller.utils.hooks import collect_dynamic_libs
    binaries += collect_dynamic_libs("onnxruntime")
except Exception:
    pass

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
    # NOTE: QtNetwork is kept — QLocalServer/QLocalSocket power the
    # single-instance guard. (Updates still use stdlib urllib, not QtNetwork.)
    excludes=["tkinter", "matplotlib", "pytest",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
              "PySide6.QtPdf", "PySide6.QtPdfWidgets",
              "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
              "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    cipher=block_cipher,
    noarchive=False,
)

# Drop bundled Qt modules we never use (QML/Quick, QtPdf, QtNetwork, Multimedia,
# Charts) + Qt translations — Widgets-only app, fitz for PDF, urllib for net.
# Saves ~20+ MB. The PySide6 hook ships these regardless of the excludes above.
_QT_DROP = (
    "qt6quick", "qt6qml", "qt6qmlmodels", "qt6quickwidgets", "qt6quickcontrols2",
    "qt6quicktemplates2", "qt6virtualkeyboard", "qt6pdf",
    "qt6multimedia", "qt6charts", "qt6datavisualization", "qt6spatialaudio",
    "qtquick", "qtqml", "qtpdf", "qtmultimedia", "qtcharts",
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

# Drop large bundled files we never use, to shrink the installer / download:
#   * OpenCV video I/O (ffmpeg) — OCR only does image ops (verified safe)
#   * Qt software-OpenGL — a Widgets app renders with the raster engine
#   * Pillow AVIF codec — not in our supported image formats (PIL skips it)
#   * Pythonwin / MFC runtime — win32com (Office COM) doesn't need them
# Saves ~60 MB uncompressed (~25-30 MB off the installer).
_HEAVY_DROP_SUBSTR = ("opencv_videoio_ffmpeg", "opengl32sw")
_HEAVY_DROP_BASE = ("mfc140u.dll", "mfcm140u.dll")


def _heavy_unused(entry) -> bool:
    n = str(entry[0]).lower().replace("\\", "/")
    base = n.rsplit("/", 1)[-1]
    if any(s in base for s in _HEAVY_DROP_SUBSTR):
        return True
    if base in _HEAVY_DROP_BASE:
        return True
    if "/pythonwin/" in n or n.startswith("pythonwin/"):
        return True
    if base.startswith("_avif") and base.endswith(".pyd"):
        return True
    return False


a.binaries = [x for x in a.binaries if not _heavy_unused(x)]
a.datas = [x for x in a.datas if not _heavy_unused(x)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MICO360DocToolkit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(RES / "app.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MICO360DocToolkit",
)
