"""Help & About page."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from mico360 import __version__
from mico360.ui.widgets import Card, section_label

_HELP_HTML = """
<h3>The Dashboard (Home)</h3>
<p>The app opens on a <b>Dashboard</b>: <b>Quick actions</b> for common jobs,
<b>Favourite tools</b> you've pinned (click the ☆ on any tool to pin it),
<b>Recent files</b> you've created, and your <b>Last activity</b>. You can
<b>drag &amp; drop files anywhere</b> in the window — they're sent to a sensible
tool automatically.</p>

<h3>Getting started</h3>
<ol>
  <li><b>Pick a tool</b> from the sidebar on the left (grouped into PDF, Convert, Images and System).
      <b>Search</b> for a tool with the box at the top of the sidebar, and click a
      <b>category heading</b> to collapse or expand it.</li>
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

<h3>The queue &amp; status</h3>
<ul>
  <li>Files you add form a <b>queue</b>. Each row shows a coloured status dot and label —
      <b>Queued</b>, <b>Working…</b>, <b>Done</b> or <b>Failed</b> — plus the file size and,
      when finished, the output name or the failure reason. The header shows a <b>live count</b>
      (working / pending / done / failed).</li>
  <li><b>Drag rows to reorder</b> the queue; long file names are trimmed in the middle so the
      extension stays visible, with the full path on hover.</li>
  <li>Toolbar: <b>Add files</b>, <b>Remove selected</b>, <b>Remove finished</b> (clears done
      <i>and</i> failed) and <b>Clear all</b>. Press <b>Delete</b> to remove the selected rows.</li>
  <li><b>Right-click</b> a row (works on a multi-selection) for: <b>Open source folder</b>,
      <b>Open output folder</b>, <b>Move to top</b> / <b>Move to bottom</b>, <b>Duplicate row(s)</b>,
      <b>Retry failed/done row(s)</b>, <b>Remove from queue</b>, and <b>Delete from disk</b>
      (sent to the Recycle Bin after a confirmation). <b>Double-click</b> a finished row to open
      its output.</li>
  <li><b>Start</b> only processes rows that aren't done yet — finished rows are skipped until
      you retry them. The same file can be queued more than once (Duplicate), each tracked
      separately.</li>
  <li><b>Cancel</b> stops the batch; long jobs (OCR, many pages) stop within a moment.</li>
</ul>

