"""Builds a form of controls from a tool's Option specs and reads back values."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mico360.config import settings
from mico360.core.tools import Option, Tool
from mico360.ui.widgets import tip


class _PosGrid(QWidget):
    """A 3×3 grid of radio buttons for choosing a placement (e.g. watermark)."""

    POSITIONS = [
        ["top-left", "top-center", "top-right"],
        ["middle-left", "center", "middle-right"],
        ["bottom-left", "bottom-center", "bottom-right"],
    ]

    def __init__(self, default: str = "center", parent: QWidget | None = None):
        super().__init__(parent)
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(8)
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QRadioButton] = {}
        for r, row in enumerate(self.POSITIONS):
            for c, pos in enumerate(row):
                rb = QRadioButton()
                rb.setObjectName("PosDot")
                rb.setCursor(Qt.PointingHandCursor)
                rb.setToolTip(pos.replace("-", " ").title())
                rb.setAccessibleName(pos.replace("-", " ").title())   # screen readers
                self._group.addButton(rb)
                self._buttons[pos] = rb
                g.addWidget(rb, r, c, Qt.AlignCenter)
        self._buttons.get(default if isinstance(default, str) else "center",
                          self._buttons["center"]).setChecked(True)

    def value(self) -> str:
        for pos, rb in self._buttons.items():
            if rb.isChecked():
                return pos
        return "center"


# Checkbox indicator + spacing, so a hint lines up with the checkbox's text.
_CHECK_TEXT_INDENT = 28


class _HintLabel(QLabel):
    """A wrapping hint that reserves only the lines it really needs. A plain
    word-wrapped QLabel in a form is sized from a guessed narrow width, so a
    one-line hint got the height of three lines — big gaps above and below."""

    def sizeHint(self):  # noqa: N802 (Qt API)
        sh = super().sizeHint()
        w = self.width()
        if self.wordWrap() and w > 40:
            sh.setHeight(self.heightForWidth(w))
        return sh

    def resizeEvent(self, event):  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        if self.wordWrap() and event.oldSize().width() != event.size().width():
            self.updateGeometry()          # re-measure for the new width


class _PagePlanField(QWidget):
    """Control for the visual page organizer: a button that opens the thumbnail
    grid for the currently-selected file, plus a one-line summary. Its value is
    the organizer's plan dict (or None until the user arranges pages)."""

    def __init__(self, owner: "OptionsWidget", parent: QWidget | None = None):
        super().__init__(parent)
        self._owner = owner
        self._plan: dict | None = None
        self._target = None            # the path the plan was built for
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.btn = QPushButton("Open visual organizer…")
        self.btn.setObjectName("Ghost")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self._open)
        lay.addWidget(self.btn)
        self.summary = QLabel("No arrangement yet — click to open.")
        self.summary.setObjectName("Hint")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

    def _open(self, _=False) -> None:
        from pathlib import Path
        getter = getattr(self._owner, "_file_getter", None)
        path = getter() if callable(getter) else None
        if not path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Add a file first",
                "Add a PDF to the queue and select it, then open the visual "
                "organizer.")
            return
        path = Path(path)
        from mico360.ui.page_organizer import PageOrganizerDialog
        seed = self._plan if self._target == path else None
        dlg = PageOrganizerDialog(path, self, seed)
        try:
            if dlg.exec():
                self._plan = dlg.plan()
                self._target = path
                self._update_summary(path.name)
        finally:
            dlg.deleteLater()           # frees its (up to 400) thumbnails

    def _update_summary(self, name: str) -> None:
        groups = (self._plan or {}).get("groups", [])
        kept = sum(len(g) for g in groups)
        files = max(1, len(groups))
        n = (self._plan or {}).get("n_src", kept)
        txt = f"{kept} of {n} page(s) kept"
        if files > 1:
            txt += f" · {files} files"
        self.summary.setText(f"{txt}  —  {name}")

    def value(self) -> dict | None:
        # The plan names the file it was arranged for, so the runner applies it
        # to that file only — never to every queued file with the same length.
        if not self._plan:
            return None
        return dict(self._plan, target=str(self._target) if self._target else "")

    def target(self):
        return self._target

    def clear(self) -> None:
        self._plan = None
        self._target = None
        self.summary.setText("No arrangement yet — click to open.")


