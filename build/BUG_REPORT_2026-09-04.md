# MICO360 Doc Toolkit — System Test & Bug Report (v7.1.0 + icon-set work)

**Date:** 2026-09-04  **Scope:** full automated suite + static audit of the working tree (Windows dev machine, Python 3.14, PySide6). Sections 1–5 are the original read-only audit; **Section 0 records the fixes applied the same day and the re-test.**

---

## 0. Resolution — all B-items fixed and re-tested (2026-09-04)

**Re-test after fixes: 65 test files, 1,193 checks, 0 failures** (32 new checks added for the fixes). Every test that touches the changed widgets passed: `icons`, `spec_parity`, `tooltips`, `v55_edge` (password eye contract), `sidebar`, `sync_audit`, `responsive`, `update_ui`, `functional_ui`, `usability`, `interface_render`, `system_e2e`, `v52/v54` feature suites, `help_legal`, `smoke`. Both themes were rendered and visually checked (tool page, Home, password eye states).

| # | Fix | Where |
|---|---|---|
| B-1 | `build/make_icon.py` now writes **`app.ico` + `app.icns` + `app.png` (512² square)** with pure Pillow (no `iconutil` needed); `app.png` is used for `setWindowIcon` in `app.py` and `main_window.py` (falls back to `logo.png`). Both specs bundle `app.png`/`app.icns`. → Dock / taskbar / Alt-Tab show the maroon tile, including when run from source on macOS. | `build/make_icon.py`, `mico360/app.py`, `mico360/ui/main_window.py`, `mico360/resources/app.{png,icns}`, both specs |
| B-2 | `theme.system_theme()` caches the OS appearance for 2 s (`invalidate_system_theme_cache()` for tests). 40 back-to-back reads → **1** OS query (was 40 `defaults` spawns on macOS). | `mico360/theme.py` |
| B-3 | macOS spec now lists `PySide6.QtSvg`, `mico360.ui.icons`, `mico360.capabilities`, `mico360.core.ai`, `mico360.core.ai_metadata`, `mico360.ui.ai_suggest`. `spec_parity_test` now **diffs the two hidden-import lists** (minus a Windows-only allow-list) and requires the icon assets, so the gap can't reopen. | `build/mico360_macos.spec`, `tests/spec_parity_test.py` |
| B-4 | Glyph → icon migration completed: favourite **star / filled star** (`IconButton`), password **eye / eye-off**, drop-zone **inbox**, toast **check / x / info**, recent-files **file** icon, update dialog **folder** + per-category icons (sparkles/bug/lock/list), Home hint **sparkles**. New shapes + a reusable `IconButton` (checked-state icon swap, theme re-tint) added to `icons.py`. `#FavStar` no longer pins a Windows-only font. Help text updated ("star button", "sun / moon button"). | `mico360/ui/icons.py`, `tool_page.py`, `options_widget.py`, `widgets.py`, `dashboard_page.py`, `update_ui.py`, `help_page.py`, `theme.py` |
| B-5 | Removed `_theme_glyph()` and `_SECTION_GLYPH`; nav items pass no emoji fallback. `sync_audit_test` now checks every tool has a line icon instead. | `mico360/ui/main_window.py`, `tests/sync_audit_test.py` |
| B-6 | Deleted the 4 stale `*.tmp.*` files (two were inside `mico360/`) and 12 scratch `build/_*` files; icon preview now goes to `build/_work/`. | tree |
| B-7 | Font stacks add macOS families: `'SF Pro Text', 'Helvetica Neue'` and `'SF Mono', 'Menlo'`. | `mico360/theme.py` |
| B-8 | `gpu_ocr_test`: 7 consecutive passes (alone ×4, in the full suite, and twice in the OCR sequence `concurrency → language → quality → gpu`); the single crash is **not reproducible**. `ai_metadata_test`: isolated to this harness's *background* runner giving the process a TTY stdin — passes every time in the foreground and with `</dev/null` (74/74); not an app or test defect. | — |
| B-9 | `build/release.ps1` runs a **pre-release test gate** (9 suites, offscreen) before building/publishing; `-SkipTests` to bypass. | `build/release.ps1` |
| B-10 | The 24 `except: pass` sites in `processors.py` (14), `app.py` (5) and `update_ui.py` (5) now log at debug/warning/error with `exc_info`; `processors.py` and `update_ui.py` gained module loggers. Trivial cleanup sites elsewhere left as-is. | `mico360/core/processors.py`, `mico360/app.py`, `mico360/ui/update_ui.py` |

Not changed (user-side, carried in §3): code signing / notarization (R-1, R-2), HTTPS for custom AI endpoints (R-3), macOS Keychain (R-4), PAT revocation (R-5), pushing to the repo (R-6).

---

## 1. Test results

