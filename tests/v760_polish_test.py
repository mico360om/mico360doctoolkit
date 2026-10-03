"""v7.6.0 polish: the built-in System AI key, sharp app icons, the update
dialog's button, and tests that can't touch the user's real settings.

Run:  python tests/v760_polish_test.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []
FAKE_KEY = "mico_builtin_test_key_0123456789"


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def test_builtin_key() -> None:
    print("--- built-in System AI key ---")
    from mico360.config import settings
    from mico360.core import ai
    check("the key is scrambled, not stored as plain text",
          FAKE_KEY not in ai.scramble_key(FAKE_KEY)
          and ai._unscramble(ai.scramble_key(FAKE_KEY)) == FAKE_KEY)

    sys.path.insert(0, str(ROOT / "build"))
    import write_build_secrets as wbs
    with tempfile.TemporaryDirectory() as td:
        out, key_file = Path(td) / "_build_secrets.py", Path(td) / "system_ai.key"
        os.environ.pop("MICO360_SYSTEM_AI_KEY", None)
        check("no key -> the app is built without one",
              wbs.write(out, key_file) == "" and 'SYSTEM_AI_KEY = ""' in out.read_text())
        key_file.write_text(FAKE_KEY + "\n", encoding="utf-8")
        src = wbs.write(out, key_file)
        text = out.read_text(encoding="utf-8")
        check("build/system_ai.key is built in, scrambled",
              src == "system_ai.key" and FAKE_KEY not in text
              and ai.scramble_key(FAKE_KEY) in text, src)
        os.environ["MICO360_SYSTEM_AI_KEY"] = "from_env_" + FAKE_KEY
        check("the environment variable wins (the macOS build's secret)",
              wbs.write(out, key_file) == "MICO360_SYSTEM_AI_KEY")
        os.environ.pop("MICO360_SYSTEM_AI_KEY", None)
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    check("the key file and the generated module are git-ignored",
          "build/system_ai.key" in ignore and "mico360/_build_secrets.py" in ignore)
    for f in ("mico360.spec", "mico360_macos.spec", "mico360_onefile.spec"):
        check(f"{f} bundles the built-in key module",
              "mico360._build_secrets" in (ROOT / "build" / f).read_text(encoding="utf-8"))
    check("the Windows build writes the key before PyInstaller",
          (ROOT / "build" / "build.ps1").read_text(encoding="utf-8").find(
              "write_build_secrets.py") > 0)
    wf = (ROOT / ".github" / "workflows" / "build-macos.yml").read_text(encoding="utf-8")
    check("the macOS build takes the key from the repository secret",
          "secrets.MICO360_SYSTEM_AI_KEY" in wf and "write_build_secrets.py" in wf)

    # The app: System AI works with no saved key; the key never goes elsewhere.
    saved = (settings.ai_api_key_sealed, settings.ai_key_origin,
             settings.ai_source, settings.ai_base_url, settings.ai_enabled)
    os.environ["MICO360_SYSTEM_AI_KEY"] = FAKE_KEY
    try:
        settings.ai_api_key_sealed = ""
        settings.ai_enabled = True
        settings.ai_source = ai.SOURCE_SYSTEM
        cfg = ai.load_config()
        check("System AI works with no key pasted", cfg.api_key == FAKE_KEY
              and cfg.is_usable()[0], cfg.is_usable()[1])
        check("the built-in key is never sent to another server",
              ai.stored_key_for("http://127.0.0.1:5000/v1") == ""
              and ai.stored_key_for("https://api.example.com/v1") == "")
        settings.ai_source = ai.SOURCE_CUSTOM
        settings.ai_base_url = "http://127.0.0.1:5000/v1"
        check("'My own AI API' doesn't get the built-in key",
              ai.load_config().api_key == "")
        settings.ai_source = ai.SOURCE_SYSTEM
        settings.ai_api_key_sealed = ai.seal_key("user_own_key_abcdefghijk")
        settings.ai_key_origin = ai._origin(ai.SYSTEM_BASE_URL)
        check("a key the user pasted for the System AI is used instead",
              ai.load_config().api_key == "user_own_key_abcdefghijk")
        settings.ai_api_key_sealed = ai.seal_key("stale_test_key_abcdefghij")
        settings.ai_key_origin = "http://127.0.0.1:60834"
        check("a saved key for another server falls back to the built-in one",
              ai.load_config().api_key == FAKE_KEY)

        from mico360.ui.settings_page import SettingsPage
        settings.ai_base_url = "http://127.0.0.1:60834/v1"
        sp = SettingsPage()
        sp.ai_source.setCurrentIndex(sp.ai_source.findData(ai.SOURCE_SYSTEM))
        sp._sync_ai_fields()
        check("System AI shows its own address, not a stale custom one",
              sp.ai_url.text() == ai.SYSTEM_BASE_URL and not sp.ai_url.isEnabled(),
              sp.ai_url.text())
        check("Settings says the key is built in",
              "built in" in sp.ai_key_state.text().lower()
              and "different ai server" not in sp.ai_key_state.text().lower(),
              sp.ai_key_state.text())
        sp.ai_source.setCurrentIndex(sp.ai_source.findData(ai.SOURCE_CUSTOM))
        check("switching to your own API brings its address back",
              sp.ai_url.text() == "http://127.0.0.1:60834/v1" and sp.ai_url.isEnabled(),
              sp.ai_url.text())
        sp.ai_source.setCurrentIndex(sp.ai_source.findData(ai.SOURCE_SYSTEM))
        sp._save_ai()
        check("saving under System AI keeps your own API's address",
              settings.ai_base_url == "http://127.0.0.1:60834/v1", settings.ai_base_url)
        try:
            sp._stop_model_work()
        except Exception:
            pass
        sp.close()
    finally:
        os.environ.pop("MICO360_SYSTEM_AI_KEY", None)
        (settings.ai_api_key_sealed, settings.ai_key_origin, settings.ai_source,
         settings.ai_base_url, settings.ai_enabled) = saved


def test_icons() -> None:
    print("--- app icon ---")
    from PIL import Image
    ico = Image.open(ROOT / "mico360" / "resources" / "app.ico")
    sizes = sorted(w for w, _ in ico.ico.sizes())
    need = [16, 20, 24, 32, 40, 48, 64, 72, 96, 128, 256]
    check("app.ico has every size Windows asks for (incl. 125-200 % scaling)",
          all(s in sizes for s in need), str(sizes))
    for s in (16, 24, 32):
        im = ico.ico.getimage((s, s)).convert("RGBA")
        white = sum(1 for p in im.get_flattened_data() if p[3] > 200 and min(p[:3]) > 235)
        check(f"the {s} px icon has crisp white lettering (not a blur)",
              white >= s * s * 0.08, f"{white} solid white px")
    from mico360.ui.icons import app_icon
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    got = sorted(z.width() for z in app_icon().availableSizes())
    check("the window icon carries every size, not one big picture",
          len(got) >= 10 and 16 in got and 256 in got, str(got))
    iss = (ROOT / "build" / "installer.iss").read_text(encoding="utf-8")
    check("the installer refreshes Explorer's icon cache",
          "ChangesAssociations=yes" in iss)


def test_update_dialog() -> None:
    print("--- update-complete dialog ---")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from mico360.theme import stylesheet
    from mico360.ui.update_ui import UpdateCompletedDialog
    css = stylesheet("light")
    focus = [ln for ln in css.splitlines() if "QPushButton#Primary:focus" in ln]
    check("the primary button's focus ring isn't a heavy dark outline",
          focus and "#16171A" not in focus[0] and "rgba(255, 255, 255" in focus[0],
          focus[0] if focus else "missing")
    d = UpdateCompletedDialog("7.6.0", "October 01, 2026 at 07:54 AM")
    d.resize(460, 280)
    d.show()
    QApplication.processEvents()
    b = d.btn_ok
    centre = b.mapTo(d, b.rect().center()).x()
    check("the Great button is centred like the rest of the dialog",
          abs(centre - d.width() / 2) <= 4, f"{centre} vs {d.width() / 2}")
    check("the Great button is a comfortable size", b.width() >= 150, str(b.width()))
    d.close()


def test_settings_isolation() -> None:
    print("--- tests never touch the real settings ---")
    code = ("import os, sys; os.environ.pop('MICO360_SETTINGS_FILE', None); "
            f"sys.path.insert(0, r'{ROOT}'); "
            "from mico360.config import settings; print(settings._s.fileName())")
    env = {k: v for k, v in os.environ.items() if k != "MICO360_SETTINGS_FILE"}
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "tests" / "probe_test.py"
        fake.parent.mkdir()
        fake.write_text(code, encoding="utf-8")
        out = subprocess.run([sys.executable, str(fake)], capture_output=True,
                             text=True, env=env, stdin=subprocess.DEVNULL,
                             timeout=120).stdout.strip()
    check("a test script run directly gets a throw-away settings file",
          "mico360_test_" in out and "DocToolkit.ini" not in out, out)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])   # noqa: F841 (keep alive)
    test_builtin_key()
    test_icons()
    test_update_dialog()
    test_settings_isolation()
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All v7.6.0 polish checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
