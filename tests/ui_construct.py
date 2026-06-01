"""Offscreen construction test for the GUI (no window is shown to the user)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from mico360.config import settings
from mico360.logging_setup import setup_logging
from mico360.theme import stylesheet

setup_logging()
app = QApplication([])
app.setStyleSheet(stylesheet(settings.theme))

from mico360.ui.main_window import MainWindow

w = MainWindow()
w.show()
from mico360.core.tools import TOOLS
expected = len(TOOLS) + 3   # tools + Settings + Activity + Help
n_pages = len(w._titles)
print("MainWindow OK — nav items:", len(w.sidebar._items), "pages:", n_pages)
assert len(w.sidebar._items) == n_pages == expected, (len(w.sidebar._items), n_pages, expected)

w.apply_theme("light")
w.apply_theme("dark")
print("Theme toggle OK")

# Exercise the responsive sidebar collapse/expand + lazily build EVERY page.
w.sidebar.set_collapsed(True)
w.sidebar.set_collapsed(False)
for i in sorted(w._titles):
    w.sidebar.select(i)
    app.processEvents()
assert len(w._widgets) == n_pages, f"only {len(w._widgets)}/{n_pages} pages built"
print("Lazy navigation built all", len(w._widgets), "pages OK")
print("Done.")
