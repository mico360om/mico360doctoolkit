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
EXCEL = {".xlsx", ".xls", ".ods", ".csv"}
PPT = {".pptx", ".ppt", ".odp"}
OFFICE = WORD | EXCEL | PPT                 # Office → PDF (auto-detected)
MARKDOWN_INPUTS = WORD | EXCEL | PPT | PDF  # anything → Markdown

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
        id="pdf_organize", name="Organize PDF", icon="🧩",
        tagline="Rotate, delete, extract or reorder pages.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_organize, group="PDF",
        options=[
            Option("operation", "Action", "choice", "rotate", [
                ("rotate", "Rotate pages"),
                ("delete", "Delete pages"),
                ("extract", "Extract pages (keep only these)"),
                ("reorder", "Reorder pages"),
            ]),
            Option("angle", "Rotate by", "choice", 90, [
                (90, "90° clockwise"), (180, "180°"), (270, "270° (90° anti-clockwise)"),
            ], visible_when=("operation", "rotate")),
            Option("pages", "Pages", "text", "all",
                   hint="e.g. 1-3, 5, 8  ·  use 'all' for every page",
                   visible_when=("operation", "rotate")),
            Option("del_pages", "Pages to delete", "text", "",
                   hint="e.g. 2, 5-7", visible_when=("operation", "delete")),
            Option("ext_pages", "Pages to extract", "text", "",
                   hint="in output order, e.g. 1, 3, 5-8", visible_when=("operation", "extract")),
            Option("order", "New page order", "text", "",
                   hint="every page, in the order you want, e.g. 3, 1, 2, 4-10",
                   visible_when=("operation", "reorder")),
        ],
    ),
    Tool(
        id="pdf_protect", name="Protect PDF", icon="🔒",
        tagline="Add or remove a password on a PDF.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_protect, group="PDF",
        options=[
            Option("operation", "Action", "choice", "protect", [
                ("protect", "Add a password (encrypt)"),
                ("unlock", "Remove the password (decrypt)"),
            ]),
            Option("password", "Password", "password", ""),
            Option("confirm_password", "Confirm password", "password", "",
                   hint="Re-enter the password to confirm.",
                   visible_when=("operation", "protect")),
        ],
    ),
    Tool(
        id="pdf_watermark", name="Watermark PDF", icon="💧",
        tagline="Stamp text — or a logo/image — across every page.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_watermark, group="PDF",
        options=[
            Option("wm_type", "Watermark", "choice", "text", [
                ("text", "Text"), ("image", "Logo / image"),
            ]),
            Option("text", "Watermark text", "text", "CONFIDENTIAL",
                   visible_when=("wm_type", "text")),
            Option("image_path", "Logo / image file", "file", "",
                   hint="A PNG with transparency works best.",
                   visible_when=("wm_type", "image")),
            Option("font_size", "Font size", "int", 48, minimum=6, maximum=400,
                   suffix=" pt", visible_when=("wm_type", "text")),
            Option("scale", "Size", "int", 40, minimum=5, maximum=100,
                   suffix=" % of page width", visible_when=("wm_type", "image")),
            Option("color", "Colour", "choice", "gray", [
                ("gray", "Grey"), ("red", "Red"), ("blue", "Blue"), ("black", "Black"),
            ], visible_when=("wm_type", "text")),
            Option("opacity", "Opacity", "int", 20, minimum=1, maximum=100, suffix=" %"),
            Option("rotation", "Angle", "int", 45, minimum=-180, maximum=180, suffix="°"),
            Option("position", "Position", "posgrid", "center"),
        ],
    ),
    Tool(
        id="pdf_page_numbers", name="Add Page Numbers", icon="#️⃣",
        tagline="Stamp page numbers onto every page.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_page_numbers, group="PDF",
        options=[
            Option("position", "Position", "choice", "bottom-center", [
                ("bottom-center", "Bottom centre"), ("bottom-right", "Bottom right"),
                ("bottom-left", "Bottom left"), ("top-center", "Top centre"),
                ("top-right", "Top right"), ("top-left", "Top left"),
            ]),
            Option("format", "Style", "choice", "n", [
                ("n", "1, 2, 3 …"), ("n_of_total", "1 / N"), ("page_n", "Page 1"),
            ]),
            Option("start", "Start at", "int", 1, minimum=1, maximum=1000000),
            Option("font_size", "Font size", "int", 11, minimum=6, maximum=72,
                   suffix=" pt"),
        ],
    ),
    Tool(
        id="pdf_sign", name="Sign PDF", icon="✍️",
        tagline="Stamp a signature image onto the PDF.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_sign, group="PDF",
        options=[
            Option("image_path", "Signature image", "file", "",
                   hint="A PNG with transparency works best."),
            Option("page", "Apply to", "choice", "last", [
                ("last", "Last page"), ("first", "First page"), ("all", "Every page"),
            ]),
            Option("position", "Position", "choice", "bottom-right", [
                ("bottom-right", "Bottom right"), ("bottom-left", "Bottom left"),
                ("bottom-center", "Bottom centre"), ("top-right", "Top right"),
                ("top-left", "Top left"), ("top-center", "Top centre"),
            ]),
            Option("width", "Size", "int", 25, minimum=5, maximum=100,
                   suffix=" % of page width"),
        ],
    ),
    Tool(
        id="pdf_metadata", name="Edit Metadata", icon="🏷️",
        tagline="Edit title, author, subject and keywords.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_metadata, group="PDF",
        options=[
            Option("title", "Title", "text", "", hint="Leave blank to keep existing."),
            Option("author", "Author", "text", ""),
            Option("subject", "Subject", "text", ""),
            Option("keywords", "Keywords", "text", "", hint="comma,separated"),
        ],
    ),
    Tool(
        id="pdf_ocr", name="Searchable PDF (OCR)", icon="🔍",
        tagline="Make scanned PDFs selectable & searchable.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_ocr, group="PDF",
        options=[
            Option("quality", "Recognition quality", "choice", "balanced", [
                ("fast", "Fast — 200 dpi"),
                ("balanced", "Balanced — 300 dpi (recommended)"),
                ("high", "High — 400 dpi (best on small text)"),
            ], hint="Higher quality reads small or faint text better, but is slower."),
        ],
    ),
    Tool(
        id="pdf_convert", name="PDF → …", icon="🔄",
        tagline="Convert a PDF to Word, PowerPoint, Excel or images.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_convert, group="Convert",
        options=[
            Option("target", "Convert to", "choice", "word", [
                ("word", "Word document (.docx)"),
                ("pptx", "PowerPoint slides (.pptx)"),
                ("excel", "Excel workbook (.xlsx)"),
                ("image", "Images (one per page)"),
            ]),
            # Word target
            Option("word_ocr", "OCR scanned pages (recognise text from images)",
                   "bool", False, hint="Turn on for scanned PDFs with no selectable text.",
                   visible_when=("target", "word")),
            # PowerPoint target
            Option("mode", "Slides", "choice", "auto", [
                ("auto", "Auto — editable text, image where needed (recommended)"),
                ("text", "Editable text only"),
                ("image", "Exact page image (not editable)"),
            ], visible_when=("target", "pptx")),
            Option("pptx_ocr", "OCR scanned pages (recognise text from images)",
                   "bool", False,
                   hint="Makes scanned / image-only pages editable instead of flat images.",
                   visible_when=("target", "pptx")),
            # Image target
            Option("format", "Image format", "choice", "png", IMG_FMT_CHOICES,
                   visible_when=("target", "image")),
            Option("dpi", "Resolution", "int", 150, minimum=72, maximum=600,
                   suffix=" dpi", visible_when=("target", "image")),
            Option("jpeg_quality", "JPEG quality", "int", 90, minimum=10, maximum=100,
                   suffix=" %", visible_when=("target", "image")),
        ],
    ),
    Tool(
        id="office_to_pdf", name="Office → PDF", icon="📄",
        tagline="Convert Word, Excel or PowerPoint to PDF — type auto-detected.",
        mode=PER_FILE, accept=OFFICE, runner=processors.office_to_pdf, group="Convert",
        options=[],
    ),
    Tool(
        id="to_markdown", name="Document → Markdown", icon="📋",
        tagline="Convert Word, Excel, PowerPoint or PDF to Markdown (.md).",
        mode=PER_FILE, accept=MARKDOWN_INPUTS, runner=processors.to_markdown,
        group="Convert", options=[],
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
        mode=PER_FILE, accept=IMAGES, runner=processors.image_compress, group="Images",
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
    Tool(
        id="image_resize", name="Resize Image", icon="📐",
        tagline="Batch-resize images by dimensions or percentage.",
        mode=PER_FILE, accept=IMAGES, runner=processors.image_resize, group="Images",
        options=[
            Option("mode", "Resize by", "choice", "dimensions", [
                ("dimensions", "Width / height (px)"), ("percent", "Percentage"),
            ]),
            Option("width", "Width", "int", 1280, minimum=0, maximum=60000,
                   suffix=" px", visible_when=("mode", "dimensions")),
            Option("height", "Height (0 = auto)", "int", 0, minimum=0, maximum=60000,
                   suffix=" px", visible_when=("mode", "dimensions")),
            Option("keep_aspect", "Keep aspect ratio", "bool", True,
                   visible_when=("mode", "dimensions")),
            Option("percent", "Scale", "int", 50, minimum=1, maximum=1000,
                   suffix=" %", visible_when=("mode", "percent")),
        ],
    ),
    Tool(
        id="image_convert", name="Convert Image", icon="🔁",
        tagline="Change image format (PNG ⇄ JPG ⇄ WEBP ⇄ TIFF).",
        mode=PER_FILE, accept=IMAGES, runner=processors.image_convert, group="Images",
        options=[
            Option("format", "Convert to", "choice", "png", [
                ("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"),
                ("tiff", "TIFF"), ("bmp", "BMP"),
            ]),
            Option("quality", "Quality", "int", 90, minimum=5, maximum=100,
                   suffix=" %", hint="Applies to JPEG / WEBP."),
        ],
    ),
    Tool(
        id="image_watermark", name="Watermark Image", icon="💧",
        tagline="Stamp text or a logo onto images.",
        mode=PER_FILE, accept=IMAGES, runner=processors.image_watermark, group="Images",
        options=[
            Option("wm_type", "Watermark", "choice", "text", [
                ("text", "Text"), ("image", "Logo / image"),
            ]),
            Option("text", "Watermark text", "text", "CONFIDENTIAL",
                   visible_when=("wm_type", "text")),
            Option("image_path", "Logo / image file", "file", "",
                   hint="A PNG with transparency works best.",
                   visible_when=("wm_type", "image")),
            Option("font_size", "Font size", "int", 48, minimum=6, maximum=2000,
                   suffix=" px", visible_when=("wm_type", "text")),
            Option("scale", "Size", "int", 40, minimum=5, maximum=100,
                   suffix=" % of width", visible_when=("wm_type", "image")),
            Option("color", "Colour", "choice", "gray", [
                ("gray", "Grey"), ("red", "Red"), ("blue", "Blue"),
                ("black", "Black"), ("white", "White"),
            ], visible_when=("wm_type", "text")),
            Option("opacity", "Opacity", "int", 25, minimum=1, maximum=100, suffix=" %"),
            Option("rotation", "Angle", "int", 30, minimum=-180, maximum=180, suffix="°"),
        ],
    ),
]

TOOLS_BY_ID = {t.id: t for t in TOOLS}


def all_accept_exts() -> set:
    out: set = set()
    for t in TOOLS:
        out |= t.accept
    return out
