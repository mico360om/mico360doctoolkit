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
  <li>Optional, <b>opt-in AI</b> metadata suggestions using the System AI or your own
      OpenAI-compatible API — you review every suggestion before anything is applied.</li>
  <li>On Windows, an optional <b>“MICO360 Toolkit” right-click menu</b> that sends a file
      straight to the matching tool, plus <b>keyboard shortcuts</b> for the whole workflow.</li>
  <li>Clean light &amp; dark themes (light by default), and built-in automatic updates.</li>
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

<h3>4. AI features (optional)</h3>
<p>AI-assisted features (such as metadata suggestions) are <b>off by default</b>
and used only when you enable and invoke them. You choose the AI provider — the
<b>System AI</b> operated for you, or <b>your own</b> OpenAI-compatible API. You
are responsible for keeping your API key secure, for any usage, quotas or fees on
the provider you configure, and for complying with that provider's terms and with
all laws applicable to the content you submit. AI suggestions are proposals only:
you review them and decide what to apply, and {__publisher__} does not warrant
their accuracy. The System AI is provided on an "as available" basis and may
change or be withdrawn.</p>

<h3>5. Windows Explorer integration (optional)</h3>
<p>On Windows you may enable a "MICO360 Toolkit" right-click menu. It adds a
per-user entry to your own Windows registry (no administrator rights required),
does not alter your default programs, and is removed when you turn it off in
Settings or uninstall the Software.</p>

<h3>6. No warranty</h3>
<p>The Software is provided "as is", without warranty of any kind, express or
implied. Always keep backups of important files; {__publisher__} is not responsible
for any data loss arising from use of the Software.</p>

<h3>7. Limitation of liability</h3>
<p>To the maximum extent permitted by law, {__publisher__} shall not be liable for
any indirect, incidental, or consequential damages arising from use of the
Software.</p>

<h3>8. Updates &amp; changes</h3>
<p>These terms may be updated from time to time. Continued use of the Software
constitutes acceptance of the current terms.</p>

<h3>9. Contact</h3>
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
<p>The <b>one exception</b> is the optional AI features, which are <b>off unless you
turn them on</b>: when you explicitly ask for an AI suggestion, a short excerpt of
that one document is sent to the AI provider <b>you</b> configure. See section 3.</p>

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
<li><b>AI suggestions (only if you enable them)</b> — AI features are <b>off by
default</b>. If you turn them on and ask for a suggestion, a short excerpt of that
one document (not the whole file, and never your other files) is sent to the AI
endpoint <b>you</b> configure — the <b>System AI</b> operated for you, or <b>your
own</b> OpenAI-compatible API. Nothing is sent otherwise, and this app stores no
copy of the document or the suggestion. Your API key is stored encrypted on your
computer (Windows account protection / DPAPI on Windows; obfuscated on macOS) and
is never displayed again after you save it. Note: the System AI connection is not
yet encrypted in transit, so prefer a trusted network — or use your own HTTPS
endpoint — when the content is sensitive.</li>
<li><b>Error reports (only if you ask)</b> — if something goes wrong, a report (with a
copy of the recent log) is saved <b>on your computer</b>. It is <b>never sent
automatically</b>; you decide whether to open a <b>pre-filled GitHub issue</b> (which you
review and submit yourself), copy it, or email it. You can disable the prompt in
<b>Settings → Updates</b>.</li>
</ul>

<h3>4. Windows Explorer integration (optional)</h3>
<p>If you turn on the "MICO360 Toolkit" right-click menu (Windows only), the app
adds a small entry to <b>your own user's Windows registry</b> so File Explorer can
show the menu. This stores no personal data, collects nothing, and is removed when
you turn it off in Settings or uninstall. When you pick a file from that menu, the
file path is passed to the app on your own computer to open the tool — it is not
sent anywhere.</p>

<h3>5. What is stored locally</h3>
<p>Only your app preferences (theme, output folder, last-used options, and — if
you configure AI — your encrypted API key and remembered model list) are saved on
your own computer so the app remembers your settings. A local activity log is kept
on your device to help with troubleshooting. You can clear it any time from the
Activity page, and it never leaves your machine.</p>

<h3>6. Your access level</h3>
<p>Optional modules (AI, GPU-accelerated OCR, the conversion engine, the Explorer
right-click menu) are <b>off or absent until you enable them</b>, and some are
platform-specific — for example, the Explorer menu and Windows account key
encryption are Windows-only. The <b>Help → “Your setup &amp; permissions”</b>
section shows exactly what is enabled and available to you right now. What this
policy describes for a given feature applies to you only when that feature is
active for you.</p>

<h3>7. Outputs</h3>
<p>Converted/compressed files are written only to the output folder you choose (or
next to your originals). Your original files are never modified.</p>

<h3>8. Optional contact</h3>
<p>If you choose to email us at <a href="mailto:{EMAIL}">{EMAIL}</a>, we use your
message only to respond to you.</p>

<h3>9. Contact</h3>
<p>Questions about privacy? Email <a href="mailto:{EMAIL}">{EMAIL}</a> or visit
<a href="{WEBSITE_URL}">{WEBSITE}</a>.</p>
"""
