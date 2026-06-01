"""Qt glue for auto-update: background workers + the update dialog.

Kept apart from updater.py so the core logic stays Qt-free and unit-testable.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mico360 import __app_name__, __version__
from mico360 import updater
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


def start_check(parent, on_found, on_up_to_date=None, on_failed=None) -> QThread:
    worker = CheckWorker()
    thread = _run_in_thread(parent, worker)

    def finish(fn, *args):
        if fn:
            fn(*args)
        thread.quit()
    worker.found.connect(lambda info: finish(on_found, info))
    worker.up_to_date.connect(lambda: finish(on_up_to_date))
    worker.failed.connect(lambda msg: finish(on_failed, msg))
    return thread


# --- dialog --------------------------------------------------------------
class UpdateDialog(QDialog):
    """Shows release notes and drives download + install."""

    def __init__(self, info: UpdateInfo, parent: QWidget | None = None):
        super().__init__(parent)
        self._info = info
        self._thread: QThread | None = None
        self._worker: DownloadWorker | None = None
        self.setWindowTitle(f"Update available — {__app_name__}")
        self.resize(560, 480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        title = QLabel(f"Version {info.version} is available")
        title.setObjectName("PageTitle")
        lay.addWidget(title)
        sub = QLabel(f"You have v{__version__}. Review what's new, then update.")
        sub.setObjectName("PageSubtitle")
        lay.addWidget(sub)

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(info.notes or "_No release notes provided._")
        lay.addWidget(notes, 1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        lay.addWidget(self.bar)

        self.status = QLabel("")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.btn_page = QPushButton("Release page")
        self.btn_page.setObjectName("Ghost")
        self.btn_page.clicked.connect(self._open_page)
        self.btn_later = QPushButton("Later")
        self.btn_later.setObjectName("Ghost")
        self.btn_later.clicked.connect(self.reject)
        self.btn_install = QPushButton("Download && Install")
        self.btn_install.setObjectName("Primary")
        self.btn_install.setDefault(True)
        self.btn_install.clicked.connect(self._start_download)
        btns.addWidget(self.btn_page)
        btns.addStretch(1)
        btns.addWidget(self.btn_later)
        btns.addWidget(self.btn_install)
        lay.addLayout(btns)

    def _open_page(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(self._info.page))

    def _start_download(self) -> None:
        self.btn_install.setEnabled(False)
        self.btn_page.setEnabled(False)
        self.btn_later.setText("Cancel")
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)  # busy until first progress
        self.status.setText("Downloading update…")

        self._worker = DownloadWorker(self._info)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread = _run_in_thread(self, self._worker)
        # Repurpose "Cancel" to abort the download.
        self.btn_later.clicked.disconnect()
        self.btn_later.clicked.connect(self._cancel_download)

    def _cancel_download(self) -> None:
        if self._worker:
            self._worker.cancel()
        self.status.setText("Cancelling…")

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(done * 100 / total))
            mb = lambda n: f"{n / (1024*1024):.1f} MB"
            self.status.setText(f"Downloading… {mb(done)} / {mb(total)}")

    def _on_done(self, path: str) -> None:
        if self._thread:
            self._thread.quit()
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.status.setText("Download complete. Launching the installer — "
                            "the app will close to finish updating.")
        try:
            updater.apply_and_exit(path)
        except Exception as exc:
            self.status.setText(f"Could not start the installer: {exc}")
            return
        # Quit the app so files can be replaced.
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _on_failed(self, msg: str) -> None:
        if self._thread:
            self._thread.quit()
        self.bar.setVisible(False)
        self.status.setText(f"Update failed: {msg}")
        self.btn_install.setEnabled(True)
        self.btn_page.setEnabled(True)
        self.btn_later.setText("Close")
        try:
            self.btn_later.clicked.disconnect()
        except RuntimeError:
            pass
        self.btn_later.clicked.connect(self.reject)
