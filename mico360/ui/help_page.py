"""Help & About page."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from mico360 import __version__
from mico360.ui.widgets import Card, section_label

_HELP_HTML = """
<h3>Getting started</h3>
<ol>
  <li><b>Pick a tool</b> from the sidebar on the left (grouped into PDF, Convert and Image).</li>
  <li><b>Add your files</b> — drag &amp; drop files or whole folders onto the drop zone, or
      click <b>Browse files</b> / <b>Browse folder</b>. Folders are scanned recursively, and
      only the file types that tool accepts are added.</li>
  <li><b>Set the options</b> on the right (quality, format, page ranges, OCR, target size…).
      The app remembers your last-used options for each tool.</li>
  <li><b>Choose where outputs go</b> — a folder you pick, or tick <b>Save next to the original
      files</b> to write each result beside its source (named “name (1).ext”, “name (2).ext”…).</li>
  <li>Click <b>Start</b>. Your <b>original files are never modified</b>. Watch progress in the
      bar and the Activity log; click a finished file to open its output.</li>
</ol>

<h3>The file list &amp; status</h3>
<ul>
  <li>Each file shows a status: <b>•</b> pending, <b>⏳</b> running, <b>✓</b> done (with the output
      name), <b>✗</b> failed (with the reason).</li>
  <li><b>Start</b> only processes files that aren't done yet — finished files are skipped.</li>
  <li><b>Redo</b> re-arms finished files so they run again. <b>Remove done</b> clears them.</li>
  <li><b>Double-click</b> a finished file to reveal its output; <b>right-click</b> for more
      actions (open output / open source folder / redo this one / remove). Press <b>Delete</b>
      to remove the selected files.</li>
  <li><b>Cancel</b> stops the batch; long jobs (OCR, many pages) stop within a moment.</li>
</ul>

