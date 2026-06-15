"""Qt glue for auto-update: background workers + the update dialog.

Kept apart from updater.py so the core logic stays Qt-free and unit-testable.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mico360 import __app_name__, __version__
from mico360 import updater
from mico360.core.util import human_size
from mico360.updater import UpdateInfo


# --- background workers --------------------------------------------------
class CheckWorker(QObject):
    """Runs updater.check_for_update() off the UI thread."""
    found = Signal(object)      # UpdateInfo
    up_to_date = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            info = updater.check_for_update()
        except Exception as exc:  # network / parse error
            self.failed.emit(str(exc))
            return
        if info:
            self.found.emit(info)
        else:
            self.up_to_date.emit()


class DownloadWorker(QObject):
    """Downloads + verifies the installer, reporting progress."""
    progress = Signal(int, int)   # done, total
    done = Signal(str)            # local path
    failed = Signal(str)

    def __init__(self, info: UpdateInfo):
        super().__init__()
        self._info = info
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            path = updater.download(
                self._info,
                progress=lambda d, t: self.progress.emit(d, t),
                is_cancelled=lambda: self._cancel,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.done.emit(path)


def _run_in_thread(parent, worker: QObject) -> QThread:
    """Move worker to a QThread, start it, and keep references alive on parent."""
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    # Keep python refs so they aren't GC'd mid-flight.
    if not hasattr(parent, "_update_threads"):
        parent._update_threads = []
    parent._update_threads.append((thread, worker))

    def _cleanup():
        thread.quit()
        thread.wait(2000)
        try:
            parent._update_threads.remove((thread, worker))
        except (ValueError, AttributeError):
            pass
    worker.destroyed.connect(lambda: None)
    thread._cleanup = _cleanup  # type: ignore[attr-defined]
    thread.start()
    return thread


class _CheckController(QObject):
    """Runs a CheckWorker on a background thread and delivers the result to the
    callbacks **on the GUI thread**.

    This object is parented to a main-thread widget and is NOT moved to the
    worker thread, so the worker's cross-thread signals are delivered to these
    slots via Qt's automatic queued connection — i.e. the callbacks (and any
    widgets they create, like the update dialog) run on the GUI thread.
    """

    def __init__(self, parent, on_found, on_up_to_date, on_failed):
        super().__init__(parent)
        self._callbacks = (on_found, on_up_to_date, on_failed)
        self._thread = QThread(self)
        self._worker = CheckWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.found.connect(self._on_found)
        self._worker.up_to_date.connect(self._on_up_to_date)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _finish(self, index: int, *args) -> None:
        self._thread.quit()
        self._thread.wait(3000)
        cb = self._callbacks[index]
        if cb:
            cb(*args)
        self.deleteLater()

    def _on_found(self, info) -> None:
        self._finish(0, info)

    def _on_up_to_date(self) -> None:
        self._finish(1)

    def _on_failed(self, msg: str) -> None:
        self._finish(2, msg)


def start_check(parent, on_found, on_up_to_date=None, on_failed=None) -> "_CheckController":
    """Check for updates off the GUI thread; deliver results on the GUI thread."""
    return _CheckController(parent, on_found, on_up_to_date, on_failed)


# --- dialog --------------------------------------------------------------
# Status → (badge text, Chip state). Chip states: ready/run/ok/err.
_STATES = {
    "available":   ("Available", "run"),
    "downloading": ("Downloading", "run"),
    "installing":  ("Installing", "run"),
    "completed":   ("Completed", "ok"),
    "failed":      ("Failed", "err"),
}


def _meta_label(caption: str, value: str) -> QWidget:
    """A small 'CAPTION: value' pair for the details row."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    cap = QLabel(caption)
    cap.setObjectName("UpdMetaCap")
    val = QLabel(value or "—")
    val.setObjectName("UpdMetaVal")
    row.addWidget(cap)
    row.addWidget(val)
    return w


def _notes_section(title: str, items: list, icon: str) -> QWidget | None:
    """A labelled bullet list for one category (or None when empty)."""
    if not items:
        return None
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 4, 0, 4)
    v.setSpacing(3)
    head = QLabel(f"{icon}  {title}")
    head.setObjectName("UpdSectionHead")
    v.addWidget(head)
    for it in items[:20]:
        b = QLabel(f"•  {it}")
        b.setObjectName("UpdBullet")
        b.setWordWrap(True)
        v.addWidget(b)
    return box


