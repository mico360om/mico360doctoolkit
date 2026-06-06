"""A self-contained, responsive page for a single tool.

Layout: header (icon + title + status chip) → a ResponsiveRow of the input
panel and the options panel (side-by-side on wide windows, stacked when narrow)
→ an activity log. The processing wiring is unchanged from the engine.

The input panel is a proper QUEUE: a compact drop band on top and a large file
list below, with a toolbar (Add files / Remove selected / Remove finished /
Clear all) and a right-click menu per row. Each row is an independent QueueItem
(by id, not path) so the same file can appear more than once (Duplicate), and
results are mapped back by submission index — robust to duplicates and to
reordering mid-run.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mico360.config import settings
from mico360.core.engine import BatchController, UnitResult
from mico360.core.tools import AGGREGATE, Tool
from mico360.core.util import human_size
from mico360.logging_setup import get_logger
from mico360.theme import palette
from mico360.ui.file_collector import collect_files
from mico360.ui.options_widget import OptionsWidget
from mico360.ui.widgets import (
    Card, Chip, DropArea, FileListWidget, ResponsiveRow, section_label)

log = get_logger("mico360.ui")

_row_ids = itertools.count(1)


@dataclass
class QueueItem:
    """One row in the queue. Identified by ``id`` (not path) so the same file
    can be queued more than once with independent status."""
    path: Path
    id: int = field(default_factory=lambda: next(_row_ids))
    state: str = "pending"          # pending | running | done | failed
    msg: str = ""
    outputs: list = field(default_factory=list)


class _StatusProxy:
    """A dict-like view over a QueueItem's status. Lets path-keyed callers do
    ``st["state"]`` / ``st.update(state=...)`` against the item model."""
    __slots__ = ("_it",)

    def __init__(self, item: QueueItem):
        self._it = item

    def __getitem__(self, key):
        return getattr(self._it, key)

    def __setitem__(self, key, value):
        setattr(self._it, key, value)

    def get(self, key, default=None):
        return getattr(self._it, key, default)

    def update(self, *args, **kw):
        for key, value in dict(*args, **kw).items():
            setattr(self._it, key, value)


class ToolPage(QWidget):
    activity = Signal(str)        # forwards notable lines to the global activity log
    toast = Signal(str, str)      # (message, kind) for a transient notification

    def __init__(self, tool: Tool, parent: QWidget | None = None):
        super().__init__(parent)
        self.tool = tool
        self.items: list[QueueItem] = []
        self._run_t0 = None
        self._run_total = 0
        self._run_items: list[QueueItem] = []   # snapshot submitted to a run
        self.controller: BatchController | None = None
        self._last_outputs: list[Path] = []
        self._build_ui()

    # -----------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        root.addLayout(self._build_header())

        # The options column is clamped to a stable width range so the split is
        # identical on every tool (no per-selection width jump) and the form
        # never sprawls on very wide windows; the files column takes the rest.
        self.body = ResponsiveRow(self._build_files_card(),
                                  self._build_options_card(),
                                  threshold=820, stretch=(3, 2),
                                  secondary_width=(320, 460))
        root.addWidget(self.body, 1)

        # Activity log (this run)
        log_card = Card()
        head = QHBoxLayout()
        head.addWidget(section_label("Activity"))
        head.addStretch(1)
        log_card.add_layout(head)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(80)
        self.log_view.setMaximumHeight(132)
        log_card.add(self.log_view)
        root.addWidget(log_card)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(12)
        icon = QLabel(self.tool.icon)
        icon.setObjectName("ToolIcon")
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        t = QLabel(self.tool.name)
        t.setObjectName("PageTitle")
        sub = QLabel(self.tool.tagline)
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        title_box.addWidget(t)
        title_box.addWidget(sub)
        header.addWidget(icon, 0, Qt.AlignTop)
        header.addLayout(title_box, 1)
        from PySide6.QtGui import QFont
        self.btn_fav = QPushButton()
        self.btn_fav.setObjectName("FavStar")
        self.btn_fav.setCursor(Qt.PointingHandCursor)
        self.btn_fav.setFixedSize(34, 32)
        _star_font = QFont("Segoe UI Symbol")
        _star_font.setPointSize(14)
        self.btn_fav.setFont(_star_font)
        self.btn_fav.clicked.connect(self._toggle_favorite)
        self._sync_fav()
        header.addWidget(self.btn_fav, 0, Qt.AlignTop)
        self.header_chip = Chip("Ready", "ready")
        header.addWidget(self.header_chip, 0, Qt.AlignTop)
        return header

    def _sync_fav(self) -> None:
        on = self.tool.id in settings.favorite_tools
        self.btn_fav.setText("★" if on else "☆")
        self.btn_fav.setProperty("pinned", "true" if on else "false")
        self.btn_fav.style().unpolish(self.btn_fav)
        self.btn_fav.style().polish(self.btn_fav)
        self.btn_fav.setToolTip("Unpin from favourites" if on
                                else "Pin to favourites (shown on Home)")

    def _toggle_favorite(self) -> None:
        settings.toggle_favorite(self.tool.id)
        self._sync_fav()

    def _build_files_card(self) -> Card:
        card = Card()
        head = QHBoxLayout()
        head.addWidget(section_label("Queue"))
        head.addStretch(1)
        self.count_lbl = QLabel("0 files")
        self.count_lbl.setObjectName("Hint")
        self.count_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.count_lbl)
        card.add_layout(head)

        # Compact drop band — small, so the queue gets the vertical space.
        self.drop = DropArea(compact=True)
        self.drop.pathsAdded.connect(self.add_paths)
        self.drop.browseFiles.connect(self._browse_files)
        self.drop.browseFolder.connect(self._browse_folder)
        card.add(self.drop)

        # The queue list — the star of the panel; it takes all the spare height.
        self.file_list = FileListWidget(
            "No files in the queue yet.\n\nDrag files onto the band above, "
            "or use Add files.")
        self.file_list.setObjectName("FileList")
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setMinimumHeight(220)
        self.file_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.file_list.itemDoubleClicked.connect(self._open_item_output)
        # Drag-to-reorder is always available now (a queue is inherently ordered);
        # self.items is re-synced from the view after any move.
        self.file_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.file_list.setDefaultDropAction(Qt.MoveAction)
        self.file_list.model().rowsMoved.connect(self._sync_order_from_list)
        self.file_list.setToolTip(
            "Drag to reorder. Double-click a finished row to open its output. "
            "Right-click for more.")
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._file_menu)
        from PySide6.QtGui import QKeySequence, QShortcut
        del_sc = QShortcut(QKeySequence(Qt.Key_Delete), self.file_list)
        del_sc.activated.connect(self._remove_selected)
        card.add(self.file_list)

        # Queue toolbar.
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_add = QPushButton("Add files")
        self.btn_add.setObjectName("Subtle")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setToolTip("Add files to the queue.")
        self.btn_add.clicked.connect(self._browse_files)

        self.btn_remove_sel = QPushButton("Remove selected")
        self.btn_remove_sel.setObjectName("Subtle")
        self.btn_remove_sel.setCursor(Qt.PointingHandCursor)
        self.btn_remove_sel.setToolTip("Take the selected rows off the queue (Del).")
        self.btn_remove_sel.clicked.connect(self._remove_selected)

        self.btn_remove_fin = QPushButton("Remove finished")
        self.btn_remove_fin.setObjectName("Subtle")
        self.btn_remove_fin.setCursor(Qt.PointingHandCursor)
        self.btn_remove_fin.setToolTip("Take every finished row (done or failed) off the queue.")
        self.btn_remove_fin.clicked.connect(self._remove_finished)

        self.btn_clear = QPushButton("Clear all")
        self.btn_clear.setObjectName("Subtle")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setToolTip("Empty the queue.")
        self.btn_clear.clicked.connect(self._clear)

        bar.addWidget(self.btn_add)
        bar.addStretch(1)
        bar.addWidget(self.btn_remove_sel)
        bar.addWidget(self.btn_remove_fin)
        bar.addWidget(self.btn_clear)
        card.add_layout(bar)
        self._update_counts()
        return card

    def _build_options_card(self) -> Card:
        card = Card()
        card.add(section_label("Options"))

        self.options_widget = OptionsWidget(self.tool)
        card.add(self.options_widget)

        card.add(section_label("Output"))
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        self.out_edit.setCursorPosition(0)
        self._set_output_path(settings.output_dir)
        btn_out = QPushButton("Change")
        btn_out.setObjectName("Ghost")
        btn_out.setCursor(Qt.PointingHandCursor)
        btn_out.clicked.connect(self._choose_output)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(btn_out)
        card.add_layout(out_row)

        self.chk_same = QCheckBox("Save beside originals")
        self.chk_same.setToolTip(
            "Saves each result in the same folder as its source, named "
            '"name (1).ext", "name (2).ext", … so your originals are never changed.')
        self.chk_same.setChecked(settings.same_as_source)
        self.chk_same.stateChanged.connect(self._sync_output_mode)
        self.out_edit.setEnabled(not self.chk_same.isChecked())
        card.add(self.chk_same)

        self.chk_overwrite = QCheckBox("Overwrite same-named files")
        self.chk_overwrite.setToolTip(
            "When an output file already exists, replace it instead of adding a "
            "number to the name.")
        self.chk_overwrite.setChecked(settings.overwrite)
        card.add(self.chk_overwrite)

        self.note_lbl = QLabel("Your original files are always kept untouched.")
        self.note_lbl.setObjectName("Muted")
        self.note_lbl.setWordWrap(True)
        card.add(self.note_lbl)
        self._sync_output_mode()

        card.layout().addStretch(1)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        card.add(self.progress)

        self.status_lbl = QLabel("Ready when you are.")
        self.status_lbl.setObjectName("Hint")
        card.add(self.status_lbl)

        actions = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setToolTip(f"Start {self.tool.name}")
        self.btn_start.clicked.connect(self.start)
        self.btn_open = QPushButton("Open output")
        self.btn_open.setObjectName("Ghost")
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setToolTip("Open the folder of the last results.")
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_last_output)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("Ghost")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        actions.addWidget(self.btn_start, 1)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_cancel)
        card.add_layout(actions)
        return card

    def _sync_output_mode(self) -> None:
        """Reflect the 'save next to source' choice in the output controls."""
        same = self.chk_same.isChecked()
        self.out_edit.setEnabled(not same)
        if same:
            self.note_lbl.setText(
                'Saved beside each source as "name (1).ext", "name (2).ext", … — '
                "originals untouched.")
        else:
            self.note_lbl.setText("Your original files are always kept untouched.")

    # -----------------------------------------------------------------
    # Queue model helpers
    # -----------------------------------------------------------------
    def _selected_items(self) -> list[QueueItem]:
        """QueueItems for the current selection, in on-screen (top→bottom) order."""
        ids = []
        for i in self.file_list.selectedItems():
            ids.append(i.data(Qt.UserRole))
        by_id = {it.id: it for it in self.items}
        # Preserve view order.
        ordered = []
        for r in range(self.file_list.count()):
            rid = self.file_list.item(r).data(Qt.UserRole)
            if rid in ids and rid in by_id:
                ordered.append(by_id[rid])
        return ordered

    def _item_at_row(self, row: int) -> QueueItem | None:
        if 0 <= row < len(self.items):
            return self.items[row]
        return None

    # --- backward-compatible, path-keyed accessors over the item model -------
    @property
    def files(self) -> list:
        return [it.path for it in self.items]

    @files.setter
    def files(self, paths) -> None:
        self.items = [QueueItem(path=Path(p)) for p in paths]
        self._refresh_list()

    @property
    def status(self) -> dict:
        return {it.path: _StatusProxy(it) for it in self.items}

    def _st(self, p) -> _StatusProxy:
        for it in self.items:
            if it.path == p:
                return _StatusProxy(it)
        it = QueueItem(path=Path(p))
        self.items.append(it)
        return _StatusProxy(it)

    def _redo(self) -> None:
        """Reset every finished/failed row back to pending."""
        self._retry([it for it in self.items if it.state in ("done", "failed")])

    def _remove_done(self) -> None:
        """Remove only successfully-done rows (failed rows stay)."""
        before = len(self.items)
        self.items = [it for it in self.items if it.state != "done"]
        if len(self.items) != before:
            self._refresh_list()

    # -----------------------------------------------------------------
    # File management
    # -----------------------------------------------------------------
    def add_paths(self, paths: list) -> None:
        found = collect_files(paths, self.tool.accept)
        existing = {p.resolve() for p in (it.path for it in self.items)}
        added = 0
        for p in found:
            if p.resolve() not in existing:
                self.items.append(QueueItem(path=p))
                existing.add(p.resolve())
                added += 1
        self._refresh_list()
        if added:
            self._log(f"Added {added} file(s).")
        elif found:
            self._log("Those files are already in the queue.")
        else:
            self._log("No supported files found in the selection.")

    _ICONS = {"pending": "•", "done": "✓", "failed": "✗", "running": "⏳"}

    def _refresh_list(self) -> None:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QListWidgetItem

        theme = palette(settings.theme)
        colors = {"done": QColor(theme["success"]), "failed": QColor(theme["error"]),
                  "running": QColor(theme["info"])}
        # Preserve selection across the rebuild (by row id).
        prev_sel = {self.file_list.item(r).data(Qt.UserRole)
                    for r in range(self.file_list.count())
                    if self.file_list.item(r).isSelected()}
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for it in self.items:
            try:
                size = human_size(it.path.stat().st_size)
            except OSError:
                size = "?"
            icon = self._ICONS.get(it.state, "•")
            tail = f"    ·    {it.msg}" if it.msg else ""
            row = QListWidgetItem(f"{icon}  {it.path.name}    —    {size}{tail}")
            row.setToolTip(str(it.path) + (f"\n{it.msg}" if it.msg else ""))
            row.setData(Qt.UserRole, it.id)
            if it.state in colors:
                row.setForeground(colors[it.state])
            self.file_list.addItem(row)
            if it.id in prev_sel:
                row.setSelected(True)
        self.file_list.blockSignals(False)
        self._update_counts()

    def _sync_order_from_list(self, *args) -> None:
        """After a drag-reorder, rebuild self.items to match the on-screen order."""
        by_id = {it.id: it for it in self.items}
        new = [by_id[i] for i in (self.file_list.item(r).data(Qt.UserRole)
                                  for r in range(self.file_list.count()))
               if i in by_id]
        if len(new) == len(self.items):
            self.items = new
            self._update_counts()

    def _counts(self) -> tuple[int, int, int, int]:
        n = len(self.items)
        done = sum(1 for it in self.items if it.state == "done")
        failed = sum(1 for it in self.items if it.state == "failed")
        pending = n - done - failed - sum(1 for it in self.items if it.state == "running")
        return n, done, failed, max(0, pending)

    def _update_counts(self) -> None:
        n, done, failed, pending = self._counts()
        if n == 0:
            self.count_lbl.setText("0 files")
            self.count_lbl.setToolTip("")
        else:
            total_bytes = 0
            for it in self.items:
                try:
                    total_bytes += it.path.stat().st_size
                except OSError:
                    pass
            bits = [f"{n} file{'s' if n != 1 else ''}", human_size(total_bytes)]
            if pending:
                bits.append(f"{pending} pending")
            if done:
                bits.append(f"{done} done")
            if failed:
                bits.append(f"{failed} failed")
            summary = "  ·  ".join(bits)
            self.count_lbl.setText(summary)
            self.count_lbl.setToolTip(summary)
        running = self.controller is not None
        self.btn_remove_sel.setEnabled(n > 0)
        self.btn_remove_fin.setEnabled((done + failed) > 0)
        self.btn_clear.setEnabled(n > 0 and not running)

    def _remove_selected(self) -> None:
        sel = {it.id for it in self._selected_items()}
        if not sel:
            return
        self.items = [it for it in self.items if it.id not in sel]
        self._refresh_list()

    def _remove_finished(self) -> None:
        before = len(self.items)
        self.items = [it for it in self.items if it.state not in ("done", "failed")]
        removed = before - len(self.items)
        self._refresh_list()
        if removed:
            self._log(f"Removed {removed} finished row(s).")

    def _clear(self) -> None:
        self.items.clear()
        self._refresh_list()

    def _total_saved(self) -> str:
        """For compression tools, summarise the total bytes saved this batch."""
        if self.tool.id not in ("pdf_compress", "image_compress"):
            return ""
        before = after = 0
        for it in self.items:
            outs = it.outputs or []
            if it.state != "done" or not outs:
                continue
            try:
                before += it.path.stat().st_size
                after += sum(o.stat().st_size for o in outs if o.exists())
            except OSError:
                continue
        if before <= 0 or after <= 0:
            return ""
        diff = before - after
        pct = diff / before * 100
        if diff > 0:
            return f"saved {human_size(diff)} ({pct:.0f}%)"
        return "already optimized (no reduction)"

    def _browse_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(self.tool.accept))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select files", "", f"Supported files ({exts});;All files (*.*)")
        if files:
            self.add_paths(files)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select a folder")
        if folder:
            self.add_paths([folder])

    def _set_output_path(self, path: str) -> None:
        self.out_edit.setText(path)
        self.out_edit.setToolTip(path)
        self.out_edit.setCursorPosition(len(path))

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder",
                                                  self.out_edit.text())
        if folder:
            self._set_output_path(folder)
            settings.output_dir = folder

    # -----------------------------------------------------------------
    # Right-click context menu
    # -----------------------------------------------------------------
    def _file_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        clicked = self.file_list.itemAt(pos)
        if clicked is None:
            return
        # If the right-clicked row isn't part of the selection, select just it.
        if not clicked.isSelected():
            self.file_list.clearSelection()
            clicked.setSelected(True)
        sel = self._selected_items()
        if not sel:
            return
        n = len(sel)
        s = "s" if n != 1 else ""
        primary = sel[0]
        has_output = any(it.outputs for it in sel)
        has_finished = any(it.state in ("done", "failed") for it in sel)

        menu = QMenu(self)
        act_src = menu.addAction("Open source folder")
        act_out = menu.addAction("Open output folder")
        act_out.setEnabled(has_output)
        menu.addSeparator()
        act_top = menu.addAction("Move to top")
        act_bottom = menu.addAction("Move to bottom")
        act_dup = menu.addAction(f"Duplicate row{s}")
        act_retry = menu.addAction(f"Retry failed/done row{s}")
        act_retry.setEnabled(has_finished)
        menu.addSeparator()
        act_remove = menu.addAction(f"Remove {n} from queue")
        act_delete = menu.addAction(f"Delete {n} from disk…")

        chosen = menu.exec(self.file_list.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_src:
            self._open_in_explorer(primary.path)
        elif chosen is act_out:
            self._open_output_for(sel)
        elif chosen is act_top:
            self._move_selected(to_top=True)
        elif chosen is act_bottom:
            self._move_selected(to_top=False)
        elif chosen is act_dup:
            self._duplicate(sel)
        elif chosen is act_retry:
            self._retry(sel)
        elif chosen is act_remove:
            self._remove_selected()
        elif chosen is act_delete:
            self._delete_from_disk(sel)

    def _open_output_for(self, items: list[QueueItem]) -> None:
        for it in items:
            if it.outputs:
                self._open_in_explorer(it.outputs[0])
                return
        self._log("No output yet for the selected row(s) — click Start first.")

    def _move_selected(self, to_top: bool) -> None:
        sel_ids = {it.id for it in self._selected_items()}
        if not sel_ids:
            return
        moved = [it for it in self.items if it.id in sel_ids]
        rest = [it for it in self.items if it.id not in sel_ids]
        self.items = moved + rest if to_top else rest + moved
        self._refresh_list()
        # Keep the moved rows selected at their new home.
        self._select_ids(sel_ids)

    def _select_ids(self, ids: set) -> None:
        for r in range(self.file_list.count()):
            if self.file_list.item(r).data(Qt.UserRole) in ids:
                self.file_list.item(r).setSelected(True)

    def _duplicate(self, items: list[QueueItem]) -> None:
        """Insert a fresh (pending) copy of each selected row right after it."""
        by_id = {it.id: it for it in items}
        new_list: list[QueueItem] = []
        new_ids = set()
        for it in self.items:
            new_list.append(it)
            if it.id in by_id:
                copy = QueueItem(path=it.path)
                new_list.append(copy)
                new_ids.add(copy.id)
        self.items = new_list
        self._refresh_list()
        self._select_ids(new_ids)
        self._log(f"Duplicated {len(by_id)} row(s).")

    def _retry(self, items: list[QueueItem]) -> None:
        reset = 0
        for it in items:
            if it.state in ("done", "failed"):
                it.state, it.msg, it.outputs = "pending", "", []
                reset += 1
        self._refresh_list()
        if reset:
            self._log(f"Reset {reset} row(s) to pending — Start will process them again.")

    def _delete_from_disk(self, items: list[QueueItem]) -> None:
        from PySide6.QtGui import QGuiApplication
        from mico360.core.platform_utils import move_to_trash

        # Distinct source paths (duplicates of the same file map to one delete).
        paths = []
        seen = set()
        for it in items:
            rp = it.path.resolve()
            if rp not in seen:
                seen.add(rp)
                paths.append(it.path)
        n = len(paths)
        if n == 0:
            return
        if QGuiApplication.platformName() != "offscreen":
            names = "\n".join(f"• {p.name}" for p in paths[:10])
            more = f"\n…and {n - 10} more" if n > 10 else ""
            res = QMessageBox.question(
                self, "Delete from disk?",
                f"Send {n} source file(s) to the Recycle Bin?\n\n{names}{more}\n\n"
                "They can be restored from the Recycle Bin.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if res != QMessageBox.Yes:
                return
        trashed = set()
        failed = 0
        for p in paths:
            if move_to_trash(p):
                trashed.add(p.resolve())
            else:
                failed += 1
        # Drop every row whose source was trashed (covers duplicates too).
        self.items = [it for it in self.items if it.path.resolve() not in trashed]
        self._refresh_list()
        self._log(f"Deleted {len(trashed)} file(s) to the Recycle Bin"
                  + (f"; {failed} could not be deleted." if failed else "."))
        if failed and QGuiApplication.platformName() != "offscreen":
            QMessageBox.warning(self, "Delete from disk",
                                f"{failed} file(s) could not be sent to the Recycle Bin.")

    # -----------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------
    def start(self) -> None:
        if not self.items:
            QMessageBox.information(self, "No files", "Add one or more files first.")
            return

        # Only process rows that are not already done; "done" rows are skipped
        # until the user retries (or removes & re-adds them).
        todo = [it for it in self.items if it.state != "done"]
        if not todo:
            QMessageBox.information(
                self, "Already done",
                "Every row here is already done.\n\nRight-click → \"Retry\" to "
                "process them again, or add new files.")
            return
        if self.tool.mode == AGGREGATE and self.tool.id == "pdf_merge" and len(todo) < 2:
            QMessageBox.information(self, "Need more files",
                                    "Select at least two PDFs to merge.")
            return

        skipped_done = len(self.items) - len(todo)
        options = self.options_widget.values()
        self.options_widget.save()           # remember these for next time
        options["overwrite"] = self.chk_overwrite.isChecked()
        same_as_source = self.chk_same.isChecked()
        out_dir = Path(self.out_edit.text())

        settings.same_as_source = same_as_source
        settings.overwrite = self.chk_overwrite.isChecked()

        for it in todo:                      # mark queued rows as running
            it.state, it.msg = "running", ""
        self._run_items = list(todo)         # snapshot: index aligns with engine
        self._refresh_list()

        self._set_running(True)
        self.progress.setMaximum(0)  # busy until 'started' sets total
        self.log_view.clear()
        msg = f"Starting {self.tool.name} on {len(todo)} file(s)…"
        if skipped_done:
            msg += f"  ({skipped_done} already done, skipped)"
        self._log(msg)

        self.controller = BatchController(max_workers=settings.max_workers, parent=self)
        c = self.controller
        c.started.connect(self._on_started)
        c.progress.connect(self._on_progress)
        c.fine_progress.connect(self._on_fine_progress)
        c.log.connect(self._on_unit_log)
        c.unit_finished.connect(self._on_unit_finished)
        c.finished.connect(self._on_finished)
        c.start(self.tool, [it.path for it in todo], out_dir, options, same_as_source)

    def _cancel(self) -> None:
        if self.controller:
            self.controller.cancel()
            self._log("Cancelling… (in-flight files will finish)")
            self.btn_cancel.setEnabled(False)

    def _set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        if running:
            self.header_chip.set_state("run", "Working…")
        self._update_counts()

    def _on_started(self, total: int) -> None:
        import time
        self._run_t0 = time.monotonic()
        self._run_total = total
        if total > 1:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        else:
            self.progress.setRange(0, 0)
        self._update_progress_detail(0.0)

    def _on_fine_progress(self, pct: float) -> None:
        if self.progress.maximum() == 0:        # was the busy/animated bar
            self.progress.setRange(0, 100)
        self.progress.setValue(int(round(pct)))
        self._update_progress_detail(pct)

    def _on_progress(self, done: int, total: int) -> None:
        self._update_progress_detail(self.progress.value()
                                     if self.progress.maximum() else 0.0)

    @staticmethod
    def _fmt_eta(secs: float) -> str:
        secs = int(max(0, secs))
        if secs >= 60:
            return f"{secs // 60}m {secs % 60:02d}s"
        return f"{secs}s"

    def _update_progress_detail(self, pct: float) -> None:
        total = self._run_total or len(self.items) or 1
        done = sum(1 for it in self.items if it.state in ("done", "failed"))
        running = next((it.path.name for it in self.items
                        if it.state == "running"), None)
        parts = [f"Processing {min(done + 1, total)} / {total} files"]
        if running:
            parts.append(f"Current: {running}")
        if self._run_t0 is not None and pct and pct > 1:
            import time
            elapsed = time.monotonic() - self._run_t0
            remaining = elapsed * (100.0 - pct) / max(pct, 1.0)
            parts.append(f"ETA {self._fmt_eta(remaining)}")
        self.status_lbl.setText("   ·   ".join(parts))

    def _on_unit_log(self, label: str, message: str) -> None:
        self._log(f"  {label}: {message}")

    def _on_unit_finished(self, result: UnitResult) -> None:
        # Map the result back to the submitted row(s) BY INDEX (robust to
        # duplicates and to reordering during the run).
        if result.skipped:
            new_state, note = "pending", ""
            self._log(f"⏭  {result.label} — skipped")
        elif result.ok:
            outs = result.outputs or []
            note = (f"→ {outs[0].name}" if len(outs) == 1
                    else (f"→ {len(outs)} files" if outs else "done"))
            new_state = "done"
            self._log(f"✓  {result.label} — done")
        else:
            new_state, note = "failed", result.message
            self._log(f"✗  {result.label} — {result.message}")

        if self.tool.mode == AGGREGATE:
            targets = list(self._run_items)
        elif 0 <= result.index < len(self._run_items):
            # Normal path: map by submission index (robust to duplicates).
            targets = [self._run_items[result.index]]
        else:
            targets = []
        if not targets:
            # Fallback (direct calls / stale snapshot): map by source path,
            # preferring rows currently marked running.
            srcs = {Path(s) for s in (result.sources or [])}
            targets = [it for it in self.items
                       if it.path in srcs and it.state == "running"]
            if not targets:
                targets = [it for it in self.items if it.path in srcs]
        for it in targets:
            it.state, it.msg, it.outputs = new_state, note, list(result.outputs or [])
        self._refresh_list()

    def _on_finished(self, summary: dict) -> None:
        self.controller = None
        self._set_running(False)
        total = max(1, summary.get("total", 1))
        processed = summary.get("ok", 0) + summary.get("failed", 0)
        self.progress.setRange(0, 100)
        self.progress.setValue(int(100 * processed / total)
                               if summary.get("cancelled") else 100)
        elapsed = summary["elapsed"]
        msg = (f"Done — {summary['ok']} ok, {summary['failed']} failed, "
               f"{summary['skipped']} skipped in {elapsed:.1f}s")
        saved = self._total_saved()
        if saved:
            msg += f"  ·  {saved}"
        self.status_lbl.setText(msg)
        self._log(msg)
        self.activity.emit(f"[{self.tool.name}] {msg}")

        from PySide6.QtGui import QGuiApplication
        if summary["failed"]:
            self.header_chip.set_state("err", "Errors")
            if QGuiApplication.platformName() != "offscreen":
                details = "\n".join(f"• {lbl}: {err}"
                                    for lbl, err in summary["errors"][:12])
                QMessageBox.warning(self, "Completed with errors",
                                    f"{summary['failed']} file(s) failed:\n\n{details}")
        elif summary["cancelled"]:
            self.header_chip.set_state("ready", "Cancelled")
        else:
            self.header_chip.set_state("ok", "Done")

        outputs = summary.get("outputs") or []
        self._last_outputs = list(outputs)
        self.btn_open.setEnabled(bool(outputs))

        if outputs:
            try:
                settings.add_recent_files([str(o) for o in outputs])
            except Exception:
                pass
        ok, failed = summary.get("ok", 0), summary.get("failed", 0)
        if summary.get("cancelled"):
            settings.add_activity(f"{self.tool.name} — cancelled")
        elif failed:
            settings.add_activity(f"{self.tool.name} — {ok} done, {failed} failed")
            self.toast.emit(f"{self.tool.name}: {failed} file(s) failed", "error")
        else:
            settings.add_activity(f"{self.tool.name} — {ok} file(s) done")
            self.toast.emit(f"{self.tool.name}: {ok} file(s) done", "ok")

        if (outputs and settings.open_output_when_done and not summary["cancelled"]
                and QGuiApplication.platformName() != "offscreen"):
            self._open_in_explorer(outputs[0])

    # -----------------------------------------------------------------
    def _open_in_explorer(self, sample: Path) -> None:
        from mico360.core.platform_utils import reveal
        reveal(sample)

    def _open_last_output(self) -> None:
        if self._last_outputs:
            self._open_in_explorer(self._last_outputs[0])

    def _open_item_output(self, item) -> None:
        """Double-click a finished row to reveal its output."""
        row = self.file_list.row(item)
        it = self._item_at_row(row)
        if it is None:
            return
        if it.outputs:
            self._open_in_explorer(it.outputs[0])
        else:
            self._log("That row hasn't been processed yet — click Start.")

    def _log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())
