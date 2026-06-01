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
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Keep the build venv outside any cloud-synced folder to avoid file locks.
$Venv = Join-Path $env:LOCALAPPDATA "mico360-build-venv"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "Creating build venv at $Venv" -ForegroundColor Cyan
    py -3 -m venv $Venv
}

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $Py -m pip install --upgrade pip
& $Py -m pip install -r requirements.txt
& $Py -m pip install pyinstaller

Write-Host "Generating icon..." -ForegroundColor Cyan
& $Py build\make_icon.py

Write-Host "Running smoke test..." -ForegroundColor Cyan
$env:QT_QPA_PLATFORM = "offscreen"
& $Py tests\smoke_test.py
Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue

Write-Host "Building with PyInstaller..." -ForegroundColor Cyan
& $Py -m PyInstaller build\mico360.spec --noconfirm --distpath dist --workpath build\_work

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($iscc) {
    Write-Host "Compiling installer with Inno Setup..." -ForegroundColor Cyan
    & $iscc.Source build\installer.iss
    Write-Host "Installer written to dist\installer\" -ForegroundColor Green
} else {
    Write-Host "Inno Setup (iscc) not found on PATH - skipping installer step." -ForegroundColor Yellow
    Write-Host "Install from https://jrsoftware.org/isdl.php then run: iscc build\installer.iss" -ForegroundColor Yellow
}

Write-Host "Done. App: dist\MICO360DocToolkit\MICO360DocToolkit.exe" -ForegroundColor Green
