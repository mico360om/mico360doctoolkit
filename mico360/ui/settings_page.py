"""Settings page: appearance, output, performance, external dependencies."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mico360 import __app_name__, __version__, legal
from mico360.config import settings
from mico360.core.deps import find_ghostscript, find_libreoffice
from mico360.paths import logs_dir
from mico360.theme import palette
from mico360.ui.widgets import Card, section_label


class SettingsPage(QWidget):
    themeChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        header = QLabel("Settings")
        header.setObjectName("PageTitle")
        root.addWidget(header)
        sub = QLabel("Appearance, output, performance and external tools.")
        sub.setObjectName("PageSubtitle")
        root.addWidget(sub)

        root.addWidget(self._appearance_card())
        root.addWidget(self._output_card())
        root.addWidget(self._performance_card())
        root.addWidget(self._updates_card())
        root.addWidget(self._deps_card())
        root.addWidget(self._about_card())
        root.addStretch(1)

    # ------------------------------------------------------------------
    def _updates_card(self) -> Card:
        card = Card()
        card.add(section_label("Updates"))

        info = QLabel(f"You're on <b>{__app_name__} v{__version__}</b>.")
        info.setObjectName("Hint")
        info.setTextFormat(Qt.RichText)
        card.add(info)

        row = QHBoxLayout()
        self.btn_check = QPushButton("Check for updates")
        self.btn_check.setObjectName("Ghost")
        self.btn_check.setCursor(Qt.PointingHandCursor)
        self.btn_check.clicked.connect(self._check_updates)
        row.addWidget(self.btn_check)
        self.update_status = QLabel("")
        self.update_status.setObjectName("Hint")
        self.update_status.setTextFormat(Qt.RichText)
        self.update_status.setOpenExternalLinks(True)
        row.addWidget(self.update_status, 1)
        w = QWidget(); w.setLayout(row); card.add(w)

        self.chk_auto_update = QCheckBox("Check for updates automatically on startup")
        self.chk_auto_update.setChecked(settings.auto_check_updates)
        self.chk_auto_update.stateChanged.connect(
            lambda: setattr(settings, "auto_check_updates",
                            self.chk_auto_update.isChecked()))
        card.add(self.chk_auto_update)
        return card

    def _check_updates(self) -> None:
        from mico360 import updater
        from mico360.ui.update_ui import UpdateDialog, start_check

        if not updater.is_configured():
            self.update_status.setText(
                "Updates aren't configured for this build.")
            return
        self.btn_check.setEnabled(False)
        self.update_status.setText("Checking…")

        def on_found(info):
            self.btn_check.setEnabled(True)
            self.update_status.setText(
                f"Version {info.version} is available.")
            UpdateDialog(info, self).exec()

        def on_up_to_date():
            self.btn_check.setEnabled(True)
            green = palette(settings.theme)["success"]
            self.update_status.setText(
                f"<span style='color:{green};'>You're up to date. ✓</span>")

        def on_failed(msg):
            self.btn_check.setEnabled(True)
            self.update_status.setText(
                f"Couldn't check for updates. "
                f"<a href='{updater.RELEASES_PAGE}'>Open releases page</a>")

        start_check(self, on_found, on_up_to_date, on_failed)

    # ------------------------------------------------------------------
    def _about_card(self) -> Card:
        card = Card()
        card.add(section_label("About & Legal"))

        info = QLabel(
            f"<b>{__app_name__}</b> v{__version__}<br>"
            f"PDF &amp; image toolkit for Windows. Everything runs locally — "
            f"your files never leave your computer.<br>"
            f"Email: <a href='mailto:{legal.EMAIL}'>{legal.EMAIL}</a> &nbsp;·&nbsp; "
            f"Website: <a href='{legal.WEBSITE_URL}'>{legal.WEBSITE}</a>")
        info.setObjectName("Hint")
        info.setTextFormat(Qt.RichText)
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        card.add(info)

        row = QHBoxLayout()
        for label, getter in (("About Us", legal.about_us),
                              ("Terms & Conditions", legal.terms_and_conditions),
                              ("Privacy Policy", legal.privacy_policy)):
            b = QPushButton(label)
            b.setObjectName("Ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, t=label, g=getter: self._show_doc(t, g()))
            row.addWidget(b)
        row.addStretch(1)
        w = QWidget(); w.setLayout(row); card.add(w)
        return card

    def _show_doc(self, title: str, html: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{title} — {__app_name__}")
        dlg.resize(620, 560)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)
        lay.addWidget(browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec()

    # ------------------------------------------------------------------
    def _appearance_card(self) -> Card:
        card = Card()
        card.add(section_label("Appearance"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Theme"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.setCurrentIndex(0 if settings.theme == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(
            lambda: self.themeChanged.emit(self.theme_combo.currentData()))
        row.addWidget(self.theme_combo)
        row.addStretch(1)
        w = QWidget(); w.setLayout(row); card.add(w)
        return card

    def sync_theme_combo(self) -> None:
        """Reflect the current theme without re-emitting themeChanged
        (used when the theme is toggled from the top bar)."""
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(0 if settings.theme == "dark" else 1)
        self.theme_combo.blockSignals(False)

    def _output_card(self) -> Card:
        card = Card()
        card.add(section_label("Output"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Default output folder"))
        self.out_edit = QLineEdit(settings.output_dir)
        self.out_edit.setReadOnly(True)
        btn = QPushButton("Change…"); btn.setObjectName("Ghost")
        btn.clicked.connect(self._choose_output)
        row.addWidget(self.out_edit, 1); row.addWidget(btn)
        w = QWidget(); w.setLayout(row); card.add(w)

        self.chk_open = QCheckBox("Open output folder when a batch finishes")
        self.chk_open.setChecked(settings.open_output_when_done)
        self.chk_open.stateChanged.connect(
            lambda: setattr(settings, "open_output_when_done", self.chk_open.isChecked()))
        card.add(self.chk_open)

        self.chk_overwrite = QCheckBox("Overwrite existing files by default")
        self.chk_overwrite.setChecked(settings.overwrite)
        self.chk_overwrite.stateChanged.connect(
            lambda: setattr(settings, "overwrite", self.chk_overwrite.isChecked()))
        card.add(self.chk_overwrite)
        return card

    def _performance_card(self) -> Card:
        card = Card()
        card.add(section_label("Performance"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Parallel workers (0 = automatic)"))
        self.workers = QSpinBox()
        self.workers.setRange(0, 64)
        self.workers.setValue(settings.max_workers)
        self.workers.valueChanged.connect(
            lambda v: setattr(settings, "max_workers", v))
        row.addWidget(self.workers); row.addStretch(1)
        w = QWidget(); w.setLayout(row); card.add(w)
        hint = QLabel(f"Detected CPU cores: {os.cpu_count()}. "
                      "Automatic uses cores − 1.")
        hint.setObjectName("Hint")
        card.add(hint)
        return card

    def _deps_card(self) -> Card:
        card = Card()
        card.add(section_label("External tools"))

        self.gs_edit = QLineEdit(settings.ghostscript_path)
        self.lo_edit = QLineEdit(settings.libreoffice_path)

        card.add(self._dep_row("Ghostscript (PDF compression)", self.gs_edit,
                               "gswin64c.exe", "ghostscript"))
        card.add(self._dep_row("LibreOffice (Word → PDF)", self.lo_edit,
                               "soffice.exe", "libreoffice"))

        btns = QHBoxLayout()
        detect = QPushButton("Auto-detect"); detect.setObjectName("Ghost")
        detect.clicked.connect(self._detect)
        openlogs = QPushButton("Open logs folder"); openlogs.setObjectName("Ghost")
        openlogs.clicked.connect(self._open_logs)
        btns.addWidget(detect); btns.addWidget(openlogs); btns.addStretch(1)
        w = QWidget(); w.setLayout(btns); card.add(w)

        self.status = QLabel()
        self.status.setObjectName("Hint")
        card.add(self.status)
        self._refresh_status()
        return card

    def _dep_row(self, label: str, edit: QLineEdit, exe: str, key: str) -> QWidget:
        box = QVBoxLayout()
        box.addWidget(QLabel(label))
        row = QHBoxLayout()
        edit.setPlaceholderText(f"Path to {exe} (leave blank to auto-detect)")
        btn = QPushButton("Browse…"); btn.setObjectName("Ghost")

        def browse():
            f, _ = QFileDialog.getOpenFileName(self, f"Locate {exe}", "",
                                               f"{exe};;All files (*.*)")
            if f:
                edit.setText(f)
                setattr(settings, f"{key}_path", f)
                self._refresh_status()

        def changed():
            setattr(settings, f"{key}_path", edit.text().strip())
            self._refresh_status()

        btn.clicked.connect(browse)
        edit.editingFinished.connect(changed)
        row.addWidget(edit, 1); row.addWidget(btn)
        rw = QWidget(); rw.setLayout(row)
        box.addWidget(rw)
        wrap = QWidget(); wrap.setLayout(box)
        return wrap

    # ------------------------------------------------------------------
    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select default output folder",
                                                  settings.output_dir)
        if folder:
            self.out_edit.setText(folder)
            settings.output_dir = folder

    def _detect(self) -> None:
        gs = find_ghostscript()
        lo = find_libreoffice()
        if gs:
            self.gs_edit.setText(gs)
        if lo:
            self.lo_edit.setText(lo)
        self._refresh_status()

    def _refresh_status(self) -> None:
        gs = find_ghostscript()
        lo = find_libreoffice()
        def mark(found):
            return "✓ found" if found else "✗ not found"
        self.status.setText(
            f"Ghostscript: {mark(gs)}   ·   LibreOffice: {mark(lo)}\n"
            "Both are bundled with the installer; manual paths override detection.")

    def _open_logs(self) -> None:
        path = logs_dir()
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass
