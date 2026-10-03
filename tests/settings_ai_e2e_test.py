"""End-to-end: Settings → AI, the update-complete dialog, and the sidebar.

Drives the real widgets the way a user does — clicks, typing, Save, Test
connection — against stub AI servers that behave like the platform (API keys,
model list, errors). Covers:

* functionality — every control on the AI page, the update dialog, sidebar
  search / navigation, the theme toggle and the menu button;
* validation — bad addresses, keys with stray spaces, unknown models,
  unreachable servers;
* permissions — a key only goes to the server it was saved for, the built-in
  System AI key only to the System AI, keys are never shown or stored in clear;
* data saving — everything survives a restart (read back in a new process);
* responsive design — the AI page and the dialog at small and large windows
  and at 100 / 150 / 200 % display scaling (real Windows rendering, screenshots
  saved for review). Run with --layout-only to repeat just that part.

Run:  python tests/settings_ai_e2e_test.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []
GOOD_KEY = "mico_e2e_good_key_0123456789abcdef"
MODELS = ["qwen2.5:0.5b", "llama3.1:8b"]


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


class Stub(BaseHTTPRequestHandler):
    """An OpenAI-compatible server; each instance records what it received."""
    seen: list = []

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        auth = self.headers.get("Authorization", "")
        type(self).seen.append((self.server.server_address[1], self.path, auth))
        if auth != f"Bearer {GOOD_KEY}":
            return self._send(401, {"error": {"message": "Invalid or missing API key."}})
        if self.path.rstrip("/").endswith("/models"):
            return self._send(200, {"data": [{"id": m} for m in MODELS]})
        return self._send(200, {"choices": [{"message": {"content": "{}"}}]})

    do_GET = do_POST = _handle


def _serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"


def status(sp) -> str:
    """The status line as the user reads it (HTML tags and entities removed)."""
    import html
    import re
    return html.unescape(re.sub(r"<[^>]+>", "", sp.ai_status.text()))


def wait_for(cond, timeout=20.0) -> bool:
    from PySide6.QtWidgets import QApplication
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    QApplication.processEvents()
    return bool(cond())


def click(widget):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QCheckBox
    if isinstance(widget, QCheckBox):      # on the box itself, like a person
        QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier,
                         QPoint(9, widget.height() // 2))
    else:
        QTest.mouseClick(widget, Qt.LeftButton)


def paste_into(edit, text):
    """Paste text (e.g. a copied API key with a trailing line break)."""
    from PySide6.QtWidgets import QApplication
    edit.setFocus()
    edit.clear()
    QApplication.clipboard().setText(text)
    edit.paste()


def type_into(edit, text):
    from PySide6.QtTest import QTest
    edit.setFocus()
    edit.selectAll()
    edit.clear()
    QTest.keyClicks(edit, text)


# =====================================================================
def test_ai_settings(ini: Path) -> None:
    from PySide6.QtWidgets import QApplication
    from mico360.config import settings
    from mico360.core import ai
    from mico360.ui.settings_page import SettingsPage

    sys_srv, sys_url = _serve()          # stands in for the System AI
    own_srv, own_url = _serve()          # "my own AI API"
    other_srv, other_url = _serve()      # a different server
    ai.SYSTEM_BASE_URL = sys_url
    sp = None
    try:
        print("--- first run ---")
        sp = SettingsPage()
        sp.resize(900, 900)
        sp.show()
        QApplication.processEvents()
        check("AI features are off until the user turns them on",
              not sp.chk_ai.isChecked() and not settings.ai_enabled)
        check("System AI is the default provider",
              sp.ai_source.currentData() == ai.SOURCE_SYSTEM)
        check("System AI shows its own address, read-only",
              sp.ai_url.text() == sys_url and not sp.ai_url.isEnabled(), sp.ai_url.text())
        check("without a built-in key, it says no key is saved",
              "no api key saved" in sp.ai_key_state.text().lower(), sp.ai_key_state.text())

        print("--- enable + System AI with the built-in key ---")
        os.environ["MICO360_SYSTEM_AI_KEY"] = GOOD_KEY
        sp._sync_ai_fields()
        check("with a built-in key, Settings says there's nothing to paste",
              "built into the app" in sp.ai_key_state.text()
              and "built in" in sp.ai_key.placeholderText().lower(), sp.ai_key_state.text())
        click(sp.chk_ai)
        check("ticking Enable AI features saves it at once", settings.ai_enabled)
        Stub.seen.clear()
        click(sp.btn_ai_test)
        check("Test connection is disabled while it runs", not sp.btn_ai_test.isEnabled())
        check("Test connection succeeds with the built-in key",
              wait_for(lambda: "✓" in status(sp)), status(sp))
        check("Test connection is available again afterwards", sp.btn_ai_test.isEnabled())
        check("the built-in key went to the System AI only",
              Stub.seen and all(p == sys_srv.server_address[1] and a == f"Bearer {GOOD_KEY}"
                                for p, _path, a in Stub.seen), str(Stub.seen[:3]))
        check("the model list fills from the server",
              wait_for(lambda: all(sp.ai_model.findText(m) >= 0 for m in MODELS)),
              str([sp.ai_model.itemText(i) for i in range(sp.ai_model.count())]))

        print("--- my own API: validation ---")
        sp.ai_source.setCurrentIndex(sp.ai_source.findData(ai.SOURCE_CUSTOM))
        check("choosing My own AI API makes the address editable",
              sp.ai_url.isEnabled() and sp.ai_url.text() == "", sp.ai_url.text())
        for bad, why in (("not a url", "spaces"), ("ftp://files.example.com", "http"),
                         ("http://", "server name"), ("http://host:99999/v1", "port"),
                         ("", "enter the address")):
            before = settings.ai_base_url
            type_into(sp.ai_url, bad)
            click(sp.btn_ai_save)
            check(f"Save refuses {bad!r} and says why",
                  why in status(sp).lower() and "nothing was saved"
                  in status(sp).lower() and settings.ai_base_url == before,
                  status(sp)[:90])
        check("an invalid address isn't sent to Test connection either",
              (type_into(sp.ai_url, "not a url") or True)
              and (click(sp.btn_ai_test) or True)
              and "nothing was saved" in status(sp).lower())

        port = own_srv.server_address[1]
        type_into(sp.ai_url, f"127.0.0.1:{port}")
        paste_into(sp.ai_key, f"  {GOOD_KEY}\r\n")       # copied with a line break
        click(sp.btn_ai_save)
        check("a bare host is completed to a full API address",
              sp.ai_url.text() == own_url and settings.ai_base_url == own_url,
              sp.ai_url.text())
        check("Save confirms", status(sp) == "Saved.", status(sp))

        print("--- my own API: the key ---")
        check("the key box is cleared after saving", sp.ai_key.text() == "")
        check("the saved key is shown masked, never in full",
              GOOD_KEY not in sp.ai_key.placeholderText()
              and sp.ai_key.placeholderText().startswith(ai.masked_key(GOOD_KEY)),
              sp.ai_key.placeholderText())
        check("stray spaces/line breaks are removed from the key",
              ai.unseal_key(settings.ai_api_key_sealed) == GOOD_KEY)
        settings._s.sync()
        check("the key is not stored in clear text", GOOD_KEY not in ini.read_text("utf-8"))

        Stub.seen.clear()
        click(sp.btn_ai_test)
        check("Test connection with your own key succeeds and names the model",
              wait_for(lambda: "✓" in status(sp)) and "connected" in
              status(sp).lower(), status(sp))

        type_into(sp.ai_key, "wrong-key-value-123")
        click(sp.btn_ai_test)
        check("a wrong key is reported clearly",
              wait_for(lambda: "✗" in status(sp))
              and "rejected" in status(sp).lower(), status(sp))
        type_into(sp.ai_key, GOOD_KEY)
        click(sp.btn_ai_save)

        print("--- permissions: keys stay with their server ---")
        Stub.seen.clear()
        type_into(sp.ai_url, other_url)
        click(sp.btn_ai_test)
        wait_for(lambda: "✗" in status(sp) or "✓" in status(sp), 10)
        leaked = [a for p, _path, a in Stub.seen if GOOD_KEY in a]
        check("the saved key is NOT sent to a different server", not leaked, str(leaked))
        check("…and Settings says that server needs its own key",
              "different ai server" in sp.ai_key_state.text().lower()
              or "no ai api key" in status(sp).lower(), status(sp))
        type_into(sp.ai_url, own_url)
        click(sp.btn_ai_save)
        check("switching back to the key's own server uses it again",
              ai.load_config().api_key == GOOD_KEY)

        type_into(sp.ai_url, "http://127.0.0.1:9/v1")
        paste_into(sp.ai_key, "key-for-a-server-that-is-down")
        click(sp.btn_ai_test)
        check("an unreachable server is reported without freezing",
              wait_for(lambda: "✗" in status(sp), 40)
              and "couldn't reach" in status(sp).lower(), status(sp))
        type_into(sp.ai_url, own_url)
        paste_into(sp.ai_key, GOOD_KEY)
        click(sp.btn_ai_save)

        print("--- models ---")
        click(sp.btn_models_refresh)
        check("Refresh lists the server's models",
              wait_for(lambda: "model(s) available" in sp.ai_models_state.text()),
              sp.ai_models_state.text())
        sp.ai_model.setEditText("my-own-model")
        click(sp.btn_ai_save)
        check("typing a new model adds it (kept as your own)",
              "my-own-model" in settings.ai_models
              and "my-own-model" in settings.ai_custom_models
              and settings.ai_model == "my-own-model")
        click(sp.btn_ai_test)
        check("Test connection warns (⚠, not ✓) when the model isn't offered",
              wait_for(lambda: "isn't one of them" in status(sp))
              and status(sp).startswith("⚠"), status(sp))
        sp.ai_model.setCurrentIndex(sp.ai_model.findText("my-own-model"))
        click(sp.btn_models_remove)
        check("Remove takes it off the list and picks another",
              "my-own-model" not in settings.ai_models
              and sp.ai_model.findText("my-own-model") < 0
              and settings.ai_model in MODELS, settings.ai_model)
        sp.ai_model.setCurrentIndex(sp.ai_model.findText("llama3.1:8b"))
        click(sp.btn_ai_save)

        print("--- switching back to System AI ---")
        sp.ai_source.setCurrentIndex(sp.ai_source.findData(ai.SOURCE_SYSTEM))
        check("System AI shows its address again; your own is kept",
              sp.ai_url.text() == sys_url and settings.ai_base_url == own_url)
        click(sp.btn_ai_save)
        check("saving under System AI doesn't overwrite your own API's address",
              settings.ai_base_url == own_url and settings.ai_source == ai.SOURCE_SYSTEM)
        os.environ.pop("MICO360_SYSTEM_AI_KEY", None)
        sp._sync_ai_fields()
        check("a key saved for another server isn't offered to the System AI",
              ai.load_config().api_key == "", ai.load_config().api_key[:6])
        sp.ai_source.setCurrentIndex(sp.ai_source.findData(ai.SOURCE_CUSTOM))
        click(sp.btn_ai_save)
        settings._s.sync()
    finally:
        os.environ.pop("MICO360_SYSTEM_AI_KEY", None)
        if sp is not None:
            sp._stop_model_work()
            sp.close()
        for s in (sys_srv, own_srv, other_srv):
            s.shutdown()

    print("--- data saving: a fresh start reads it all back ---")
    probe = (
        "import sys, json; sys.path.insert(0, r'%s');"
        "from mico360.config import settings; from mico360.core import ai;"
        "print(json.dumps(dict(enabled=settings.ai_enabled, source=settings.ai_source,"
        " url=settings.ai_base_url, model=settings.ai_model, models=settings.ai_models,"
        " key=ai.unseal_key(settings.ai_api_key_sealed) == '%s')))" % (ROOT, GOOD_KEY))
    env = dict(os.environ, MICO360_SETTINGS_FILE=str(ini), QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                         env=env, stdin=subprocess.DEVNULL, timeout=120)
    try:
        got = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        got = {}
    check("after a restart: AI on, own API, its address, model and key are kept",
          got.get("enabled") is True and got.get("source") == "custom"
          and got.get("url") == own_url and got.get("model") == "llama3.1:8b"
          and got.get("key") is True and "my-own-model" not in got.get("models", []),
          str(got) or out.stderr[-300:])


# =====================================================================
def test_update_dialog() -> None:
    print("--- update-complete dialog ---")
    from PySide6.QtWidgets import QApplication, QDialog
    from mico360 import __version__
    from mico360.config import settings
    from mico360.ui import update_ui

    shown = []

    def fake_exec(self):
        shown.append(self)
        self.show()
        QApplication.processEvents()
        click(self.btn_ok)                 # the user presses "Great"
        return self.result()

    orig = update_ui.UpdateCompletedDialog.exec
    update_ui.UpdateCompletedDialog.exec = fake_exec
    try:
        settings.pending_update = {"version": __version__}
        update_ui.maybe_show_update_completed(None)
        check("after an update the confirmation is shown once", len(shown) == 1)
        if shown:
            d = shown[0]
            text = " ".join(lbl.text() for lbl in d.findChildren(type(d.btn_ok.parent()
                                                                       .findChild(QDialog)
                                                                       or d)))
            from PySide6.QtWidgets import QLabel
            text = " ".join(lbl.text() for lbl in d.findChildren(QLabel))
            check("it names the new version and when it was installed",
                  f"v{__version__}" in text and "Updated on" in text, text[:120])
            check("pressing Great closes it", d.result() == QDialog.Accepted
                  and not d.isVisible())
        check("the 'just updated' marker is cleared", not settings.pending_update)
        update_ui.maybe_show_update_completed(None)
        check("it isn't shown again on the next start", len(shown) == 1)
        settings.pending_update = {"version": "999.0.0"}
        update_ui.maybe_show_update_completed(None)
        check("a failed update (still the old version) shows no 'success'",
              len(shown) == 1 and not settings.pending_update)
    finally:
        update_ui.UpdateCompletedDialog.exec = orig


# =====================================================================
def test_sidebar() -> None:
    print("--- sidebar, theme, menu ---")
    from PySide6.QtWidgets import QApplication
    from mico360.config import settings
    from mico360.ui.main_window import MainWindow
    win = MainWindow()
    win.resize(1200, 800)
    win.show()
    QApplication.processEvents()
    sb = win.sidebar
    labels = {it._label: it for it in sb._items}
    wanted = ["Add Page Numbers", "Sign PDF", "Edit Metadata", "Resize Image",
              "Watermark Image", "Protect PDF", "Searchable PDF (OCR)",
              "Edit File Properties", "Settings", "Activity", "Help"]
    missing = [w for w in wanted if w not in labels]
    check("every item in the screenshot is in the sidebar", not missing, str(missing))
    wrong = []
    for name in wanted:
        if name not in labels:
            continue
        click(labels[name])
        QApplication.processEvents()
        if not (labels[name].isChecked() and name.split(" (")[0].lower()
                in win.top_title.text().lower()):
            wrong.append(f"{name} -> {win.top_title.text()!r}")
    check("clicking each item opens its page", not wrong, str(wrong))

    sb._search.setText("sign")
    QApplication.processEvents()
    vis = [it._label for it in sb._items if it.isVisibleTo(sb)]
    check("searching 'sign' shows Sign PDF", "Sign PDF" in vis, str(vis))
    check("…and hides unrelated tools", "Resize Image" not in vis)
    sb._search.setText("password")
    QApplication.processEvents()
    vis = [it._label for it in sb._items if it.isVisibleTo(sb)]
    check("search also matches what a tool does ('password' -> Protect PDF)",
          "Protect PDF" in vis, str(vis))
    sb._search.setText("")
    QApplication.processEvents()
    check("clearing the search shows the tools again",
          labels["Resize Image"].isVisibleTo(sb) or labels["Resize Image"]._group["collapsed"])

    before = settings.theme
    click(win.btn_theme)
    check("the theme button switches light/dark and remembers it",
          settings.theme != before)
    click(win.btn_theme)
    check("…and back", settings.theme == before)
    collapsed = sb.collapsed
    win._toggle_sidebar()
    check("the menu button collapses / expands the sidebar", sb.collapsed != collapsed)
    win._toggle_sidebar()
    win.close()


# =====================================================================
LAYOUT_PROBE = r"""
import json, os, sys
sys.path.insert(0, ROOT)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QLabel, QScrollArea
from mico360.app import configure_high_dpi
configure_high_dpi()          # start Qt exactly as the app does (exact 125/150 %)
app = QApplication([])
from mico360.theme import stylesheet
from mico360.ui.main_window import MainWindow
from mico360.ui.update_ui import UpdateCompletedDialog
app.setStyleSheet(stylesheet("light"))
res = []
for (w, h) in SIZES:
    win = MainWindow()
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.resize(w, h)
    win.show()
    labels = {it._label: it for it in win.sidebar._items}
    labels["Settings"].click()
    app.processEvents()
    sp = win.settings_page
    from PySide6.QtWidgets import QTabWidget
    tabw = sp.findChild(QTabWidget)
    tabw.setCurrentIndex(2)
    app.processEvents()
    page = tabw.currentWidget()
    scroll = page if isinstance(page, QScrollArea) else page.findChild(QScrollArea)
    bad = []
    for b in (sp.btn_ai_save, sp.btn_ai_test, sp.btn_models_refresh, sp.btn_models_remove):
        if b.width() < b.minimumSizeHint().width() - 1:
            bad.append(f"{b.text()} squeezed {b.width()}<{b.minimumSizeHint().width()}")
        g = b.mapTo(scroll.widget(), b.rect().topRight())
        if g.x() > scroll.viewport().width() + 1:
            bad.append(f"{b.text()} beyond the right edge")
    hbar = scroll.horizontalScrollBar()
    if hbar.isVisible() and hbar.maximum() > 0:
        bad.append(f"horizontal scrolling ({hbar.maximum()} px)")
    for lbl in (sp.ai_key_state, sp.ai_models_state, sp.ai_status):
        lbl.setText("A long status message that has to wrap onto several lines "
                    "rather than push the page wider than the window. " * 2)
    for _ in range(40):           # let the scroll area grow the page (it takes
        app.processEvents()       # a few passes; the first is mid-layout)
    if hbar.isVisible() and hbar.maximum() > 0:
        bad.append("long messages make the page scroll sideways")
    for wdg in (sp.ai_source, sp.ai_url, sp.ai_key, sp.ai_model, sp.btn_ai_save,
                sp.btn_ai_test, sp.btn_models_refresh, sp.btn_models_remove):
        if wdg.height() < wdg.sizeHint().height() - 1:
            bad.append(f"{type(wdg).__name__} squashed to {wdg.height()}px "
                       f"(needs {wdg.sizeHint().height()})")
    win.grab().save(os.path.join(OUT, f"settings_ai_{SCALE}x_{w}x{h}.png"))
    res.append({"size": [w, h], "problems": bad})
    win.close()
d = UpdateCompletedDialog("7.6.0", "October 01, 2026 at 07:54 AM")
d.setAttribute(Qt.WA_DontShowOnScreen, True)
d.show(); app.processEvents()
b = d.btn_ok
dbad = []
if not d.rect().contains(b.geometry()):
    dbad.append("Great button outside the dialog")
for lbl in d.findChildren(QLabel):
    if lbl.text() and lbl.width() < min(lbl.sizeHint().width(), d.width() - 48) - 2 \
            and not lbl.wordWrap():
        dbad.append(f"text cut off: {lbl.text()[:30]}")
if abs(b.mapTo(d, b.rect().center()).x() - d.width() / 2) > 4:
    dbad.append("button not centred")
d.grab().save(os.path.join(OUT, f"update_done_{SCALE}x.png"))
res.append({"size": "dialog", "problems": dbad})
print("RESULT " + json.dumps(res))
"""


def test_layout(out_dir: Path) -> None:
    print("--- responsive design (real Windows rendering) ---")
    sizes = [(1000, 640), (1280, 720), (1600, 900)]
    for scale in ("1", "1.5", "2"):
        code = (f"ROOT = {str(ROOT)!r}\nOUT = {str(out_dir)!r}\nSCALE = {scale!r}\n"
                f"SIZES = {sizes!r}\n" + LAYOUT_PROBE)
        env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
        env.update(QT_SCALE_FACTOR=scale, QT_ENABLE_HIGHDPI_SCALING="1",
                   MICO360_SETTINGS_FILE=str(out_dir / f"layout_{scale}.ini"))
        if sys.platform != "win32":
            env["QT_QPA_PLATFORM"] = "offscreen"
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=300)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")), "")
        if not line:
            check(f"layout at {scale}x scaling renders", False, p.stderr[-400:])
            continue
        for r in json.loads(line[7:]):
            what = ("update dialog" if r["size"] == "dialog"
                    else f"Settings → AI at {r['size'][0]}x{r['size'][1]}")
            check(f"{what}, {scale}x scaling: nothing cut off or overflowing",
                  not r["problems"], "; ".join(r["problems"]))


def main() -> int:
    out = Path(os.environ.get("MICO360_E2E_SHOTS", "")) if os.environ.get(
        "MICO360_E2E_SHOTS") else Path(tempfile.mkdtemp(prefix="mico360_e2e_"))
    out.mkdir(parents=True, exist_ok=True)
    if "--layout-only" not in sys.argv:
        ini = out / "e2e.ini"
        if ini.exists():
            ini.unlink()
        os.environ["MICO360_SETTINGS_FILE"] = str(ini)
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.pop("MICO360_SYSTEM_AI_KEY", None)
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])   # noqa: F841
        test_ai_settings(ini)
        test_update_dialog()
        test_sidebar()
    test_layout(out)
    print(f"\nScreenshots: {out}")
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All Settings / update dialog / sidebar end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
