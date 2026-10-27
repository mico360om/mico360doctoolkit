"""AI provider client (OpenAI-compatible) and secure credential storage.

The app talks to any OpenAI-compatible endpoint — the MICO360 AI platform by
default, or whatever the user configures. Only two calls are needed: list models
(used by *Test connection*) and chat completions.

Security: the API key is **never stored in clear text**. On Windows it is sealed
with DPAPI (``CryptProtectData``), which ties it to the current user account, so
another user — or a copied settings file — cannot read it. The key is also never
shown again after saving; the UI only ever sees :func:`masked_key`.

Networking is stdlib-only (urllib), so no new dependency ships in the installer.
"""
from __future__ import annotations

import base64
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from mico360.logging_setup import get_logger

log = get_logger("mico360.ai")

# The administrator-provided default ("System AI"). Users can point elsewhere.
# HTTPS since October 2026: the server now has a certificate and no longer
# answers plain HTTP on this port at all.
SYSTEM_BASE_URL = "https://ai.mico360.com:5310/v1"
SYSTEM_MODEL = "qwen2.5:0.5b"
# What the System AI was called before it got TLS. A key saved while that was
# the address is still the System AI's key, so it moves over automatically.
_LEGACY_SYSTEM_ORIGINS = frozenset({"http://ai.mico360.com:5310"})

# A cold model load dominates the first request (~20s), so the platform's own
# guidance is a client timeout of at least 120s.
DEFAULT_TIMEOUT = 120
CONNECT_TEST_TIMEOUT = 30

# Transient statuses worth an automatic retry: 429 (rate/quota) and 503 (no node
# free right now — the platform queues work and a node may free up, and from
# relay 1.4.4 a 503 is refused before a job is created, so retrying is safe).
# 502 (the job ran and FAILED) and 504 ("the job may still be queued — do not
# blindly resubmit") are deliberately NOT retried. Retry-After is honoured.
RETRYABLE_STATUS = frozenset({429, 503})
MAX_RETRIES = 2
RETRY_BACKOFF_CAP = 8      # seconds; a longer Retry-After surfaces the message instead

SOURCE_SYSTEM = "system"
SOURCE_CUSTOM = "custom"


class AiError(Exception):
    """A user-facing AI failure — the message is safe to show as-is.
    ``status`` is the HTTP status when the server answered with an error."""

    def __init__(self, message: str = "", status: int | None = None):
        super().__init__(message)
        self.status = status


def sanitize_key(key: str) -> str:
    """An API key as it may be sent: every whitespace and control character
    removed. A pasted key with an embedded line break otherwise made
    http.client raise an error whose text contained the full key — which then
    reached the UI, the log file and crash reports."""
    return "".join(ch for ch in str(key or "")
                   if ch.isprintable() and not ch.isspace())


def _origin(url: str) -> str:
    """scheme://host:port of a URL (lower-case), '' if it has none."""
    try:
        u = urllib.parse.urlsplit(url or "")
        if not u.scheme or not u.hostname:
            return ""
        port = u.port or (443 if u.scheme == "https" else 80)
        return f"{u.scheme.lower()}://{u.hostname.lower()}:{port}"
    except ValueError:
        return ""


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects without leaking the API key: the Authorization header
    is dropped when a redirect leaves the original scheme/host/port, and an
    HTTPS → HTTP downgrade is refused outright."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if old.scheme == "https" and new.scheme != "https":
            raise urllib.error.HTTPError(
                req.full_url, code, "Refusing to follow an HTTPS → HTTP redirect",
                headers, fp)
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None and _origin(req.full_url) != _origin(newurl):
            for k in list(new_req.headers):
                if k.lower() == "authorization":
                    del new_req.headers[k]
            for k in list(new_req.unredirected_hdrs):
                if k.lower() == "authorization":
                    del new_req.unredirected_hdrs[k]
        return new_req


_opener = urllib.request.build_opener(_SafeRedirect)


