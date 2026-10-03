<#
    Build MICO360 Doc Toolkit into a distributable app + installer.

    Usage (from the project root):
        powershell -ExecutionPolicy Bypass -File build\build.ps1

    Steps:
      1. Create / reuse a build virtual environment.
      2. Install runtime + build dependencies.
      3. Generate the application icon.
      4. Run PyInstaller (onedir) -> dist\MICO360DocToolkit\
      5. If Inno Setup (iscc) is on PATH, compile the installer.

    Place portable Ghostscript and LibreOffice under .\vendor first if you want
    them bundled (see vendor\README.md).
#>
$ErrorActionPreference = "Stop"
# NOTE: "Stop" does NOT apply to native commands (python, pip, iscc) in Windows
# PowerShell 5.1 — each native call below is followed by an explicit
# $LASTEXITCODE check, so a failed step can never fall through and repackage a
# stale build as the new version.
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Keep the build venv outside any cloud-synced folder to avoid file locks.
$Venv = Join-Path $env:LOCALAPPDATA "mico360-build-venv"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "Creating build venv at $Venv" -ForegroundColor Cyan
    py -3 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Creating the build venv failed (exit $LASTEXITCODE)" }
}

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $Py -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip self-upgrade failed (exit $LASTEXITCODE)" }
& $Py -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed (exit $LASTEXITCODE)" }
& $Py -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed (exit $LASTEXITCODE)" }

# GPU OCR: swap the CPU onnxruntime that rapidocr pulled for the DirectML build,
# so OCR can run on ANY Direct3D-12 GPU (NVIDIA/AMD/Intel) with CPU fallback.
# DirectML is Windows-only; this whole script is Windows, so it always applies.
Write-Host "Enabling GPU OCR (onnxruntime-directml)..." -ForegroundColor Cyan
# pip writes "not installed" warnings to stderr; under "Stop" Windows PowerShell
# 5.1 turns redirected native stderr into a terminating error. Relax the
# preference for this one best-effort line and ignore its exit code.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & $Py -m pip uninstall -y onnxruntime onnxruntime-directml 2>$null | Out-Null
} finally {
    $ErrorActionPreference = $prevEap
}
& $Py -m pip install "onnxruntime-directml>=1.17"
if ($LASTEXITCODE -ne 0) { throw "pip install onnxruntime-directml failed (exit $LASTEXITCODE)" }
& $Py -c "import onnxruntime as o; print('  onnxruntime providers:', o.get_available_providers())"
if ($LASTEXITCODE -ne 0) { throw "onnxruntime import check failed (exit $LASTEXITCODE)" }

Write-Host "Generating icon..." -ForegroundColor Cyan
& $Py build\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "make_icon.py failed (exit $LASTEXITCODE)" }

Write-Host "Generating per-tool right-click menu icons..." -ForegroundColor Cyan
& $Py build\make_menu_icons.py
if ($LASTEXITCODE -ne 0) { throw "make_menu_icons.py failed (exit $LASTEXITCODE)" }

Write-Host "Running smoke test..." -ForegroundColor Cyan
$env:QT_QPA_PLATFORM = "offscreen"
# A throw-away settings file, so the build never rewrites the real DocToolkit.ini.
$env:MICO360_SETTINGS_FILE = Join-Path $env:TEMP ("mico360_build_" + [guid]::NewGuid().ToString("N") + ".ini")
& $Py tests\smoke_test.py
$smokeExit = $LASTEXITCODE
Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $env:MICO360_SETTINGS_FILE -ErrorAction SilentlyContinue
Remove-Item Env:\MICO360_SETTINGS_FILE -ErrorAction SilentlyContinue
if ($smokeExit -ne 0) { throw "Smoke test failed (exit $smokeExit)" }

