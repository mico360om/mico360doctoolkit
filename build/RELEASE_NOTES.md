## MICO360 Doc Toolkit v5.4.1

**Reliability fixes from a deep QA pass.**

- **Office conversions no longer hang under load.** Word → PDF, Excel → PDF and
  PowerPoint → PDF use external converters (LibreOffice / Microsoft Office) that
  are single-instance; converting **several Office files in one batch** could
  collide and hang. All Office conversions are now serialised, and each
  LibreOffice run gets its own private profile — reliable for whole batches.
- **Toasts** no longer overlap when several appear at once; each is a single,
  clearly-spaced line.
- Minor code cleanups (no behaviour change).

Everything from v5.4.0: the Dashboard home, searchable/collapsible sidebar, 13 new
tools (Rotate/Delete/Extract Pages, Add Page Numbers, Sign, Edit Metadata,
Searchable OCR, PDF↔Excel, Excel/PowerPoint → PDF, image Resize/Convert/Watermark),
Light/Dark/System theme, detailed progress with ETA, and toasts.

---
*This release is also the update manifest: the tag is the version, this text is the
release notes, and the attached Setup `.exe` (+ `.sha256`) is what the app installs.*