# =====================================================================
# Secure key storage
# =====================================================================
def _dpapi(data: bytes, protect: bool) -> bytes | None:
    """Windows DPAPI seal/unseal, scoped to the current user. None if it fails."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        src = BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data),
                                          ctypes.POINTER(ctypes.c_char)))
        out = BLOB()
        fn = (ctypes.windll.crypt32.CryptProtectData if protect
              else ctypes.windll.crypt32.CryptUnprotectData)
        # (in, desc, entropy, reserved, prompt, flags, out)
        ok = fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out))
        if not ok:
            return None
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
    except Exception:            # noqa: BLE001 - never let crypto break the app
        return None


def seal_key(plain: str) -> str:
    """Encrypt an API key for storage. Returns an opaque string."""
    if not plain:
        return ""
    raw = plain.encode("utf-8")
    blob = _dpapi(raw, protect=True)
    if blob is not None:
        return "dpapi:" + base64.b64encode(blob).decode("ascii")
    # No DPAPI (macOS/Linux): store obfuscated, never clear text, and mark it so
    # the UI can tell the user it is only lightly protected on this platform.
    return "b64:" + base64.b64encode(raw).decode("ascii")


def unseal_key(stored: str) -> str:
    """Decrypt a stored API key. Empty string when unavailable."""
    if not stored:
        return ""
    try:
        if stored.startswith("dpapi:"):
            blob = base64.b64decode(stored[6:])
            raw = _dpapi(blob, protect=False)
            return raw.decode("utf-8") if raw else ""
        if stored.startswith("b64:"):
            return base64.b64decode(stored[4:]).decode("utf-8")
    except Exception:            # noqa: BLE001
        return ""
    return ""


def masked_key(plain: str) -> str:
    """A safe display form that never reveals more than about a third of the key.

    Long keys show a recognisable head and tail (``mico_••••••••7f42``); short
    keys reveal proportionally less, and anything under 12 characters is masked
    entirely — a fixed ``first-5 + last-4`` rule exposed 9 of an 11-character
    key (82%).
    """
    if not plain:
        return ""
    n = len(plain)
    if n < 12:                       # too short to reveal any part safely
        return "•" * n
    reveal = min(n // 3, 9)          # never reveal more than a third, capped at 9
    tail = min(4, reveal)
    head = min(5, reveal - tail)
    return f"{plain[:head]}{'•' * (n - head - tail)}{plain[-tail:]}"


def is_strongly_protected() -> bool:
    """True when the platform gives us OS-backed encryption (Windows DPAPI)."""
    return sys.platform.startswith("win")


# =====================================================================
# Configuration
# =====================================================================
@dataclass
class AiConfig:
    enabled: bool = False
    source: str = SOURCE_SYSTEM      # system | custom
    base_url: str = ""
    api_key: str = ""                # plain text, in memory only
    model: str = ""

    @property
    def effective_base_url(self) -> str:
        if self.source == SOURCE_SYSTEM:
            return SYSTEM_BASE_URL
        return normalize_base_url(self.base_url)

    @property
    def effective_model(self) -> str:
        return (self.model or "").strip() or SYSTEM_MODEL

    def is_usable(self) -> tuple[bool, str]:
        """(ok, why-not). A key is always required — the platform rejects
        anonymous calls with 401."""
        if not self.enabled:
            return False, "AI features are turned off in Settings."
        if not self.effective_base_url:
            return False, "No AI API URL is configured."
        if not self.api_key:
            return False, "No AI API key is configured."
        return True, ""


def normalize_base_url(url: str) -> str:
    """Tidy a user-typed base URL.

    People paste the bare host, or include the chat path, or a trailing slash.
    The server repairs some of this, but fixing it here means *Test connection*
    reports the truth about what will actually be called.
    """
    import re
    u = (url or "").strip()
    if not u:
        return ""
    if "://" not in u:
        # A bare host: HTTPS unless it's clearly a local/LAN server (Ollama,
        # LM Studio…), which speaks plain HTTP.
        host = u.split("/")[0].split(":")[0].lower()
        local = (host == "localhost"
                 or host.endswith(".local") or host.startswith("127.")
                 or host.startswith("10.") or host.startswith("192.168.")
                 or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host) is not None)
        u = ("http://" if local else "https://") + u
    parts = urllib.parse.urlsplit(u)
    path = parts.path.rstrip("/")
    # Strip an accidentally-pasted endpoint path.
    for tail in ("/chat/completions", "/models"):
        if path.endswith(tail):
            path = path[: -len(tail)]
    path = path.rstrip("/")
    # Add the OpenAI-compatible /v1 only when the URL has no API version of its
    # own — Gemini (/v1beta/openai), Azure (/openai/deployments/…) and other
    # providers are left exactly as given.
    low = path.lower()
    if not (re.search(r"/v\d+[a-z0-9]*(/|$)", low) or "/openai" in low
            or "/deployments/" in low):
        path += "/v1"
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc, path,
                                    parts.query, ""))


def url_problem(url: str) -> str:
    """Why a (normalised) base URL can't be used, or "" when it's fine — so
    Settings refuses "not a url", "ftp://…" or a bad port up front instead of
    saving it and failing later with a confusing network error."""
    u = (url or "").strip()
    if not u:
        return "Enter the address of your AI API, for example https://api.example.com/v1"
    if any(ch.isspace() for ch in u):
        return "The API address can't contain spaces."
    try:
        parts = urllib.parse.urlsplit(u)
        port = parts.port                  # raises for a port out of range
    except ValueError:
        return "The port in the API address isn't valid (it must be 1-65535)."
    if parts.scheme not in ("http", "https"):
        return "The API address must start with http:// or https://."
    host = parts.hostname or ""
    if not host or not re.fullmatch(r"[A-Za-z0-9.\-]+|[0-9a-fA-F:]+", host) \
            or host.startswith(".") or ".." in host:
        return "The API address needs a valid server name, for example api.example.com."
    if port == 0:
        return "The port in the API address isn't valid (it must be 1-65535)."
    return ""


def _join_url(base: str, path: str) -> str:
    """base + endpoint path, keeping a query string (e.g. Azure's
    ?api-version=…) at the end where it belongs."""
    parts = urllib.parse.urlsplit(base)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc,
                                    parts.path.rstrip("/") + path, parts.query, ""))


# =====================================================================
# HTTP
# =====================================================================
def _retry_after_seconds(exc, fallback: float) -> float:
    """Seconds to wait before a retry, honouring a numeric ``Retry-After``
    header when the server sends one. HTTP-date forms fall back to our backoff."""
    hdr = None
    try:
        headers = getattr(exc, "headers", None)
        if headers is not None:
            hdr = headers.get("Retry-After")
    except Exception:           # noqa: BLE001 - a header must never break a request
        hdr = None
    if hdr:
        try:
            return max(0.0, float(hdr))
        except (TypeError, ValueError):
            return fallback
    return fallback


def _request(cfg: AiConfig, path: str, payload=None, timeout=DEFAULT_TIMEOUT,
             retries: int = 0, cancel=None):
    """Call the API. ``retries`` auto-retries transient 429/503 responses
    (honouring Retry-After). ``cancel`` is an optional event-like object with
    ``is_set()``/``wait()`` — when set it aborts the wait between retries so a
    user's Cancel is felt immediately rather than after the backoff."""
    base = cfg.effective_base_url
    if not base:
        raise AiError("No AI API URL is configured.")
    url = _join_url(base, path)
    data = None
    headers = {
        "Authorization": f"Bearer {sanitize_key(cfg.api_key)}",
        "Accept": "application/json",
        "User-Agent": "MICO360-Doc-Toolkit",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    attempt = 0
    while True:
        if cancel is not None and cancel.is_set():
            raise AiError("Cancelled.")
        try:
            with _opener.open(req, timeout=timeout) as resp:  # noqa: S310
                body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as exc:
            transient = (exc.code in RETRYABLE_STATUS and attempt < retries
                         and not (cancel is not None and cancel.is_set()))
            if transient:
                wait = _retry_after_seconds(
                    exc, fallback=min(2 * (attempt + 1), RETRY_BACKOFF_CAP))
                # A very long Retry-After means "stop retrying in a tight loop";
                # surface the server's message instead of blocking for minutes.
                if wait <= RETRY_BACKOFF_CAP:
                    if cancel is not None:
                        if cancel.wait(wait):
                            raise AiError("Cancelled.")
                    else:
                        time.sleep(wait)
                    attempt += 1
                    continue
            raise AiError(_http_message(exc, url), status=exc.code)
        except urllib.error.URLError as exc:
            raise AiError(f"Couldn't reach the AI server at {base} "
                          f"({getattr(exc, 'reason', exc)}). Check the URL, the "
                          "port and your connection.")
        except TimeoutError:
            raise AiError("The AI server took too long to respond. Large models "
                          "can need up to two minutes on the first request — try "
                          "again.")
        except json.JSONDecodeError:
            raise AiError("The AI server replied with something that isn't JSON. "
                          "That address may be a website rather than an AI API — "
                          "check the base URL includes the port and /v1.")
        except http.client.HTTPException as exc:
            # A truncated / malformed response (IncompleteRead, BadStatusLine, …)
            # is an HTTPException, not an OSError — it would otherwise escape raw.
            raise AiError(f"The AI server at {base} sent an incomplete or "
                          f"malformed response ({type(exc).__name__}). Try again "
                          "in a moment.")
        except OSError as exc:
            # A connection dropped/reset/aborted *while reading the response* is
            # not wrapped in URLError by urllib (it escapes getresponse() raw),
            # so catch it here and give friendly guidance, not a WinError code.
            raise AiError(f"The connection to the AI server at {base} was "
                          f"interrupted ({exc}). Check your connection and try "
                          "again.")
        except (ValueError, UnicodeError):
            # e.g. "Invalid header value b'Bearer <key>'" — never echo the text,
            # it can contain the key.
            raise AiError("The API key or URL contains characters that can't be "
                          "sent. Re-paste the key in Settings → AI provider.")


def _http_message(exc, url: str) -> str:
    """Turn an HTTP status into advice the user can act on."""
    code = getattr(exc, "code", 0)
    detail = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
        obj = json.loads(body)
        detail = (obj.get("error", {}) or {}).get("message", "") \
            if isinstance(obj.get("error"), dict) else str(obj.get("error", ""))
    except Exception:            # noqa: BLE001
        pass
    hints = {
        400: "The request wasn't accepted." ,
        401: "The API key was rejected. Check you pasted the whole key and that "
             "it belongs to this server.",
        403: "This key isn't allowed to use that capability.",
        404: f"No API endpoint at {url}. The base URL usually needs the port and "
             "/v1 — for example https://ai.mico360.com:5310/v1",
        413: "The document is too large for the AI server.",
        429: "Rate limit or quota reached. Wait a moment and try again.",
        502: "The AI job ran but failed on the server.",
        503: "No AI node is free right now. Try again shortly.",
        504: "The AI server timed out waiting for a node.",
    }
    msg = hints.get(code, f"The AI server returned HTTP {code}.")
    return f"{msg} ({detail})" if detail else msg


def list_models(cfg: AiConfig) -> list[str]:
    """Model ids the key may use, in order, de-duplicated and free of blanks.

    A server that returns a whitespace-only or repeated id must not put an empty
    or duplicate entry in the dropdown. Raises AiError with a readable reason.
    """
    data = _request(cfg, "/models", timeout=CONNECT_TEST_TIMEOUT)
    items = data.get("data") or []
    out: list[str] = []
    seen: set[str] = set()
    for m in items:
        if not (isinstance(m, dict) and m.get("id")):
            continue
        mid = str(m["id"]).strip()
        if mid and mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


def test_connection(cfg: AiConfig) -> tuple[bool, str]:
    """(ok, message) — used by the Test connection button. Never raises."""
    ok, why = cfg.is_usable()
    if not ok and why.startswith("AI features are turned off"):
        pass                      # allow testing before enabling
    elif not ok:
        return False, why
    try:
        models = list_models(cfg)
    except AiError as exc:
        return False, str(exc)
    except Exception as exc:      # noqa: BLE001
        # Only the type: exception text may include request headers (the key).
        return False, f"Unexpected error ({type(exc).__name__})."
    if not models:
        return True, ("Connected, but the server offers no models to this key. "
                      "Ask an administrator to enable one.")
    want = cfg.effective_model
    if want in models:
        return True, f"Connected. Using '{want}'. {len(models)} model(s) available."
    return True, (f"Connected — {len(models)} model(s) available, but '{want}' "
                  f"isn't one of them. Try: {', '.join(models[:4])}")


_THINK_RE = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)