# Remove the previous app first, so a failed PyInstaller run can never leave the
# old build in place to be repackaged (and published) as the new version.
$DistApp = Join-Path $Root "dist\MICO360DocToolkit"
if (Test-Path $DistApp) {
    Write-Host "Removing previous build at $DistApp" -ForegroundColor DarkGray
    # Dropbox/antivirus can hold a file for a moment while syncing/scanning the
    # previous build: retry a few times instead of failing the whole build.
    for ($try = 1; $try -le 6; $try++) {
        try {
            Remove-Item -LiteralPath $DistApp -Recurse -Force -ErrorAction Stop
            break
        } catch {
            if ($try -eq 6) { throw "Couldn't remove the previous build at $DistApp (a file is locked): $_" }
            Write-Host "  previous build is still locked (sync/scan) - retrying in 5 s..." -ForegroundColor DarkGray
            Start-Sleep -Seconds 5
        }
    }
}

# The System AI key is built in from build\system_ai.key or the
# MICO360_SYSTEM_AI_KEY environment variable (never from the source code).
Write-Host "Building in the System AI key..." -ForegroundColor Cyan
& $Py build\write_build_secrets.py
if ($LASTEXITCODE -ne 0) { throw "write_build_secrets.py failed (exit $LASTEXITCODE)" }

Write-Host "Building with PyInstaller..." -ForegroundColor Cyan
# PyInstaller's scratch folder lives OUTSIDE the project: inside a cloud-synced
# folder the half-built .exe gets locked by the sync client / antivirus, and
# embedding its manifest then fails (it once succeeded on the last of 20 tries).
$Work = Join-Path $env:LOCALAPPDATA "mico360-build-work"
& $Py -m PyInstaller build\mico360.spec --noconfirm --distpath dist --workpath $Work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }
if (-not (Test-Path (Join-Path $DistApp "MICO360DocToolkit.exe"))) {
    throw "PyInstaller reported success but $DistApp\MICO360DocToolkit.exe is missing"
}

# Inno Setup: PATH first, then the standard per-user / per-machine locations
# (a per-user install isn't added to PATH).
$isccPath = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $isccPath) {
    $isccPath = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if ($isccPath) {
    Write-Host "Compiling installer with Inno Setup ($isccPath)..." -ForegroundColor Cyan
    & $isccPath build\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup (iscc) failed (exit $LASTEXITCODE)" }
    Write-Host "Installer written to dist\installer\" -ForegroundColor Green

    # Emit a stable, version-less copy (+ .sha256) so the README "direct
    # download" link (releases/latest/download/...-Setup-Latest.exe) and the
    # auto-updater both keep working across versions.
    $built = Get-ChildItem dist\installer\MICO360-DocToolkit-Setup-*.exe -Exclude *Latest* -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime | Select-Object -Last 1
    if ($built) {
        $latest = Join-Path $built.DirectoryName "MICO360-DocToolkit-Setup-Latest.exe"
        Copy-Item $built.FullName $latest -Force
        $hash = (Get-FileHash $latest -Algorithm SHA256).Hash.ToLower()
        "$hash  MICO360-DocToolkit-Setup-Latest.exe" |
            Out-File "$latest.sha256" -Encoding ascii -NoNewline
        # Also write the versioned .sha256 the updater verifies against.
        $vhash = (Get-FileHash $built.FullName -Algorithm SHA256).Hash.ToLower()
        "$vhash  $($built.Name)" |
            Out-File "$($built.FullName).sha256" -Encoding ascii -NoNewline
        Write-Host "Stable copy: $latest  (sha256 $hash)" -ForegroundColor Green
    }
} else {
    Write-Host "Inno Setup (iscc) not found - skipping installer step." -ForegroundColor Yellow
    Write-Host "Install from https://jrsoftware.org/isdl.php then run: iscc build\installer.iss" -ForegroundColor Yellow
}

Write-Host "Done. App: dist\MICO360DocToolkit\MICO360DocToolkit.exe" -ForegroundColor Green
