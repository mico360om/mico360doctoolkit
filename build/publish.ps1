<#
    Publish the current version as a GitHub Release, using artifacts that are
    ALREADY built under dist\ (does NOT rebuild). Run build\build.ps1 first if
    the installer doesn't exist yet.

    Usage (from the project root):
        powershell -ExecutionPolicy Bypass -File build\publish.ps1

    It authenticates the GitHub CLI in your browser if needed, then creates the
    release tagged vX.Y.Z and uploads the Setup .exe, its .sha256 sidecar, and
    the portable one-file .exe.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Portable gh installed earlier; fall back to gh on PATH.
$Gh = Join-Path $env:LOCALAPPDATA "gh-cli\bin\gh.exe"
if (-not (Test-Path $Gh)) {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) { $Gh = $cmd.Source } else { throw "gh.exe not found. Install GitHub CLI." }
}

# Version from mico360/__init__.py
$verLine = Select-String -Path (Join-Path $Root "mico360\__init__.py") -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
$Version = $verLine.Matches[0].Groups[1].Value
$Tag = "v$Version"

$Installer = Join-Path $Root "dist\installer\MICO360-DocToolkit-Setup-$Version.exe"
$Sidecar   = "$Installer.sha256"
$Onefile   = Join-Path $Root "dist\onefile\MICO360DocToolkit.exe"
$Notes     = Join-Path $Root "build\RELEASE_NOTES.md"
if (-not (Test-Path $Installer)) { throw "Installer not found: $Installer. Run build\build.ps1 first." }
if (-not (Test-Path $Sidecar)) {
    (Get-FileHash -Algorithm SHA256 $Installer).Hash.ToLower() + "  " + (Split-Path -Leaf $Installer) |
        Out-File -FilePath $Sidecar -Encoding ascii -NoNewline
}

# Authenticate if needed (opens your browser).
& $Gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Authenticating GitHub CLI (a browser window will open)..." -ForegroundColor Cyan
    & $Gh auth login --hostname github.com --git-protocol https --web
    if ($LASTEXITCODE -ne 0) { throw "gh auth login failed/cancelled." }
}

$assets = @($Installer, $Sidecar)
if (Test-Path $Onefile) { $assets += $Onefile }

& $Gh release view $Tag *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating release $Tag..." -ForegroundColor Cyan
    $notesArg = if (Test-Path $Notes) { @("--notes-file", $Notes) } else { @("--generate-notes") }
    & $Gh release create $Tag @assets --title $Tag @notesArg
} else {
    Write-Host "Release $Tag exists; uploading/replacing assets..." -ForegroundColor Yellow
    & $Gh release upload $Tag @assets --clobber
}
if ($LASTEXITCODE -ne 0) { throw "gh release failed (exit $LASTEXITCODE)" }

Write-Host "Published $Tag:" -ForegroundColor Green
& $Gh release view $Tag --web
