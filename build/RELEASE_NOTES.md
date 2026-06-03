## MICO360 Doc Toolkit v5.6.1

**UI/UX polish + better OCR text.**

- **Stable layout** — the tool panel no longer changes width when you switch
  tools. Every tool now lays out to the same, consistent width (the options
  column is fixed and the content always fits — no more horizontal clipping or
  the panel shifting as you move between tools).
- **Cleaner tool page** — tidier "Save beside originals" / "Overwrite" controls,
  a constant **Start** button, wrapping drop-zone text, and a reserved scrollbar
  so nothing jumps as pages get taller.
- **Smarter OCR text** — the editable-text output (PDF → Word OCR, OCR to Word)
  now reflows scanned lines into proper **paragraphs** and re-joins words that
  were **hyphenated across a line break**, so the result reads like a document
  instead of one stranded line at a time.
- **OCR quality control** — *Searchable PDF (OCR)* gains a **Recognition quality**
  setting (Fast 200 dpi / Balanced 300 dpi / High 400 dpi) so you can trade speed
  for accuracy on small or faint text.

Plus everything from v5.6.0, including the bulk **Word → Markdown** converter and
the corrected app/installer icon.

---
*This release is also the update manifest: the tag is the version, this text is the
release notes, and the attached Setup `.exe` (+ `.sha256`) is what the app installs.*