def chat(cfg: AiConfig, messages: list[dict], timeout: int = DEFAULT_TIMEOUT,
         max_tokens: int | None = None, retries: int = MAX_RETRIES,
         cancel=None, temperature: float | None = None) -> str:
    """Send a chat completion and return the assistant's text.

    Transient 429/503 responses are retried automatically (``retries``); pass a
    ``cancel`` event-like object to abort the wait between retries promptly.

    ``temperature`` 0 makes structured answers repeatable, but not every
    OpenAI-compatible server accepts it — a 400/422 is retried once without it.
    (JSON mode is deliberately not used: it sent small models into endless
    repetition.) A reasoning model's ``<think>…</think>`` preamble is removed.
    """
    ok, why = cfg.is_usable()
    if not ok:
        raise AiError(why)
    payload = {"model": cfg.effective_model, "messages": messages, "stream": False}
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    extras = {}
    if temperature is not None:
        extras["temperature"] = float(temperature)
    try:
        data = _request(cfg, "/chat/completions", {**payload, **extras},
                        timeout=timeout, retries=retries, cancel=cancel)
    except AiError as exc:
        if not extras or exc.status not in (400, 422):
            raise
        log.info("AI server rejected the temperature setting (HTTP %s); "
                 "retrying without it", exc.status)
        data = _request(cfg, "/chat/completions", payload, timeout=timeout,
                        retries=retries, cancel=cancel)
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise AiError("The AI server's reply didn't contain any text.")
    return _THINK_RE.sub("", str(text)).strip()


