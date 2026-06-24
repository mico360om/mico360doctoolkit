"""Legal / company text shown in Settings (Terms, Privacy, About Us)."""
from __future__ import annotations

from mico360 import __app_name__, __publisher__, __version__

EMAIL = "info@mico360.com"
WEBSITE = "www.mico360.com"
WEBSITE_URL = "https://www.mico360.com"


def about_us() -> str:
    return f"""
<h2>About {__app_name__}</h2>
<p><b>{__app_name__}</b> is a fast, private, all-in-one desktop toolkit for
<b>Windows and macOS</b> for working with PDFs and images — compress, merge, split,
organise, protect, watermark, and convert between PDF, Word, Excel, PowerPoint,
Markdown and image formats, with OCR for scanned documents.</p>

<p>Everything runs <b>locally on your computer</b>. Your files are never uploaded
to any server, and your originals are always preserved.</p>

<h3>Highlights</h3>
<ul>
  <li><b>Lossless compression</b> for PDFs &amp; images — verified content-identical —
      plus a target-file-size mode.</li>
  <li>Convert PDF ⇄ Word / PowerPoint / Excel / images, Office → PDF, and
      Document → Markdown — the conversion engine downloads once on first use (no Office needed).</li>
  <li><b>OCR</b> turns scanned, image-only PDFs into searchable text, and uses your
      <b>GPU</b> automatically when one is available.</li>
  <li>A real <b>file queue</b> with batch processing across all CPU cores, and
      bulk <b>file-property</b> editing (dates &amp; owner).</li>
  <li>Clean light &amp; dark themes, and built-in automatic updates.</li>
</ul>

<h3>Contact</h3>
<p>
  Email: <a href="mailto:{EMAIL}">{EMAIL}</a><br>
  Website: <a href="{WEBSITE_URL}">{WEBSITE}</a>
</p>

<p style="color:#888;">{__app_name__} v{__version__} &nbsp;·&nbsp; © {__publisher__}.
All rights reserved.</p>
"""


def terms_and_conditions() -> str:
    return f"""
<h2>Terms &amp; Conditions</h2>
<p style="color:#888;">{__app_name__} v{__version__} &nbsp;·&nbsp; © {__publisher__}</p>

<p>By installing or using {__app_name__} (the "Software"), you agree to these terms.</p>

<h3>1. Licence</h3>
<p>{__publisher__} grants you a personal, non-exclusive, non-transferable licence to
install and use the Software on devices you own or control. You may not resell,
sublicense, or redistribute the Software without written permission.</p>

<h3>2. Acceptable use</h3>
<p>You agree to use the Software only with files you own or are authorised to
process, and in compliance with all applicable laws. You are responsible for the
content you process.</p>

<h3>3. Third-party components</h3>
<p>The Software may bundle, download on demand, or use third-party engines (e.g.
Ghostscript, LibreOffice, PyMuPDF, RapidOCR, and PaddleOCR / PaddlePaddle OCR
models). These remain the property of their respective owners and are provided
under their own licences.</p>

<h3>4. No warranty</h3>
<p>The Software is provided "as is", without warranty of any kind, express or
implied. Always keep backups of important files; {__publisher__} is not responsible
for any data loss arising from use of the Software.</p>

<h3>5. Limitation of liability</h3>
<p>To the maximum extent permitted by law, {__publisher__} shall not be liable for
any indirect, incidental, or consequential damages arising from use of the
Software.</p>

<h3>6. Updates &amp; changes</h3>
<p>These terms may be updated from time to time. Continued use of the Software
constitutes acceptance of the current terms.</p>

<h3>7. Contact</h3>
<p>Questions about these terms? Email <a href="mailto:{EMAIL}">{EMAIL}</a> or visit
<a href="{WEBSITE_URL}">{WEBSITE}</a>.</p>
"""


def privacy_policy() -> str:
    return f"""
<h2>Privacy Policy</h2>
<p style="color:#888;">{__app_name__} v{__version__} &nbsp;·&nbsp; © {__publisher__}</p>

<p>Your privacy matters. This policy explains what {__app_name__} does — and does
not — do with your data.</p>

<h3>1. Your files stay on your device</h3>
<p>All processing — compression, conversion, OCR (including GPU-accelerated OCR),
and everything else — happens <b>locally on your computer</b>. {__app_name__} does
<b>not</b> upload, transmit, or share your documents or images with {__publisher__}
or any third party.</p>

<h3>2. No accounts, no tracking</h3>
<p>The Software does not require an account, does not include advertising or
analytics, and does not track your activity.</p>

<h3>3. Network activity</h3>
<p>{__app_name__} contacts the internet only for these things, and <b>never to send
your files or personal data</b>:</p>
<ul>
<li><b>Updates</b> — it checks our public releases page on GitHub for a newer version
and, if you choose to update, downloads the installer. Turn the automatic check off in
<b>Settings → Updates</b>.</li>
<li><b>Optional engines &amp; language packs</b> — the first time you need them, it can
download the LibreOffice conversion engine and OCR language models (e.g. Arabic) from
their official sources. These are one-time downloads of software components, not your
data, and you can manage them in <b>Settings</b>.</li>
<li><b>Error reports (only if you ask)</b> — if something goes wrong, a report is saved
<b>on your computer</b>. It is <b>never sent automatically</b>; you decide whether to
copy or email it. You can disable the prompt in <b>Settings → Updates</b>.</li>
</ul>

<h3>4. What is stored locally</h3>
<p>Only your app preferences (theme, output folder, last-used options) are saved
on your own computer so the app remembers your settings. A local activity log is
kept on your device to help with troubleshooting. You can clear it any time from
the Activity page, and it never leaves your machine.</p>

<h3>5. Outputs</h3>
<p>Converted/compressed files are written only to the output folder you choose (or
next to your originals). Your original files are never modified.</p>

<h3>6. Optional contact</h3>
<p>If you choose to email us at <a href="mailto:{EMAIL}">{EMAIL}</a>, we use your
message only to respond to you.</p>

<h3>7. Contact</h3>
<p>Questions about privacy? Email <a href="mailto:{EMAIL}">{EMAIL}</a> or visit
<a href="{WEBSITE_URL}">{WEBSITE}</a>.</p>
"""
