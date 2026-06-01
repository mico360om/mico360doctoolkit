"""Processing functions for every tool.

Each function has one of two signatures:

  per-file   : fn(src: Path, out_dir: Path, opt: dict, report) -> list[Path]
  aggregate  : fn(srcs: list[Path], out_dir: Path, opt: dict, report) -> list[Path]

``report(msg)`` writes a line to the activity log. Functions raise
``ProcessError`` with a user-readable message on failure.
"""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

from mico360.core.deps import find_ghostscript, find_libreoffice
from mico360.core.util import (
    ProcessError,
    build_output_path,
    human_size,
    run_subprocess,
    unique_dir,
    unique_path,
)

Report = Callable[[str], None]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _clampi(value, lo: int, hi: int, default: int) -> int:
    """Coerce *value* to an int within [lo, hi]. Guards against out-of-range
    numbers that bypass the UI spinboxes (e.g. a hand-edited settings file)."""
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _progress(report: Report, current: int, total: int) -> None:
    """Report fine-grained progress within a unit, if the caller supports it.

    The engine's report callable carries a ``.progress`` attribute; plain test
    callbacks don't, so we degrade gracefully to a no-op."""
    fn = getattr(report, "progress", None)
    if fn is not None:
        try:
            fn(current, total)
        except Exception:  # pragma: no cover - never let progress break a job
            pass


def _check_cancel(report: Report) -> None:
    """Raise ProcessError('Cancelled') if the user cancelled the batch — lets
    long per-page loops stop promptly instead of running to completion."""
    fn = getattr(report, "cancelled", None)
    if fn is not None and fn():
        raise ProcessError("Cancelled")


# =========================================================================
# PDF compression
# =========================================================================
# Ghostscript distiller presets keyed by our Low/Medium/High compression labels.
_GS_PRESET = {"low": "/printer", "medium": "/ebook", "high": "/screen"}
# Target image resolution / JPEG quality used by the built-in PyMuPDF fallback
# so the Low/Medium/High choice produces meaningfully different sizes even when
# Ghostscript is unavailable.
_FALLBACK_DPI = {"low": 200, "medium": 130, "high": 90}
_FALLBACK_QUALITY = {"low": 80, "medium": 60, "high": 45}


