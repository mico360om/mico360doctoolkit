"""A self-contained, responsive page for a single tool.

Layout: header (icon + title + status chip) → a ResponsiveRow of the input
panel and the options panel (side-by-side on wide windows, stacked when narrow)
→ an activity log. The processing wiring is unchanged from the engine.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
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
from mico360.ui.widgets import Card, Chip, DropArea, ResponsiveRow, section_label

log = get_logger("mico360.ui")


class ToolPage(QWidget):
    activity = Signal(str)        # forwards notable lines to the global activity log
    toast = Signal(str, str)      # (message, kind) for a transient notification

    def __init__(self, tool: Tool, parent: QWidget | None = None):
        super().__init__(parent)
        self.tool = tool
        self.files: list[Path] = []
        self._run_t0 = None
        self._run_total = 0
        # Per-file processing status: path -> {"state","msg","outputs"}.
        # state is one of: pending | done | failed.
        self.status: dict[Path, dict] = {}
        self.controller: BatchController | None = None
        self._last_outputs: list[Path] = []
        self._build_ui()

    def _st(self, p: Path) -> dict:
        return self.status.setdefault(p, {"state": "pending", "msg": "", "outputs": []})

    # -----------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        root.addLayout(self._build_header())

        self.body = ResponsiveRow(self._build_files_card(),
                                  self._build_options_card(),
                                  threshold=860, stretch=(3, 2))
        root.addWidget(self.body)

        # Activity log (this run)
        log_card = Card()
        head = QHBoxLayout()
        head.addWidget(section_label("Activity"))
        head.addStretch(1)
        log_card.add_layout(head)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(96)
        self.log_view.setMaximumHeight(150)
        log_card.add(self.log_view)
        root.addWidget(log_card)
        root.addStretch(0)

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
        head.addWidget(section_label("Input files"))
        head.addStretch(1)
        types = QLabel(" · ".join(e.lstrip(".").upper() for e in sorted(self.tool.accept)))
        types.setObjectName("Muted")
        head.addWidget(types)
        card.add_layout(head)

        self.drop = DropArea()
        self.drop.set_formats(self.tool.accept)
        self.drop.pathsAdded.connect(self.add_paths)
        self.drop.browseFiles.connect(self._browse_files)
        self.drop.browseFolder.connect(self._browse_folder)
        card.add(self.drop)

        self.file_list = QListWidget()
        self.file_list.setObjectName("FileList")
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setMinimumHeight(120)
        self.file_list.itemDoubleClicked.connect(self._open_item_output)
        tip = ("Double-click a finished file to open its output. Right-click for more.")
        # For tools where input order matters (Merge, combined Image → PDF), let
        # the user drag rows to reorder; keep self.files in sync with the view.
        if self.tool.mode == AGGREGATE:
            self.file_list.setDragDropMode(QAbstractItemView.InternalMove)
            self.file_list.setDefaultDropAction(Qt.MoveAction)
            self.file_list.model().rowsMoved.connect(self._sync_order_from_list)
            tip = "Drag to reorder. " + tip
        self.file_list.setToolTip(tip)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._file_menu)
        from PySide6.QtGui import QKeySequence, QShortcut
        del_sc = QShortcut(QKeySequence(Qt.Key_Delete), self.file_list)
        del_sc.activated.connect(self._remove_selected)
        card.add(self.file_list)

        row = QHBoxLayout()
        self.count_lbl = QLabel("No files yet")
        self.count_lbl.setObjectName("Hint")
        row.addWidget(self.count_lbl)
        row.addStretch(1)
        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setObjectName("Subtle")
        self.btn_redo.setCursor(Qt.PointingHandCursor)
        self.btn_redo.setToolTip("Mark finished files as pending so they process again.")
        self.btn_redo.clicked.connect(self._redo)
        self.btn_remove_done = QPushButton("Remove done")
        self.btn_remove_done.setObjectName("Subtle")
        self.btn_remove_done.setCursor(Qt.PointingHandCursor)
        self.btn_remove_done.setToolTip("Take finished files off the list.")
        self.btn_remove_done.clicked.connect(self._remove_done)
        btn_clear = QPushButton("Clear all")
        btn_clear.setObjectName("Subtle")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._clear)
        row.addWidget(self.btn_redo)
        row.addWidget(self.btn_remove_done)
        row.addWidget(btn_clear)
        card.add_layout(row)
        return card

    def _build_options_card(self) -> Card:
        card = Card()
        card.add(section_label("Options"))

        self.options_widget = OptionsWidget(self.tool)
        card.add(self.options_widget)

        card.add(section_label("Output"))
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit(settings.output_dir)
        self.out_edit.setReadOnly(True)
        btn_out = QPushButton("Change")
        btn_out.setObjectName("Ghost")
        btn_out.setCursor(Qt.PointingHandCursor)
        btn_out.clicked.connect(self._choose_output)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(btn_out)
        card.add_layout(out_row)

        self.chk_same = QCheckBox("Save next to the original files")
        self.chk_same.setToolTip(
            "Saves each result in the same folder as its source, named "
            '"name (1).ext", "name (2).ext", … so your originals are never changed.')
        self.chk_same.setChecked(settings.same_as_source)
        self.chk_same.stateChanged.connect(self._sync_output_mode)
        self.out_edit.setEnabled(not self.chk_same.isChecked())
        card.add(self.chk_same)

        self.chk_overwrite = QCheckBox("Overwrite files with the same name")
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
        self.btn_start = QPushButton(f"Start  ·  {self.tool.name}")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
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
    # File management
    # -----------------------------------------------------------------
    def add_paths(self, paths: list) -> None:
        found = collect_files(paths, self.tool.accept)
        existing = {p.resolve() for p in self.files}
        added = 0
        for p in found:
            if p.resolve() not in existing:
                self.files.append(p)
                existing.add(p.resolve())
                added += 1
        self._refresh_list()
        if added:
            self._log(f"Added {added} file(s).")
        elif found:
            self._log("Those files are already in the list.")
        else:
            self._log("No supported files found in the selection.")

    _ICONS = {"pending": "•", "done": "✓", "failed": "✗", "running": "⏳"}

    def _refresh_list(self) -> None:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QListWidgetItem

        theme = palette(settings.theme)
        colors = {"done": QColor(theme["success"]), "failed": QColor(theme["error"]),
                  "running": QColor(theme["info"])}
        self.file_list.clear()
        for p in self.files:
            try:
                size = human_size(p.stat().st_size)
            except OSError:
                size = "?"
            st = self._st(p)
            icon = self._ICONS.get(st["state"], "•")
            tail = f"    ·    {st['msg']}" if st["msg"] else ""
            item = QListWidgetItem(f"{icon}  {p.name}    —    {size}{tail}")
            item.setToolTip(str(p.parent) + (f"\n{st['msg']}" if st["msg"] else ""))
            item.setData(Qt.UserRole, str(p))   # used to re-sync order after a drag
            if st["state"] in colors:
                item.setForeground(colors[st["state"]])
            self.file_list.addItem(item)
        self._update_counts()

    def _sync_order_from_list(self, *args) -> None:
        """After a drag-reorder, rebuild self.files to match the on-screen order."""
        by_str = {str(p): p for p in self.files}
        new = [by_str[s] for s in (self.file_list.item(r).data(Qt.UserRole)
                                   for r in range(self.file_list.count()))
               if s in by_str]
        if len(new) == len(self.files):
            self.files = new
            self._update_counts()

    def _update_counts(self) -> None:
        n = len(self.files)
        if n == 0:
            self.count_lbl.setText("No files yet")
            self.btn_redo.setEnabled(False)
            return
        done = sum(1 for p in self.files if self._st(p)["state"] == "done")
        failed = sum(1 for p in self.files if self._st(p)["state"] == "failed")
        pending = n - done - failed
        total_bytes = 0
        for p in self.files:
            try:
                total_bytes += p.stat().st_size
            except OSError:
                pass
        bits = [f"{n} file(s)", human_size(total_bytes)]
        if done:
            bits.append(f"{done} done")
        if failed:
            bits.append(f"{failed} failed")
        if pending:
            bits.append(f"{pending} pending")
        self.count_lbl.setText("  ·  ".join(bits))
        self.btn_redo.setEnabled(done > 0 or failed > 0)

    def _remove_selected(self) -> None:
        rows = sorted((self.file_list.row(i) for i in self.file_list.selectedItems()),
                      reverse=True)
        for r in rows:
            self.status.pop(self.files[r], None)
            del self.files[r]
        self._refresh_list()

    def _clear(self) -> None:
        self.files.clear()
        self.status.clear()
        self._refresh_list()

    def _redo(self) -> None:
        """Reset finished/failed files back to pending so they run again."""
        reset = 0
        for p in self.files:
            st = self._st(p)
            if st["state"] in ("done", "failed"):
                st.update(state="pending", msg="", outputs=[])
                reset += 1
        self._refresh_list()
        if reset:
            self._log(f"Reset {reset} file(s) to pending — Start will process them again.")

    def _remove_done(self) -> None:
        keep = [p for p in self.files if self._st(p)["state"] != "done"]
        removed = len(self.files) - len(keep)
        for p in self.files:
            if self._st(p)["state"] == "done":
                self.status.pop(p, None)
        self.files = keep
        self._refresh_list()
        if removed:
            self._log(f"Removed {removed} finished file(s).")

    def _total_saved(self) -> str:
        """For compression tools, summarise the total bytes saved this batch."""
        if self.tool.id not in ("pdf_compress", "image_compress"):
            return ""
        before = after = 0
        for p in self.files:
            st = self._st(p)
            outs = st.get("outputs") or []
            if st["state"] != "done" or not outs:
                continue
            try:
                before += p.stat().st_size
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

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder",
                                                  self.out_edit.text())
        if folder:
            self.out_edit.setText(folder)
            settings.output_dir = folder

    # -----------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------
    def start(self) -> None:
        if not self.files:
            QMessageBox.information(self, "No files", "Add one or more files first.")
            return

        # Only process files that are not already done; "done" files are skipped
        # until the user clicks Redo (or removes & re-adds them).
        todo = [p for p in self.files if self._st(p)["state"] != "done"]
        if not todo:
            QMessageBox.information(
                self, "Already done",
                "Every file here is already done.\n\nClick \"Redo\" to process "
                "them again, or add new files.")
            return
        if self.tool.mode == AGGREGATE and self.tool.id == "pdf_merge" and len(todo) < 2:
            QMessageBox.information(self, "Need more files",
                                    "Select at least two PDFs to merge.")
            return

        skipped_done = len(self.files) - len(todo)
        options = self.options_widget.values()
        self.options_widget.save()           # remember these for next time
        options["overwrite"] = self.chk_overwrite.isChecked()
        same_as_source = self.chk_same.isChecked()
        out_dir = Path(self.out_edit.text())

        settings.same_as_source = same_as_source
        settings.overwrite = self.chk_overwrite.isChecked()

        for p in todo:                       # mark queued files as running
            self._st(p).update(state="running", msg="")
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
        c.start(self.tool, list(todo), out_dir, options, same_as_source)

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

    def _on_started(self, total: int) -> None:
        import time
        self._run_t0 = time.monotonic()
        self._run_total = total
        if total > 1:
            # Multi-file: determinate from the start; fine_progress fills it as
            # files (and their pages) complete.
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        else:
            # Single unit: start as an animated busy bar; it becomes a real
            # 0→100 bar the moment the processor reports per-page progress.
            self.progress.setRange(0, 0)
        self._update_progress_detail(0.0)

    def _on_fine_progress(self, pct: float) -> None:
        if self.progress.maximum() == 0:        # was the busy/animated bar
            self.progress.setRange(0, 100)
        self.progress.setValue(int(round(pct)))
        self._update_progress_detail(pct)

    def _on_progress(self, done: int, total: int) -> None:
        # Per-unit counter drives the status text; the bar uses fine_progress.
        self._update_progress_detail(self.progress.value()
                                     if self.progress.maximum() else 0.0)

    @staticmethod
    def _fmt_eta(secs: float) -> str:
        secs = int(max(0, secs))
        if secs >= 60:
            return f"{secs // 60}m {secs % 60:02d}s"
        return f"{secs}s"

    def _update_progress_detail(self, pct: float) -> None:
        total = self._run_total or len(self.files) or 1
        done = sum(1 for p in self.files if self._st(p)["state"] in ("done", "failed"))
        running = next((p.name for p in self.files
                        if self._st(p)["state"] == "running"), None)
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
        # Map the result back to its source file(s) and record the status.
        if result.skipped:
            new_state, note = "pending", ""   # cancelled -> stays to-do
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
        for src in (result.sources or []):
            st = self._st(src)
            st.update(state=new_state, msg=note, outputs=list(result.outputs or []))
        self._refresh_list()

    def _on_finished(self, summary: dict) -> None:
        self._set_running(False)
        # Settle the (possibly busy/animated) bar to the real final value (0-100).
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

        if summary["failed"]:
            self.header_chip.set_state("err", "Errors")
            details = "\n".join(f"• {lbl}: {err}" for lbl, err in summary["errors"][:12])
            QMessageBox.warning(self, "Completed with errors",
                                f"{summary['failed']} file(s) failed:\n\n{details}")
        elif summary["cancelled"]:
            self.header_chip.set_state("ready", "Cancelled")
        else:
            self.header_chip.set_state("ok", "Done")

        outputs = summary.get("outputs") or []
        self._last_outputs = list(outputs)
        self.btn_open.setEnabled(bool(outputs))

        # Record recent files + activity for the dashboard, and toast the result.
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

        if outputs and settings.open_output_when_done and not summary["cancelled"]:
            self._open_in_explorer(outputs[0])
        self.controller = None

    # -----------------------------------------------------------------
    def _open_in_explorer(self, sample: Path) -> None:
        try:
            folder = sample.parent if sample.is_file() else sample
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(sample)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception:
            pass

    def _open_last_output(self) -> None:
        if self._last_outputs:
            self._open_in_explorer(self._last_outputs[0])

    def _open_item_output(self, item) -> None:
        """Double-click a finished file to reveal its output."""
        row = self.file_list.row(item)
        if 0 <= row < len(self.files):
            outs = self._st(self.files[row]).get("outputs") or []
            if outs:
                self._open_in_explorer(outs[0])
            else:
                self._log("That file hasn't been processed yet — click Start.")

    def _file_menu(self, pos) -> None:
        """Right-click menu for a file: open output / source, redo, remove."""
        from PySide6.QtWidgets import QMenu

        item = self.file_list.itemAt(pos)
        if item is None:
            return
        row = self.file_list.row(item)
        if not (0 <= row < len(self.files)):
            return
        p = self.files[row]
        st = self._st(p)
        menu = QMenu(self)
        act_out = menu.addAction("Open output")
        act_out.setEnabled(bool(st.get("outputs")))
        menu.addAction("Open source folder")
        redo = menu.addAction("Redo this file")
        redo.setEnabled(st["state"] in ("done", "failed"))
        menu.addSeparator()
        menu.addAction("Remove from list")
        chosen = menu.exec(self.file_list.mapToGlobal(pos))
        if chosen is None:
            return
        text = chosen.text()
        if text == "Open output" and st.get("outputs"):
            self._open_in_explorer(st["outputs"][0])
        elif text == "Open source folder":
            self._open_in_explorer(p)
        elif text == "Redo this file":
            st.update(state="pending", msg="", outputs=[])
            self._refresh_list()
        elif text == "Remove from list":
            self.status.pop(p, None)
            del self.files[row]
            self._refresh_list()

    def _log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())
