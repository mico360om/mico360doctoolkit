"""Settings page: appearance, output, performance, external dependencies."""
from __future__ import annotations

import html
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mico360 import __app_name__, __version__, legal
from mico360.config import settings
from mico360.core.deps import find_ghostscript, find_libreoffice
from mico360.paths import logs_dir
from mico360.theme import palette
from mico360.ui.widgets import Card, section_label, tip


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
        sub = QLabel("Customize application preferences.")
        sub.setObjectName("PageSubtitle")
        root.addWidget(sub)

        tabs = QTabWidget()
        tabs.setObjectName("SettingsTabs")
        tabs.addTab(self._tab(self._appearance_card(), self._about_card()), "General")
        tabs.addTab(self._tab(self._performance_card()), "Processing")
        tabs.addTab(self._tab(self._ai_card()), "AI")
        tabs.addTab(self._tab(self._output_card()), "Output")
        tabs.addTab(self._tab(self._updates_card()), "Updates")
        tabs.addTab(self._tab(self._deps_card()), "Advanced")
        root.addWidget(tabs, 1)

    def _tab(self, *cards) -> QWidget:
        """Wrap one or more cards in a scrollable tab page."""
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(2, 14, 2, 6)
        lay.setSpacing(16)
        for c in cards:
            lay.addWidget(c)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        return scroll

    # ------------------------------------------------------------------
    def _updates_card(self) -> Card:
        card = Card()
        card.add(section_label("Updates"))

        info = QLabel(f"You're on <b>{__app_name__} v{__version__}</b>.")
        info.setObjectName("Hint")
        info.setTextFormat(Qt.RichText)
        card.add(info)

        from mico360 import updater as _upd
        link_c = palette(settings.theme)["info"]
        repo = QLabel(
            f"Repository &amp; downloads: <a href='{_upd.REPO_URL}' "
            f"style='color:{link_c}; font-weight:600;'>{_upd.REPO_SHORT}</a>")
        repo.setObjectName("Hint")
        repo.setTextFormat(Qt.RichText)
        repo.setOpenExternalLinks(True)
        repo.setToolTip(_upd.REPO_URL)
        card.add(repo)

        row = QHBoxLayout()
        self.btn_check = QPushButton("Check for updates")
        self.btn_check.setObjectName("Ghost")
        self.btn_check.setCursor(Qt.PointingHandCursor)
        tip(self.btn_check,
            "Check GitHub for a newer version right now. Nothing is installed "
            "without your confirmation.")
        self.btn_check.clicked.connect(self._check_updates)
        row.addWidget(self.btn_check)
        self.update_status = QLabel("")
        self.update_status.setObjectName("Hint")
        self.update_status.setTextFormat(Qt.RichText)
        self.update_status.setOpenExternalLinks(True)
        row.addWidget(self.update_status, 1)
        w = QWidget(); w.setLayout(row); card.add(w)

        self.chk_auto_update = QCheckBox("Check for updates automatically on startup")
        tip(self.chk_auto_update,
            "Runs a quiet check a few seconds after the app opens. You're only "
            "prompted when a new version actually exists.")
        self.chk_auto_update.setChecked(settings.auto_check_updates)
        self.chk_auto_update.stateChanged.connect(
            lambda: setattr(settings, "auto_check_updates",
                            self.chk_auto_update.isChecked()))
        card.add(self.chk_auto_update)

        self.chk_crash = QCheckBox(
            "Offer to report errors when something goes wrong")
        self.chk_crash.setChecked(settings.crash_reports_enabled)
        tip(self.chk_crash,
            "Crash reports (with the recent log) are saved on your computer. "
            "Nothing is ever sent automatically — you choose whether to open a "
            "pre-filled GitHub issue, copy, or email the report.")
        self.chk_crash.toggled.connect(
            lambda v: setattr(settings, "crash_reports_enabled", v))
        card.add(self.chk_crash)
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
            # "&" in a button label is a Qt mnemonic marker (it would render as
            # "Terms _Conditions"); escape it so the ampersand shows literally.
            b = QPushButton(label.replace("&", "&&"))
            tip(b, f"Read the {label} in a window.")
            b.setObjectName("Ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, t=label, g=getter: self._show_doc(t, g()))
            row.addWidget(b)
        row.addStretch(1)
        w = QWidget(); w.setLayout(row); card.add(w)
        return card

    def _show_doc(self, title: str, html: str) -> None:
        from mico360.ui.widgets import clamp_to_screen
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{title} — {__app_name__}")
        clamp_to_screen(dlg, 620, 560)
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
        self.theme_combo.addItem("System", "system")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.setAccessibleName("Theme")
        tip(self.theme_combo,
            "System follows your Windows light/dark appearance automatically; "
            "Light or Dark pins a fixed look.")
        self.sync_theme_combo()
        self.theme_combo.currentIndexChanged.connect(
            lambda: self.themeChanged.emit(self.theme_combo.currentData()))
        row.addWidget(self.theme_combo)
        row.addStretch(1)
        w = QWidget(); w.setLayout(row); card.add(w)
        return card

    def sync_theme_combo(self) -> None:
        """Reflect the current theme mode without re-emitting themeChanged
        (used when the theme is toggled from the top bar)."""
        self.theme_combo.blockSignals(True)
        idx = self.theme_combo.findData(settings.theme_mode)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.theme_combo.blockSignals(False)

    # ------------------------------------------------------------------
    def _ai_card(self) -> Card:
        """User AI configuration: provider choice, endpoint, key, model, test."""
        from mico360.core import ai as ai_core

        card = Card()
        card.add(section_label("AI provider"))

        self.chk_ai = QCheckBox("Enable AI features")
        tip(self.chk_ai,
            "Turns on AI assistance such as metadata suggestions on the Edit "
            "Metadata page. Off by default - nothing is sent anywhere until "
            "you enable it.")
        self.chk_ai.setChecked(settings.ai_enabled)
        self.chk_ai.toggled.connect(self._on_ai_enabled)
        card.add(self.chk_ai)

        row = QHBoxLayout()
        row.addWidget(QLabel("Use"))
        self.ai_source = QComboBox()
        self.ai_source.addItem("System AI (provided for you)", ai_core.SOURCE_SYSTEM)
        self.ai_source.addItem("My own AI API", ai_core.SOURCE_CUSTOM)
        self.ai_source.setAccessibleName("AI provider")
        tip(self.ai_source,
            "System AI uses the endpoint your administrator provides. Choose "
            "My own AI API to point at any OpenAI-compatible service.")
        i = self.ai_source.findData(settings.ai_source)
        self.ai_source.setCurrentIndex(max(0, i))
        self.ai_source.currentIndexChanged.connect(self._on_ai_source)
        row.addWidget(self.ai_source, 1)
        w = QWidget(); w.setLayout(row); card.add(w)

        self.ai_url = QLineEdit(settings.ai_base_url)
        self.ai_url.setPlaceholderText(ai_core.SYSTEM_BASE_URL)
        self.ai_url.setAccessibleName("AI API URL")
        tip(self.ai_url,
            "The OpenAI-compatible base URL, including the port and /v1 - for "
            "example http://ai.mico360.com:5310/v1")
        card.add(self._labeled("API URL", self.ai_url))

        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_key.setAccessibleName("AI API key")
        tip(self.ai_key,
            "Your API key. It is encrypted before it is saved and is never "
            "shown again afterwards - retype it to replace it.")
        card.add(self._labeled("API key", self.ai_key))

        self.ai_key_state = QLabel("")
        self.ai_key_state.setObjectName("Hint")
        self.ai_key_state.setWordWrap(True)
        card.add(self.ai_key_state)

        # Editable dropdown: pick a model the server actually offers, or type a
        # new id to add one. Refresh pulls the live list; Remove drops an entry.
        self.ai_model = QComboBox()
        self.ai_model.setEditable(True)
        self.ai_model.setInsertPolicy(QComboBox.NoInsert)   # we add explicitly
        self.ai_model.lineEdit().setPlaceholderText(ai_core.SYSTEM_MODEL)
        self.ai_model.setAccessibleName("AI model")
        self.ai_model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.ai_model.setMinimumContentsLength(18)
        tip(self.ai_model,
            "Pick a model the server offers, or type a new id to add it. Small "
            "models (e.g. qwen2.5:0.5b) answer in about a second; large ones can "
            "take a minute on the first request.")

        mrow = QHBoxLayout()
        mrow.setContentsMargins(0, 0, 0, 0)
        mrow.addWidget(self.ai_model, 1)
        self.btn_models_refresh = QPushButton("Refresh")
        self.btn_models_refresh.setObjectName("Ghost")
        self.btn_models_refresh.setCursor(Qt.PointingHandCursor)
        tip(self.btn_models_refresh,
            "Ask the server which models this key may use and fill the list.")
        self.btn_models_refresh.clicked.connect(self._refresh_models)
        self.btn_models_remove = QPushButton("Remove")
        self.btn_models_remove.setObjectName("Ghost")
        self.btn_models_remove.setCursor(Qt.PointingHandCursor)
        tip(self.btn_models_remove,
            "Remove the selected model from this list. It isn't deleted from "
            "the server — only from your dropdown.")
        self.btn_models_remove.clicked.connect(self._remove_model)
        mrow.addWidget(self.btn_models_refresh)
        mrow.addWidget(self.btn_models_remove)
        mw = QWidget(); mw.setLayout(mrow)
        card.add(self._labeled("Model", mw))

        self.ai_models_state = QLabel("")
        self.ai_models_state.setObjectName("Hint")
        self.ai_models_state.setWordWrap(True)
        card.add(self.ai_models_state)

        brow = QHBoxLayout()
        self.btn_ai_save = QPushButton("Save")
        self.btn_ai_save.setObjectName("Ghost")
        self.btn_ai_save.setCursor(Qt.PointingHandCursor)
        tip(self.btn_ai_save, "Save these AI settings (the key is encrypted).")
        self.btn_ai_save.clicked.connect(self._save_ai)
        self.btn_ai_test = QPushButton("Test connection")
        self.btn_ai_test.setObjectName("Ghost")
        self.btn_ai_test.setCursor(Qt.PointingHandCursor)
        tip(self.btn_ai_test,
            "Save, then ask the server which models this key may use. Nothing "
            "is generated and no document is sent.")
        self.btn_ai_test.clicked.connect(self._test_ai)
        brow.addWidget(self.btn_ai_save)
        brow.addWidget(self.btn_ai_test)
        brow.addStretch(1)
        bw = QWidget(); bw.setLayout(brow); card.add(bw)

        self.ai_status = QLabel("")
        self.ai_status.setObjectName("Hint")
        self.ai_status.setWordWrap(True)
        card.add(self.ai_status)

        note = QLabel(
            "Your API key is encrypted on this computer"
            + (" using Windows account protection."
               if ai_core.is_strongly_protected()
               else " (basic protection on this platform).")
            + " Document text is only sent when you ask for a suggestion.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        card.add(note)

        self._load_models()
        self._sync_ai_fields()
        return card

    def _labeled(self, text: str, field) -> QWidget:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        box.addWidget(QLabel(text))
        box.addWidget(field)
        w = QWidget(); w.setLayout(box)
        return w

    # --- model dropdown ------------------------------------------------
    def _load_models(self, models=None, keep: str | None = None) -> None:
        """Fill the dropdown from the saved list (plus the current selection)."""
        from mico360.core import ai as ai_core
        known = list(models if models is not None else settings.ai_models)
        current = keep if keep is not None else self.ai_model.currentText().strip()
        for extra in (current, settings.ai_model, ai_core.SYSTEM_MODEL):
            if extra and extra not in known:
                known.append(extra)
        self.ai_model.blockSignals(True)
        self.ai_model.clear()
        self.ai_model.addItems(known)
        i = self.ai_model.findText(current or settings.ai_model)
        if i >= 0:
            self.ai_model.setCurrentIndex(i)
        elif current:
            self.ai_model.setEditText(current)
        self.ai_model.blockSignals(False)
        self.btn_models_remove.setEnabled(self.ai_model.count() > 1)

    def _refresh_models(self) -> None:
        """Fetch the live model list for the configured key."""
        from mico360.core import ai as ai_core
        self._save_ai()                       # use what's on screen right now
        self.btn_models_refresh.setEnabled(False)
        self.ai_models_state.setText("Fetching models…")
        QApplication.processEvents()
        try:
            models = ai_core.list_models(ai_core.load_config())
        except ai_core.AiError as exc:
            self.ai_models_state.setText(f"Couldn't list models: {exc}")
            return
        except Exception as exc:              # noqa: BLE001
            self.ai_models_state.setText(f"Couldn't list models: {exc}")
            return
        finally:
            self.btn_models_refresh.setEnabled(True)
        if not models:
            self.ai_models_state.setText(
                "The server offers no models to this key. Ask an administrator "
                "to enable one.")
            return
        # Keep any hand-added ids the server doesn't know about.
        merged = list(models)
        for m in settings.ai_models:
            if m not in merged:
                merged.append(m)
        settings.ai_models = merged
        self._load_models(merged)
        self.ai_models_state.setText(
            f"{len(models)} model(s) available from the server.")

    def _remove_model(self) -> None:
        """Drop the selected id from the dropdown (not from the server)."""
        name = self.ai_model.currentText().strip()
        if not name or self.ai_model.count() <= 1:
            return
        remaining = [m for m in settings.ai_models if m != name]
        settings.ai_models = remaining
        # Move the selection off the removed id BEFORE reloading — otherwise
        # _load_models re-adds it as "the currently selected model".
        new_pick = remaining[0] if remaining else ""
        settings.ai_model = new_pick
        self._load_models(remaining, keep=new_pick)
        self._save_ai()
        self.ai_models_state.setText(f"Removed '{name}' from the list.")

    def _sync_ai_fields(self) -> None:
        """Custom-only fields are disabled under System AI, and a saved key is
        shown masked - never in full."""
        from mico360.core import ai as ai_core
        custom = self.ai_source.currentData() == ai_core.SOURCE_CUSTOM
        self.ai_url.setEnabled(custom)
        stored = ai_core.unseal_key(settings.ai_api_key_sealed)
        if stored:
            self.ai_key.setPlaceholderText(ai_core.masked_key(stored) + "  (saved)")
            self.ai_key_state.setText(
                "A key is saved. Leave blank to keep it, or type a new one to "
                "replace it.")
        else:
            self.ai_key.setPlaceholderText("Paste your API key")
            self.ai_key_state.setText("No API key saved yet.")

    def _on_ai_enabled(self, on: bool) -> None:
        settings.ai_enabled = bool(on)

    def _on_ai_source(self) -> None:
        settings.ai_source = self.ai_source.currentData()
        self._sync_ai_fields()

    def _collect_ai(self):
        """Form values as an AiConfig, plus the freshly typed key (if any)."""
        from mico360.core import ai as ai_core
        typed = self.ai_key.text().strip()
        cfg = ai_core.AiConfig(
            enabled=self.chk_ai.isChecked(),
            source=self.ai_source.currentData(),
            base_url=self.ai_url.text().strip(),
            api_key=typed or ai_core.unseal_key(settings.ai_api_key_sealed),
            model=self.ai_model.currentText().strip(),
        )
        return cfg, typed

    def _save_ai(self) -> None:
        from mico360.core import ai as ai_core
        cfg, typed = self._collect_ai()
        if cfg.source == ai_core.SOURCE_CUSTOM and cfg.base_url:
            cfg.base_url = ai_core.normalize_base_url(cfg.base_url)
            self.ai_url.setText(cfg.base_url)
        # A model id typed into the editable combo becomes a saved entry, so
        # "new models can be added" simply by naming one.
        if cfg.model and cfg.model not in settings.ai_models:
            settings.ai_models = list(settings.ai_models) + [cfg.model]
        ai_core.save_config(cfg, api_key=typed if typed else None)
        self.ai_key.clear()          # never keep the secret on screen
        self._sync_ai_fields()
        self.ai_status.setText("Saved.")

    def _test_ai(self) -> None:
        from mico360.core import ai as ai_core
        self._save_ai()
        self.btn_ai_test.setEnabled(False)
        self.ai_status.setText("Testing...")
        QApplication.processEvents()
        try:
            ok, msg = ai_core.test_connection(ai_core.load_config())
        finally:
            self.btn_ai_test.setEnabled(True)
        pal = palette(settings.theme)
        # .get() with a fallback: a missing palette key must never turn a failed
        # connection test into a crash (the failure path is the one users hit).
        colour = pal.get("success" if ok else "error", pal["text"])
        self.ai_status.setTextFormat(Qt.RichText)
        mark = "✓" if ok else "✗"
        self.ai_status.setText(
            f"<span style='color:{colour};'>{mark} {html.escape(msg)}</span>")

    def _output_card(self) -> Card:
        card = Card()
        card.add(section_label("Output"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Default output folder"))
        self.out_edit = QLineEdit(settings.output_dir)
        self.out_edit.setReadOnly(True)
        self.out_edit.setAccessibleName("Default output folder")
        self.out_edit.setToolTip(settings.output_dir)   # dynamic: the full path
        btn = QPushButton("Change…"); btn.setObjectName("Ghost")
        tip(btn, "Choose where results are saved unless a tool is set to "
                 "save beside the originals.")
        btn.clicked.connect(self._choose_output)
        row.addWidget(self.out_edit, 1); row.addWidget(btn)
        w = QWidget(); w.setLayout(row); card.add(w)

        self.chk_open = QCheckBox("Open output folder when a batch finishes")
        tip(self.chk_open, "After a run completes, the folder with the results "
                           "opens automatically so they're easy to find.")
        self.chk_open.setChecked(settings.open_output_when_done)
        self.chk_open.stateChanged.connect(
            lambda: setattr(settings, "open_output_when_done", self.chk_open.isChecked()))
        card.add(self.chk_open)

        self.chk_overwrite = QCheckBox("Overwrite existing files by default")
        tip(self.chk_overwrite,
            "When an output file already exists, replace it instead of adding "
            "a number to the name. Careful: replaced files are not recoverable.")
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
        self.workers.setAccessibleName("Parallel workers")
        tip(self.workers,
            "How many files are processed at the same time. 0 = automatic "
            "(CPU cores − 1). Lower it if the PC feels sluggish during big "
            "batches; raising it beyond your core count won't help.")
        self.workers.valueChanged.connect(
            lambda v: setattr(settings, "max_workers", v))
        row.addWidget(self.workers); row.addStretch(1)
        w = QWidget(); w.setLayout(row); card.add(w)
        hint = QLabel(f"Detected CPU cores: {os.cpu_count()}. "
                      "Automatic uses cores − 1.")
        hint.setObjectName("Hint")
        card.add(hint)

        # --- GPU OCR ---------------------------------------------------------
        self.chk_gpu_ocr = QCheckBox("Use the GPU for OCR when available "
                                     "(DirectML — falls back to CPU)")
        tip(self.chk_gpu_ocr,
            "Runs text recognition on your graphics card (any NVIDIA / AMD / "
            "Intel GPU) — usually several times faster. Safe to leave on: PCs "
            "without a usable GPU automatically use the CPU.")
        self.chk_gpu_ocr.setChecked(settings.ocr_use_gpu)
        self.chk_gpu_ocr.toggled.connect(
            lambda v: setattr(settings, "ocr_use_gpu", v))
        card.add(self.chk_gpu_ocr)
        gpu_hint = QLabel(self._gpu_status_text())
        gpu_hint.setObjectName("Hint")
        gpu_hint.setWordWrap(True)
        card.add(gpu_hint)

        # --- OCR languages (on-demand language packs) ------------------------
        card.add(section_label("OCR languages"))
        self.ocr_lang_status = QLabel()
        self.ocr_lang_status.setObjectName("Hint")
        self.ocr_lang_status.setWordWrap(True)
        card.add(self.ocr_lang_status)
        lrow = QHBoxLayout()
        self.ocr_lang_combo = QComboBox()
        from mico360.core import ocr_models
        for lid, label in ocr_models.language_choices():
            if not ocr_models.language(lid).builtin:   # only downloadable packs
                self.ocr_lang_combo.addItem(label, lid)
        self.ocr_lang_combo.setAccessibleName("OCR language to download")
        tip(self.ocr_lang_combo,
            "Languages beyond English/Latin need a small recognition model. "
            "Pick one here to fetch it ahead of time.")
        self.btn_ocr_lang = QPushButton("Download language")
        self.btn_ocr_lang.setObjectName("Ghost")
        self.btn_ocr_lang.setCursor(Qt.PointingHandCursor)
        tip(self.btn_ocr_lang,
            "Download the selected OCR language now (~8 MB, one time) so it's "
            "ready to use offline — otherwise it downloads on first use.")
        self.btn_ocr_lang.clicked.connect(self._download_ocr_language)
        lrow.addWidget(self.ocr_lang_combo, 1)
        lrow.addWidget(self.btn_ocr_lang)
        lw = QWidget(); lw.setLayout(lrow); card.add(lw)
        self._refresh_ocr_lang_status()
        return card

    def _refresh_ocr_lang_status(self) -> None:
        from mico360.core import ocr_models
        ready, pending = [], []
        for lid, label in ocr_models.language_choices():
            if ocr_models.language(lid).builtin:
                ready.append(f"{label} (built in)")
            elif ocr_models.is_language_ready(lid):
                ready.append(f"{label} ✓")
            else:
                pending.append(label)
        msg = "Installed: " + ", ".join(ready) + "."
        if pending:
            msg += (" Other languages download a small model (~8 MB) once, "
                    "automatically the first time you OCR in that language — "
                    "or fetch one now below.")
        self.ocr_lang_status.setText(msg)

    def _download_ocr_language(self) -> None:
        from PySide6.QtCore import QObject, QThread, Signal
        from PySide6.QtWidgets import QMessageBox, QProgressDialog

        lid = self.ocr_lang_combo.currentData()
        label = self.ocr_lang_combo.currentText()
        if not lid:
            return
        dlg = QProgressDialog("Starting…", "Cancel", 0, 100, self)
        dlg.setWindowTitle("OCR language")
        dlg.setMinimumWidth(460)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        state = {"cancel": False}
        dlg.canceled.connect(lambda: state.__setitem__("cancel", True))

        class _Worker(QObject):
            prog = Signal(int)
            text = Signal(str)
            finished = Signal(bool, str)

            def run(self) -> None:
                outer = self

                class _Rep:
                    def __call__(self, m):
                        outer.text.emit(str(m))

                    def progress(self, c, t):
                        outer.prog.emit(int(c * 100 / t) if t else 0)

                try:
                    from mico360.core import ocr_models
                    ocr_models.ensure_language(lid, _Rep(), lambda: state["cancel"])
                    outer.finished.emit(True, "")
                except Exception as exc:  # noqa: BLE001
                    outer.finished.emit(False, str(exc))

        thread = QThread(self)
        worker = _Worker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.prog.connect(dlg.setValue)
        worker.text.connect(dlg.setLabelText)

        def _fin(ok, info):
            thread.quit()
            thread.wait(3000)
            dlg.close()
            if ok:
                QMessageBox.information(self, "OCR language",
                                        f"{label} OCR is ready.")
            elif not state["cancel"]:
                QMessageBox.warning(self, "OCR language",
                                    f"Couldn't download {label}:\n{info}")
            self._refresh_ocr_lang_status()

        worker.finished.connect(_fin)
        self._ocr_lang_thread = (thread, worker)   # keep refs alive
        self.btn_ocr_lang.setEnabled(False)
        thread.start()
        dlg.exec()
        self.btn_ocr_lang.setEnabled(True)

    @staticmethod
    def _gpu_status_text() -> str:
        """Describe, for THIS machine, whether GPU OCR can run — detected live,
        never assumed. No subprocess: just asks onnxruntime what's available."""
        try:
            import onnxruntime as ort
            dml = "DmlExecutionProvider" in ort.get_available_providers()
        except Exception:
            dml = False
        if dml:
            return ("GPU acceleration for OCR: available on this PC — scanned-PDF "
                    "OCR runs much faster.")
        return ("GPU acceleration for OCR: not available on this PC — OCR uses "
                "the CPU. (This build accelerates GPUs on Windows via DirectML.)")

    def _deps_card(self) -> Card:
        card = Card()
        card.add(section_label("External tools"))

        self.gs_edit = QLineEdit(settings.ghostscript_path)
        self.lo_edit = QLineEdit(settings.libreoffice_path)

        card.add(self._dep_row("Ghostscript (PDF compression)", self.gs_edit,
                               "gswin64c.exe", "ghostscript"))
        card.add(self._dep_row("LibreOffice (Word → PDF)", self.lo_edit,
                               "soffice.exe", "libreoffice"))

        # --- Conversion engine (on-demand LibreOffice) ----------------------
        from mico360.core import engines
        card.add(section_label("Conversion engine"))
        self.engine_status = QLabel()
        self.engine_status.setObjectName("Hint")
        self.engine_status.setWordWrap(True)
        card.add(self.engine_status)
        erow = QHBoxLayout()
        self.btn_engine = QPushButton("Download engine now")
        self.btn_engine.setObjectName("Ghost")
        self.btn_engine.setCursor(Qt.PointingHandCursor)
        tip(self.btn_engine,
            "Fetch the LibreOffice conversion engine now (~340 MB, one time) "
            "instead of waiting for the first Office conversion. It survives "
            "app updates.")
        self.btn_engine.clicked.connect(self._download_engine)
        erow.addWidget(self.btn_engine); erow.addStretch(1)
        ew = QWidget(); ew.setLayout(erow); card.add(ew)
        self.chk_auto_engine = QCheckBox(
            "Download it automatically the first time it's needed")
        tip(self.chk_auto_engine,
            "If off, Office → PDF and Document → Markdown will ask you to "
            "install LibreOffice yourself (or download the engine here).")
        self.chk_auto_engine.setChecked(settings.auto_download_engine)
        self.chk_auto_engine.toggled.connect(
            lambda v: setattr(settings, "auto_download_engine", v))
        card.add(self.chk_auto_engine)
        self._engines = engines
        self._refresh_engine_status()

        btns = QHBoxLayout()
        detect = QPushButton("Auto-detect"); detect.setObjectName("Ghost")
        tip(detect, "Search the standard install locations for Ghostscript "
                    "and LibreOffice and fill in the paths above.")
        detect.clicked.connect(self._detect)
        openlogs = QPushButton("Open logs folder"); openlogs.setObjectName("Ghost")
        tip(openlogs, "Open the folder with the app's log files — useful when "
                      "reporting a problem.")
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
        edit.setAccessibleName(label)
        tip(edit, f"Full path to {exe}. Leave blank to auto-detect — a manual "
                  "path here overrides detection.")
        btn = QPushButton("Browse…"); btn.setObjectName("Ghost")
        tip(btn, f"Locate {exe} on disk manually.")

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
            self.out_edit.setToolTip(folder)
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
            "Manual paths override detection. The LibreOffice engine is downloaded "
            "on demand (see above); Ghostscript is optional.")

    def _refresh_engine_status(self) -> None:
        import sys

        from mico360.core.deps import find_libreoffice as _find_lo
        lo = _find_lo()
        if lo:
            self.engine_status.setText(
                "Conversion engine: ready ✓  — used for Office → PDF and "
                "Document → Markdown.")
            self.btn_engine.setText("Re-download engine")
            self.btn_engine.setEnabled(True)
        elif sys.platform.startswith("win"):
            self.engine_status.setText(
                "Conversion engine: not installed. It downloads automatically "
                "(~340 MB, one time) the first time you convert an Office file — "
                "or download it now.")
            self.btn_engine.setText("Download engine now")
            self.btn_engine.setEnabled(True)
        else:
            self.engine_status.setText(
                "Conversion engine: install LibreOffice from libreoffice.org and "
                "set its path above (auto-download is Windows-only).")
            self.btn_engine.setEnabled(False)

    def _download_engine(self) -> None:
        from PySide6.QtCore import QObject, QThread, Signal
        from PySide6.QtWidgets import QMessageBox, QProgressDialog

        dlg = QProgressDialog("Starting…", "Cancel", 0, 100, self)
        dlg.setWindowTitle("Conversion engine")
        dlg.setMinimumWidth(460)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        state = {"cancel": False}
        dlg.canceled.connect(lambda: state.__setitem__("cancel", True))

        class _Worker(QObject):
            prog = Signal(int)
            text = Signal(str)
            finished = Signal(bool, str)

            def run(self) -> None:
                outer = self

                class _Rep:
                    def __call__(self, m):
                        outer.text.emit(str(m))

                    def progress(self, c, t):
                        outer.prog.emit(int(c * 100 / t) if t else 0)

                try:
                    from mico360.core import engines
                    path = engines.download_engine(_Rep(), lambda: state["cancel"])
                    outer.finished.emit(True, path)
                except Exception as exc:  # noqa: BLE001
                    outer.finished.emit(False, str(exc))

        thread = QThread(self)
        worker = _Worker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.prog.connect(dlg.setValue)
        worker.text.connect(dlg.setLabelText)

        def _fin(ok, info):
            thread.quit()
            thread.wait(3000)
            dlg.close()
            if ok:
                QMessageBox.information(self, "Conversion engine",
                                        "The conversion engine is ready.")
            elif not state["cancel"]:
                QMessageBox.warning(self, "Conversion engine",
                                    f"Couldn't download the engine:\n{info}")
            self._refresh_engine_status()

        worker.finished.connect(_fin)
        self._engine_thread = (thread, worker)   # keep refs alive
        self.btn_engine.setEnabled(False)
        thread.start()
        dlg.exec()
        self.btn_engine.setEnabled(True)

    def _open_logs(self) -> None:
        from mico360.core.platform_utils import open_path
        open_path(logs_dir())
