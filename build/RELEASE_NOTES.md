## MICO360 Doc Toolkit v7.4.1

**OCR fix release — Searchable PDF keeps working after the first run.**

**Bugs fixed**
- **OCR accuracy on large text:** headings, phone photos and zoomed scans (and any
  page at the Balanced/High quality settings) could come back split or garbled —
  e.g. "RECEIPT page 1" read as "RECEIPT r" + "page". OCR now adapts to the size
  of the text automatically, so it reads correctly at every quality setting.
- **Running OCR again doubled the text:** OCR on a PDF that had already been made
  searchable added a second copy of the text. It now recognises an existing OCR
  layer, and tells you plainly when there is nothing to OCR.
- **New "Redo OCR on pages that already have text" option:** replaces an earlier
  or poor OCR text layer by reading those pages again. Real, visible text is
  never removed.
- **Running a tool again:** pressing Start when every file is already done now
  offers to run them again (instead of a dead end), and adding a file that was
  already processed queues it to run again.

**Reliability**
- The packaged app's built-in self-test (`--selftest`) now also runs several OCR
  jobs in a row, large text, and a re-run/redo, so every build is checked for
  this.

_Windows: the installer updates in place — your settings and favourites are kept.
macOS: open the `.dmg` and drag the app to Applications._

---

### Also in v7.4 (from v7.4.0)

**A big reliability, privacy and polish release** — every item from the September 2026 full-app review is fixed.

**New**
- **OCR "Use AI"** (Searchable PDF): when AI is set up, the recognised text can be
  cleaned up by your AI provider and an empty Title/Subject filled in. It sends the
  text of every page, says so in each run's log, and only accepts small,
  character-level fixes that never change a number.
- **Explorer right-click menu**: works with several selected files (one window, one
  queue), with folders and folder backgrounds, and adds "Open with MICO360 Toolkit"
  plus per-tool icons. The installer offers it as a checkbox, and turning it off in
  Settings is remembered across updates.

**Bugs fixed**
- Office conversions could overwrite an unrelated same-named file in the output
  folder (now converted in a private staging folder).
- Ctrl+Enter during a run no longer starts a second batch that processed every
  file twice.
- Output folder / Overwrite / Save-beside-originals follow Settings; a page opened
  earlier can no longer switch Overwrite back on.
- A visual-organizer arrangement now applies only to the file it was made for, and
  the organizer releases the PDF when closed (the file was locked on Windows).
- Launching several files at once from Explorer opens one window, not several.
- Phone photos keep their orientation in every image tool and in Image → PDF.
- Arabic, Cyrillic and accented text in searchable PDFs is now readable and
  searchable.
- Page lists: invalid or out-of-range pages are reported instead of being skipped;
  Reorder must list every page.
- Rotated pages: watermarks, signatures and PDF → PowerPoint text land in the right
  place, upright.
- Protect, Unlock, Rotate, Delete, Extract, Split, Merge and the organizer keep
  bookmarks and document properties.
- Lossless image compression keeps every TIFF page and the DPI; HEIC compression
  writes real JPEGs; transparent images become white in JPEG; converting to the
  same format never overwrites the source.
- Merge / Images → PDF: output names are sanitised; Images → PDF uses real page
  sizes and far less memory.
- A failed or cancelled file no longer leaves a 0-byte output behind.
- Queue: re-running Merge uses every file, Undo keeps files added since, Retry failed
  runs only the failed rows, the "X of Y" counter counts only the current run,
  Delete/Esc only act where you expect, and drag-and-drop handles folders.
- The "System" theme follows Windows light/dark switches correctly.
- Edit Metadata: per-document values aren't remembered for other files; edits are
  mirrored into XMP (PDF/A identification kept); Privacy Scrub also removes custom
  properties, comment authors, attachments and the file identifier.
- Date fields reject ambiguous dates like 03/04/2026 instead of guessing.
- Closing the window during an AI request no longer crashes the app.

**Security & privacy**
- API keys are cleaned of hidden characters and never appear in errors, logs or
  crash reports; a saved key is only sent to the server it was saved for, and never
  forwarded on a redirect to another host.
- A bare AI host now defaults to HTTPS (local/LAN servers keep HTTP).
- Crash reports opened on GitHub or by email no longer include your user name,
  home folder or document names.
- Updates: the checksum is required before installing; pre-releases are ranked
  correctly.
- The OCR language model is pinned to a fixed version and re-verified before use.
- Privacy Policy, Terms and Help now describe exactly what the AI features send.

**Reliability**
- GPU OCR falls back to the CPU if the graphics card fails mid-job.
- OCR adapts to free memory, and if a page runs out of memory it finishes the
  rest one page at a time instead of failing the file.
- Compress-to-target can be cancelled and shows real progress.
- The conversion-engine download cleans up after itself and never reuses a broken
  installer.
- Friendlier errors for password-protected PDFs in Watermark, Page numbers,
  PDF → Image and PDF → PowerPoint.
- Accessibility: queue status is read by screen readers, and low-contrast text now
  meets WCAG AA.