| Layer | Coverage | Result |
|---|---|---|
| Full automated suite | **65 test files, 1,161 checks** — all 21 tools, queue/progress/cancel, AI metadata (+retry/cancel), OCR (CPU/GPU/languages/concurrency), HEIC, SVG trace/embed, updater/download-resume, single-instance IPC, shell integration, help/legal, responsive/DPI, icons, stress/bulk | **1,161 / 1,161 PASS, 0 FAIL** |
| Intermittent (see B-8) | `ai_metadata_test` exited rc=127 once inside the sequential run (0 checks ran — shell/harness); `gpu_ocr_test` crashed once with 2 tracebacks after 3 passes | Both **pass on re-run**: 71/71 and 5/5 ×4 consecutive |
| New icon-set tests | `icons_test.py` — mapping for all 21 tools, every shape renders, tinting, cache, theme re-tint, nav/tile/header/toggle wiring | 20/20 PASS |
| Static | `compileall` over `mico360/`, `run.py`, build helpers | clean |
| Code smells | TODO / FIXME / HACK / XXX; stray `print()` in package | none |
| Real-machine logs | `%LOCALAPPDATA%\MICO360\DocToolkit\logs` | **no new crash since 25 Jun 2026**; the 16 error lines since 21 Aug are all test-generated (`broken.png` probes in `Temp\claude\…`) |
| Dependencies | `requirements.txt` vs. code | complete — `pillow-heif` and `vtracer` **are** listed (they were merely not installed in this dev venv; installed during the previous session) |

Slowest tests: `bulk_processing` 120 s, `robustness` 26 s, `all_tools` 21 s, `interface_render` 20 s.

---

## 2. Findings (ranked)

### B-1 · Medium · macOS Dock / window icon uses the wide word-mark, and `app.icns` is not in the tree
- `mico360/app.py:181-183` sets the application icon from **`logo.png`, a 2330×1095 RGBA word-mark** (not square). Qt uses that as the Dock icon on macOS (and Alt-Tab / taskbar on Windows when running from source), so it is squeezed into a square → appears tiny/blank. **This is the "icon not showing on the Mac" symptom** when running `python3 run.py`.
- `mico360/resources/` contains `app.ico` (Windows) but **no `app.icns`**; `build/mico360_macos.spec:135` references it and it only exists after the CI step `make_iconset.py` + `iconutil`. A local `pyinstaller mico360_macos.spec` without that step yields an app with a generic icon.
- Suggested fix: ship a square 512/1024-px PNG (the `make_icon.build_master()` output) in resources and use it for `setWindowIcon`; commit `app.icns` (or run the iconset step in a local build script).

### B-2 · Medium · "System" theme on macOS spawns a subprocess on every theme read
- `mico360/theme.py:21-34 system_theme()` runs `defaults read -g AppleInterfaceStyle` (3 s timeout). `config.settings.theme` calls it on **every read** when `theme_mode == "system"` (`config.py:103`).
- `ui/icons.theme_color()` → `settings.theme` runs once **per icon per refresh** (`IconLabel.refresh_icon`, `NavItem.refresh_icon`, `refresh_all` on `_apply_visuals`). With ~25 nav items + ~11 tile chips + header, a theme apply/startup in System mode on macOS = **~40+ process spawns**, each up to 3 s if `defaults` stalls. Windows path uses `winreg` per call (cheap, but also uncached).
- Suggested fix: cache the resolved theme for the duration of an apply (or a short TTL), or pass the theme into `theme_color()`.

### B-3 · Medium · Windows/macOS PyInstaller spec parity gap (hidden imports)
Present in `build/mico360.spec` but **missing** from `build/mico360_macos.spec`:
`PySide6.QtSvg`, `mico360.ui.icons`, `mico360.capabilities`, `mico360.core.ai`, `mico360.core.ai_metadata`, `mico360.ui.ai_suggest` (`mico360.shell_integration` is Windows-only — correct to omit).
- These are imported lazily inside functions; PyInstaller usually still finds them, but the Windows spec lists them explicitly *because* that was needed. If missed on macOS: **blank tool icons and/or a missing AI panel in the .app**.
- `tests/spec_parity_test.py` checks only 5 package tokens, so this gap is not covered.
- Needs verification on an actual macOS build (`Contents/Frameworks/PySide6/QtSvg*` + `mico360/ui/icons` in the PYZ).

