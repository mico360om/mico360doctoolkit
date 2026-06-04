## MICO360 Doc Toolkit v6.1.1

**Faster, more reliable update downloads.**

The previous updater opened a **single connection** and rode it to the end — so
if the download server handed it a slow edge, the whole update crawled at that
speed with no way out. The downloader is now smarter:

- **Reconnects off a slow connection** — if throughput drops, it drops that
  connection and grabs a fresh (often much faster) one, *resuming* via HTTP Range
  instead of starting over. So it rides the fast moments instead of getting stuck
  on a slow one.
- **Resumes after stalls/drops** — a hiccup no longer fails the update or
  restarts it from zero; it picks up exactly where it left off.
- **Lighter on your PC while downloading** — progress updates are throttled, so
  the download thread isn't competing with constant UI refreshes (which could
  slow it on a busy or low-end machine).
- The finished file is still **SHA-256 verified** before it installs.

Everything from v6.1.0 (UI/UX refresh) and v6.0.0 (multi-resolution / high-DPI,
single-instance, crash guard) carries over.

---
*This release is also the update manifest: the tag is the version, this text is the
release notes, and the attached Setup `.exe` (+ `.sha256`) is what the app installs.*
