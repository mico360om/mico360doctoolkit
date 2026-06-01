<#
    Cut a GitHub release for MICO360 Doc Toolkit — this *is* the auto-update
    "manifest". The app's updater.py reads the repo's latest release: the tag is
    the version, the body is the release notes, and the assets are the installer
    plus a .sha256 sidecar that the app verifies after downloading.

    Usage (from the project root):
        powershell -ExecutionPolicy Bypass -File build\release.ps1

    What it does:
      1. Builds the app + installer (delegates to build\build.ps1).
      2. Computes the installer's SHA-256 into <installer>.sha256.
      3. If the GitHub CLI (gh) is authenticated, creates/updates the release
         "vX.Y.Z" and uploads the installer + sidecar. Otherwise prints the exact
         manual steps.

    The tag MUST be v<version> so updater.is_newer() compares correctly.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# --- read version from mico360/__init__.py -------------------------------
$initPath = Join-Path $Root "mico360\__init__.py"
$verLine = Select-String -Path $initPath -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $verLine) { throw "Could not find __version__ in $initPath" }
$Version = $verLine.Matches[0].Groups[1].Value
$Tag = "v$Version"
Write-Host "Releasing $Tag" -ForegroundColor Cyan

# --- 1. build ------------------------------------------------------------
Write-Host "Building app + installer..." -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File (Join-Path $Root "build\build.ps1")
if ($LASTEXITCODE -ne 0) { throw "build.ps1 failed (exit $LASTEXITCODE)" }

$Installer = Join-Path $Root "dist\installer\MICO360-DocToolkit-Setup-$Version.exe"
if (-not (Test-Path $Installer)) {
    throw "Installer not found at $Installer. Is Inno Setup (iscc) installed?"
}

# --- 2. sha256 sidecar ---------------------------------------------------
Write-Host "Computing SHA-256..." -ForegroundColor Cyan
$Hash = (Get-FileHash -Algorithm SHA256 -Path $Installer).Hash.ToLower()
$Sidecar = "$Installer.sha256"
# "<hash>  <filename>" — updater reads the first whitespace-delimited token.
"$Hash  $(Split-Path -Leaf $Installer)" | Out-File -FilePath $Sidecar -Encoding ascii -NoNewline
Write-Host "  $Hash" -ForegroundColor DarkGray

# --- 3. publish ----------------------------------------------------------
$notesPath = Join-Path $Root "build\RELEASE_NOTES.md"
$haveNotes = Test-Path $notesPath

$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
    Write-Host "Publishing release via GitHub CLI..." -ForegroundColor Cyan
    $notesArg = if ($haveNotes) { @("--notes-file", $notesPath) } else { @("--generate-notes") }
    # Create the release if it doesn't exist; otherwise just upload assets.
    & gh release view $Tag *> $null
    if ($LASTEXITCODE -ne 0) {
        & gh release create $Tag $Installer $Sidecar --title "$Tag" @notesArg
    } else {
        Write-Host "Release $Tag exists; uploading/replacing assets." -ForegroundColor Yellow
        & gh release upload $Tag $Installer $Sidecar --clobber
    }
    if ($LASTEXITCODE -ne 0) { throw "gh release failed (exit $LASTEXITCODE)" }
    Write-Host "Released $Tag." -ForegroundColor Green
} else {
    Write-Host "GitHub CLI (gh) not found. Do it manually:" -ForegroundColor Yellow
    Write-Host "  1. Install gh from https://cli.github.com and run: gh auth login" -ForegroundColor Yellow
    Write-Host "  2. gh release create $Tag `"$Installer`" `"$Sidecar`" --title $Tag --generate-notes" -ForegroundColor Yellow
    Write-Host "  -- or on github.com: Releases > Draft a new release > tag '$Tag', attach:" -ForegroundColor Yellow
    Write-Host "       $Installer" -ForegroundColor Yellow
    Write-Host "       $Sidecar" -ForegroundColor Yellow
}

Write-Host "Done." -ForegroundColor Green
