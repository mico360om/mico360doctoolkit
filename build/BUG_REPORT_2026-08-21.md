# MICO360 Doc Toolkit — full-system test & bug report

**Date:** 2026-08-21 · **Source under test:** `main` @ `c48c248` (v6.9.8 + 2 unpublished commits)
**Scope:** entire application — every tool, UI, AI features, settings, updater, engine — plus static analysis, real-machine logs, and targeted probes beyond the suite. **Nothing was fixed; findings only**, per instruction.

---

## 1. What was tested, and passed

| Layer | Coverage | Result |
|---|---|---|
| Full automated suite | 60 test files, **1,088 checks** — all tools (compress/merge/split/organize/protect/watermark/convert/OCR/metadata/images), queue, progress/cancel/retry, robustness (corrupt/empty/huge files), stress batches, settings sync, tooltips, updater, crash reporter, single-instance, DPI/responsive | **60/60 files, 1,088/1,088 checks PASS** |
| AI feature group | metadata suggestions (71), retry+cancel (16), end-to-end incl. security probes (48) | **135/135 PASS** |
| Cancel/retry race hunt | 10 consecutive runs of the retry/cancel test + 3 runs of an edge-case stress probe (rapid suggest→cancel→suggest, cancel with auto-apply, overlapping suggests, teardown mid-flight, garbage/HTTP-date `Retry-After`) | clean |
| Static analysis | `compileall` with `SyntaxWarning` as errors across `mico360/` | clean |
| Code smells | TODO/FIXME/XXX/HACK scan | none |
| Real-machine logs | `%LOCALAPPDATA%\MICO360\DocToolkit\logs` | no new crashes since the v6.9.4–v6.9.8 fixes; latest crash report is from 25 Jun (pre-dates current code); May–Jun engine errors are the pre-hardening `broken.png` cases already fixed and regression-tested |

---

## 2. Bugs found (not yet fixed)

### BUG-1 · Settings → AI → **Test connection freezes the whole window** — *Medium*
`_test_ai()` in `mico360/ui/settings_page.py` calls `ai_core.test_connection()` **synchronously on the UI thread**. Against an unreachable or non-routable host the underlying connect blocks for the full `CONNECT_TEST_TIMEOUT` (**30 s**) — measured: a probe with a 3 s timeout blocked the caller for exactly 3.0 s, so the real button freezes the app for up to 30 s with "Testing..." and no way to interact, resize, or cancel. The model-list refresh beside it already runs on a worker thread; Test connection should too.
*Repro:* Settings → AI → set API URL to `http://10.255.255.1:5310/v1` → Test connection → window unresponsive ~30 s.

### BUG-2 · Background model refresh **silently deletes hand-added model ids** and mislabels them — *Medium-low*
A user can type a custom model id (tooltip: *"You can still type an id to use one that isn't listed"*), and Save adds it to the saved list. But every background/auto refresh executes `settings.ai_models = models` (server list only), which **erases any hand-added id that isn't the current selection** — and the status line then reports the user's own entry as *"Hidden (offline or switched off): my-private-model:v1"*, which is wrong on both counts. This contradicts the Remove button's tooltip (*"Forget a model you added by hand"* — implying they otherwise persist). The v6.9.5 implementation explicitly merged hand-added ids; the v6.9.8 mirror-the-server rewrite dropped that preservation.
*Repro (verified):* save custom model `my-private-model:v1` alongside a server model, select the server model, open Settings → after the auto-refresh the custom id is gone from dropdown **and** settings, labelled "offline or switched off".

### BUG-3 · `masked_key` reveals most of a short key — *Low*
For keys of exactly ≤10 chars everything is masked; at **11 chars the mask flips to `first5 + •••• + last4`, revealing 9 of 11 characters (82%)**. Real `mico_…` keys are long (last-4 + public prefix is fine there), but the boundary behaviour is a leak for any short key. A proportional rule (never reveal more than ~⅓) would close it.

---

## 3. Known gaps & risks (not code defects, but report-worthy)

| # | Item | Impact |
|---|---|---|
| R-1 | **Windows installer is unsigned** | Every download triggers SmartScreen "unknown publisher"; auto-updates inherit the warning. Needs a code-signing cert (OV/EV or Azure Trusted Signing) — largest trust/conversion issue for distribution. |
| R-2 | **macOS app is ad-hoc signed only** | Users must right-click→Open past Gatekeeper; needs Developer ID + notarization ($99/yr). |
| R-3 | **AI traffic is plain HTTP** (per the API guide: "prompts and API keys cross the network in clear text") | Key + document excerpts are sniffable off the trusted network. Server-side fix (TLS reverse proxy) — the app can't fix this alone, but could warn when a non-HTTPS URL is configured. |
| R-4 | **macOS API-key storage is base64-obfuscation only** (`b64:` fallback — DPAPI is Windows-only) | A copied settings file exposes the key on macOS. Keychain integration would fix it. |
| R-5 | **Exposed GitHub PAT** (`ghp_…VavwF`, pasted in an earlier session, expired) | Should still be revoked at github.com/settings/tokens — only you can do this. |
| R-6 | **Release gap:** commits `dbb3bde` + `c48c248` are unpublished | The shipped v6.9.8 still: leaks raw `WinError 10053`/`IncompleteRead` messages on dropped connections, can show blank/duplicate model ids from a misbehaving server, has the shutdown crash risk in AI-panel thread teardown, and lacks Cancel + 429/503 auto-retry. All fixed on `main`, waiting for a v6.9.9 release. |
| R-7 | Parked file `installer/_workflow_hardened_macos.yml` | macOS CI hardening still not landed (needs a `workflow`-scoped token). |

---

## 4. Test-infrastructure observations (no action required)

* **Rare environmental flake:** running all 60 GUI test processes back-to-back can very occasionally fail one test (`v54_ui_test` once in ~5 full passes) that then passes 8/8 in isolation — resource contention, not a product defect.
* The pre-existing PySide **interpreter-shutdown abort (0xC0000409)** that used to randomly fail up to 6 passing tests per run is mitigated suite-wide by the `os._exit(rc)` teardown guard; results have been deterministic since.
* Suite wall-time is ~5 min per full pass (sequential process-per-test); a pytest/xdist migration would cut iteration time.

---

## 5. Summary

**No functional defects were found in the shipped feature set** — all 1,088 automated checks and all targeted probes pass, and the machine's own logs show no new crashes since the v6.9.4 fixes. Three genuine bugs were identified for the next fix round (**UI freeze in Test connection; hand-added models deleted by the refresh; masked-key boundary**), alongside seven risk/gap items of which **revoking the old PAT (R-5)** and **publishing the pending fixes (R-6)** are the immediate low-effort wins, and **code signing (R-1)** is the highest-impact investment.
