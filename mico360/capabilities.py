"""Per-user capability / access summary.

The desktop app has no login, but every install has a different effective
"access level": which optional modules are enabled, configured, or available on
that platform. This module reports that state so user-facing pages (Help) can
reflect what THIS user can actually do — AI, GPU OCR, the conversion engine, the
Explorer right-click menu, and platform/admin-gated features — instead of a
one-size-fits-all description.

Every probe is wrapped so a slow or failing check never breaks the page.
"""
from __future__ import annotations

import html
import sys


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        return p.netloc or url
    except Exception:
        return url


def _ai() -> tuple[str, str]:
    """(state, description). state in {'off','system','custom'}."""
    try:
        from mico360.core import ai as ai_core
        cfg = ai_core.load_config()
        ok, _ = cfg.is_usable()
        if not ok:
            return ("off", "Off — optional, and off by default. Turn it on in "
                           "Settings → AI (choose the System AI or your own "
                           "OpenAI-compatible API).")
        model = cfg.effective_model
        if cfg.source == ai_core.SOURCE_SYSTEM:
            return ("system", f"Active — using the System AI provided for you "
                              f"(model <b>{html.escape(model)}</b>).")
        return ("custom", "Active — using <b>your own</b> AI API at "
                          f"<b>{html.escape(_host(cfg.effective_base_url))}</b> "
                          f"(model <b>{html.escape(model)}</b>).")
    except Exception:
        return ("off", "Off.")


def _key_protection() -> str:
    try:
        from mico360.core import ai as ai_core
        if ai_core.is_strongly_protected():
            return ("Your saved AI API key is <b>encrypted with your Windows "
                    "account protection (DPAPI)</b> and never shown again.")
        return ("Your saved AI API key is stored obfuscated on this platform "
                "(no OS keychain integration yet) and never shown again.")
    except Exception:
        return "Your saved AI API key is stored securely and never shown again."


def _gpu_ocr() -> str:
    try:
        from mico360.config import settings
        if settings.ocr_use_gpu:
            return ("On — OCR uses a compatible graphics card automatically "
                    "when one is present (DirectML; any NVIDIA / AMD / Intel "
                    "GPU), and falls back to the CPU otherwise.")
        return "Off — OCR runs on the CPU. Enable it in Settings → Processing."
    except Exception:
        return "Automatic (GPU when available, else CPU)."


def _engine() -> str:
    try:
        from mico360.core import engines
        from mico360.core.deps import find_libreoffice
        if find_libreoffice():
            return "Ready — an existing LibreOffice on this PC is used."
        if engines.is_engine_installed():
            return "Ready — the conversion engine has been downloaded."
        from mico360.config import settings
        if settings.auto_download_engine:
            return ("Not yet installed — it downloads automatically (one time, "
                    "~340 MB) the first time you convert an Office file.")
        return ("Not installed, and automatic download is off — install "
                "LibreOffice, or download the engine in Settings → Advanced.")
    except Exception:
        return "Downloads automatically on first use."


def _ghostscript() -> str:
    try:
        from mico360.core.deps import find_ghostscript
        if find_ghostscript():
            return "Detected — used for the smallest lossy PDF compression."
        return ("Not found — the built-in compressor is used (lossless "
                "compression is unaffected).")
    except Exception:
        return "Optional — used for lossy PDF compression when present."


def _shell_menu() -> str:
    if not sys.platform.startswith("win"):
        return "Windows only — not available on this platform."
    try:
        from mico360 import shell_integration
        if shell_integration.is_registered():
            return ("On — right-click a supported file in File Explorer to send "
                    "it straight to a tool. Toggle in Settings → Advanced.")
        return ("Off — turn on \"Add MICO360 to the right-click menu\" in "
                "Settings → Advanced.")
    except Exception:
        return "Manage it in Settings → Advanced."


def _platform_note() -> str:
    if sys.platform == "darwin":
        return ("You're on <b>macOS</b>. The Explorer right-click menu, Windows "
                "DPAPI key encryption, and file-property <i>Owner</i> editing are "
                "Windows-only; everything else works the same.")
    if sys.platform.startswith("win"):
        return ("You're on <b>Windows</b>. Editing a file's <i>Owner</i> in Edit "
                "File Properties needs administrator rights and a valid Windows "
                "account; every other tool works without admin.")
    return "Some Windows/macOS-specific features may be unavailable here."


def capability_state() -> dict:
    """Structured state (used by tests and the HTML renderer)."""
    ai_state, ai_desc = _ai()
    return {
        "platform": sys.platform,
        "ai_state": ai_state,
        "ai": ai_desc,
        "key_protection": _key_protection(),
        "gpu_ocr": _gpu_ocr(),
        "engine": _engine(),
        "ghostscript": _ghostscript(),
        "shell_menu": _shell_menu(),
        "platform_note": _platform_note(),
    }


def capabilities_html() -> str:
    """A user-facing summary of what THIS user/install can currently do."""
    s = capability_state()
    return f"""
<p>This reflects <b>your</b> current setup — what's enabled and available to you
right now. Everything optional is off until you turn it on, and you can change
any of it in <b>Settings</b>.</p>
<ul>
  <li><b>AI suggestions:</b> {s['ai']}</li>
  <li><b>AI key storage:</b> {s['key_protection']}</li>
  <li><b>GPU-accelerated OCR:</b> {s['gpu_ocr']}</li>
  <li><b>Office conversion engine:</b> {s['engine']}</li>
  <li><b>Ghostscript (PDF compression):</b> {s['ghostscript']}</li>
  <li><b>Explorer right-click menu:</b> {s['shell_menu']}</li>
  <li><b>Your platform:</b> {s['platform_note']}</li>
</ul>
"""
