"""Builds a form of controls from a tool's Option specs and reads back values."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mico360.config import settings
from mico360.core.tools import Option, Tool


class OptionsWidget(QWidget):
    def __init__(self, tool: Tool, parent: QWidget | None = None):
        super().__init__(parent)
        self.tool = tool
        self._controls: dict[str, QWidget] = {}
        self._rows: dict[str, tuple[QWidget, QWidget]] = {}  # key -> (label, field)
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
        default = self._saved.get(opt.key, opt.default)
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
            chk = QCheckBox(opt.label)
            chk.setChecked(bool(default))
            chk.stateChanged.connect(self._apply_visibility)
            field = chk
        else:  # text
            le = QLineEdit(str(default if default is not None else ""))
            field = le

        self._controls[opt.key] = read_widget if read_widget is not None else field

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
            hint = QLabel(opt.hint)
            hint.setObjectName("Hint")
            hint.setWordWrap(True)
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
            elif isinstance(ctrl, QLineEdit):
                out[opt.key] = ctrl.text().strip()
        return out

    def save(self) -> None:
        """Remember the current option values for next time."""
        settings.set_tool_options(self.tool.id, self.values())
