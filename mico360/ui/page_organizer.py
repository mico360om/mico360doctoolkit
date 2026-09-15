"""Visual page organizer — a thumbnail grid for a single PDF where pages can be
dragged to reorder, rotated, deleted, and split into several output files.

The dialog is self-contained: it renders page thumbnails with PyMuPDF, lets the
user rearrange them, and hands back a *plan* that :func:`mico360.core.processors.
pdf_organize` (operation ``"visual"``) applies:

    {"n_src": <original page count>,
     "groups": [ [ {"src": <0-based orig index>, "rotate": <0|90|180|270>}, ... ],
                 ...  # one list per output file; >1 list == split ]}

Pages the user deletes are simply absent from every group. A "split" marker
starts a new group (a new output file) at that point.

Thumbnails render **progressively** on a timer after the dialog opens, so even a
big PDF on slow hardware shows instantly (as numbered placeholders) and stays
responsive while the images fill in. Rendering is capped so a huge document
can't exhaust memory — pages past the cap stay as placeholders but remain fully
usable (reorder / rotate / delete / split all act on the plan, not the image).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from mico360.logging_setup import get_logger
from mico360.ui.icons import icon as make_icon
from mico360.ui.icons import label_pixmap, theme_color

log = get_logger("mico360.page_organizer")

# Roles stored on each grid item.
_SRC = Qt.UserRole            # original 0-based page index (int); None for a split
_ROT = Qt.UserRole + 1        # rotation in degrees (0/90/180/270)
_DIVIDER = Qt.UserRole + 2    # True for a "split here" marker

THUMB_W = 132                 # rendered page width in px (device-independent)
TILE = QSize(150, 200)
MAX_THUMBS = 400              # cap on eagerly-rendered thumbnails (memory guard)
_BATCH_MS = 28               # render budget per timer tick (keeps the UI live)


def render_page_thumbs(path: Path, width: int = THUMB_W,
                       max_pages: int | None = None) -> list[QPixmap]:
    """Render pages of ``path`` to upright QPixmaps (index = page order), up to
    ``max_pages``. Returns [] if the file can't be opened."""
    import fitz
    pixmaps: list[QPixmap] = []
    try:
        doc = fitz.open(str(path))
    except Exception as exc:            # noqa: BLE001
        log.debug("page thumbs: cannot open %s: %s", path, exc)
        return []
    try:
        count = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
        for i in range(count):
            pixmaps.append(_render_page(doc, i, width))
    except Exception as exc:            # noqa: BLE001
        log.debug("page thumbs: render failed on %s: %s", path, exc)
    finally:
        doc.close()
    return pixmaps


def _render_page(doc, i: int, width: int = THUMB_W) -> QPixmap:
    import fitz
    page = doc.load_page(i)
    zoom = width / max(1.0, page.rect.width)
    pm = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = QImage(pm.samples, pm.width, pm.height, pm.stride,
                 QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img)