<h3>The tools, in detail</h3>
<ul>
  <li><b>Compress PDF</b> — <i>Lossless</i> (the default) reduces size with <b>zero change</b> to
      images, text, fonts or layout and is verified content-identical; or pick <i>Low / Medium /
      High</i>, a <i>Target file size</i> (e.g. 250&nbsp;KB — the app auto-picks settings to land
      at or just under it), or <i>Custom</i> DPI + JPEG quality. Uses Ghostscript when available,
      otherwise a built-in compressor.</li>
  <li><b>Merge PDF</b> — combines two or more PDFs into one. <b>Drag files in the list to
      reorder</b> them before merging (also works for combined Image → PDF).</li>
  <li><b>Split PDF</b> — split <i>every page</i>, into <i>fixed page counts</i>, or by
      <i>custom ranges</i> like <i>1-3, 5, 8-10</i>. Each source gets its own output subfolder.</li>
  <li><b>Organize PDF</b> — <i>rotate</i> (all or chosen pages), <i>delete</i> pages,
      <i>extract</i> only the pages you want, or <i>reorder</i> the whole document. Pages
      are given 1-based, e.g. <i>3, 1, 2, 5-8</i> (ranges may run backwards).</li>
  <li><b>Protect PDF</b> — add a password (strong AES-256 encryption — you confirm it,
      with show/hide toggles) or remove one (enter the PDF's current password to unlock).
      Passwords are never saved.</li>
  <li><b>Watermark PDF</b> — stamp <i>text</i> (e.g. “CONFIDENTIAL”) or a <i>logo/image</i>
      across every page, with adjustable size, opacity, angle and <b>position</b> (a 3×3
      grid — any corner, edge or the centre). For an image watermark, a PNG with
      transparency works best.</li>
  <li><b>Add Page Numbers</b> — choose the position, style (<i>1, 2, 3</i> · <i>1 / N</i>
      · <i>Page 1</i>) and starting number.</li>
  <li><b>Sign PDF</b> — stamp a signature image on the last/first/every page.</li>
  <li><b>Edit Metadata</b> — set the document Title, Author, Subject and Keywords.</li>
  <li><b>Searchable PDF (OCR)</b> — add an invisible text layer to a scanned PDF so it
      becomes selectable and searchable (the look of the page is unchanged).</li>
  <li><b>PDF → …</b> — one tool to convert a PDF to <b>Word</b> (editable .docx; turn on
      <b>OCR</b> for scanned pages), <b>PowerPoint</b> (<i>Auto</i> keeps text editable and
      falls back to a page image so slides are never empty; OCR optional), <b>Excel</b>
      (pulls out tables, or page text when none are found), or <b>Images</b> (one per page,
      JPG / PNG / WEBP / BMP / TIFF at a chosen DPI). Pick the target from <i>Convert to</i>.</li>
  <li><b>Office → PDF</b> — convert <b>Word, Excel or PowerPoint</b> to PDF; the type is
      detected from the file automatically. The conversion engine (<b>LibreOffice</b>) is
      <b>built in</b>, so it works on any PC with no setup — including legacy <i>.doc/.xls/.ppt</i>
      and machines without Microsoft Office.</li>
  <li><b>Document → Markdown</b> — convert <b>Word, Excel, PowerPoint or PDF</b> to clean
      Markdown (.md): headings, <b>bold</b>/<i>italic</i>, lists and tables for Word; a table
      per sheet for Excel; a section per slide for PowerPoint; page text (and tables) for PDF.
      <i>.docx/.xlsx/.pptx/.pdf/.csv</i> work directly; other Office formats need LibreOffice.</li>
  <li><b>Image → PDF</b> — combine images into one PDF, or make one PDF per image.</li>
  <li><b>Resize Image</b> — batch-resize by width/height or percentage.</li>
  <li><b>Convert Image</b> — change format between PNG / JPG / WEBP / TIFF / BMP.</li>
  <li><b>Watermark Image</b> — stamp text or a logo onto images.</li>
  <li><b>Compress Image</b> — presets, a <i>Target file size</i>, or custom quality; optional
      resize and format change (JPEG / PNG / WEBP).</li>
  <li><b>Edit File Properties</b> (System) — bulk-set Windows file properties on <b>any</b>
      files: <b>Date Created</b>, <b>Date Modified</b> and <b>Owner</b>. Type a date like
      <i>2026-06-07 14:30</i> (or <i>now</i>); leave a field blank to keep it. Your originals
      are never changed — a copy with the new properties is written to the output folder.
      Setting the Owner needs administrator rights and a valid Windows account.</li>
</ul>

<h3>OCR — turning scanned pages into editable text</h3>
<p>A “scanned” PDF is really a picture of a page, so its words can’t be selected,
searched or edited. <b>OCR</b> (Optical Character Recognition) reads those pictures
and recovers the text.</p>
<ul>
  <li>Turn on <b>OCR</b> in <b>PDF → …</b> (Word or PowerPoint target) when your PDF
      is scanned or image-only. Pages that already have a real text layer are converted
      directly (no OCR needed), so it’s safe to leave on.</li>
  <li>Recognised text is laid out in reading order — words on the same line are kept
      together, and clear vertical gaps become paragraph breaks.</li>
  <li>It runs <b>entirely on your computer</b> — nothing is uploaded — and works offline.</li>
  <li><b>GPU acceleration:</b> if your PC has a graphics card, OCR automatically runs on it
      (via DirectML — any NVIDIA / AMD / Intel GPU) for a large speed-up, falling back to the
      CPU when no GPU is available. Toggle this in <b>Settings → Processing</b>.</li>
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
  <li>The update panel shows full details — the <b>new version</b>, <b>download size</b>,
      <b>release date</b>, and what changed split into <b>New features</b>, <b>Bugs fixed</b>
      and <b>Security improvements</b>, with a live <b>status</b> (Available / Downloading /
      Installing / Completed / Failed), a <b>progress bar with percentage and time remaining</b>,
      and a <b>Retry</b> option if anything fails.</li>
  <li>When you choose to update, the new version is <b>downloaded, verified (SHA-256) and
      installed</b> for you; the app closes briefly to finish and your settings are kept. After
      it reopens you'll see a <b>confirmation</b> with the installed version and time.</li>
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
  <li><b>Appearance</b> — choose <b>System</b> (follow your Windows/macOS theme), <b>Light</b>
      or <b>Dark</b> (the ☀/🌙 button in the top bar pins Light/Dark). Defaults to System on
      first run.</li>
  <li><b>Output</b> — default output folder, “open the folder when a batch finishes”, and
      overwrite behaviour.</li>
  <li><b>Processing</b> — number of parallel workers (0 = automatic, uses CPU cores − 1), and
      <b>Use the GPU for OCR</b> when a graphics card is available (with automatic CPU fallback).</li>
  <li><b>Updates</b> — see your current version, check for updates on demand, and turn the
      automatic startup check on or off.</li>
  <li><b>External tools</b> — LibreOffice (Office → PDF) is <b>built in</b>; you can point the
      app at a different LibreOffice or at Ghostscript (for the smallest lossy PDF compression)
      here. Both are optional.</li>
  <li><b>About &amp; Legal</b> — About Us, Terms &amp; Conditions, Privacy Policy, and contact info.</li>
</ul>

<h3>Tips &amp; troubleshooting</h3>
<ul>
  <li>Everything runs <b>locally</b> — your files are never uploaded anywhere.</li>
  <li>Processing runs in <b>parallel across CPU cores</b> — tune it in
      <b>Settings → Performance</b>.</li>
  <li>If a file fails, hover it for the reason, or open <b>Activity</b> /
      <b>Settings → Open logs folder</b> for details.</li>
  <li>Office → PDF works out of the box (LibreOffice is built in) — no Microsoft Office needed.</li>
  <li>Compress PDF is <b>Lossless</b> by default (no quality loss); for the smallest <i>lossy</i>
      result on image-heavy PDFs, Ghostscript can be set in Settings → External tools.</li>
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
        about_lbl = QLabel(
            f"<b>MICO360 Doc Toolkit</b> v{__version__}<br>"
            "PDF &amp; image management for Windows 10 / 11 (64-bit) and macOS.<br>"
            "Contact: <a href='mailto:info@mico360.com'>info@mico360.com</a><br>"
            "© MICO360. Bundles LibreOffice (MPL) and RapidOCR; "
            "uses Ghostscript (AGPL) when available.")
        about_lbl.setTextFormat(Qt.RichText)
        about_lbl.setOpenExternalLinks(True)
        about_lbl.setWordWrap(True)
        about.add(about_lbl)
        root.addWidget(about)
