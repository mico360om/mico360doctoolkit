"""On-demand provisioning of the LibreOffice conversion engine.

The installer ships WITHOUT LibreOffice (≈1 GB) to stay small. The engine is
downloaded once, on first use (or from Settings), into a user-writable folder
that survives app updates — so a user only ever pays the ~340 MB download once.

Windows only (MSI admin-install, no admin needed). On macOS/Linux the app uses an
installed LibreOffice; this module's download is a no-op there.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from mico360.logging_setup import get_logger
from mico360.paths import user_data_dir

log = get_logger("mico360.engines")

# Pinned LibreOffice build. Kept as a constant so it's easy to bump.
LO_VERSION = "26.2.3"
LO_MSI_URL = (f"https://download.documentfoundation.org/libreoffice/stable/"
              f"{LO_VERSION}/win/x86_64/LibreOffice_{LO_VERSION}_Win_x86-64.msi")
LO_DOWNLOAD_PAGE = "https://www.libreoffice.org/download/download-libreoffice/"

_CHUNK = 1 << 20          # 1 MB reads — fewer iterations on a fast link
_provision_lock = threading.Lock()


def engine_root() -> Path:
    """Where an on-demand LibreOffice is installed (user-writable, persists)."""
    return user_data_dir() / "engines" / "libreoffice"


def engine_soffice() -> Path:
    return engine_root() / "program" / "soffice.exe"


def is_engine_installed() -> bool:
    return engine_soffice().exists()


# --- download -------------------------------------------------------------
def _download(url: str, dest: Path, report=None, is_cancelled=None) -> None:
    """Resumable download with progress, reusing a ``.part`` file across retries."""
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "MICO360-Doc-Toolkit"}
    total: int | None = None
    stuck = 0
    while True:
        existing = part.stat().st_size if part.exists() else 0
        if total is not None and existing >= total > 0:
            break
        h = dict(headers)
        if existing:
            h["Range"] = f"bytes={existing}-"
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                ranged = getattr(resp, "status", 200) == 206
                if total is None:
                    cr = resp.headers.get("Content-Range") or ""
                    total = (int(cr.rsplit("/", 1)[-1]) if "/" in cr
                             else int(resp.headers.get("Content-Length") or 0) or None)
                if existing and not ranged:
                    existing = 0
                done = existing
                last = time.monotonic()
                with open(part, "ab" if existing else "wb") as fh:
                    while True:
                        if is_cancelled and is_cancelled():
                            raise RuntimeError("Cancelled")
                        chunk = resp.read(_CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        now = time.monotonic()
                        if report is not None and (now - last) >= 0.2:
                            last = now
                            fn = getattr(report, "progress", None)
                            if fn and total:
                                try:
                                    fn(done, total)
                                except Exception:
                                    pass
        except RuntimeError:
            raise
        except Exception as exc:  # network blip — resume
            log.info("engine download retry: %s", exc)
        new = part.stat().st_size if part.exists() else 0
        if total and new >= total:
            break
        if new <= existing:
            stuck += 1
            if stuck > 6:
                raise RuntimeError(
                    "The engine download kept stalling. Check your connection, or "
                    "install LibreOffice manually and set its path in Settings.")
            time.sleep(min(1.0 + stuck, 5.0))
        else:
            stuck = 0
    os.replace(part, dest)


def _extract_msi(msi: Path, report=None) -> None:
    """Admin-install (no admin) the MSI and stage LibreOffice into engine_root()."""
    import shutil

    extract = Path(tempfile.mkdtemp(prefix="mico360_lo_x"))
    if report:
        report("Installing the conversion engine (one-time)…")
    p = subprocess.run(
        ["msiexec.exe", "/a", str(msi), "/qn", f"TARGETDIR={extract}"],
        capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"engine install failed (msiexec {p.returncode})")
    found = next((f for f in extract.rglob("soffice.exe")), None)
    if not found:
        raise RuntimeError("engine files were not found after install")
    lo_root = found.parent.parent          # the dir that contains program/ + share/
    target = engine_root()
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(lo_root), str(target))
    shutil.rmtree(extract, ignore_errors=True)
    if not engine_soffice().exists():
        raise RuntimeError("engine staging failed")


def download_engine(report=None, is_cancelled=None) -> str:
    """Download + install LibreOffice on demand (Windows). Returns the soffice
    path. Serialised so a batch only ever downloads once. Raises on failure."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("On-demand engine download is Windows-only.")
    with _provision_lock:
        if is_engine_installed():
            return str(engine_soffice())
        tmp = Path(tempfile.gettempdir()) / f"LibreOffice_{LO_VERSION}.msi"
        if report:
            report("First-time setup: downloading the conversion engine "
                   "(~340 MB, one time)…")
        if not (tmp.exists() and tmp.stat().st_size > 200 * 1024 * 1024):
            _download(LO_MSI_URL, tmp, report, is_cancelled)
        _extract_msi(tmp, report)
        try:
            tmp.unlink()
        except OSError:
            pass
        if report:
            report("Conversion engine ready ✓")
        return str(engine_soffice())


def ensure_libreoffice(report=None, is_cancelled=None, auto: bool | None = None):
    """Return a usable LibreOffice path, downloading it on demand if needed and
    permitted. Returns None if it isn't available and can't/shouldn't be fetched
    (the caller then shows its 'needs LibreOffice' guidance)."""
    from mico360.core.deps import find_libreoffice
    found = find_libreoffice()
    if found:
        return found
    if auto is None:
        try:
            from mico360.config import settings
            auto = settings.auto_download_engine
        except Exception:
            auto = True
    if not auto or not sys.platform.startswith("win"):
        return None
    try:
        return download_engine(report, is_cancelled)
    except Exception as exc:  # noqa: BLE001
        if report:
            report(f"Couldn't set up the conversion engine ({exc}).")
        log.warning("engine provisioning failed: %s", exc)
        return None
