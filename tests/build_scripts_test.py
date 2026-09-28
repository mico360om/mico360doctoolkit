"""Static guards for the build / release pipeline (nothing is built or published).

* build.ps1 checks $LASTEXITCODE after every native step and wipes the previous
  dist\\MICO360DocToolkit before PyInstaller, so a failed build can never be
  repackaged and shipped (H-6); the best-effort pip uninstall can't abort it.
* release.ps1 / publish.ps1 upload all four Windows assets, incl. the stable
  Setup-Latest.exe + .sha256 the README and the updater fallback need (M-35).
* The portable onefile spec keeps QtNetwork (single-instance guard) and bundles
  the same feature-critical modules/data as the onedir spec (M-36).
* installer.iss registers the menu as the logged-in user, relaunches the app
  after a silent auto-update, and clears stale _internal\\ libraries (M-33/34).
* The macOS workflow builds the requested tag and checks it against __version__.
* Every .ps1 parses (Windows PowerShell parser), when PowerShell is available.

Run:  python tests/build_scripts_test.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _hidden_imports(spec_text: str) -> set[str]:
    m = re.search(r"hiddenimports\s*=\s*\[(.*?)\n\]", spec_text, re.S)
    return set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()


def _tuple_body(spec_text: str, name: str) -> str:
    m = re.search(name + r"\s*=\s*\((.*?)\n\)", spec_text, re.S)
    return m.group(1) if m else ""


def test_build_ps1() -> None:
    lines = _read(BUILD / "build.ps1").splitlines()
    code = [(i, ln.strip()) for i, ln in enumerate(lines)
            if ln.strip() and not ln.strip().startswith("#")]
    native = re.compile(r"^(&\s*\$Py\b|&\s*\$iscc\.Source\b|py\s+-3\b)")
    unchecked = []
    for idx, (i, ln) in enumerate(code):
        if not native.match(ln) or "pip uninstall" in ln:
            continue
        window = " ".join(c for _, c in code[idx + 1: idx + 3])
        if "$LASTEXITCODE" not in window:
            unchecked.append(f"line {i + 1}: {ln}")
    check("build.ps1: every native call is followed by a $LASTEXITCODE check",
          not unchecked, "; ".join(unchecked))
    text = "\n".join(lines)
    for step in ("make_icon.py", "make_menu_icons.py", "smoke_test.py",
                 "PyInstaller", "installer.iss"):
        check(f"build.ps1: runs {step}", step in text)
    check("build.ps1: failures throw", text.count("throw ") >= 8, str(text.count("throw ")))

    rm = next((i for i, ln in enumerate(lines) if "Remove-Item" in ln and "$DistApp" in ln), -1)
    pyi = next((i for i, ln in enumerate(lines) if "PyInstaller build\\mico360.spec" in ln), -1)
    check("build.ps1: previous dist\\MICO360DocToolkit is removed BEFORE PyInstaller",
          0 <= rm < pyi and 'dist\\MICO360DocToolkit"' in text, f"rm={rm} pyi={pyi}")

    uninstall = next((i for i, ln in enumerate(lines) if "pip uninstall" in ln), -1)
    before = "\n".join(lines[max(0, uninstall - 6):uninstall])
    after = "\n".join(lines[uninstall:uninstall + 4])
    check("build.ps1: pip uninstall runs with ErrorActionPreference=Continue",
          uninstall > 0 and '$ErrorActionPreference = "Continue"' in before
          and "$ErrorActionPreference = $prevEap" in after)
    check("build.ps1: pip uninstall exit code is not treated as fatal",
          "$LASTEXITCODE" not in lines[uninstall])


def test_release_scripts() -> None:
    rel = _read(BUILD / "release.ps1")
    pub = _read(BUILD / "publish.ps1")
    for name, text, arr in (("release.ps1", rel, "$Assets"), ("publish.ps1", pub, "$assets")):
        m = re.search(re.escape(arr) + r"\s*=\s*@\(([^)]*)\)", text)
        members = [x.strip() for x in m.group(1).split(",")] if m else []
        check(f"{name}: uploads versioned exe + sidecar + Latest exe + sidecar",
              members[:4] == ["$Installer", "$Sidecar", "$Latest", "$LatestSidecar"],
              str(members))
        check(f"{name}: builds the Setup-Latest.exe copy + its .sha256",
              '"MICO360-DocToolkit-Setup-Latest.exe"' in text
              and re.search(r'\$LatestSidecar\s*=\s*"\$Latest\.sha256"', text) is not None
              and "Copy-Item -LiteralPath $Installer -Destination $Latest" in text)
        check(f"{name}: Latest copy is checked against this version's hash",
              "$LatestHash -ne $Hash" in text)
        check(f"{name}: create AND upload paths both send every asset",
              re.search(r"release create \$Tag @" + re.escape(arr[1:]), text, re.I) is not None
              and re.search(r"release upload \$Tag @" + re.escape(arr[1:]), text, re.I) is not None)
    check("release.ps1: keeps the -SkipTests switch and the test gate",
          "[switch]$SkipTests" in rel and "if (-not $SkipTests)" in rel
          and "Test gate failed" in rel)


def test_onefile_spec() -> None:
    one = _read(BUILD / "mico360_onefile.spec")
    onedir = _read(BUILD / "mico360.spec")
    drop = _tuple_body(one, "_QT_DROP").lower()
    check("onefile: QtNetwork is NOT in the Qt drop list",
          drop and "network" not in drop, drop)
    ex = re.search(r"excludes\s*=\s*\[(.*?)\]", one, re.S)
    check("onefile: QtNetwork is NOT excluded",
          ex and "QtNetwork" not in ex.group(1))
    check("onefile: QtNetwork is a hidden import (single-instance guard)",
          "PySide6.QtNetwork" in _hidden_imports(one))
    missing = sorted(_hidden_imports(onedir) - _hidden_imports(one))
    check("onefile: lists every hidden import the onedir spec has", not missing, str(missing))
    for token in ("app.png", "app.icns", "ocr_data", "menu_icons", '"vtracer"',
                  '"pillow_heif"', "collect_dynamic_libs"):
        check(f"onefile: bundles {token}", token in one)
    loop = re.search(r"for pkg in \((.*?)\):", one, re.S)
    check("onefile: collect_all() covers vtracer + pillow_heif",
          loop and '"vtracer"' in loop.group(1) and '"pillow_heif"' in loop.group(1))
    try:
        compile(one, "mico360_onefile.spec", "exec")
        check("onefile: spec is valid Python", True)
    except SyntaxError as exc:
        check("onefile: spec is valid Python", False, str(exc))


def test_no_control_characters() -> None:
    """A stray control character in a script (e.g. a carriage return where a
    backslash sequence was meant) silently breaks a path — it happened once in
    release.ps1 ("tests<CR>un_suite.py")."""
    import re
    bad = []
    for f in sorted(BUILD.glob("*.ps1")) + sorted(BUILD.glob("*.iss")) + sorted(BUILD.glob("*.spec")):
        for n, line in enumerate(_read(f).replace("\r\n", "\n").split("\n"), 1):
            if re.search(r"[\x00-\x08\x0b-\x1f]", line):
                bad.append(f"{f.name}:{n}")
    check("build scripts contain no stray control characters", not bad, str(bad))


def test_installer_iss() -> None:
    iss = _read(BUILD / "installer.iss")
    run = iss.split("[Run]", 1)[1].split("\n[", 1)[0] if "[Run]" in iss else ""
    entries = [ln for ln in run.splitlines() if ln.strip() and not ln.strip().startswith(";")]
    reg = [e for e in entries if "--register-shell" in e or "--unregister-shell" in e]
    check("iss: the shell menu is (un)registered as the original (logged-in) user",
          len(reg) >= 1 and all("runasoriginaluser" in e for e in reg), str(reg))
    check("iss: the right-click menu is an installer Task (optional, remembered)",
          'Name: "shellmenu"' in iss
          and all("Tasks: shellmenu" in e or "Tasks: not shellmenu" in e for e in reg),
          str(reg))
    check("iss: an unticked menu Task records the opt-out",
          any("--unregister-shell --opt-out" in e and "not shellmenu" in e for e in reg))
    silent = [e for e in entries if "Check: WizardSilent" in e
              and "-shell" not in e]
    check("iss: a silent install relaunches the app",
          len(silent) == 1 and "runasoriginaluser" in silent[0] and "nowait" in silent[0]
          and "--" not in silent[0] and "postinstall" not in silent[0], str(silent))
    inter = [e for e in entries if "postinstall" in e]
    check("iss: interactive 'Launch' entry kept (postinstall skipifsilent)",
          len(inter) == 1 and "skipifsilent" in inter[0], str(inter))
    check("iss: [InstallDelete] clears stale {app}\\_internal on upgrade",
          re.search(r"\[InstallDelete\]\s*(?:;[^\n]*\n\s*)*Type:\s*filesandordirs;\s*"
                    r'Name:\s*"\{app\}\\_internal"', iss) is not None)
    check("iss: AppId unchanged",
          "AppId={{8E5C2A41-9F3B-4D8E-AB12-CD34EF567890}}" in iss)


def test_macos_workflow() -> None:
    import yaml
    wf = ROOT / ".github" / "workflows" / "build-macos.yml"
    data = yaml.safe_load(wf.read_text(encoding="utf-8"))
    steps = data["jobs"]["build-macos"]["steps"]
    co = next((s for s in steps if str(s.get("uses", "")).startswith("actions/checkout")), {})
    check("workflow: checkout builds the requested tag on workflow_dispatch",
          (co.get("with") or {}).get("ref") == "${{ github.event.inputs.tag || github.ref }}",
          str(co))
    verify = next((s for s in steps if "__version__" in str(s.get("name", ""))), None)
    body = str((verify or {}).get("run", ""))
    check("workflow: fails when the tag != v<__version__>",
          verify is not None and '"v$VER"' in body and "exit 1" in body
          and "inputs.tag" in str(verify.get("env", {})))
    idx_verify = steps.index(verify) if verify in steps else 99
    idx_build = next((i for i, s in enumerate(steps) if "pyinstaller" in str(s.get("run", ""))), -1)
    check("workflow: the tag check runs before the build", idx_verify < idx_build)
    tests = next((s for s in steps if "tests/" in str(s.get("run", ""))), {})
    run = str(tests.get("run", ""))
    # Suites are passed to tests/run_suite.py by name ("page_organizer") —
    # accept either that or the file name.
    for t in ("page_organizer", "low_resource", "spec_parity", "ocr_images", "ocr_rerun",
              "docs_sync", "selftest_mode", "options_layout"):
        check(f"workflow: runs the {t} suite on macOS",
              re.search(rf"\b{t}(_test\.py)?\b", run) is not None)
    check("workflow: suites go through run_suite.py (timeouts, isolated settings)",
          "tests/run_suite.py" in run)
    selftest = next((s for s in steps if "--selftest" in str(s.get("run", ""))), None)
    idx_self = steps.index(selftest) if selftest in steps else 99
    idx_dmg = next((i for i, s in enumerate(steps) if "hdiutil" in str(s.get("run", ""))), -1)
    check("workflow: the built .app runs its --selftest before the .dmg is made",
          selftest is not None and idx_build < idx_self < idx_dmg)
    check("workflow: a failed self-test fails the build",
          selftest is not None and "exit 1" in str(selftest.get("run", "")))


def test_ps_parse() -> None:
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        print("[SKIP] PowerShell not available - parse check skipped")
        return
    for f in ("build.ps1", "release.ps1", "publish.ps1"):
        path = str(BUILD / f).replace("'", "''")
        cmd = ("$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::"
               f"ParseFile('{path}',[ref]$t,[ref]$e);"
               "foreach($x in $e){Write-Output ($x.Extent.StartLineNumber.ToString()+': '+$x.Message)};"
               "exit $e.Count")
        r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=60)
        check(f"{f} parses without errors", r.returncode == 0,
              (r.stdout + r.stderr).strip())


def main() -> int:
    test_build_ps1()
    test_release_scripts()
    test_onefile_spec()
    test_installer_iss()
    test_no_control_characters()
    test_macos_workflow()
    test_ps_parse()
    print()
    if failures:
        print(f"{len(failures)} build-script check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All build-script checks passed.")
    return 0


if __name__ == "__main__":
    _rc = main()
    import os as _os
    sys.stdout.flush(); sys.stderr.flush()
    _os._exit(_rc if isinstance(_rc, int) else 0)
