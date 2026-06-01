"""Declarative registry of the 10 tools: metadata, accepted inputs, options.

The UI is generated from these definitions, so adding a tool is a data change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from mico360.core import processors

PER_FILE = "per_file"
AGGREGATE = "aggregate"


@dataclass
class Option:
    key: str
    label: str
    kind: str                       # choice | int | bool | text
    default: object = None
    choices: list = field(default_factory=list)   # list[(value, label)]
    minimum: int = 0
    maximum: int = 10000
    suffix: str = ""
    hint: str = ""
    visible_when: tuple | None = None  # (other_key, value) -> show only when equal


@dataclass
class Tool:
    id: str
    name: str
    icon: str                        # emoji glyph used in the nav + header
    tagline: str
    mode: str
    accept: set                      # accepted input extensions (lowercase, with dot)
    runner: Callable
    options: list = field(default_factory=list)
    group: str = "PDF"


PDF = {".pdf"}
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
WORD = {".doc", ".docx", ".odt", ".rtf"}

_QUALITY_CHOICES = [
    ("low", "Low compression — best quality"),
    ("medium", "Medium — balanced (recommended)"),
    ("high", "High compression — smallest size"),
    ("target", "Target file size…"),
    ("custom", "Custom…"),
]

IMG_FMT_CHOICES = [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"),
                   ("tiff", "TIFF"), ("bmp", "BMP")]


TOOLS: list[Tool] = [
    Tool(
        id="pdf_compress", name="Compress PDF", icon="🗜️",
        tagline="Shrink PDF file size with selectable quality.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_compress, group="PDF",
        options=[
            Option("level", "Compression", "choice", "medium", _QUALITY_CHOICES,
                   hint="Higher compression = smaller file, lower fidelity."),
            Option("target_kb", "Target size", "int", 250, minimum=10, maximum=200000,
                   suffix=" KB", visible_when=("level", "target"),
                   hint="Auto-selects DPI & quality to land at or just under this size."),
            Option("dpi", "Image DPI", "int", 150, minimum=36, maximum=600,
                   suffix=" dpi", visible_when=("level", "custom")),
            Option("jpeg_quality", "JPEG quality", "int", 75, minimum=10, maximum=100,
                   suffix=" %", visible_when=("level", "custom")),
        ],
    ),
    Tool(
        id="pdf_merge", name="Merge PDF", icon="🔗",
        tagline="Combine several PDFs into a single document.",
        mode=AGGREGATE, accept=PDF, runner=processors.pdf_merge, group="PDF",
        options=[
            Option("output_name", "Output file name", "text", "merged",
                   hint="Saved as <name>.pdf in the output folder."),
        ],
    ),
    Tool(
        id="pdf_split", name="Split PDF", icon="✂️",
        tagline="Break a PDF into multiple files by page, count or range.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_split, group="PDF",
        options=[
            Option("mode", "Split by", "choice", "each", [
                ("each", "Every page → separate file"),
                ("every_n", "Fixed number of pages per file"),
                ("ranges", "Custom page ranges"),
            ]),
            Option("every_n", "Pages per file", "int", 2, minimum=1, maximum=5000,
                   visible_when=("mode", "every_n")),
            Option("ranges", "Ranges", "text", "1-3, 4-6",
                   hint="e.g. 1-3, 5, 8-10", visible_when=("mode", "ranges")),
        ],
    ),
    Tool(
        id="pdf_to_word", name="PDF → Word", icon="📝",
        tagline="Convert PDF documents to editable Word (.docx).",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_to_word, group="Convert",
        options=[
            Option("ocr", "OCR scanned pages (recognise text from images)", "bool", False,
                   hint="Turn on for scanned PDFs with no selectable text."),
        ],
    ),
    Tool(
        id="pdf_to_pptx", name="PDF → PowerPoint", icon="📊",
        tagline="Turn each PDF page into a PowerPoint slide.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_to_pptx, group="Convert",
        options=[
            Option("mode", "Slides", "choice", "auto", [
                ("auto", "Auto — editable text, image where needed (recommended)"),
                ("text", "Editable text only"),
                ("image", "Exact page image (not editable)"),
            ], hint="Auto keeps text editable but never leaves a slide empty for "
                    "scanned / image-only PDFs."),
            Option("ocr", "OCR scanned pages (recognise text from images)", "bool", False,
                   hint="Makes scanned / image-only pages editable instead of flat images.",
                   visible_when=("mode", "auto")),
        ],
    ),
    Tool(
        id="word_to_pdf", name="Word → PDF", icon="📄",
        tagline="Convert Word documents to PDF — works out of the box.",
        mode=PER_FILE, accept=WORD, runner=processors.word_to_pdf, group="Convert",
    ),
    Tool(
        id="pdf_to_image", name="PDF → Image", icon="🖼️",
        tagline="Render PDF pages to image files.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_to_image, group="Convert",
        options=[
            Option("format", "Image format", "choice", "png", IMG_FMT_CHOICES),
            Option("dpi", "Resolution", "int", 150, minimum=72, maximum=600, suffix=" dpi"),
            Option("jpeg_quality", "JPEG quality", "int", 90, minimum=10, maximum=100,
                   suffix=" %", visible_when=("format", "jpg")),
        ],
    ),
    Tool(
        id="image_to_pdf", name="Image → PDF", icon="📑",
        tagline="Convert images into PDF — one file each or combined.",
        mode=AGGREGATE, accept=IMAGES, runner=processors.image_to_pdf, group="Convert",
        options=[
            Option("combine", "Combine all images into one PDF", "bool", True),
            Option("output_name", "Combined file name", "text", "images",
                   visible_when=("combine", True)),
        ],
    ),
    Tool(
        id="image_compress", name="Compress Image", icon="🏞️",
        tagline="Reduce image file size with quality control.",
        mode=PER_FILE, accept=IMAGES, runner=processors.image_compress, group="Image",
        options=[
            Option("level", "Compression", "choice", "medium", _QUALITY_CHOICES,
                   hint="Higher compression = smaller file, lower fidelity."),
            Option("target_kb", "Target size", "int", 250, minimum=5, maximum=200000,
                   suffix=" KB", visible_when=("level", "target"),
                   hint="Auto-selects quality (and downscales if needed) to land "
                        "at or just under this size."),
            Option("quality", "Quality", "int", 65, minimum=5, maximum=100, suffix=" %",
                   visible_when=("level", "custom")),
            Option("format", "Output format", "choice", "keep", [
                ("keep", "Keep original"), ("jpg", "JPEG"), ("png", "PNG"),
                ("webp", "WEBP")]),
            Option("max_dimension", "Max width/height (0 = keep)", "int", 0,
                   minimum=0, maximum=20000, suffix=" px"),
        ],
    ),
]

TOOLS_BY_ID = {t.id: t for t in TOOLS}


def all_accept_exts() -> set:
    out: set = set()
    for t in TOOLS:
        out |= t.accept
    return out