# =====================================================================
# Settings bridge
# =====================================================================
_SCRAMBLE = b"MICO360-Doc-Toolkit/system-ai"


def scramble_key(key: str) -> str:
    """Reversible scrambling for the System AI key built into the app, so it
    isn't readable as plain text in the program files. (Not encryption: an app
    can always recover a key it ships with — use a key meant for the app.)"""
    raw = key.encode("utf-8")
    return base64.b64encode(bytes(b ^ _SCRAMBLE[i % len(_SCRAMBLE)]
                                  for i, b in enumerate(raw))).decode("ascii")


def _unscramble(text: str) -> str:
    try:
        raw = base64.b64decode(text or "")
        return bytes(b ^ _SCRAMBLE[i % len(_SCRAMBLE)]
                     for i, b in enumerate(raw)).decode("utf-8")
    except (ValueError, UnicodeError):
        return ""


def builtin_system_key() -> str:
    """The System AI key built into this copy of the app ("" if none). The
    build writes it to mico360/_build_secrets.py from build/system_ai.key or
    the MICO360_SYSTEM_AI_KEY environment variable — never into the source."""
    import os
    env = sanitize_key(os.environ.get("MICO360_SYSTEM_AI_KEY", ""))
    if env:
        return env
    try:
        from mico360 import _build_secrets
    except ImportError:
        return ""
    return sanitize_key(_unscramble(getattr(_build_secrets, "SYSTEM_AI_KEY", "")))


