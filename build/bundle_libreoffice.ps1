<#
    Build MICO360 Doc Toolkit as a FOLDER (onedir) with LibreOffice bundled,
    so Word->PDF has exact fidelity with zero setup on any PC.

    Usage (from the project root):
        powershell -ExecutionPolicy Bypass -File build\bundle_libreoffice.ps1

    What it does:
      1. Stages a LibreOffice into .\vendor\libreoffice\ if not already there:
           - uses an installed LibreOffice (Program Files) if found, else
           - downloads the official MSI and extracts it WITHOUT admin
             (msiexec /a — an "administrative install" just unpacks files).
      2. Runs the onedir PyInstaller build (build\mico360.spec), which bundles
         everything under vendor\ into the app folder.
      3. Output: dist\MICO360DocToolkit\  (run MICO360DocToolkit.exe inside it)

    The app's find_libreoffice() looks for vendor\libreoffice\program\soffice.exe,
    so once staged the bundled copy is used automatically.
#>
param(
    [string]$MsiUrl = "https://download.documentfoundation.org/libreoffice/stable/26.2.3/win/x86_64/LibreOffice_26.2.3_Win_x86-64.msi",
    [string]$DistPath = "dist"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Venv = Join-Path $env:LOCALAPPDATA "mico360-build-venv"
$Py = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Creating build venv at $Venv" -ForegroundColor Cyan
    py -3 -m venv $Venv
    & $Py -m pip install --upgrade pip
    & $Py -m pip install -r requirements.txt pyinstaller
}

$vendorLO = Join-Path $Root "vendor\libreoffice"
$soffice = Join-Path $vendorLO "program\soffice.exe"

if (Test-Path $soffice) {
    Write-Host "LibreOffice already staged in vendor\libreoffice." -ForegroundColor Green
} else {
    # Prefer an already-installed LibreOffice (fast, no download).
    $installed = @(
        "C:\Program Files\LibreOffice",
        "C:\Program Files (x86)\LibreOffice"
    ) | Where-Object { Test-Path (Join-Path $_ "program\soffice.exe") } | Select-Object -First 1

    if ($installed) {
        Write-Host "Copying installed LibreOffice from $installed ..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Force $vendorLO | Out-Null
        robocopy $installed $vendorLO /E /NFL /NDL /NJH /NJS /NP | Out-Null
    } else {
        $msi = Join-Path $env:TEMP "LibreOffice.msi"
        if (-not (Test-Path $msi) -or (Get-Item $msi).Length -lt 200MB) {
            Write-Host "Downloading LibreOffice MSI (~340 MB; resumable)..." -ForegroundColor Cyan
            curl.exe -L --retry 8 --retry-delay 4 -C - -o $msi $MsiUrl
        }
        if ((Get-Item $msi).Length -lt 200MB) {
            throw "LibreOffice MSI download looks incomplete ($([int]((Get-Item $msi).Length/1MB)) MB). Re-run to resume."
        }
        $extract = Join-Path $env:TEMP "LO_extract"
        if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
        New-Item -ItemType Directory -Force $extract | Out-Null
        Write-Host "Extracting MSI (no admin needed)..." -ForegroundColor Cyan
        $p = Start-Process msiexec.exe -ArgumentList @("/a", "`"$msi`"", "/qn", "TARGETDIR=`"$extract`"") -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "msiexec extraction failed (exit $($p.ExitCode))." }
        $found = Get-ChildItem $extract -Recurse -Filter soffice.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $found) { throw "soffice.exe not found after extraction." }
        $loRoot = $found.Directory.Parent.FullName  # ...\LibreOffice (parent of program\)
        Write-Host "Staging LibreOffice from $loRoot ..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Force $vendorLO | Out-Null
        robocopy $loRoot $vendorLO /E /NFL /NDL /NJH /NJS /NP | Out-Null
    }
    if (-not (Test-Path $soffice)) { throw "Staging failed: $soffice not present." }
    Write-Host "LibreOffice staged." -ForegroundColor Green
}

Write-Host "Generating icon..." -ForegroundColor Cyan
& $Py build\make_icon.py

Write-Host "Building onedir app with LibreOffice bundled..." -ForegroundColor Cyan
& $Py -m PyInstaller build\mico360.spec --noconfirm --distpath $DistPath --workpath build\_work
Write-Host "Done. App folder: $DistPath\MICO360DocToolkit\ (run MICO360DocToolkit.exe)" -ForegroundColor Green
