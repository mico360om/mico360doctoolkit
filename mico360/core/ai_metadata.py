"""AI metadata suggestions: read a document, propose document properties.

The document's own text is extracted locally (PyMuPDF / python-docx / pptx) and
only an excerpt is sent to the configured AI provider — never the whole file.
The model is asked for strict JSON, and the reply is parsed defensively because
small models like to wrap JSON in prose or code fences.

Nothing is ever written to the file here: this module only *suggests*. Applying
is the user's explicit choice in the UI.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mico360.core.ai import AiConfig, AiError, chat
from mico360.logging_setup import get_logger

log = get_logger("mico360.ai_metadata")

# Fields we ask for, in the order the UI shows them.
FIELDS = ("title", "author", "subject", "keywords", "comments", "category",
          "language")

FIELD_LABELS = {
    "title": "Title",
    "author": "Author",
    "subject": "Subject",
    "keywords": "Keywords",
    "comments": "Description / Comments",
    "category": "Category",
    "language": "Language",
}

# How much document text to send. Enough to characterise the document, well
# under the platform's 32,000-character prompt limit.
MAX_CHARS = 8000

_PROMPT = """You are a document cataloguing assistant. Read the document excerpt and \
return metadata for it.

Reply with ONE JSON object and nothing else. Use exactly these keys:
"title", "author", "subject", "keywords", "comments", "category", "language".

Rules:
- title: the document's real title, not the file name. Concise.
- author: only if the document clearly states one, else "".
- subject: one short line describing what the document is about.
- keywords: 3-8 comma-separated terms, lowercase.
- comments: a 1-2 sentence description.
- category: one short classifier, e.g. Report, Invoice, Contract, Manual, Article.
- language: the BCP-47 tag of the document's language, e.g. en-US, ar, fr-FR.
- Use "" for anything you cannot determine. Never invent an author or a date.

Document excerpt:
---
{excerpt}
---"""


class NoTextError(AiError):
    """The document has no extractable text (e.g. a scan needing OCR first)."""


# =====================================================================
# Local text extraction
# =====================================================================
def extract_text(path: Path, max_chars: int = MAX_CHARS) -> str:
    """Pull a representative text excerpt out of a document, locally.

    Raises NoTextError when there's nothing to read — a scanned PDF should be
    run through Searchable PDF (OCR) first, and we say so.
    """
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            text = _from_pdf(p, max_chars)
        elif ext == ".docx":
            import docx
            text = "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
        elif ext == ".pptx":
            from pptx import Presentation
            chunks = []
            for slide in Presentation(str(p)).slides:
                for shape in slide.shapes:
                    if getattr(shape, "has_text_frame", False):
                        chunks.append(shape.text_frame.text)
            text = "\n".join(chunks)
        elif ext in (".txt", ".md", ".csv"):
            text = p.read_text(encoding="utf-8", errors="replace")
        else:
            raise NoTextError(
                f"'{p.name}' isn't a text document the AI can read "
                "(PDF, Word, PowerPoint, text).")
    except NoTextError:
        raise
    except Exception as exc:      # noqa: BLE001
        raise AiError(f"Couldn't read '{p.name}' ({exc}).")

    text = re.sub(r"[ \t]+", " ", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 20:
        raise NoTextError(
            f"'{p.name}' has no selectable text. If it's a scan, run "
            "Searchable PDF (OCR) on it first, then try again.")
    return text[:max_chars]


def _from_pdf(p: Path, max_chars: int) -> str:
    """First pages carry the identity of a document; that's what we need."""
    import fitz
    doc = fitz.open(str(p))
    try:
        parts = []
        total = 0
        for i in range(min(doc.page_count, 10)):
            t = doc[i].get_text("text")
            if t:
                parts.append(t)
                total += len(t)
            if total >= max_chars:
                break
        return "\n".join(parts)
    finally:
        doc.close()


# =====================================================================
# Suggestion
# =====================================================================
def _parse_json_object(reply: str) -> dict:
    """Extract the JSON object from a model reply that may include prose or
    ```json fences."""
    s = (reply or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    if not s.startswith("{"):
        start, end = s.find("{"), s.rfind("}")
        if start >= 0 and end > start:
            s = s[start:end + 1]
    try:
        obj = json.loads(s)
    except (ValueError, TypeError):
        raise AiError("The AI reply couldn't be understood as metadata. "
                      "Try again, or use a larger model.")
    return obj if isinstance(obj, dict) else {}


def _clean(value) -> str:
    """Normalise one suggested value to a single tidy line."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    text = re.sub(r"\s+", " ", str(value)).strip()
    # Models sometimes echo a placeholder rather than leaving it empty.
    if text.lower() in ("n/a", "none", "unknown", "null", "not specified", "-"):
        return ""
    return text[:500]


def suggest_metadata(path: Path, cfg: AiConfig, excerpt: str | None = None) -> dict:
    """Return {field: suggested value} for a document. Raises AiError."""
    text = excerpt if excerpt is not None else extract_text(Path(path))
    reply = chat(cfg, [
        {"role": "system",
         "content": "You reply with a single JSON object and no other text."},
        {"role": "user", "content": _PROMPT.format(excerpt=text)},
    ])
    obj = _parse_json_object(reply)
    out = {}
    for key in FIELDS:
        val = _clean(obj.get(key))
        if val:
            out[key] = val
    if not out:
        raise AiError("The AI didn't return any usable metadata for this "
                      "document. Try again, or use a larger model.")
    log.info("AI suggested %d metadata field(s) for %s", len(out), Path(path).name)
    return out
