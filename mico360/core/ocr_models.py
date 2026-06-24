"""On-demand OCR language packs.

The bundled OCR recognises Latin scripts (English and other Western languages,
digits and punctuation). Other scripts — Arabic to begin with — need their own
recognition model, which would bloat the installer if shipped for everyone. So
each extra language is a small ONNX model (≈8 MB) downloaded once, on first use,
into a user-writable folder that survives app updates.

The text *detector* (which only finds where text is) is script-agnostic and is
always the bundled one; only the *recogniser* (which reads the glyphs) is
swapped per language, together with that language's character dictionary.
"""
from __future__ import annotations

import threading
from pathlib import Path

from mico360.logging_setup import get_logger
from mico360.paths import app_root, user_data_dir

log = get_logger("mico360.ocr_models")

_provision_lock = threading.Lock()


class OcrLanguage:
    """A selectable OCR language. ``model_url`` is None for the built-in Latin
    recogniser (no download, no recogniser swap)."""

    def __init__(self, lang_id, label, *, model_url=None, model_sha256=None,
                 model_size=0, keys_file=None, rtl=False):
        self.id = lang_id
        self.label = label
        self.model_url = model_url
        self.model_sha256 = model_sha256
        self.model_size = model_size
        self.keys_file = keys_file
        self.rtl = rtl

    @property
    def builtin(self) -> bool:
        return self.model_url is None


# Registry. Add new languages here — each just needs an ONNX recogniser whose
# CTC output matches its bundled character dictionary (dict + blank + space).
LANGUAGES: dict[str, OcrLanguage] = {
    "latin": OcrLanguage(
        "latin", "English / Latin"),
    "arabic": OcrLanguage(
        "arabic", "Arabic",
        # Official PaddlePaddle PP-OCRv5 mobile Arabic recogniser (ONNX).
        model_url="https://huggingface.co/PaddlePaddle/"
                  "arabic_PP-OCRv5_mobile_rec_onnx/resolve/main/inference.onnx",
        model_sha256="799113ebf267fbe742deb99eb36e8d42c9ddc5291ceacf92add41b4d52a59110",
        model_size=7998947,
        keys_file="arabic_keys.txt",
        rtl=True),
}

DEFAULT_LANG = "latin"


def language(lang_id: str | None) -> OcrLanguage:
    """The OcrLanguage for an id, falling back to Latin for unknown/empty."""
    return LANGUAGES.get((lang_id or DEFAULT_LANG).lower(), LANGUAGES[DEFAULT_LANG])


def language_choices() -> list[tuple[str, str]]:
    """(id, label) pairs for a UI selector, Latin first."""
    return [(lang.id, lang.label) for lang in LANGUAGES.values()]


def _keys_path(lang: OcrLanguage) -> Path | None:
    """Resolve a language's bundled character dictionary (works from source and
    from a PyInstaller bundle)."""
    if not lang.keys_file:
        return None
    p = app_root() / "mico360" / "core" / "ocr_data" / lang.keys_file
    return p if p.exists() else None


def model_dir(lang: OcrLanguage) -> Path:
    """User-writable folder where a downloaded recogniser lives (persists across
    app updates)."""
    return user_data_dir() / "ocr" / lang.id


def model_path(lang: OcrLanguage) -> Path:
    return model_dir(lang) / "rec.onnx"


def is_language_ready(lang_id: str | None) -> bool:
    """True if the language can be used right now without a download."""
    lang = language(lang_id)
    if lang.builtin:
        return True
    return model_path(lang).exists() and _keys_path(lang) is not None


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()


def ensure_language(lang_id, report=None, is_cancelled=None) -> dict | None:
    """Make a language usable, downloading its recogniser on first use.

    Returns None for the built-in Latin recogniser (the default engine is used
    as-is). For a downloaded language returns ``{"model_path", "keys_path",
    "rtl"}``. Raises :class:`ProcessError` if the model can't be provisioned.
    """
    from mico360.core.processors import ProcessError

    lang = language(lang_id)
    if lang.builtin:
        return None

    keys = _keys_path(lang)
    if keys is None:
        raise ProcessError(
            f"The {lang.label} OCR dictionary is missing from this build.")

    dest = model_path(lang)
    with _provision_lock:
        if not (dest.exists() and dest.stat().st_size == lang.model_size):
            from mico360.core.engines import _download
            if report:
                report(f"First-time setup: downloading the {lang.label} OCR "
                       f"model (~{round(lang.model_size / 1_000_000)} MB, one time)…")
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                _download(lang.model_url, dest, report, is_cancelled)
            except Exception as exc:  # noqa: BLE001
                raise ProcessError(
                    f"Couldn't download the {lang.label} OCR model ({exc}). "
                    "Check your internet connection and try again.")
            # Verify integrity; a corrupt model would silently produce garbage.
            if lang.model_sha256 and _sha256(dest) != lang.model_sha256:
                try:
                    dest.unlink()
                except OSError:
                    pass
                raise ProcessError(
                    f"The downloaded {lang.label} OCR model failed its integrity "
                    "check. Please try again.")
            if report:
                report(f"{lang.label} OCR model ready ✓")
    return {"model_path": str(dest), "keys_path": str(keys), "rtl": lang.rtl}