def is_system_url(base_url: str) -> bool:
    return bool(base_url) and _origin(base_url) == _origin(SYSTEM_BASE_URL)


def stored_key_for(base_url: str) -> str:
    """The saved API key, but only for the server it was saved for. Typing a
    new custom URL must not send the saved key (e.g. the System-AI key) to that
    host. A key saved before this check existed is bound on first use to the
    server it was configured with. The System AI falls back to the key built
    into the app, which is never sent anywhere else."""
    from mico360.config import settings
    key = sanitize_key(unseal_key(settings.ai_api_key_sealed))
    want = _origin(base_url)
    if key:
        bound = settings.ai_key_origin
        if not bound:
            saved = AiConfig(source=settings.ai_source, base_url=settings.ai_base_url)
            bound = _origin(saved.effective_base_url)
            if bound:
                settings.ai_key_origin = bound
        if bound in _LEGACY_SYSTEM_ORIGINS and is_system_url(base_url):
            # Saved for the System AI before it moved to HTTPS: same server,
            # same key — rebind rather than make the user paste it again.
            settings.ai_key_origin = bound = _origin(SYSTEM_BASE_URL)
            log.info("System AI key re-bound to its HTTPS address")
        if want and want == bound:
            return key
    return builtin_system_key() if is_system_url(base_url) else ""


def load_config() -> AiConfig:
    """Build an AiConfig from saved settings (decrypting the key)."""
    from mico360.config import settings
    cfg = AiConfig(
        enabled=settings.ai_enabled,
        source=settings.ai_source,
        base_url=settings.ai_base_url,
        model=settings.ai_model,
    )
    cfg.api_key = stored_key_for(cfg.effective_base_url)
    return cfg


def save_config(cfg: AiConfig, api_key: str | None = None) -> None:
    """Persist settings. ``api_key`` is sealed; pass None to keep the stored one."""
    from mico360.config import settings
    settings.ai_enabled = cfg.enabled
    settings.ai_source = cfg.source
    settings.ai_base_url = cfg.base_url
    settings.ai_model = cfg.model
    if api_key is not None:
        settings.ai_api_key_sealed = seal_key(sanitize_key(api_key))
        settings.ai_key_origin = _origin(cfg.effective_base_url)
