## MICO360 Doc Toolkit v7.6.0

**Smarter, more trustworthy AI, a sharp new icon — and a working macOS app.**

**New features**
- Suggest All with AI now reads the document's own facts first — its main heading, printed dates, invoice/quotation/policy/reference numbers, the "Prepared by" name, the copyright line and the language — so suggestions match the document.
- Custom properties now pick up the document's reference numbers automatically, for example "Invoice Number = INV-1042" or "Policy Number = POL-IT-007".

**Bugs fixed**
- macOS app: OCR (Searchable PDF) and PDF → Word failed to start with an OpenCV "recursion" error. Both work again, and the macOS build now runs the full self-test before it is released.
- The app icon was blurry on the taskbar, title bar and desktop, which made the running app hard to spot on the taskbar. It is now sharp at every size and display scaling.
- Settings → AI showed an old address under "System AI"; it now shows the System AI's own address, and your own API's address is kept for when you switch back.
- The button on the "Update completed" message had a heavy dark outline and sat off to one side; it is now a clean, centred button.
- Settings → AI saved an unusable API address (with spaces, no server name, ftp://, or an impossible port) and only failed later; it now refuses it straight away and says what's wrong. An address ending in "/V1" no longer gets a second "/v1" added.
- Test connection showed a green tick when the server worked but your chosen model wasn't offered; it now shows a warning and suggests models that are.
- Damaged, empty, password-protected or wrongly named files (for example a picture renamed to .pdf) and files deleted after being added now give one clear reason on every tool. Several tools showed a technical "Unexpected error" instead, and a damaged Word file could even be "converted" into a meaningless PDF.
- AI suggestions no longer invent authors, companies or dates: every value is checked against the document, and anything it doesn't say is left out.
- AI suggestions no longer put the literal word "Unknown" (or "N/A") into fields.
- A due date or expiry date is no longer suggested as the document's creation date.
- AI no longer guesses Creator, Producer or Trapped — they describe how the file was made, which the document's text can't tell.
- Text inside a document that tries to instruct the AI (for example "ignore previous instructions") is now removed before anything is sent, so it can't change the suggestions.
- With the System AI, Suggest All with AI no longer fails with "The AI reply couldn't be understood" when the model repeated itself; the complete fields are kept.
- If the AI can't answer at all, you now see what the app found in the document itself, with a note, instead of just an error.
- OCR "Use AI" now actually corrects text with the System AI — before, its answers were all rejected. It also never swaps a word for a different one (for example "may" for "can").
- Arabic PDFs are now read correctly for AI suggestions (letters stored in their display forms were sent as unreadable text).

**Improvements**
- The AI category is always one of a fixed list (Invoice, Report, Contract, Letter, Manual…), and keywords are terms that appear in the document.
- The document's language is detected by the app itself, including Arabic, Persian and Urdu, and short business documents.
- A company letterhead is no longer taken as the document's title.
- OCR "Use AI" fixes certain recognition slips instantly without the AI (a letter O read inside a number, a 1 read inside a word), and with a small model sends only the lines that look misread.
- AI answers are steadier (the same document gives the same suggestions), and replies from reasoning models are handled.

_Windows: the installer updates in place — your settings and favourites are kept. macOS: open the `.dmg` and drag the app to Applications._
