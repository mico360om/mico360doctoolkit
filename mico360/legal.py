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

<p>Everything runs <b>locally on your computer</b>, and your originals are always
preserved. Your files are never uploaded — the only exception is the optional AI
features, and only when you turn them on (see the Privacy Policy).</p>

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
  <li>Optional, <b>opt-in AI</b>: metadata suggestions you review before anything is
      applied, and an OCR clean-up that sends the recognised text to the AI you
      configure — the System AI or your own OpenAI-compatible API.</li>
  <li>On Windows, an optional <b>“MICO360 Toolkit” right-click menu</b> (for files,
      several selected files and folders) that sends them straight to the matching
      tool, plus <b>keyboard shortcuts</b> for the whole workflow.</li>
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
<p>AI-assisted features are <b>off by default</b> and work only after you set up
an AI provider in Settings — the <b>System AI</b> operated for you, or <b>your
own</b> OpenAI-compatible API. They are:</p>
<ul>
<li><b>Metadata suggestions</b> (Edit Metadata) — proposals only: you review them
and decide what to apply.</li>
<li><b>OCR clean-up</b> (Searchable PDF → "Use AI") — once AI is set up this option
is on by default and can be turned off per run. It sends the <b>recognised text of
every page</b> to your AI provider, which corrects obvious recognition mistakes; the
app accepts only small, character-level corrections and never changes numbers.
It can also fill in an empty Title or Subject. These changes are applied
automatically, so check important documents.</li>
</ul>
<p>You are responsible for keeping your API key secure, for any usage, quotas or
fees on the provider you configure, for complying with that provider's terms and
with all laws applicable to the content you submit, and for deciding whether a
document may be sent to an AI provider at all. {__publisher__} does not warrant
the accuracy of AI output. The System AI is provided on an "as available" basis
and may change or be withdrawn.</p>

<h3>5. Windows Explorer integration (optional)</h3>
<p>On Windows the installer offers a "MICO360 Toolkit" right-click menu (a
checkbox you can untick). It adds a per-user entry to your own Windows registry,
does not alter your default programs, stays off once you turn it off in Settings
(updates don't add it back), and is removed when you uninstall the Software.</p>

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
set up an AI provider</b>. Then: asking for metadata suggestions sends a short
excerpt of that one document, and the OCR "Use AI" option sends the
<b>recognised text of every page</b> of the files you OCR, to the AI provider
<b>you</b> configure. See section 3.</p>

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
<li><b>AI features (only if you set them up)</b> — AI is <b>off by default</b>.
Once you configure an AI provider — the <b>System AI</b> operated for you, or
<b>your own</b> OpenAI-compatible API:
<ul>
<li><b>Metadata suggestions</b>: when you ask, a short excerpt of that one document
is sent.</li>
<li><b>OCR "Use AI"</b> (on by default once AI is set up; untick it to keep OCR
fully offline): the <b>full recognised text of every page</b> of each file you OCR
is sent for clean-up, and each run's log says so and names the server. Recognition
itself always runs on your computer.</li>
</ul>
Nothing else is sent, and this app stores no copy of the text or the replies.
Your saved API key is only ever sent to the server it was saved for. Your API key is stored encrypted on your
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
on your device to help with troubleshooting and never leaves your machine unless
you choose to attach it to an error report. <b>Clear</b> on the Activity page empties
the on-screen list; the log files themselves are in the app's logs folder, where
you can delete them.</p>

<h3>6. Your access level</h3>
<p>Optional modules differ in their defaults: <b>AI</b> stays off until you set up
a provider; the <b>conversion engine</b> and <b>OCR language packs</b> download only
when first needed; <b>GPU-accelerated OCR</b> is on by default where a supported GPU
exists (Windows) and can be turned off in Settings; the <b>Explorer right-click
menu</b> is offered by the installer and can be turned off in Settings. Some are
platform-specific — for example, the Explorer menu, GPU OCR and Windows account
key encryption are Windows-only. The <b>Help → “Your setup &amp; permissions”</b>
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
