"""Complete per-module audit across all six layers.

Imports and exercises every module in the app — entry/bootstrap, core processing,
core supporting services, UI shell & pages, UI components, and cross-cutting
infrastructure — so a breakage in any single module surfaces here even when the
feature suites don't touch it.

Run:  python tests/module_audit_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures: list[str] = []


def step(name, fn):
    """Run one audit step; record PASS/FAIL with the exception if it raises."""
    try:
        ok = fn()
        ok = True if ok is None else bool(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            failures.append(name)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name}: {exc.__class__.__name__}: {exc}")
        traceback.print_exc()
        failures.append(name)


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
TMP = Path(tempfile.mkdtemp(prefix="mico360_audit_"))


def _make_pdf(path: Path) -> Path:
    import fitz
    d = fitz.open(); d.new_page(); d.save(str(path)); d.close()
    return path


# =====================================================================
# 1. Entry & bootstrap
# =====================================================================
def audit_entry():
    print("\n--- 1. Entry & bootstrap ---")

    def _meta():
        import mico360
        assert mico360.__version__ and mico360.__app_name__ and mico360.__publisher__
        return True
    step("mico360 package metadata present", _meta)

    def _main_module():
        import importlib
        m = importlib.import_module("mico360.__main__")
        return callable(m.main)
    step("__main__ imports without launching", _main_module)

    def _app():
        from mico360 import app
        app.configure_high_dpi()
        app._set_windows_app_id()
        from mico360.logging_setup import get_logger
        app.install_crash_guard(get_logger())
        return callable(app.main)
    step("app: high-DPI / app-id / crash-guard install", _app)


# =====================================================================
# 2. Core — processing
# =====================================================================
def audit_core_processing():
    print("\n--- 2. Core — processing ---")

    def _tools():
        from mico360.core import tools
        assert tools.TOOLS and tools.TOOLS_BY_ID
        for t in tools.TOOLS:
            assert callable(t.runner), f"{t.id} runner not callable"
            assert t.group in tools.GROUP_ORDER, f"{t.id} group {t.group!r} not ordered"
            for o in t.options:
                assert o.kind in ("text", "textarea", "choice", "int", "bool",
                                  "file", "password", "posgrid"), f"{t.id}:{o.key} {o.kind}"
                if o.kind == "choice":
                    assert o.choices, f"{t.id}:{o.key} choice has no options"
        return True
    step("tools: registry valid (runners, groups, option kinds)", _tools)

    def _processors():
        from mico360.core import processors
        # a real, self-contained run: edit metadata on a generated PDF
        src = _make_pdf(TMP / "p.pdf")
        outs = processors.pdf_metadata(src, TMP / "o", {"title": "Audit"},
                                       lambda *a, **k: None)
        assert outs and outs[0].exists()
        from pypdf import PdfReader
        assert str(PdfReader(str(outs[0])).metadata.get("/Title")) == "Audit"
        # helper sanity
        assert processors._pdf_date.__call__
        return True
    step("processors: end-to-end tool run (pdf_metadata)", _processors)

    def _engine():
        from mico360.core.engine import BatchController, UnitResult  # noqa: F401
        bc = BatchController(max_workers=0)
        return bc is not None
    step("engine: BatchController constructs", _engine)


# =====================================================================
# 3. Core — supporting services
# =====================================================================
def audit_core_services():
    print("\n--- 3. Core — supporting services ---")

    def _engines():
        from mico360.core import engines
        assert engines.engine_root() and engines.engine_soffice()
        assert isinstance(engines.is_engine_installed(), bool)
        assert engines.LO_MSI_URL.startswith("http")
        return True
    step("engines: on-demand LibreOffice surface", _engines)

    def _ocr():
        from mico360.core import ocr_models
        ch = dict(ocr_models.language_choices())
        assert "latin" in ch and "arabic" in ch
        assert ocr_models.is_language_ready("latin") is True
        assert ocr_models.ensure_language("latin") is None
        return True
    step("ocr_models: language registry + Latin built-in", _ocr)

    def _deps():
        from mico360.core import deps
        assert deps.find_ghostscript() is None or isinstance(deps.find_ghostscript(), str)
        assert deps.find_libreoffice() is None or isinstance(deps.find_libreoffice(), str)
        assert isinstance(deps.dependency_status(), dict)
        return True
    step("deps: ghostscript / libreoffice detection", _deps)

    def _crash():
        from mico360.core import crash
        try:
            raise ValueError("audit-boom")
        except ValueError:
            et, e, tb = sys.exc_info()
        rep = crash.format_report(et, e, tb)
        assert "audit-boom" in rep
        url = crash.github_issue_url(crash.issue_title(et, e), rep, None)
        assert url.startswith("https://github.com/") and len(url) <= 7000
        assert crash.mailto_url(rep).startswith("mailto:")
        return True
    step("crash: report + github-issue + mailto", _crash)

    def _util():
        from mico360.core import util
        src = _make_pdf(TMP / "u.pdf")
        out = util.build_output_path(src, TMP / "uo", ".pdf")
        assert str(out).endswith(".pdf")
        d = util.unique_dir(TMP / "ud")
        assert d.exists()
        assert util.human_size(1536).endswith("KB")
        return True
    step("util: output paths / unique dir / human size", _util)

    def _platform_utils():
        from mico360.core import platform_utils
        # build the commands but never actually open/trash anything
        assert platform_utils.open_command(TMP) is None or isinstance(
            platform_utils.open_command(TMP), list)
        assert callable(platform_utils.open_path) and callable(platform_utils.move_to_trash)
        return True
    step("platform_utils: command builders present", _platform_utils)


# =====================================================================
# 4. UI — shell & pages
# =====================================================================
def audit_ui_shell():
    print("\n--- 4. UI — shell & pages ---")

    from mico360.ui.main_window import MainWindow
    win = MainWindow()
    win.resize(1180, 760)
    win.show()
    for _ in range(4):
        app.processEvents()

    def _all_pages():
        built = 0
        for idx in sorted(win._titles):
            win.sidebar.select(idx)
            for _ in range(3):
                app.processEvents()
            assert win._widgets.get(idx) is not None, f"page {idx} ({win._titles[idx]}) not built"
            built += 1
        return built == len(win._titles)
    step(f"main_window: builds & shows every page (sidebar/tool/settings/help/log)", _all_pages)

    def _update_ui():
        from mico360.ui import update_ui
        from mico360.updater import UpdateInfo
        info = UpdateInfo(version="9.9.9", url="https://example/Setup.exe",
                          asset_name="Setup.exe", sha256="0" * 64,
                          notes="## New features\n- Thing\n## Bug fixes\n- Other",
                          page="https://example/releases", size=1234567,
                          published_at="2026-06-25T00:00:00Z")
        dlg = update_ui.UpdateDialog(info)
        assert dlg is not None
        assert callable(update_ui.start_check)
        update_ui.maybe_show_update_completed(win)   # no-op when nothing pending
        return True
    step("update_ui: UpdateDialog builds from UpdateInfo", _update_ui)

    win.close()


# =====================================================================
# 5. UI — components
# =====================================================================
def audit_ui_components():
    print("\n--- 5. UI — components ---")

    def _options_all_tools():
        from mico360.ui.options_widget import OptionsWidget
        from mico360.core.tools import TOOLS
        n = 0
        for t in TOOLS:
            w = OptionsWidget(t)
            vals = w.values()                 # exercises every option kind
            for o in t.options:
                assert o.key in vals or o.kind in ("file", "password"), \
                    f"{t.id}:{o.key} missing from values()"
            n += 1
        return n == len(TOOLS)
    step("options_widget: builds + reads values for every tool", _options_all_tools)

    def _file_collector():
        from mico360.ui.file_collector import collect_files
        d = TMP / "fc"; d.mkdir(exist_ok=True)
        (d / "a.pdf").write_bytes(b"%PDF-1.4")
        (d / "b.txt").write_text("x")
        got = collect_files([str(d)], {".pdf"})
        assert len(got) == 1 and got[0].name == "a.pdf"
        assert len(collect_files([str(d)], {"*"})) == 2
        return True
    step("file_collector: recursive collect + filtering", _file_collector)

    def _widgets():
        from mico360.ui import widgets
        from PySide6.QtWidgets import QLabel, QWidget
        host = QWidget()
        widgets.Card(); widgets.Divider(); widgets.Chip("ready")
        widgets.section_label("X"); widgets.hint_label("h")
        widgets.Toast(host, "hello", kind="ok")
        rr = widgets.ResponsiveRow(QLabel("a"), QLabel("b"))
        rr.resize(500, 100)
        return rr is not None
    step("widgets: shared components construct", _widgets)


# =====================================================================
# 6. Cross-cutting / infrastructure
# =====================================================================
def audit_cross_cutting():
    print("\n--- 6. Cross-cutting / infrastructure ---")

    def _config():
        from mico360.config import settings
        prev = settings.overwrite
        settings.overwrite = not prev
        assert settings.overwrite == (not prev)
        settings.overwrite = prev
        return True
    step("config: settings round-trip", _config)

    def _paths():
        from mico360 import paths
        assert paths.app_root().exists()
        assert paths.user_data_dir().exists() and paths.logs_dir().exists()
        assert str(paths.resource_path("logo.png")).endswith("logo.png")
        return True
    step("paths: source/bundle resolution", _paths)

    def _theme():
        from mico360 import theme
        assert len(theme.stylesheet("light")) > 100
        assert len(theme.stylesheet("dark")) > 100
        assert theme.system_theme() in ("light", "dark")
        return True
    step("theme: light/dark stylesheets + system detection", _theme)

    def _legal():
        from mico360 import legal
        for fn in (legal.about_us, legal.terms_and_conditions, legal.privacy_policy):
            assert len(fn()) > 100
        return True
    step("legal: about / terms / privacy render", _legal)

    def _logging():
        from mico360.logging_setup import setup_logging, get_logger
        setup_logging()
        log = get_logger()
        log.info("module audit log line")
        return log is not None
    step("logging_setup: setup + logger", _logging)

    def _single_instance():
        from mico360.single_instance import SingleInstance
        si = SingleInstance("mico360-audit-unique")
        running = si.is_running()           # no other instance under this name
        assert isinstance(running, bool)
        si.deleteLater()
        return True
    step("single_instance: guard constructs", _single_instance)

    def _updater():
        from mico360 import updater
        assert updater.clean_version("v6.9.1") == "6.9.1"
        assert updater.parse_version("6.9.1") == (6, 9, 1)
        assert updater.is_newer("6.9.2", "6.9.1") and not updater.is_newer("6.9.1", "6.9.1")
        assert updater.is_configured()
        assets = [{"name": "MICO360-DocToolkit-Setup-6.9.1.exe",
                   "browser_download_url": "u", "size": 1},
                  {"name": "MICO360-DocToolkit-macos-6.9.1.dmg",
                   "browser_download_url": "u", "size": 1}]
        pick = updater._pick_installer(assets)
        assert pick and pick["name"].endswith(".exe")
        return True
    step("updater: version math + installer pick", _updater)


def main() -> int:
    audit_entry()
    audit_core_processing()
    audit_core_services()
    audit_ui_shell()
    audit_ui_components()
    audit_cross_cutting()

    import shutil
    shutil.rmtree(TMP, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} module(s) FAILED: {', '.join(failures)}")
        return 1
    print("All module audits passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