class UpdateDialog(QDialog):
    """A complete, professional update panel: app + versions, status badge, size,
    release date, categorised release notes (new features / fixes / security),
    live download progress with %/size/ETA, restart notice, and error + retry."""

    def __init__(self, info: UpdateInfo, parent: QWidget | None = None):
        super().__init__(parent)
        self._info = info
        self._thread: QThread | None = None
        self._worker: DownloadWorker | None = None
        self._t0 = 0.0
        self.setWindowTitle(f"Software Update — {__app_name__}")
        from mico360.ui.widgets import Chip, Divider, clamp_to_screen
        clamp_to_screen(self, 600, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        # --- header: app name + status badge ---------------------------
        header = QHBoxLayout()
        header.setSpacing(10)
        glyph = QLabel("🗂️")
        glyph.setObjectName("ToolIcon")
        header.addWidget(glyph, 0, Qt.AlignVCenter)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        app = QLabel(__app_name__)
        app.setObjectName("PageTitle")
        head_sub = QLabel("A software update is available")
        head_sub.setObjectName("PageSubtitle")
        titles.addWidget(app)
        titles.addWidget(head_sub)
        header.addLayout(titles, 1)
        self.badge = Chip(_STATES["available"][0], _STATES["available"][1])
        header.addWidget(self.badge, 0, Qt.AlignTop)
        root.addLayout(header)

        # --- versions + meta -------------------------------------------
        ver = QLabel(f"v{__version__}    →    v{info.version}")
        ver.setObjectName("UpdVersions")
        root.addWidget(ver)

        vmeta = QHBoxLayout()
        vmeta.setSpacing(18)
        vmeta.addWidget(_meta_label("Current version:", f"v{__version__}"))
        vmeta.addWidget(_meta_label("New version:", f"v{info.version}"))
        vmeta.addStretch(1)
        root.addLayout(vmeta)

        meta = QHBoxLayout()
        meta.setSpacing(18)
        size_txt = human_size(info.size) if info.size else "—"
        date_txt = updater.format_release_date(info.published_at) or "—"
        meta.addWidget(_meta_label("Download size:", size_txt))
        meta.addWidget(_meta_label("Released:", date_txt))
        meta.addStretch(1)
        root.addLayout(meta)

        # Direct GitHub repo link — so the user can always download manually.
        from mico360.config import settings as _settings
        from mico360.theme import palette as _palette
        _link = _palette(_settings.theme)["info"]
        gh = QLabel(
            f"Prefer to download manually? Get it directly from GitHub: "
            f"<a href='{updater.REPO_URL}/releases/latest' "
            f"style='color:{_link}; font-weight:600;'>{updater.REPO_SHORT}</a>")
        gh.setObjectName("UpdRepoLink")
        gh.setTextFormat(Qt.RichText)
        gh.setOpenExternalLinks(True)
        gh.setWordWrap(True)
        gh.setToolTip(updater.REPO_URL)
        root.addWidget(gh)

        line = Divider()
        root.addWidget(line)

        # --- categorised release notes (scrollable) --------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(2, 0, 2, 0)
        bv.setSpacing(6)
        whats_new = QLabel(f"What's new in v{info.version}")
        whats_new.setObjectName("SectionLabel")
        bv.addWidget(whats_new)

        cats = updater.categorize_notes(info.notes)
        added_any = False
        for key, title, icon in (
                ("features", "New features", "✨"),
                ("fixes", "Bugs fixed", "🐛"),
                ("security", "Security improvements", "🔒"),
                ("other", "Other changes", "•")):
            sec = _notes_section(title, cats.get(key, []), icon)
            if sec is not None:
                bv.addWidget(sec)
                added_any = True
        if not added_any:
            fallback = QLabel(
                info.notes.strip() if info.notes.strip()
                else "Release notes aren't available here — open the Release page "
                     "for full details.")
            fallback.setObjectName("UpdBullet")
            fallback.setWordWrap(True)
            bv.addWidget(fallback)
        bv.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # --- progress + status -----------------------------------------
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        root.addWidget(self.bar)

        self.progress_caption = QLabel("")
        self.progress_caption.setObjectName("ProgressCaption")
        self.progress_caption.setVisible(False)
        root.addWidget(self.progress_caption)

        self.status = QLabel("")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        root.addWidget(self.status)

        self.error = QLabel("")
        self.error.setObjectName("UpdError")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        root.addWidget(self.error)

        # --- buttons ---------------------------------------------------
        btns = QHBoxLayout()
        self.btn_page = QPushButton("Open on GitHub")
        self.btn_page.setObjectName("Ghost")
        self.btn_page.setCursor(Qt.PointingHandCursor)
        self.btn_page.setToolTip(f"Open {updater.REPO_SHORT} to download manually")
        self.btn_page.clicked.connect(self._open_page)
        self.btn_later = QPushButton("Later")
        self.btn_later.setObjectName("Ghost")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(self.reject)
        self.btn_retry = QPushButton("Retry")
        self.btn_retry.setObjectName("Ghost")
        self.btn_retry.setCursor(Qt.PointingHandCursor)
        self.btn_retry.setVisible(False)
        self.btn_retry.clicked.connect(self._start_download)
        self.btn_install = QPushButton("Download && Install")
        self.btn_install.setObjectName("Primary")
        self.btn_install.setCursor(Qt.PointingHandCursor)
        self.btn_install.setDefault(True)
        self.btn_install.clicked.connect(self._start_download)
        btns.addWidget(self.btn_page)
        btns.addStretch(1)
        btns.addWidget(self.btn_retry)
        btns.addWidget(self.btn_later)
        btns.addWidget(self.btn_install)
        root.addLayout(btns)

    # --- state ---------------------------------------------------------
    def _set_state(self, key: str) -> None:
        text, chip = _STATES[key]
        self.badge.set_state(chip, text)

    def _open_page(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(self._info.page))

    def _start_download(self) -> None:
        self._set_state("downloading")
        self.btn_install.setEnabled(False)
        self.btn_install.setVisible(False)
        self.btn_retry.setVisible(False)
        self.btn_page.setEnabled(True)
        self.error.setVisible(False)
        self.btn_later.setText("Cancel")
        try:
            self.btn_later.clicked.disconnect()
        except RuntimeError:
            pass
        self.btn_later.clicked.connect(self._cancel_download)

        self.bar.setVisible(True)
        self.bar.setRange(0, 0)            # busy until first byte
        self.progress_caption.setVisible(True)
        self.progress_caption.setText("Starting download…")
        self.status.setVisible(False)
        self._t0 = time.monotonic()

        self._worker = DownloadWorker(self._info)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread = _run_in_thread(self, self._worker)

    def _cancel_download(self) -> None:
        if self._worker:
            self._worker.cancel()
        self.progress_caption.setText("Cancelling…")

    @staticmethod
    def _eta(elapsed: float, done: int, total: int) -> str:
        if done <= 0 or total <= 0 or elapsed <= 0:
            return ""
        rate = done / elapsed
        if rate <= 0:
            return ""
        remaining = (total - done) / rate
        remaining = int(max(0, remaining))
        if remaining >= 60:
            return f"about {remaining // 60}m {remaining % 60:02d}s left"
        return f"about {remaining}s left"

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            pct = int(done * 100 / total)
            self.bar.setRange(0, 100)
            self.bar.setValue(pct)
            eta = self._eta(time.monotonic() - self._t0, done, total)
            parts = [f"{human_size(done)} / {human_size(total)}", f"{pct}%"]
            if eta:
                parts.append(eta)
            self.progress_caption.setText("Downloading update   ·   "
                                          + "   ·   ".join(parts))

    def _on_done(self, path: str) -> None:
        if self._thread:
            self._thread.quit()
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self._set_state("installing")
        self.progress_caption.setText("Download complete   ·   100%")
        self.status.setVisible(True)
        self.status.setText("↻  Installing the update — the app will close and "
                            "reopen automatically to finish. Please approve the "
                            "Windows prompt if it appears.")
        # Record what we're installing so the next launch can confirm success.
        try:
            from mico360.config import settings
            settings.pending_update = {"version": self._info.version,
                                       "started": time.time()}
        except Exception:
            pass
        try:
            updater.apply_and_exit(path)
        except Exception as exc:
            self._on_failed(f"Could not start the installer: {exc}")
            return
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _on_failed(self, msg: str) -> None:
        if self._thread:
            self._thread.quit()
        self._set_state("failed")
        self.bar.setVisible(False)
        self.progress_caption.setVisible(False)
        self.error.setVisible(True)
        self.error.setText(f"⚠  Update failed: {msg}")
        self.btn_install.setVisible(False)
        self.btn_retry.setVisible(True)
        self.btn_page.setEnabled(True)
        self.btn_later.setText("Close")
        try:
            self.btn_later.clicked.disconnect()
        except RuntimeError:
            pass
        self.btn_later.clicked.connect(self.reject)


# --- post-install confirmation ------------------------------------------
class UpdateCompletedDialog(QDialog):
    """Shown on first launch after a successful update: installed version + time."""

    def __init__(self, version: str, when_text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Update complete — {__app_name__}")
        from mico360.ui.widgets import clamp_to_screen
        clamp_to_screen(self, 440, 240)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(10)
        icon = QLabel("✅")
        icon.setObjectName("ToolIcon")
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        title = QLabel("Update completed successfully")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        msg = QLabel(f"{__app_name__} is now on <b>v{version}</b>.<br>"
                     f"Updated on {when_text}.")
        msg.setObjectName("PageSubtitle")
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        lay.addWidget(msg)
        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Great")
        ok.setObjectName("Primary")
        ok.setCursor(Qt.PointingHandCursor)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addLayout(row)


def maybe_show_update_completed(parent) -> None:
    """If we just updated (a pending marker exists and the running version now
    matches/exceeds it), show the completion confirmation and clear the marker."""
    try:
        from mico360.config import settings
        pend = settings.pending_update
    except Exception:
        return
    if not pend:
        return
    target = str(pend.get("version", ""))
    settings.pending_update = {}        # one-shot, whatever the outcome
    if not target:
        return
    if updater.parse_version(__version__) >= updater.parse_version(target):
        import datetime
        when = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
        try:
            UpdateCompletedDialog(target, when, parent).exec()
        except Exception:
            pass
