"""Declarative registry of the 10 tools: metadata, accepted inputs, options.

The UI is generated from these definitions, so adding a tool is a data change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from mico360.core import processors
from mico360.core import ocr_models

PER_FILE = "per_file"
AGGREGATE = "aggregate"

# Languages the OCR can recognise. Latin (English & Western scripts) is built in;
# others are small models downloaded once on first use.
OCR_LANG_CHOICES = ocr_models.language_choices()


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
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
          ".heic", ".heif"}   # HEIC/HEIF (Apple photos) via pillow-heif
SVG = {".svg"}
WORD = {".doc", ".docx", ".odt", ".rtf"}
EXCEL = {".xlsx", ".xls", ".ods", ".csv"}
PPT = {".pptx", ".ppt", ".odp"}
OFFICE = WORD | EXCEL | PPT                 # Office → PDF (auto-detected)
MARKDOWN_INPUTS = WORD | EXCEL | PPT | PDF  # anything → Markdown

# Compression levels. "Lossless" is the default and is content-verified: it
# reduces size with zero change to images/text/fonts/metadata. The other levels
# re-compress images for a smaller file (text/links/etc. are still preserved).
_QUALITY_CHOICES = [
    ("lossless", "Lossless — no quality loss, verified identical (recommended)"),
    ("low", "Low — light image compression"),
    ("medium", "Medium — balanced (re-compresses images)"),
    ("high", "High — smallest (re-compresses images more)"),
    ("target", "Target file size…"),
    ("custom", "Custom…"),
]

IMG_FMT_CHOICES = [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"),
                   ("tiff", "TIFF"), ("bmp", "BMP")]


TOOLS: list[Tool] = [
    Tool(
        id="pdf_compress", name="Compress PDF", icon="🗜️",
        tagline="Shrink PDF file size with selectable quality.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_compress, group="Optimize",
        options=[
            Option("level", "Compression", "choice", "lossless", _QUALITY_CHOICES,
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
        mode=AGGREGATE, accept=PDF, runner=processors.pdf_merge, group="Organize",
        options=[
            Option("output_name", "Output file name", "text", "merged",
                   hint="Saved as <name>.pdf in the output folder."),
        ],
    ),
    Tool(
        id="pdf_split", name="Split PDF", icon="✂️",
        tagline="Break a PDF into multiple files by page, count or range.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_split, group="Organize",
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
        mode=PER_FILE, accept=PDF, runner=processors.pdf_organize, group="Organize",
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
        mode=PER_FILE, accept=PDF, runner=processors.pdf_protect, group="Secure",
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
        mode=PER_FILE, accept=PDF, runner=processors.pdf_watermark, group="Edit",
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
        mode=PER_FILE, accept=PDF, runner=processors.pdf_page_numbers, group="Edit",
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
        mode=PER_FILE, accept=PDF, runner=processors.pdf_sign, group="Edit",
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
        tagline="Edit every document property — or strip it all out.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_metadata, group="Edit",
        options=[
            # Privacy mode first: "off" edits the fields below; a preset hides them
            # and runs a one-shot scrub instead.
            Option("privacy", "Privacy", "choice", "", [
                ("", "Off — edit the fields below"),
                ("scrub", "Scrub identifying info (keep Title / Subject / Keywords)"),
                ("all", "Remove ALL metadata"),
            ], hint="Scrub clears Author, Creator, Producer, Company, Manager and "
                    "Comments and resets the dates; Remove all also strips XMP. "
                    "Ideal before sharing a file."),
            # Each editable field is blank-by-default and only changes what you fill
            # in; everything else is preserved. They hide when a privacy preset is on.
            Option("title", "Title", "text", "", hint="Leave blank to keep existing.",
                   visible_when=("privacy", "")),
            Option("author", "Author", "text", "", visible_when=("privacy", "")),
            Option("subject", "Subject", "text", "", visible_when=("privacy", "")),
            Option("keywords", "Keywords", "text", "", hint="comma,separated",
                   visible_when=("privacy", "")),
            Option("creator", "Creator (authoring app)", "text", "",
                   hint="The program the document was originally created in.",
                   visible_when=("privacy", "")),
            Option("producer", "Producer (PDF software)", "text", "",
                   hint="The app/library that produced the PDF.",
                   visible_when=("privacy", "")),
            Option("creation_date", "Creation date", "text", "",
                   hint="e.g. 2026-06-07 14:30, or 'now' — blank keeps existing.",
                   visible_when=("privacy", "")),
            Option("mod_date", "Modification date", "text", "",
                   hint="e.g. 2026-06-07, or 'now'.", visible_when=("privacy", "")),
            Option("company", "Company", "text", "",
                   hint="Custom property (shown in Acrobat's Custom tab).",
                   visible_when=("privacy", "")),
            Option("manager", "Manager", "text", "", visible_when=("privacy", "")),
            Option("category", "Category", "text", "", visible_when=("privacy", "")),
            Option("comments", "Comments", "text", "", visible_when=("privacy", "")),
            Option("custom", "Custom properties", "textarea", "",
                   hint="Your own fields, one per line as  Key = Value  "
                        "(e.g. Department = Finance). Shown in Acrobat's Custom tab.",
                   visible_when=("privacy", "")),
            Option("copyright", "Copyright", "text", "",
                   hint="Stored in XMP rights metadata; marks the file as copyrighted.",
                   visible_when=("privacy", "")),
            Option("language", "Language", "text", "",
                   hint="e.g. en-US — improves accessibility / screen readers.",
                   visible_when=("privacy", "")),
            Option("trapped", "Trapped", "choice", "", [
                ("", "Keep current"),
                ("Unknown", "Unknown"),
                ("True", "True"),
                ("False", "False"),
            ], hint="Prepress trapping flag.", visible_when=("privacy", "")),
            Option("show_title", "Show document Title (not file name) in the window bar",
                   "bool", False, visible_when=("privacy", "")),
        ],
    ),
    Tool(
        id="pdf_ocr", name="Searchable PDF (OCR)", icon="🔍",
        tagline="Make scanned PDFs selectable & searchable.",
        mode=PER_FILE, accept=PDF, runner=processors.pdf_ocr, group="Recognize",
        options=[
            Option("ocr_lang", "Language", "choice", "latin", OCR_LANG_CHOICES,
                   hint="Pick the document's main script. Non-Latin languages "
                        "download a small model once on first use."),
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
            Option("ocr_lang", "OCR language", "choice", "latin", OCR_LANG_CHOICES,
                   hint="Pick the document's main script.",
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
        mode=PER_FILE, accept=IMAGES, runner=processors.image_compress, group="Optimize",
        options=[
            Option("level", "Compression", "choice", "lossless", _QUALITY_CHOICES,
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
        mode=PER_FILE, accept=IMAGES, runner=processors.image_resize, group="Edit",
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
        tagline="Change image format (incl. HEIC → PNG / JPG / WEBP).",
        mode=PER_FILE, accept=IMAGES, runner=processors.image_convert, group="Convert",
        options=[
            Option("format", "Convert to", "choice", "png", [
                ("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"),
                ("tiff", "TIFF"), ("bmp", "BMP"), ("heic", "HEIC"),
            ]),
            Option("quality", "Quality", "int", 90, minimum=5, maximum=100,
                   suffix=" %", hint="Applies to JPEG / WEBP."),
        ],
    ),
    Tool(
        id="image_watermark", name="Watermark Image", icon="💧",
        tagline="Stamp text or a logo onto images.",
        mode=PER_FILE, accept=IMAGES, runner=processors.image_watermark, group="Edit",
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
    Tool(
        id="svg_to_image", name="SVG → Image", icon="🖼️",
        tagline="Rasterise SVG vector files to PNG, JPEG or WEBP.",
        mode=PER_FILE, accept=SVG, runner=processors.svg_to_image, group="Convert",
        options=[
            Option("format", "Output format", "choice", "png", [
                ("png", "PNG (transparent)"), ("jpg", "JPEG"), ("webp", "WEBP")]),
            Option("width", "Width (0 = SVG's own size)", "int", 1024,
                   minimum=0, maximum=20000, suffix=" px",
                   hint="Height scales to keep the aspect ratio."),
            Option("background", "Background", "choice", "transparent", [
                ("transparent", "Transparent (PNG/WEBP)"), ("white", "White")],
                   hint="JPEG has no transparency and always uses a background."),
        ],
    ),
    Tool(
        id="image_to_svg", name="Image → SVG", icon="✒️",
        tagline="Convert images to SVG — trace to vectors, or embed exactly.",
        mode=PER_FILE, accept=IMAGES, runner=processors.image_to_svg, group="Convert",
        options=[
            Option("mode", "Conversion", "choice", "trace", [
                ("trace", "Trace to vector paths (best for logos / line art)"),
                ("embed", "Embed image exactly (best for photos)")]),
            Option("colors", "Colours", "choice", "color", [
                ("color", "Full colour"), ("bw", "Black & white")],
                   visible_when=("mode", "trace")),
        ],
    ),
    Tool(
        id="file_properties", name="Edit File Properties", icon="🗂️",
        tagline="Bulk-set Date Created, Date Modified and Owner on any files.",
        mode=PER_FILE, accept={"*"}, runner=processors.set_file_properties,
        group="Files",
        options=[
            Option("date_created", "Date Created", "text", "",
                   hint="e.g. 2026-06-07 or 2026-06-07 14:30 — leave blank to keep. "
                        "(Windows)"),
            Option("date_modified", "Date Modified", "text", "",
                   hint="e.g. 2026-06-07 14:30, or 'now' — leave blank to keep."),
            Option("owner", "Owner", "text", "",
                   hint=r"Windows account, e.g. PC\\Name — needs admin; blank to keep."),
        ],
    ),
]

TOOLS_BY_ID = {t.id: t for t in TOOLS}

# Sidebar order for the job-based tool groups (tools are grouped by what you're
# doing, not by file type). Any group not listed falls to the end, alphabetically.
GROUP_ORDER = ["Convert", "Optimize", "Edit", "Organize", "Secure",
               "Recognize", "Files"]


def all_accept_exts() -> set:
    out: set = set()
    for t in TOOLS:
        out |= t.accept
    return out
