<#
    Stage Ghostscript into .\vendor\ghostscript\ so it is bundled into the build
    and used automatically for the best PDF compression.

    Usage (from the project root):
        powershell -ExecutionPolicy Bypass -File build\bundle_ghostscript.ps1

    The app's find_ghostscript() looks for vendor\ghostscript\bin\gswin64c.exe,
    and ALSO auto-detects a normally-installed Ghostscript (C:\Program Files\gs\…)
    — so if you just install Ghostscript the usual way, the app already uses it
    and you don't strictly need to bundle anything.

    This script bundles a copy for a fully self-contained / offline build:
      1. If Ghostscript is installed (Program Files), copy it into vendor\.
      2. Otherwise download the official installer and run it (you approve the
         one-time UAC prompt), then copy it into vendor\.
#>
param(
    [string]$GsUrl = "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10071/gs10071w64.exe"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$vendorGs = Join-Path $Root "vendor\ghostscript"
if (Test-Path (Join-Path $vendorGs "bin\gswin64c.exe")) {
    Write-Host "Ghostscript already staged in vendor\ghostscript." -ForegroundColor Green
    return
}

function Copy-Gs($srcRoot) {
    Write-Host "Copying Ghostscript from $srcRoot ..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force $vendorGs | Out-Null
    foreach ($sub in @("bin", "lib", "Resource", "iccprofiles")) {
        $s = Join-Path $srcRoot $sub
        if (Test-Path $s) { robocopy $s (Join-Path $vendorGs $sub) /E /NFL /NDL /NJH /NJS /NP | Out-Null }
    }
}

# 1. Use an installed Ghostscript if present.
$installed = Get-ChildItem "C:\Program Files\gs" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "bin\gswin64c.exe") } |
    Sort-Object Name -Descending | Select-Object -First 1
if ($installed) {
    Copy-Gs $installed.FullName
} else {
    # 2. Download + run the official installer (needs your UAC approval, once).
    $setup = Join-Path $env:TEMP "gs_setup.exe"
    if (-not (Test-Path $setup) -or (Get-Item $setup).Length -lt 20MB) {
        Write-Host "Downloading Ghostscript installer..." -ForegroundColor Cyan
        curl.exe -L --retry 10 -C - -o $setup $GsUrl
    }
    Write-Host "Running the Ghostscript installer (approve the UAC prompt)..." -ForegroundColor Yellow
    $p = Start-Process $setup -ArgumentList "/S" -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Ghostscript installer exited $($p.ExitCode)." }
    $installed = Get-ChildItem "C:\Program Files\gs" -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "bin\gswin64c.exe") } |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $installed) { throw "Ghostscript not found after install." }
    Copy-Gs $installed.FullName
}

if (Test-Path (Join-Path $vendorGs "bin\gswin64c.exe")) {
    Write-Host "Ghostscript staged into vendor\ghostscript. Rebuild to bundle it." -ForegroundColor Green
} else {
    throw "Staging failed."
}