def pdf_compress(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    level = opt.get("level", "medium")
    out = build_output_path(src, out_dir, ".pdf", name_suffix="_compressed",
                            overwrite=opt.get("overwrite", False),
                            numbered=opt.get("same_as_source", False))
    before = src.stat().st_size

    if level == "target":
        target_bytes = max(1, int(opt.get("target_kb", 250))) * 1024
        _pdf_compress_to_target(src, out, target_bytes, before, report)
        return [out]

    gs = find_ghostscript()
    if gs:
        args = [
            gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
            "-dNOPAUSE", "-dBATCH", "-dQUIET", "-dSAFER",
            "-dDetectDuplicateImages=true", "-dCompressFonts=true",
            "-dSubsetFonts=true",
        ]
        if level == "custom":
            dpi = _clampi(opt.get("dpi", 150), 36, 600, 150)
            jpegq = _clampi(opt.get("jpeg_quality", 75), 10, 100, 75)
            args += [
                "-dPDFSETTINGS=/printer",
                "-dDownsampleColorImages=true", "-dColorImageDownsampleType=/Bicubic",
                f"-dColorImageResolution={dpi}",
                "-dDownsampleGrayImages=true", "-dGrayImageDownsampleType=/Bicubic",
                f"-dGrayImageResolution={dpi}",
                "-dDownsampleMonoImages=true", f"-dMonoImageResolution={max(dpi, 300)}",
                "-dAutoFilterColorImages=false", "-dColorImageFilter=/DCTEncode",
                f"-dJPEGQ={jpegq}",
            ]
        else:
            args.append(f"-dPDFSETTINGS={_GS_PRESET.get(level, '/ebook')}")
        args += [f"-sOutputFile={out}", str(src)]

        report(f"Ghostscript compressing ({level})…")
        try:
            proc = run_subprocess(args)
        except subprocess.TimeoutExpired:
            raise ProcessError(
                "Compression timed out (over 10 minutes). Try a lower compression "
                "level, or split very large PDFs first.")
        if proc.returncode != 0 or not out.exists():
            raise ProcessError(
                "Ghostscript failed: " + (proc.stderr or proc.stdout or "unknown error").strip()[:300]
            )
    else:
        report("Ghostscript not found — using built-in PyMuPDF compressor.")
        _pymupdf_compress(src, out, level, opt, report)

    after = out.stat().st_size
    pct = (1 - after / before) * 100 if before else 0
    report(f"{human_size(before)} → {human_size(after)} ({pct:+.0f}%)")
    if after >= before:
        report("Note: file was already well-optimized; little/no size reduction.")
    return [out]


def _pymupdf_compress(src: Path, out: Path, level: str, opt: dict, report: Report) -> None:
    """Built-in fallback used when Ghostscript is unavailable.

    Downsamples and re-encodes embedded raster images to a resolution / JPEG
    quality chosen by the compression *level* (text and vector content are kept
    intact), then rebuilds the file: garbage-collects unused objects, deflates
    streams/fonts, subsets fonts and cleans content. This makes the Low / Medium
    / High choice produce visibly different sizes. Ghostscript (bundled) remains
    the recommended engine for the most aggressive size reduction.
    """
    import fitz  # PyMuPDF

    if level == "custom":
        dpi_target = _clampi(opt.get("dpi", 150), 36, 600, 150)
        quality = _clampi(opt.get("jpeg_quality", 75), 10, 100, 75)
    else:
        dpi_target = _FALLBACK_DPI.get(level, _FALLBACK_DPI["medium"])
        quality = _FALLBACK_QUALITY.get(level, _FALLBACK_QUALITY["medium"])

    doc = fitz.open(src)
    try:
        # PyMuPDF >= 1.24 can downsample/recompress images in place. Only images
        # whose effective resolution exceeds the target are touched, so we never
        # upscale or bloat already-small images.
        if hasattr(doc, "rewrite_images"):
            try:
                # rewrite_images requires dpi_target < dpi_threshold: any image
                # above the threshold is downsampled to the target. Using
                # target + 1 means "normalize everything above the target DPI".
                doc.rewrite_images(
                    dpi_threshold=dpi_target + 1, dpi_target=dpi_target,
                    quality=quality, lossy=True, lossless=True,
                )
            except Exception as exc:  # pragma: no cover - version/feature guard
                report(f"Image recompression unavailable ({exc}); rebuilding only.")
        doc.save(str(out), garbage=4, deflate=True, deflate_images=True,
                 deflate_fonts=True, clean=True)
    finally:
        doc.close()


def _pdf_compress_to_target(src: Path, out: Path, target_bytes: int,
                            before: int, report: Report) -> None:
    """Compress a PDF to land at or just under *target_bytes*.

    Binary-searches a strength scale (image DPI + JPEG quality, applied via
    PyMuPDF's in-place image rewriter) for the gentlest setting whose output is
    still <= target, so quality is maximised without exceeding the size limit.
    All other settings are chosen automatically.
    """
    import fitz

    report(f"Targeting <= {human_size(target_bytes)} (auto-selecting settings)…")

    def produce(scale: int | None) -> int:
        # scale None = lossless rebuild (highest quality, no image re-encoding).
        # scale 0..100: higher = higher dpi/quality = larger file.
        doc = fitz.open(src)
        try:
            if scale is not None and hasattr(doc, "rewrite_images"):
                dpi = int(40 + scale / 100 * (250 - 40))
                quality = int(20 + scale / 100 * (88 - 20))
                try:
                    doc.rewrite_images(dpi_threshold=dpi + 1, dpi_target=dpi,
                                       quality=quality, lossy=True, lossless=True)
                except Exception:  # pragma: no cover
                    pass
            doc.save(str(out), garbage=4, deflate=True, deflate_images=True,
                     deflate_fonts=True, clean=True)
        finally:
            doc.close()
        return out.stat().st_size

    _TOTAL_STEPS = 10  # 1 lossless probe + up to 8 search probes + 1 final write

    # Best quality first: if a plain lossless rebuild already fits, keep it.
    if produce(None) <= target_bytes:
        _progress(report, _TOTAL_STEPS, _TOTAL_STEPS)
        achieved = out.stat().st_size
        pct = (1 - achieved / before) * 100 if before else 0
        report(f"{human_size(before)} → {human_size(achieved)} ({pct:+.0f}%, lossless)")
        return
    _progress(report, 1, _TOTAL_STEPS)

    lo, hi, best = 0, 100, None
    for step in range(8):  # ~log2(100) probes
        if lo > hi:
            break
        mid = (lo + hi) // 2
        size = produce(mid)
        _progress(report, 2 + step, _TOTAL_STEPS)
        if size <= target_bytes:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    # Materialise the chosen setting (last probe may not be the best one).
    final_scale = best if best is not None else 0
    achieved = produce(final_scale)
    _progress(report, _TOTAL_STEPS, _TOTAL_STEPS)

    pct = (1 - achieved / before) * 100 if before else 0
    report(f"{human_size(before)} → {human_size(achieved)} ({pct:+.0f}%)")
    if achieved > target_bytes:
        report("Note: the target is smaller than this PDF's text/vector content "
               "allows — produced the smallest possible instead.")


# =========================================================================
# Merge PDFs (aggregate)
# =========================================================================
def pdf_merge(srcs: list[Path], out_dir: Path, opt: dict, report: Report) -> list[Path]:
    from pypdf import PdfReader, PdfWriter

    if len(srcs) < 2:
        raise ProcessError("Select at least two PDF files to merge.")
    name = (opt.get("output_name") or "merged").strip() or "merged"
    out = unique_path(out_dir / f"{name}.pdf", opt.get("overwrite", False))
    out_dir.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter()
    total = 0
    for i, s in enumerate(srcs):
        report(f"Adding {s.name}")
        try:
            reader = PdfReader(str(s))
            pages = list(reader.pages)
        except Exception as exc:
            raise ProcessError(f"Couldn't read '{s.name}' — it may be corrupt or "
                               f"password-protected ({exc}).")
        for page in pages:
            writer.add_page(page)
        total += len(pages)
        _progress(report, i + 1, len(srcs))
    with open(out, "wb") as fh:
        writer.write(fh)
    report(f"Merged {len(srcs)} files / {total} pages → {out.name}")
    return [out]


# =========================================================================
# Split PDF (per-file → many outputs)
# =========================================================================
def pdf_split(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    from pypdf import PdfReader, PdfWriter

    try:
        reader = PdfReader(str(src))
        n = len(reader.pages)
    except Exception as exc:
        raise ProcessError(f"Couldn't read '{src.name}' — it may be corrupt or "
                           f"password-protected ({exc}).")
    mode = opt.get("mode", "each")
    overwrite = opt.get("overwrite", False)
    # Unique subfolder per source so two same-named PDFs from different folders
    # don't write into the same "stem/" directory and collide.
    dest = unique_dir(out_dir / src.stem)
    outputs: list[Path] = []

    def write_pages(indices: list[int], label: str) -> None:
        w = PdfWriter()
        for i in indices:
            w.add_page(reader.pages[i])
        p = unique_path(dest / f"{src.stem}_{label}.pdf", overwrite)
        with open(p, "wb") as fh:
            w.write(fh)
        outputs.append(p)
        report(f"Wrote {p.name}")

    if mode == "each":
        for i in range(n):
            _check_cancel(report)
            write_pages([i], f"page{i + 1}")
            _progress(report, i + 1, n)
    elif mode == "every_n":
        step = max(1, int(opt.get("every_n", 1)))
        for start in range(0, n, step):
            idx = list(range(start, min(start + step, n)))
            write_pages(idx, f"p{idx[0] + 1}-{idx[-1] + 1}")
            _progress(report, idx[-1] + 1, n)
    elif mode == "ranges":
        ranges = _parse_ranges(opt.get("ranges", ""), n)
        for j, (label, idx) in enumerate(ranges):
            write_pages(idx, label)
            _progress(report, j + 1, len(ranges) or 1)
        if not outputs:
            raise ProcessError("No valid page ranges were provided (e.g. '1-3, 5, 8-10').")
    else:
        raise ProcessError(f"Unknown split mode: {mode}")
    return outputs


def _parse_ranges(spec: str, n: int) -> list[tuple[str, list[int]]]:
    out: list[tuple[str, list[int]]] = []
    for chunk in spec.replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk:
            a, _, b = chunk.partition("-")
            try:
                start, end = int(a), int(b)
            except ValueError:
                continue
            start = max(1, start)
            end = min(n, end)
            if start <= end:
                out.append((f"p{start}-{end}", list(range(start - 1, end))))
        else:
            try:
                p = int(chunk)
            except ValueError:
                continue
            if 1 <= p <= n:
                out.append((f"page{p}", [p - 1]))
    return out


# =========================================================================
# Page-spec helpers shared by Organize PDF (1-based input → 0-based indices)
# =========================================================================
def _page_list(spec: str, n: int, default_all: bool = False) -> list[int]:
    """Parse a page spec like ``3, 1, 2, 5-8`` into an *ordered* list of 0-based
    indices (preserving the given order, ranges allowed in either direction).
    Empty / 'all' → every page when ``default_all`` else []."""
    spec = (spec or "").strip().lower()
    if spec in ("", "all"):
        return list(range(n)) if default_all else []
    out: list[int] = []
    for chunk in spec.replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk[1:]:  # a range (a leading '-' would be a stray sign)
            a, _, b = chunk.partition("-")
            try:
                start, end = int(a), int(b)
            except ValueError:
                continue
            rng = range(start, end + 1) if start <= end else range(start, end - 1, -1)
            out.extend(p - 1 for p in rng if 1 <= p <= n)
        else:
            try:
                p = int(chunk)
            except ValueError:
                continue
            if 1 <= p <= n:
                out.append(p - 1)
    return out


def _page_set(spec: str, n: int, default_all: bool = False) -> set:
    return set(_page_list(spec, n, default_all=default_all))


# =========================================================================
# Organize PDF — rotate / delete / extract / reorder pages
# =========================================================================
def pdf_organize(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    from pypdf import PdfReader, PdfWriter

    try:
        reader = PdfReader(str(src))
        n = len(reader.pages)
    except Exception as exc:
        raise ProcessError(f"Couldn't read '{src.name}' — it may be corrupt or "
                           f"password-protected ({exc}).")
    op = opt.get("operation", "rotate")
    writer = PdfWriter()

    if op == "rotate":
        angle = _clampi(opt.get("angle", 90), -270, 270, 90)
        if angle % 90 != 0:
            raise ProcessError("Rotation must be a multiple of 90°.")
        targets = _page_set(opt.get("pages", "all"), n, default_all=True)
        for i in range(n):
            page = reader.pages[i]
            if i in targets:
                page.rotate(angle)
            writer.add_page(page)
            _progress(report, i + 1, n)
        suffix = "_rotated"
    elif op == "delete":
        remove = _page_set(opt.get("del_pages", ""), n)
        if not remove:
            raise ProcessError("Enter the page(s) to delete, e.g. 2, 5-7.")
        kept = [i for i in range(n) if i not in remove]
        if not kept:
            raise ProcessError("That would delete every page.")
        for j, i in enumerate(kept):
            writer.add_page(reader.pages[i])
            _progress(report, j + 1, len(kept))
        suffix = "_pages-removed"
    elif op in ("extract", "reorder"):
        key = "ext_pages" if op == "extract" else "order"
        order = _page_list(opt.get(key, ""), n)
        if not order:
            raise ProcessError("Enter the pages, e.g. 3, 1, 2, 5-8.")
        for j, i in enumerate(order):
            writer.add_page(reader.pages[i])
            _progress(report, j + 1, len(order))
        suffix = "_extracted" if op == "extract" else "_reordered"
    else:
        raise ProcessError(f"Unknown operation: {op}")

    out = build_output_path(src, out_dir, ".pdf", name_suffix=suffix,
                            overwrite=opt.get("overwrite", False),
                            numbered=opt.get("same_as_source", False))
    with open(out, "wb") as fh:
        writer.write(fh)
    report(f"Saved {len(writer.pages)} page(s) → {out.name}")
    return [out]


# =========================================================================
# Protect / Unlock PDF — add or remove a password
# =========================================================================
def pdf_protect(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    from pypdf import PdfReader, PdfWriter

    op = opt.get("operation", "protect")
    pw = opt.get("password", "") or ""
    try:
        reader = PdfReader(str(src))
    except Exception as exc:
        raise ProcessError(f"Couldn't read '{src.name}' ({exc}).")

    if reader.is_encrypted:
        try:
            ok = bool(int(reader.decrypt(pw)))
        except Exception:
            ok = False
        if not ok:
            if op == "unlock":
                raise ProcessError("Incorrect password — couldn't unlock this PDF.")
            raise ProcessError("This PDF is already password-protected. Unlock it "
                               "with its current password first.")
    elif op == "unlock":
        report(f"'{src.name}' isn't password-protected — saving a copy.")

    writer = PdfWriter()
    try:
        for page in reader.pages:
            writer.add_page(page)
    except Exception as exc:
        raise ProcessError(f"Couldn't read pages from '{src.name}' ({exc}).")

    if op == "protect":
        if not pw:
            raise ProcessError("Enter a password to protect the PDF.")
        # Prefer strong AES-256 (needs `cryptography`); fall back to the
        # dependency-free RC4-128 so protection always works.
        try:
            writer.encrypt(user_password=pw, algorithm="AES-256")
        except Exception:
            try:
                writer.encrypt(user_password=pw, algorithm="RC4-128")
            except Exception:
                writer.encrypt(pw)
        suffix = "_protected"
    else:
        suffix = "_unlocked"

    out = build_output_path(src, out_dir, ".pdf", name_suffix=suffix,
                            overwrite=opt.get("overwrite", False),
                            numbered=opt.get("same_as_source", False))
    with open(out, "wb") as fh:
        writer.write(fh)
    report(f"{'Protected' if op == 'protect' else 'Unlocked'} → {out.name}")
    return [out]


# =========================================================================
# Watermark PDF — overlay diagonal text on every page
# =========================================================================
_WM_COLORS = {
    "gray": (0.5, 0.5, 0.5), "red": (0.78, 0.12, 0.12),
    "blue": (0.13, 0.27, 0.62), "black": (0.0, 0.0, 0.0),
}


def pdf_watermark(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    """Stamp a watermark on every page — either diagonal text or a logo/image."""
    opacity = _clampi(opt.get("opacity", 20), 1, 100, 20) / 100.0
    rotation = _clampi(opt.get("rotation", 45), -180, 180, 45)
    if opt.get("wm_type", "text") == "image":
        return _pdf_watermark_image(src, out_dir, opt, report, opacity, rotation)

    import fitz
    text = (opt.get("text") or "").strip()
    if not text:
        raise ProcessError("Enter the watermark text.")
    size = _clampi(opt.get("font_size", 48), 6, 400, 48)
    color = _WM_COLORS.get(opt.get("color", "gray"), (0.5, 0.5, 0.5))

    try:
        doc = fitz.open(str(src))
    except Exception as exc:
        raise ProcessError(f"Couldn't open '{src.name}' ({exc}).")
    try:
        for i, page in enumerate(doc):
            _check_cancel(report)
            rect = page.rect
            cx, cy = rect.width / 2.0, rect.height / 2.0
            tl = fitz.get_text_length(text, fontname="helv", fontsize=size)
            tw = fitz.TextWriter(rect, color=color)
            tw.append(fitz.Point(cx - tl / 2.0, cy + size * 0.30), text, fontsize=size)
            morph = (fitz.Point(cx, cy), fitz.Matrix(rotation))
            tw.write_text(page, opacity=opacity, morph=morph, overlay=True)
            _progress(report, i + 1, doc.page_count)
        out = build_output_path(src, out_dir, ".pdf", name_suffix="_watermarked",
                                overwrite=opt.get("overwrite", False),
                                numbered=opt.get("same_as_source", False))
        pages = doc.page_count
        doc.save(str(out), garbage=3, deflate=True)
    finally:
        doc.close()
    report(f"Watermarked {pages} page(s) → {out.name}")
    return [out]


def _pdf_watermark_image(src: Path, out_dir: Path, opt: dict, report: Report,
                         opacity: float, rotation: int) -> list[Path]:
    """Overlay a logo/image (PNG transparency honoured) centred on every page."""
    import os
    import tempfile

    import fitz
    from PIL import Image

    raw = (opt.get("image_path") or "").strip()
    if not raw:
        raise ProcessError("Choose a logo / image for the watermark.")
    imgpath = Path(raw)
    if not imgpath.exists():
        raise ProcessError(f"Watermark image not found: {raw}")
    try:
        logo = Image.open(imgpath).convert("RGBA")
    except Exception as exc:
        raise ProcessError(f"Couldn't open image '{imgpath.name}' ({exc}).")

    # Apply opacity to the alpha channel; rotate (transparent corners) if asked.
    if opacity < 1.0:
        logo.putalpha(logo.split()[3].point(lambda a: int(a * opacity)))
    if rotation % 360:
        logo = logo.rotate(rotation, expand=True, resample=Image.BICUBIC)
    scale = _clampi(opt.get("scale", 40), 5, 100, 40) / 100.0
    ratio = (logo.height / logo.width) if logo.width else 1.0

    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        logo.save(tmp, "PNG")
        try:
            doc = fitz.open(str(src))
        except Exception as exc:
            raise ProcessError(f"Couldn't open '{src.name}' ({exc}).")
        try:
            for i, page in enumerate(doc):
                _check_cancel(report)
                rect = page.rect
                w = rect.width * scale
                h = w * ratio
                cx, cy = rect.width / 2.0, rect.height / 2.0
                box = fitz.Rect(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
                page.insert_image(box, filename=tmp, overlay=True, keep_proportion=True)
                _progress(report, i + 1, doc.page_count)
            out = build_output_path(src, out_dir, ".pdf", name_suffix="_watermarked",
                                    overwrite=opt.get("overwrite", False),
                                    numbered=opt.get("same_as_source", False))
            pages = doc.page_count
            doc.save(str(out), garbage=3, deflate=True)
        finally:
            doc.close()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    report(f"Watermarked {pages} page(s) with {imgpath.name} → {out.name}")
    return [out]


# =========================================================================
# PDF → Word
# =========================================================================
def pdf_to_word(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    out = build_output_path(src, out_dir, ".docx", overwrite=opt.get("overwrite", False),
                            numbered=opt.get("same_as_source", False))

    # Scanned / image-only PDF + OCR enabled -> recognise text into a docx.
    if bool(opt.get("ocr", False)):
        import fitz
        doc = fitz.open(src)
        try:
            has_any_text = any(_page_has_text(p) for p in doc)
        finally:
            doc.close()
        if not has_any_text:
            _ocr_pdf_to_docx(src, out, report)
            return [out]

    try:
        from pdf2docx import Converter
    except Exception as exc:  # pragma: no cover
        raise ProcessError(f"pdf2docx is not available: {exc}")
    report("Converting layout to Word…")
    cv = Converter(str(src))
    try:
        cv.convert(str(out), start=0, end=None)
    finally:
        cv.close()
    if not out.exists():
        raise ProcessError("Conversion produced no output.")
    return [out]


def _ocr_pdf_to_docx(src: Path, out: Path, report: Report) -> None:
    """OCR every page of a scanned PDF into an editable .docx (python-docx)."""
    import fitz
    import docx

    engine = _make_ocr_engine()
    document = docx.Document()
    pdf = fitz.open(src)
    try:
        for i, page in enumerate(pdf):
            _check_cancel(report)
            report(f"OCR page {i + 1}/{pdf.page_count}…")
            # Reconstruct visual rows (fragments on the same line joined L→R,
            # ordered top→bottom) for clean, readable paragraphs.
            rows = _ocr_rows(_ocr_page_lines(engine, page))
            if i:
                document.add_page_break()
            if not rows:
                document.add_paragraph("(No text recognised on this page.)")
            prev_bottom = None
            for text, y_top, height in rows:
                # Insert a blank line where there's a clear vertical gap, so
                # paragraphs/headings stay visually separated.
                if prev_bottom is not None and (y_top - prev_bottom) > height * 1.2:
                    document.add_paragraph("")
                document.add_paragraph(text)
                prev_bottom = y_top + height
            _progress(report, i + 1, pdf.page_count)
        document.save(str(out))
    finally:
        pdf.close()
    if not out.exists():
        raise ProcessError("OCR produced no output.")


# =========================================================================
# OCR helpers (scanned / image-only pages → editable text)
# =========================================================================
# OCR is recognised at this DPI (higher = more accurate on small text, slower).
_OCR_DPI = 300
# Detections below this confidence are discarded as noise.
_OCR_MIN_SCORE = 0.5
# The RapidOCR engine loads several ONNX models; build it once and reuse it
# across every page and file in a batch instead of paying that cost per file.
_ocr_engine_cache = None
_ocr_engine_lock = threading.Lock()


def _make_ocr_engine():
    """Return a cached RapidOCR engine (models load once), or raise ProcessError."""
    global _ocr_engine_cache
    if _ocr_engine_cache is not None:
        return _ocr_engine_cache
    with _ocr_engine_lock:
        if _ocr_engine_cache is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except Exception as exc:  # pragma: no cover - optional dependency
                raise ProcessError(
                    "OCR engine is not available in this build. " + str(exc))
            _ocr_engine_cache = RapidOCR()
    return _ocr_engine_cache


def _page_has_text(page, threshold: int = 8) -> bool:
    return len(page.get_text("text").strip()) >= threshold


def _ocr_page_lines(engine, page, dpi: int = _OCR_DPI,
                    min_score: float = _OCR_MIN_SCORE) -> list[tuple[str, tuple]]:
    """OCR one page; return [(text, (x0, y0, x1, y1)] with coords in PDF points.

    Renders at ``dpi`` (clamped) for accuracy and drops detections whose
    confidence is below ``min_score`` so OCR noise doesn't leak into the output.
    """
    import numpy as np

    dpi = _clampi(dpi, 72, 400, _OCR_DPI)
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = np.ascontiguousarray(img[:, :, :3])
    elif pix.n == 1:
        img = np.ascontiguousarray(np.repeat(img, 3, axis=2))
    result, _ = engine(img)
    scale = 72.0 / dpi
    lines: list[tuple[str, tuple]] = []
    for box, text, score in (result or []):
        t = str(text).strip()
        if not t:
            continue
        try:
            if score is not None and float(score) < min_score:
                continue
        except (TypeError, ValueError):
            pass
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        lines.append((t, (min(xs) * scale, min(ys) * scale,
                          max(xs) * scale, max(ys) * scale)))
    return lines


def _ocr_rows(lines: list[tuple[str, tuple]]) -> list[tuple[str, float, float]]:
    """Group OCR fragments into visual rows for clean, readable output.

    Fragments whose vertical centres are within a tolerance of each other are
    treated as one line and joined left→right. Returns
    ``[(row_text, y_top, row_height)]`` ordered top→bottom.
    """
    if not lines:
        return []
    items = []  # (text, x0, y0, height, y_center)
    for text, (x0, y0, x1, y1) in lines:
        items.append((text, x0, y0, max(1.0, y1 - y0), (y0 + y1) / 2.0))
    heights = sorted(it[3] for it in items)
    med_h = heights[len(heights) // 2] or 10.0
    tol = max(4.0, med_h * 0.6)

    items.sort(key=lambda it: it[4])  # by vertical centre
    rows: list[list] = [[items[0]]]
    centre = items[0][4]
    for it in items[1:]:
        if abs(it[4] - centre) <= tol:
            rows[-1].append(it)
        else:
            rows.append([it])
        centre = sum(c[4] for c in rows[-1]) / len(rows[-1])

    out: list[tuple[str, float, float]] = []
    for row in rows:
        row.sort(key=lambda it: it[1])  # left → right
        text = " ".join(c[0] for c in row).strip()
        if not text:
            continue
        out.append((text, min(c[2] for c in row), max(c[3] for c in row)))
    return out


# =========================================================================
# PDF → PowerPoint  (one slide per page)
# =========================================================================
def pdf_to_pptx(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    """Turn each PDF page into a slide.

    ``mode`` controls how:
      * ``auto``  (default) — extract editable text boxes where the page has a
        real text layer; for image-only / scanned pages, OCR them (if enabled)
        or drop in the rendered page image so the slide is never empty.
      * ``text``  — editable text boxes only (small, fully editable).
      * ``image`` — render every page as an exact image (pixel-perfect look,
        not editable).

    ``ocr`` (bool) — when a page has no text layer, recognise its text so it
    still becomes editable text boxes instead of a flat image.
    """
    import tempfile

    import fitz
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Emu, Pt

    mode = opt.get("mode", "auto")
    ocr = bool(opt.get("ocr", False))
    ocr_engine = None
    out = build_output_path(src, out_dir, ".pptx", overwrite=opt.get("overwrite", False),
                            numbered=opt.get("same_as_source", False))
    doc = fitz.open(src)
    prs = Presentation()
    blank = prs.slide_layouts[6]
    EMU_PER_PT = 12700  # 914400 EMU per inch / 72 pt per inch

    def add_text_boxes(slide, page) -> int:
        boxes = 0
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type", 0) != 0:
                continue  # 0 = text block
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = "".join(s.get("text", "") for s in spans)
                x0, y0, x1, y1 = line["bbox"]
                tb = slide.shapes.add_textbox(
                    Emu(int(x0 * EMU_PER_PT)), Emu(int(y0 * EMU_PER_PT)),
                    Emu(int(max(2, x1 - x0) * EMU_PER_PT)),
                    Emu(int(max(8, y1 - y0) * EMU_PER_PT)))
                tf = tb.text_frame
                tf.word_wrap = False
                tf.margin_left = tf.margin_right = 0
                tf.margin_top = tf.margin_bottom = 0
                run = tf.paragraphs[0].add_run()
                run.text = text
                s0 = spans[0]
                run.font.size = Pt(max(6.0, float(s0.get("size", 12))))
                flags = int(s0.get("flags", 0))
                run.font.bold = bool(flags & 16)
                run.font.italic = bool(flags & 2)
                col = int(s0.get("color", 0))
                run.font.color.rgb = RGBColor((col >> 16) & 255, (col >> 8) & 255, col & 255)
                boxes += 1
        return boxes

    def add_ocr_boxes(slide, lines) -> int:
        for text, (x0, y0, x1, y1) in lines:
            tb = slide.shapes.add_textbox(
                Emu(int(x0 * EMU_PER_PT)), Emu(int(y0 * EMU_PER_PT)),
                Emu(int(max(2, x1 - x0) * EMU_PER_PT)),
                Emu(int(max(8, y1 - y0) * EMU_PER_PT)))
            tf = tb.text_frame
            tf.word_wrap = False
            tf.margin_left = tf.margin_right = 0
            tf.margin_top = tf.margin_bottom = 0
            run = tf.paragraphs[0].add_run()
            run.text = text
            run.font.size = Pt(max(7.0, min(40.0, (y1 - y0) * 0.85)))
        return len(lines)

    try:
        if doc.page_count:
            r0 = doc[0].rect
            prs.slide_width = Emu(int(r0.width * EMU_PER_PT))
            prs.slide_height = Emu(int(r0.height * EMU_PER_PT))
        with tempfile.TemporaryDirectory() as tmp:
            for i, page in enumerate(doc):
                _check_cancel(report)
                _progress(report, i, doc.page_count)
                slide = prs.slides.add_slide(blank)
                has_text = _page_has_text(page)
                if mode == "image":
                    pass  # always render the page image (below)
                elif has_text:
                    n = add_text_boxes(slide, page)
                    report(f"Slide {i + 1}/{doc.page_count} — {n} editable text box(es)")
                    continue
                elif ocr:
                    if ocr_engine is None:
                        ocr_engine = _make_ocr_engine()
                    n = add_ocr_boxes(slide, _ocr_page_lines(ocr_engine, page))
                    report(f"Slide {i + 1}/{doc.page_count} — {n} OCR text box(es)")
                    continue
                elif mode == "text":
                    report(f"Slide {i + 1}/{doc.page_count} — no text layer "
                           "(turn on OCR for scanned pages)")
                    continue
                # mode == image, or auto/text fallback to a page image
                pix = page.get_pixmap(dpi=150)
                img_path = Path(tmp) / f"p{i}.png"
                pix.save(str(img_path))
                slide.shapes.add_picture(str(img_path), 0, 0,
                                         width=prs.slide_width, height=prs.slide_height)
                report(f"Slide {i + 1}/{doc.page_count} — page image")
            prs.save(str(out))
    finally:
        doc.close()
    return [out]


# =========================================================================
# Word → PDF   (engine chain: LibreOffice → MS Word → built-in fallback)
# =========================================================================
def word_to_pdf(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    """Convert a Word document to PDF, trying the best available engine.

    Order: bundled/installed LibreOffice (highest fidelity, cross-platform) →
    Microsoft Word via COM (Windows, exact) → a built-in pure-Python renderer
    (text, headings, basic styling and tables) so it always produces a PDF even
    with nothing installed.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    final = build_output_path(src, out_dir, ".pdf", overwrite=opt.get("overwrite", False),
                              numbered=opt.get("same_as_source", False))
    errors: list[str] = []

    soffice = find_libreoffice()
    if soffice:
        try:
            _word_to_pdf_libreoffice(soffice, src, out_dir, final, report)
            return [final]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"LibreOffice: {exc}")

    try:
        if _word_to_pdf_msword(src, final, report):
            return [final]
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Microsoft Word: {exc}")

    try:
        _word_to_pdf_python(src, final, report)
        return [final]
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Built-in: {exc}")

    raise ProcessError("Word→PDF failed with every engine. " + " | ".join(errors))


def _word_to_pdf_libreoffice(soffice: str, src: Path, out_dir: Path,
                             final: Path, report: Report) -> None:
    report("LibreOffice converting to PDF…")
    args = [soffice, "--headless", "--norestore", "--convert-to", "pdf",
            "--outdir", str(out_dir), str(src)]
    proc = run_subprocess(args, timeout=300)
    produced = out_dir / f"{src.stem}.pdf"
    if proc.returncode != 0 or not produced.exists():
        raise RuntimeError((proc.stderr or proc.stdout or "no output").strip()[:200])
    if produced != final:
        if final.exists():
            final.unlink()
        produced.rename(final)


def _word_to_pdf_msword(src: Path, final: Path, report: Report) -> bool:
    """Use Microsoft Word via COM. Returns False if Word/docx2pdf isn't present."""
    try:
        from docx2pdf import convert
    except Exception:
        return False
    com_inited = False
    try:
        import pythoncom  # from pywin32; required for COM in a worker thread
        pythoncom.CoInitialize()
        com_inited = True
    except Exception:
        pass
    try:
        report("Microsoft Word converting to PDF…")
        convert(str(src), str(final))
    finally:
        if com_inited:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
    if not final.exists():
        raise RuntimeError("Word produced no output")
    return True


def _word_to_pdf_python(src: Path, final: Path, report: Report) -> None:
    """Pure-Python fallback: render the document's text with python-docx +
    reportlab. Preserves paragraphs, headings, bold/italic and simple tables —
    not exact layout, but always works with no external program."""
    import html

    import docx  # python-docx
    from docx.table import Table as _Tbl
    from docx.text.paragraph import Paragraph as _Par
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    report("Converting with the built-in engine…")
    document = docx.Document(str(src))
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontSize=11, leading=15)

    def heading_style(level: int) -> ParagraphStyle:
        size = max(12, 22 - 2 * level)
        return ParagraphStyle(f"h{level}", parent=styles["Normal"], fontSize=size,
                              leading=size + 4, spaceBefore=8, spaceAfter=4,
                              textColor=colors.HexColor("#1A1A1A"))

    def run_markup(par: _Par) -> str:
        parts = []
        for r in par.runs:
            t = html.escape(r.text or "")
            if not t:
                continue
            if r.bold:
                t = f"<b>{t}</b>"
            if r.italic:
                t = f"<i>{t}</i>"
            if r.underline:
                t = f"<u>{t}</u>"
            parts.append(t)
        return "".join(parts) or html.escape(par.text or "")

    flow: list = []
    # Walk the body in document order so paragraphs and tables stay interleaved.
    parent = document.element.body
    for child in parent.iterchildren():
        if child.tag.endswith("}p"):
            par = _Par(child, document)
            text = run_markup(par)
            if not text.strip():
                flow.append(Spacer(1, 6))
                continue
            name = (par.style.name or "").lower() if par.style else ""
            if name.startswith("heading") or name == "title":
                try:
                    level = int(name.split()[-1])
                except (ValueError, IndexError):
                    level = 1
                flow.append(Paragraph(text, heading_style(level)))
            else:
                flow.append(Paragraph(text, body_style))
        elif child.tag.endswith("}tbl"):
            tbl = _Tbl(child, document)
            data = [[Paragraph(html.escape(c.text or ""), body_style) for c in row.cells]
                    for row in tbl.rows]
            if data:
                t = Table(data, hAlign="LEFT")
                t.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B0B0B0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                flow.append(t)
                flow.append(Spacer(1, 8))

    if not flow:
        flow.append(Paragraph("(This document contained no extractable text.)", body_style))

    doc = SimpleDocTemplate(str(final), pagesize=LETTER,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch)
    doc.build(flow)
    if not final.exists():
        raise RuntimeError("no output produced")


# =========================================================================
# PDF → Image  (per-file → one image per page)
# =========================================================================
def pdf_to_image(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    import fitz

    fmt = opt.get("format", "png").lower()
    dpi = _clampi(opt.get("dpi", 150), 72, 600, 150)
    overwrite = opt.get("overwrite", False)
    ext = {"jpg": ".jpg", "jpeg": ".jpg", "png": ".png", "webp": ".webp",
           "tiff": ".tiff", "bmp": ".bmp"}.get(fmt, ".png")
    dest = unique_dir(out_dir / src.stem)
    doc = fitz.open(src)
    outputs: list[Path] = []
    try:
        for i, page in enumerate(doc):
            _check_cancel(report)
            pix = page.get_pixmap(dpi=dpi)
            p = unique_path(dest / f"{src.stem}_page{i + 1}{ext}", overwrite)
            if ext == ".png":
                pix.save(str(p))  # native, keeps any alpha
            else:
                # PyMuPDF's pix.save only handles a few formats; use Pillow for
                # jpg / webp / bmp / tiff to guarantee correct encoding.
                import io

                from PIL import Image
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                if ext == ".jpg":
                    img.save(p, quality=int(opt.get("jpeg_quality", 90)), optimize=True)
                else:
                    img.save(p)
            outputs.append(p)
            report(f"Page {i + 1}/{doc.page_count} → {p.name}")
            _progress(report, i + 1, doc.page_count)
    finally:
        doc.close()
    return outputs


# =========================================================================
# Image → PDF  (aggregate; one-per-image OR combined)
# =========================================================================
def image_to_pdf(srcs: list[Path], out_dir: Path, opt: dict, report: Report) -> list[Path]:
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    overwrite = opt.get("overwrite", False)
    combine = opt.get("combine", True)
    imgs = [s for s in srcs if s.suffix.lower() in IMAGE_EXTS]
    if not imgs:
        raise ProcessError("No supported image files were provided.")

    def load(p: Path) -> "Image.Image":
        im = Image.open(p)
        if im.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            return bg
        return im.convert("RGB")

    if combine:
        name = (opt.get("output_name") or "images").strip() or "images"
        out = unique_path(out_dir / f"{name}.pdf", overwrite)
        loaded = []
        for j, p in enumerate(imgs):
            loaded.append(load(p))
            _progress(report, j + 1, len(imgs))
        first, *rest = loaded
        first.save(out, save_all=True, append_images=rest)
        report(f"Combined {len(imgs)} images → {out.name}")
        return [out]

    outputs: list[Path] = []
    numbered = opt.get("same_as_source", False)
    for j, p in enumerate(imgs):
        _check_cancel(report)
        # For "save next to source" in this aggregate tool, each PDF must land
        # beside its OWN image — not all beside the first one (the engine passes
        # a single base dir for aggregate units).
        dest = p.parent if numbered else out_dir
        out = build_output_path(p, dest, ".pdf", overwrite=overwrite, numbered=numbered)
        load(p).save(out)
        outputs.append(out)
        report(f"{p.name} → {out.name}")
        _progress(report, j + 1, len(imgs))
    return outputs


# =========================================================================
# Image compression
# =========================================================================
_IMG_QUALITY = {"low": 85, "medium": 65, "high": 45}


def image_compress(src: Path, out_dir: Path, opt: dict, report: Report) -> list[Path]:
    from PIL import Image

    if src.suffix.lower() not in IMAGE_EXTS:
        raise ProcessError(f"Unsupported image type: {src.suffix}")
    level = opt.get("level", "medium")
    # The "quality" spinbox only applies in custom mode; for the Low/Medium/High
    # presets use the level's own quality so the choice actually takes effect.
    # (values() always reports the hidden spinbox, so we must branch on level.)
    if level == "custom":
        quality = _clampi(opt.get("quality", 65), 5, 100, 65)
    else:
        quality = _IMG_QUALITY.get(level, 65)
    out_format = opt.get("format", "keep")
    max_dim = _clampi(opt.get("max_dimension", 0), 0, 20000, 0)
    overwrite = opt.get("overwrite", False)
    before = src.stat().st_size

    try:
        im = Image.open(src)
        im.load()
    except Exception as exc:
        raise ProcessError(f"Couldn't open '{src.name}' — it may be corrupt or not "
                           f"a supported image ({exc}).")
    # Optional downscale
    if max_dim and max(im.size) > max_dim:
        ratio = max_dim / max(im.size)
        im = im.resize((int(im.width * ratio), int(im.height * ratio)), Image.LANCZOS)
        report(f"Resized to {im.width}x{im.height}")

    if out_format == "keep":
        ext = src.suffix.lower()
        if ext in (".tif", ".tiff", ".bmp"):
            ext = ".jpg"  # these don't benefit from lossy 'quality'; convert
    else:
        ext = {"jpg": ".jpg", "png": ".png", "webp": ".webp"}.get(out_format, ".jpg")

    # --- compress-to-target-size ---------------------------------------
    if level == "target":
        if ext == ".png":
            ext = ".jpg"  # need a lossy format to hit an arbitrary size
        target_bytes = max(1, int(opt.get("target_kb", 250))) * 1024
        out = build_output_path(src, out_dir, ext, name_suffix="_compressed",
                                overwrite=overwrite,
                                numbered=opt.get("same_as_source", False))
        after = _image_compress_to_target(im, out, ext, target_bytes, report)
        pct = (1 - after / before) * 100 if before else 0
        report(f"{human_size(before)} → {human_size(after)} ({pct:+.0f}%)")
        if after > target_bytes:
            report("Note: couldn't reach the target even at lowest quality / "
                   "smallest size; produced the smallest possible.")
        return [out]

    out = build_output_path(src, out_dir, ext, name_suffix="_compressed", overwrite=overwrite,
                            numbered=opt.get("same_as_source", False))
    save_kwargs: dict = {}
    if ext in (".jpg", ".jpeg"):
        im = im.convert("RGB")
        save_kwargs = {"quality": quality, "optimize": True, "progressive": True}
    elif ext == ".webp":
        save_kwargs = {"quality": quality, "method": 6}
    elif ext == ".png":
        if im.mode not in ("RGBA", "RGB", "P", "L"):
            im = im.convert("RGBA")
        save_kwargs = {"optimize": True}
    im.save(out, **save_kwargs)

    after = out.stat().st_size
    pct = (1 - after / before) * 100 if before else 0
    report(f"{human_size(before)} → {human_size(after)} ({pct:+.0f}%)")
    return [out]


def _encode_image(im, ext: str, quality: int) -> bytes:
    """Encode *im* to *ext* at *quality* in memory and return the bytes."""
    import io

    buf = io.BytesIO()
    work = im
    if ext in (".jpg", ".jpeg"):
        if work.mode != "RGB":
            work = work.convert("RGB")
        work.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    elif ext == ".webp":
        work.save(buf, "WEBP", quality=quality, method=6)
    else:  # pragma: no cover - target only uses lossy formats
        work.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _image_compress_to_target(im, out: Path, ext: str, target_bytes: int,
                              report: Report) -> int:
    """Save *im* as the largest-quality encoding that stays <= target_bytes,
    downscaling progressively if even the lowest quality is too big. Returns the
    achieved byte size."""
    from PIL import Image

    report(f"Targeting <= {human_size(target_bytes)} (auto-selecting quality)…")
    best: bytes | None = None
    scale = 1.0
    for _ in range(7):
        work = im if scale == 1.0 else im.resize(
            (max(1, int(im.width * scale)), max(1, int(im.height * scale))),
            Image.LANCZOS)
        lo, hi, found = 5, 95, None
        while lo <= hi:                       # binary search quality
            q = (lo + hi) // 2
            data = _encode_image(work, ext, q)
            if len(data) <= target_bytes:
                found = data
                lo = q + 1
            else:
                hi = q - 1
        if found is not None:
            best = found
            break
        scale *= 0.8                          # too big even at q=5 -> shrink
        if min(int(im.width * scale), int(im.height * scale)) < 24:
            best = _encode_image(work, ext, 5)
            break
    if best is None:
        best = _encode_image(im, ext, 5)
    out.write_bytes(best)
    return len(best)
