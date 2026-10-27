## MICO360 Doc Toolkit v7.6.1

**The System AI is back — and now encrypted.**

**Bugs fixed**
- AI features stopped working with the System AI after the server moved to a secure (HTTPS) connection: "Test connection", "Suggest All with AI" and OCR "Use AI" all failed to reach it. The app now connects over HTTPS and verifies the server's certificate.
- A System AI key you had already saved keeps working after this update — there's nothing to paste again.
- Typing just "ai.mico360.com:5310" as an address now becomes https://…, not http://….
- Closing the window while a large batch (for example 200+ files) was still running left the app working invisibly for minutes, and relaunching it then said it was "already running" — it looked like a crash. Closing now stops the batch: queued files are skipped and helper programs are stopped.
- Cancel now also stops a long-running helper program (Ghostscript, LibreOffice) straight away instead of waiting for it to finish, and a cancelled file never leaves a half-written output behind.
- If the app ever crashes inside one of its engines, a trace is now written to the logs folder (native_crash.log) so the cause can be found.

**Security improvements**
- Everything sent to the System AI — document excerpts for suggestions and recognised text for OCR clean-up — now travels encrypted. The Privacy page is updated to say so.

_Windows: the installer updates in place — your settings and favourites are kept. macOS: open the `.dmg` and drag the app to Applications._