<h3>The tools, in detail</h3>
<ul>
  <li><b>Compress PDF</b> — choose <i>Low / Medium / High</i>, a <i>Target file size</i>
      (e.g. 250&nbsp;KB — the app auto-picks settings to land at or just under it), or
      <i>Custom</i> DPI + JPEG quality. Uses Ghostscript when available, otherwise a built-in
      compressor.</li>
  <li><b>Merge PDF</b> — combines two or more PDFs into one. <b>Drag files in the list to
      reorder</b> them before merging (also works for combined Image → PDF).</li>
  <li><b>Split PDF</b> — split <i>every page</i>, into <i>fixed page counts</i>, or by
      <i>custom ranges</i> like <i>1-3, 5, 8-10</i>. Each source gets its own output subfolder.</li>
  <li><b>Organize PDF</b> — <i>rotate</i> (all or chosen pages), <i>delete</i> pages,
      <i>extract</i> only the pages you want, or <i>reorder</i> the whole document. Pages
      are given 1-based, e.g. <i>3, 1, 2, 5-8</i> (ranges may run backwards).</li>
  <li><b>Protect PDF</b> — add a password (strong AES-256 encryption) or remove one
      (enter the PDF's current password to unlock).</li>
  <li><b>Watermark PDF</b> — stamp diagonal text (e.g. “CONFIDENTIAL”) across every page,
      with adjustable size, opacity, angle and colour.</li>
  <li><b>PDF → Word</b> — produces a fully <b>editable .docx</b> (text + layout). For scanned,
      image-only PDFs, turn on <b>OCR</b> to recognise the text.</li>
  <li><b>PDF → PowerPoint</b> — <i>Auto</i> makes editable text boxes where there's a text
      layer and falls back to a page image otherwise (so slides are never empty); turn on
      <b>OCR</b> to make scanned pages editable too. You can also force <i>Editable text only</i>
      or <i>Exact page image</i>.</li>
  <li><b>Word → PDF</b> — works out of the box: it uses LibreOffice or Microsoft Word when
      present, and a built-in converter otherwise.</li>
  <li><b>PDF → Image</b> — render each page to JPG / PNG / WEBP / BMP / TIFF at a chosen DPI.</li>
  <li><b>Image → PDF</b> — combine images into one PDF, or make one PDF per image.</li>
  <li><b>Compress Image</b> — presets, a <i>Target file size</i>, or custom quality; optional
      resize and format change (JPEG / PNG / WEBP).</li>
</ul>

<h3>OCR — turning scanned pages into editable text</h3>
<p>A “scanned” PDF is really a picture of a page, so its words can’t be selected,
searched or edited. <b>OCR</b> (Optical Character Recognition) reads those pictures
and recovers the text.</p>
<ul>
  <li>Turn on <b>OCR</b> in <b>PDF → Word</b> or <b>PDF → PowerPoint</b> when your PDF
      is scanned or image-only. Pages that already have a real text layer are converted
      directly (no OCR needed), so it’s safe to leave on.</li>
  <li>Recognised text is laid out in reading order — words on the same line are kept
      together, and clear vertical gaps become paragraph breaks.</li>
  <li>It runs <b>entirely on your computer</b> — nothing is uploaded — and works offline.</li>
  <li><b>For the best accuracy:</b> start from a clean, straight, high-resolution scan
      (300&nbsp;dpi or more). Faint, skewed or low-contrast scans recognise less reliably.</li>
  <li>OCR is heavier than a normal conversion, so large documents take longer; the
      progress bar and Activity log show page-by-page progress, and <b>Cancel</b> stops
      it within a moment.</li>
  <li>Recognition is tuned for Latin-script text and digits (English and similar
      languages).</li>
</ul>

<h3>Staying up to date</h3>
<ul>
  <li>The app can <b>check for new versions automatically on startup</b> and let you know
      when one is available — toggle this in <b>Settings → Updates</b>.</li>
  <li>Click <b>Settings → Updates → Check for updates</b> any time to check on demand and
      read what’s new.</li>
  <li>When you choose to update, the new version is <b>downloaded, verified (SHA-256) and
      installed</b> for you; the app closes briefly to finish and your settings are kept.</li>
  <li>Everything is optional — you can turn auto-checking off and update whenever you like.</li>
</ul>

<h3>Keyboard &amp; mouse</h3>
<ul>
  <li><b>Drag &amp; drop</b> files or folders onto the drop zone to add them.</li>
  <li><b>Double-click</b> a finished file to reveal its output; <b>right-click</b> any file
      for more actions; <b>Delete</b> removes the selected files.</li>
  <li><b>Tab / Shift+Tab</b> move between controls; <b>Space</b> toggles a checkbox or
      presses a button; <b>Enter</b> activates the focused button.</li>
  <li>Use the <b>☰</b> button to collapse the sidebar for more room, and <b>☀ / 🌙</b> to
      switch light / dark.</li>
</ul>

<h3>Settings</h3>
<ul>
  <li><b>Appearance</b> — switch Light / Dark (also via the ☀/🌙 button in the top bar). On first
      run the app follows your Windows theme; after that it remembers your choice.</li>
  <li><b>Output</b> — default output folder, “open the folder when a batch finishes”, and
      overwrite behaviour.</li>
  <li><b>Performance</b> — number of parallel workers (0 = automatic, uses CPU cores − 1).</li>
  <li><b>Updates</b> — see your current version, check for updates on demand, and turn the
      automatic startup check on or off.</li>
  <li><b>External tools</b> — set or auto-detect Ghostscript (best PDF compression) and
      LibreOffice (Word → PDF). Both are optional; the app works without them.</li>
  <li><b>About &amp; Legal</b> — About Us, Terms &amp; Conditions, Privacy Policy, and contact info.</li>
</ul>

<h3>Tips &amp; troubleshooting</h3>
<ul>
  <li>Everything runs <b>locally</b> — your files are never uploaded anywhere.</li>
  <li>Processing runs in <b>parallel across CPU cores</b> — tune it in
      <b>Settings → Performance</b>.</li>
  <li>If a file fails, hover it for the reason, or open <b>Activity</b> /
      <b>Settings → Open logs folder</b> for details.</li>
  <li>Word → PDF gives the most exact result with LibreOffice or Microsoft Word installed.</li>
  <li>For the best PDF compression, install or bundle Ghostscript (Settings → External tools).</li>
</ul>

<h3>Need help?</h3>
<p>Email <a href="mailto:info@mico360.com">info@mico360.com</a> or visit
<a href="https://www.mico360.com">www.mico360.com</a>.</p>
"""


class HelpPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        title = QLabel("Help")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        sub = QLabel("Everything you need to get going.")
        sub.setObjectName("PageSubtitle")
        root.addWidget(sub)

        card = Card()
        card.add(section_label("How to use MICO360 Doc Toolkit"))
        body = QLabel(_HELP_HTML)
        body.setObjectName("HelpBody")
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        body.setOpenExternalLinks(True)
        card.add(body)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(card)
        root.addWidget(scroll, 1)

        about = Card()
        about.add(section_label("About"))
        about.add(QLabel(
            f"<b>MICO360 Doc Toolkit</b> v{__version__}<br>"
            "PDF &amp; image management for Windows 10 / 11 (64-bit).<br>"
            "© MICO360. Bundles Ghostscript (AGPL) and LibreOffice (MPL)."))
        root.addWidget(about)