### B-4 · Low · Icon-set migration is incomplete — text/emoji glyphs remain
The 21 tool icons, nav items, tile chips, tool header and theme toggle now use the tinted SVG set, but these still use font glyphs (inconsistent weight/colour, OS-dependent rendering, can't take brand red uniformly):

| Where | Glyph | Note |
|---|---|---|
| `ui/tool_page.py:195` favourite button | `★ / ☆` | `#FavStar` QSS (`theme.py:392-395`) pins font **"Segoe UI Symbol"** — Windows-only. Icon set already has an unused `star` shape. |
| `ui/widgets.py:370, 421` drop areas | `⬇` | |
| `ui/options_widget.py:125` password eye | `👁` | |
| `ui/dashboard_page.py:257` recent files | `📄` | `icons.file` exists |
| `ui/dashboard_page.py:168` greeting | `👋` | decorative |
| `ui/update_ui.py:210, 281-282` | `🗂️ 🐛 🔒` | |
| `ui/widgets.py:562` toast | `✓ ✗ ℹ` | |
| `ui/sidebar.py:180` section chevrons | `▸ ▾` | |
| `ui/help_page.py:218, 225` | text says "**☀ / 🌙** button" | now a sun/moon *icon*; wording slightly stale |

### B-5 · Low · Dead code left by the icon migration
- `ui/main_window.py:518 _theme_glyph()` — no callers.
- `ui/main_window.py:46 _SECTION_GLYPH` — only referenced by `tests/sync_audit_test.py`.
- `core/tools.py` emoji `icon=` field and the emoji first-arg to `sidebar.add_item(...)` (`main_window.py:242, 260, 269, 276`) are now fallback-only.

### B-6 · Low · Working-tree hygiene
- **Stale editor temp files inside the package:** `mico360/core/processors.py.tmp.45332.…` (25 Jun, 74 diff lines vs live) and `mico360/updater.py.tmp.39696.…` (5 Jun, 207 diff lines); also `build/mico360.spec.tmp.…`, `build/RELEASE_NOTES.md.tmp.…`. Not imported, but easy to open by mistake and picked up by any `rglob`.
- Scratch artefacts in `build/`: `_baseline_*.png`, `_v7_*.png`, `_icon_preview.png`, `_build_630.log`, `_bulk_test.log`, `_iscc.log`, `_pyi.log`, `_screens.py`.
- 12 `__pycache__` dirs; local `dist/` 419 MB, `build/_work` 82 MB, `vendor/` 1.1 GB (expected, but not in any ignore list since the folder isn't a git checkout).

### B-7 · Low · Font stack is Windows-first (cosmetic on macOS)
`theme.py:142` `'Segoe UI Variable','Segoe UI','Inter',Arial` → macOS falls through to **Arial**; `theme.py:470` `'Cascadia Mono','Consolas',monospace` → generic monospace. Adding `-apple-system`/`'Helvetica Neue'` and `'SF Mono'/'Menlo'` would match the native look.

### B-8 · Low · Intermittent test behaviour
- `gpu_ocr_test.py`: 1 crash (2 tracebacks, after 3 passing checks) in the full sequential run; 5/5 on four consecutive stand-alone runs. Trace not captured by the runner — likely resource/timing interaction with the preceding OCR tests.
- `ai_metadata_test.py`: one rc=127 with zero checks executed (shell "command not found"-class harness glitch); 71/71 stand-alone.
- OCR quality observation: multi-page check found **5 of 6** page markers on CPU (passes the threshold; one page's text missed).

### B-9 · Process · No test gate in the Windows build/release scripts
`build/build.ps1`, `release.ps1`, `publish.ps1` invoke no tests; the macOS CI runs 5. A green suite is currently a manual step before `publish`.

### B-10 · Style · 47 `except …: pass` sites
`core/processors.py` 14, `app.py` 5, `ui/update_ui.py` 5, others ≤4. Pre-existing; they trade diagnostics for robustness — worth at least `log.debug` in the processor paths.

---

## 3. Carried over from the 2026-08-21 report (still open, user-side or unverified)

| # | Item | Status |
|---|---|---|
| R-1 | Windows installer unsigned (SmartScreen) | open — needs OV/EV cert |
| R-2 | macOS app ad-hoc signed (Gatekeeper right-click → Open) | open — needs Developer ID + notarization |
| R-3 | AI traffic to custom endpoints over plain HTTP | open |
| R-4 | macOS API key stored base64-obfuscated (no Keychain) | open (`capabilities.py:54` discloses it in Help — good) |
| R-5 | Exposed GitHub PAT | revoke at github.com/settings/tokens — user only |
| R-6 | Unpublished commits vs shipped release | **cannot verify here** — this folder is not a git checkout; the icon-set work is also unpushed |
| R-7 | Parked `installer/_workflow_hardened_macos.yml` | still present |

---

## 4. What is clean

Compile, smells, dependencies, platform guards (`shell_integration` only reachable on Windows: `settings_page.py:976`, `capabilities.py:102`), macOS system-theme detection exists, single-instance IPC, updater fallbacks, help/legal capability gating, and all 21 tool pipelines — all pass. Hard-coded `C:\…` strings in five tests are literal values/fallbacks, not environment dependencies.

## 5. Suggested order of work
1. **B-1** square app icon for `setWindowIcon` + commit/generate `app.icns` (fixes the Mac Dock icon; small).
2. **B-3** add the missing hidden imports to the macOS spec and extend `spec_parity_test` to diff the two lists (small; de-risks the next .dmg).
3. **B-2** cache the resolved theme (small; real macOS perf win in System mode).
4. **B-4/B-5** finish the glyph → icon migration and delete dead glyph code (medium; pure polish).
5. **B-6** delete the four `.tmp.*` files and `build/_*` scratch (trivial).
6. B-7, B-9, B-10 as time allows.