class OptionsWidget(QWidget):
    def __init__(self, tool: Tool, parent: QWidget | None = None):
        super().__init__(parent)
        self.tool = tool
        self._controls: dict[str, QWidget] = {}
        self._rows: dict[str, tuple[QWidget, QWidget]] = {}  # key -> (label, field)
        self._password_keys: set[str] = set()   # never stripped, never saved
        self._no_save_keys: set[str] = set()     # ephemeral (e.g. page plans)
        self._file_getter = None                 # set by the tool page (page_plan)
        self._saved = settings.tool_options(tool.id)  # last-used values, if any

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._form = QFormLayout()
        self._form.setLabelAlignment(Qt.AlignLeft)
        self._form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._form.setHorizontalSpacing(14)
        self._form.setVerticalSpacing(10)
        root.addLayout(self._form)

        if not tool.options:
            note = QLabel("No options for this tool.")
            note.setObjectName("Hint")
            root.addWidget(note)

        for opt in tool.options:
            self._add_option(opt)
        self._apply_visibility()

    # --- construction ----------------------------------------------------
    def _add_option(self, opt: Option) -> None:
        # Start from the last-used value if we have one, else the spec default.
        # Per-document values (persist=False) always start blank.
        if getattr(opt, "persist", True):
            default = self._saved.get(opt.key, opt.default)
        else:
            self._no_save_keys.add(opt.key)
            default = opt.default
        field: QWidget
        read_widget: QWidget | None = None   # widget values() reads (if != field)
        if opt.kind == "file":
            le = QLineEdit(str(default if default is not None else ""))
            le.setPlaceholderText("Choose a file…")
            browse = QPushButton("Browse…")
            browse.setObjectName("Ghost")
            browse.setCursor(Qt.PointingHandCursor)
            holder = QWidget()
            h = QHBoxLayout(holder)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            h.addWidget(le, 1)
            h.addWidget(browse)

            def _pick(_=False, _le=le):
                f, _sel = QFileDialog.getOpenFileName(
                    self, "Choose image", "",
                    "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;"
                    "All files (*.*)")
                if f:
                    _le.setText(f)
            browse.clicked.connect(_pick)
            field = holder
            read_widget = le
        elif opt.kind == "password":
            self._password_keys.add(opt.key)
            le = QLineEdit("")            # never pre-filled from saved settings
            le.setEchoMode(QLineEdit.Password)
            le.setPlaceholderText("••••••••")
            from mico360.ui.icons import IconButton
            # Line-icon eye; swaps to a struck-through eye while revealed.
            eye = IconButton("eye", 18, "text_muted",
                             checked_name="eye-off", checked_role="primary")
            eye.setObjectName("EyeToggle")
            eye.setCheckable(True)
            eye.setFixedWidth(38)
            eye.setCursor(Qt.PointingHandCursor)
            eye.setToolTip("Show / hide password")

            def _toggle(checked, _le=le):
                _le.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
            eye.toggled.connect(_toggle)
            holder = QWidget()
            h = QHBoxLayout(holder)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            h.addWidget(le, 1)
            h.addWidget(eye)
            field = holder
            read_widget = le
        elif opt.kind == "posgrid":
            field = _PosGrid(default if isinstance(default, str) else "center")
        elif opt.kind == "page_plan":
            self._no_save_keys.add(opt.key)   # file-specific; never persisted
            field = _PagePlanField(self)
        elif opt.kind == "choice":
            cb = QComboBox()
            for value, label in opt.choices:
                cb.addItem(label, value)
            idx = cb.findData(default)
            if idx < 0:                       # saved value no longer valid
                idx = cb.findData(opt.default)  # fall back to the spec default
            cb.setCurrentIndex(max(0, idx))
            cb.currentIndexChanged.connect(self._apply_visibility)
            # Keep long item captions (e.g. "Medium — balanced (recommended)")
            # from forcing the whole options panel wider than it should be: the
            # closed combo may shrink and elide, while the popup still shows the
            # full text.
            cb.setMinimumContentsLength(6)
            cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            field = cb
        elif opt.kind == "int":
            sp = QSpinBox()
            sp.setRange(opt.minimum, opt.maximum)
            try:
                sp.setValue(int(default if default is not None else 0))
            except (TypeError, ValueError):
                sp.setValue(int(opt.default or 0))
            if opt.suffix:
                sp.setSuffix(opt.suffix)
            field = sp
        elif opt.kind == "bool":
            # "&&": Qt reads a single "&" as a keyboard-shortcut marker and hides
            # it ("text & fill" showed as "text  fill").
            chk = QCheckBox(opt.label.replace("&", "&&"))
            chk.setChecked(bool(default))
            chk.stateChanged.connect(self._apply_visibility)
            field = chk
        elif opt.kind == "textarea":
            te = QPlainTextEdit(str(default if default is not None else ""))
            te.setPlaceholderText("Key = Value   (one per line)")
            te.setFixedHeight(96)
            te.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            field = te
        else:  # text
            le = QLineEdit(str(default if default is not None else ""))
            field = le

        self._controls[opt.key] = read_widget if read_widget is not None else field

        # Accessibility + hover help, generated from the spec: the control is
        # named after its label for screen readers, and the option's hint (when
        # it has one) doubles as a word-wrapped tooltip on the control itself —
        # so the explanation is available right under the pointer, not only in
        # the small hint line below. Obvious, hint-less options get no tooltip.
        detail = getattr(opt, "details", "") or opt.hint
        for w in {field, read_widget} - {None}:
            w.setAccessibleName(opt.label)
            if detail:
                tip(w, detail)

        if opt.kind == "bool":
            # Span the whole row so the checkbox sits left-aligned with its
            # label, instead of being pushed into the right-hand field column.
            self._form.addRow(field)
            self._rows[opt.key] = (field, field)
        else:
            lbl = QLabel(opt.label)
            self._form.addRow(lbl, field)
            self._rows[opt.key] = (lbl, field)

        if opt.hint:
            hint = _HintLabel(opt.hint)
            hint.setObjectName("Hint")
            hint.setWordWrap(True)
            if getattr(opt, "details", ""):
                tip(hint, opt.details)
            if opt.kind == "bool":
                # Directly under the checkbox, aligned with its text — not
                # pushed into the right-hand field column with a ragged gap.
                hint.setIndent(_CHECK_TEXT_INDENT)
                self._form.addRow(hint)
            else:
                self._form.addRow("", hint)
            # tie hint visibility to the field via a synthetic key
            self._rows[f"__hint__{opt.key}"] = (hint, hint)

    # --- dynamic visibility ---------------------------------------------
    def _apply_visibility(self) -> None:
        values = self.values()
        for opt in self.tool.options:
            show = True
            if opt.visible_when is not None:
                dep_key, dep_val = opt.visible_when
                show = values.get(dep_key) == dep_val
            for key in (opt.key, f"__hint__{opt.key}"):
                row = self._rows.get(key)
                if row:
                    for w in row:
                        w.setVisible(show)

    # --- readout ---------------------------------------------------------
    def values(self) -> dict:
        out: dict = {}
        for opt in self.tool.options:
            ctrl = self._controls[opt.key]
            if isinstance(ctrl, QComboBox):
                out[opt.key] = ctrl.currentData()
            elif isinstance(ctrl, QSpinBox):
                out[opt.key] = ctrl.value()
            elif isinstance(ctrl, QCheckBox):
                out[opt.key] = ctrl.isChecked()
            elif isinstance(ctrl, _PosGrid):
                out[opt.key] = ctrl.value()
            elif isinstance(ctrl, _PagePlanField):
                out[opt.key] = ctrl.value()
            elif isinstance(ctrl, QPlainTextEdit):
                out[opt.key] = ctrl.toPlainText().strip()
            elif isinstance(ctrl, QLineEdit):
                # Passwords are taken verbatim (never stripped).
                out[opt.key] = (ctrl.text() if opt.key in self._password_keys
                                else ctrl.text().strip())
        return out

    def set_file_getter(self, fn) -> None:
        """Provide a callable returning the path the page_plan control should
        operate on (the tool page's selected/first file)."""
        self._file_getter = fn

    def prune_page_plans(self, present_paths) -> None:
        """Forget an organizer arrangement whose file has left the queue."""
        from pathlib import Path
        keep = {Path(p) for p in present_paths}
        for ctrl in self._controls.values():
            if isinstance(ctrl, _PagePlanField) and ctrl.target() is not None                     and Path(ctrl.target()) not in keep:
                ctrl.clear()

    def save(self) -> None:
        """Remember the current option values for next time — but never persist
        passwords or file-specific plans to disk."""
        skip = self._password_keys | self._no_save_keys
        # A control that is disabled (e.g. OCR "Use AI" before AI is set up)
        # holds a forced value, not a choice — saving it would override the
        # default once the feature becomes available.
        disabled = {k for k, c in self._controls.items() if not c.isEnabled()}
        vals = {k: v for k, v in self.values().items()
                if k not in skip and k not in disabled}
        old = settings.tool_options(self.tool.id)
        for k in disabled - skip:
            if k in old:
                vals[k] = old[k]              # keep a real earlier choice
        settings.set_tool_options(self.tool.id, vals)