class PageOrganizerDialog(QDialog):
    """Modal thumbnail grid for arranging one PDF's pages."""

    def __init__(self, path: Path, parent=None, plan: dict | None = None):
        super().__init__(parent)
        self.path = Path(path)
        self.setWindowTitle(f"Organize pages — {self.path.name}")
        self.setModal(True)
        self.resize(760, 620)

        # Open once; count pages now, render thumbnails progressively below.
        self._doc = None
        self._n = 0
        try:
            import fitz
            self._doc = fitz.open(str(self.path))
            self._n = self._doc.page_count
        except Exception as exc:            # noqa: BLE001
            log.debug("page organizer: cannot open %s: %s", self.path, exc)
        self._thumbs: dict[int, QPixmap] = {}       # index -> rendered pixmap
        self._render_queue: list[int] = list(range(min(self._n, MAX_THUMBS)))

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        head = QLabel("Drag to reorder · select pages then rotate or delete · "
                      "add a split to start a new file.")
        head.setObjectName("Hint")
        head.setWordWrap(True)
        root.addWidget(head)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_rot_ccw = self._tool_btn("rotate-ccw", "Rotate left", self._rotate_ccw)
        self.btn_rot_cw = self._tool_btn("rotate-cw", "Rotate right", self._rotate_cw)
        self.btn_delete = self._tool_btn("trash", "Delete", self._delete_selected)
        self.btn_split = self._tool_btn("scissors", "Add split", self._add_split)
        self.btn_reset = self._tool_btn("repeat", "Reset", self.reset)
        for b in (self.btn_rot_ccw, self.btn_rot_cw, self.btn_delete, self.btn_split):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.btn_reset)
        root.addLayout(bar)

        self.grid = QListWidget()
        self.grid.setObjectName("PageGrid")
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setFlow(QListWidget.LeftToRight)
        self.grid.setWrapping(True)
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Snap)
        self.grid.setSpacing(10)
        self.grid.setIconSize(QSize(THUMB_W, int(THUMB_W * 1.35)))
        self.grid.setGridSize(TILE)
        self.grid.setUniformItemSizes(False)
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grid.setDragDropMode(QAbstractItemView.InternalMove)
        self.grid.setDefaultDropAction(Qt.MoveAction)
        self.grid.itemSelectionChanged.connect(self._sync_toolbar)
        self.grid.model().rowsMoved.connect(lambda *_: self._update_summary())
        root.addWidget(self.grid, 1)

        self.summary = QLabel("")
        self.summary.setObjectName("Hint")
        root.addWidget(self.summary)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if self._n == 0:
            head.setText("This PDF has no readable pages, or it couldn't be opened.")
            self.grid.setEnabled(False)
            for b in (self.btn_rot_ccw, self.btn_rot_cw, self.btn_delete,
                      self.btn_split, self.btn_reset):
                b.setEnabled(False)
        elif plan:
            self._load_plan(plan)
        else:
            self.reset()
        if self._n > MAX_THUMBS:
            head.setText(head.text() + f"  (Showing thumbnails for the first "
                         f"{MAX_THUMBS} of {self._n} pages; all pages are still "
                         f"editable.)")
        self._sync_toolbar()

        # Kick off progressive rendering (no-op once the queue drains).
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._render_batch)
        if self._render_queue:
            self._timer.start()

    # -- rendering -----------------------------------------------------------
    def _render_batch(self) -> None:
        import time
        t0 = time.monotonic()
        while self._render_queue and (time.monotonic() - t0) * 1000 < _BATCH_MS:
            i = self._render_queue.pop(0)
            if self._doc is not None and i not in self._thumbs:
                try:
                    self._thumbs[i] = _render_page(self._doc, i)
                except Exception:       # noqa: BLE001
                    continue
                self._repaint_src(i)
        if not self._render_queue:
            self._timer.stop()
            self._close_doc()

    def render_all_now(self) -> None:
        """Synchronously finish rendering every queued thumbnail (tests / grab)."""
        while self._render_queue:
            i = self._render_queue.pop(0)
            if self._doc is not None and i not in self._thumbs:
                try:
                    self._thumbs[i] = _render_page(self._doc, i)
                except Exception:       # noqa: BLE001
                    continue
                self._repaint_src(i)
        if hasattr(self, "_timer"):
            self._timer.stop()
        self._close_doc()

    def _close_doc(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:           # noqa: BLE001
                pass
            self._doc = None

    def _repaint_src(self, src: int) -> None:
        for row in range(self.grid.count()):
            it = self.grid.item(row)
            if not it.data(_DIVIDER) and it.data(_SRC) == src:
                self._paint_item(it)

    def closeEvent(self, ev):           # noqa: N802
        self._close_doc()
        super().closeEvent(ev)

    # -- construction helpers ------------------------------------------------
    def _tool_btn(self, icon_name: str, label: str, slot) -> QPushButton:
        b = QPushButton(f"  {label}")
        b.setObjectName("Ghost")
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(make_icon(icon_name, 16, theme_color("text")))
        b.clicked.connect(slot)
        return b

    def _make_page_item(self, src: int, rotate: int = 0) -> QListWidgetItem:
        it = QListWidgetItem()
        it.setData(_SRC, int(src))
        it.setData(_ROT, int(rotate) % 360)
        it.setData(_DIVIDER, False)
        it.setSizeHint(TILE)
        it.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self._paint_item(it)
        return it

    def _make_split_item(self) -> QListWidgetItem:
        it = QListWidgetItem()
        it.setData(_SRC, None)
        it.setData(_DIVIDER, True)
        it.setIcon(make_icon("scissors", 40, theme_color("primary")))
        it.setText("Split →\nnew file")
        it.setSizeHint(QSize(96, TILE.height()))
        it.setTextAlignment(Qt.AlignCenter)
        it.setToolTip("Pages after this marker go into a new output file. "
                      "Drag it to move the split; delete it to remove the split.")
        return it

    def _paint_item(self, it: QListWidgetItem) -> None:
        src = it.data(_SRC)
        rot = int(it.data(_ROT) or 0)
        if src is None or not (0 <= src < self._n):
            return
        pm = self._thumbs.get(src)
        if pm is None:                  # not rendered yet (or past the cap)
            it.setIcon(label_pixmap("file-text", 44, theme_color("text_faint")))
        else:
            if rot:
                pm = pm.transformed(QTransform().rotate(rot), Qt.SmoothTransformation)
            it.setIcon(pm)
        deg = f" · {rot}°" if rot else ""
        it.setText(f"Page {src + 1}{deg}")

    # -- toolbar actions -----------------------------------------------------
    def _page_selection(self) -> list[QListWidgetItem]:
        return [it for it in self.grid.selectedItems()
                if not it.data(_DIVIDER)]

    def _rotate(self, delta: int) -> None:
        for it in self._page_selection():
            it.setData(_ROT, (int(it.data(_ROT) or 0) + delta) % 360)
            self._paint_item(it)
        self._update_summary()

    def _rotate_cw(self) -> None:
        self._rotate(90)

    def _rotate_ccw(self) -> None:
        self._rotate(-90)

    def _delete_selected(self) -> None:
        for it in self.grid.selectedItems():
            self.grid.takeItem(self.grid.row(it))
        self._sync_toolbar()
        self._update_summary()

    def _add_split(self) -> None:
        sel = self.grid.selectedItems()
        row = (self.grid.row(sel[-1]) + 1) if sel else self.grid.count()
        if row == 0:
            return
        prev = self.grid.item(row - 1)
        if prev is not None and prev.data(_DIVIDER):
            return
        self.grid.insertItem(row, self._make_split_item())
        self._update_summary()

    def reset(self) -> None:
        self.grid.clear()
        for i in range(self._n):
            self.grid.addItem(self._make_page_item(i, 0))
        self._update_summary()

    def _load_plan(self, plan: dict) -> None:
        self.grid.clear()
        groups = plan.get("groups") or []
        for gi, group in enumerate(groups):
            if gi > 0:
                self.grid.addItem(self._make_split_item())
            for item in group:
                src = int(item.get("src", -1))
                if 0 <= src < self._n:
                    self.grid.addItem(self._make_page_item(src, item.get("rotate", 0)))
        if self.grid.count() == 0:
            self.reset()
        self._update_summary()

    # -- state ---------------------------------------------------------------
    def _sync_toolbar(self) -> None:
        has_page = bool(self._page_selection())
        has_any = bool(self.grid.selectedItems())
        for b in (self.btn_rot_cw, self.btn_rot_ccw):
            b.setEnabled(has_page)
        self.btn_delete.setEnabled(has_any)

    def _update_summary(self) -> None:
        groups = self.plan()["groups"]
        kept = sum(len(g) for g in groups)
        files = max(1, len(groups))
        deleted = self._n - kept
        parts = [f"{kept} of {self._n} page(s)"]
        if deleted:
            parts.append(f"{deleted} deleted")
        parts.append(f"{files} output file(s)" if files > 1 else "1 output file")
        self.summary.setText("  ·  ".join(parts))

    def plan(self) -> dict:
        """The current arrangement as a plan dict (see module docstring)."""
        groups: list[list[dict]] = []
        current: list[dict] = []
        for row in range(self.grid.count()):
            it = self.grid.item(row)
            if it.data(_DIVIDER):
                if current:
                    groups.append(current)
                    current = []
                continue
            src = it.data(_SRC)
            if src is None:
                continue
            current.append({"src": int(src), "rotate": int(it.data(_ROT) or 0)})
        if current:
            groups.append(current)
        return {"n_src": self._n, "groups": groups}
