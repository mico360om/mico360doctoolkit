<#
    Cut a GitHub release for MICO360 Doc Toolkit — this *is* the auto-update
    "manifest". The app's updater.py reads the repo's latest release: the tag is
    the version, the body is the release notes, and the assets are the installer
    plus a .sha256 sidecar that the app verifies after downloading.

    Usage (from the project root):
        powershell -ExecutionPolicy Bypass -File build\release.ps1

    What it does:
      1. Builds the app + installer (delegates to build\build.ps1).
      2. Computes the installer's SHA-256 into <installer>.sha256, and refreshes
         the stable MICO360-DocToolkit-Setup-Latest.exe copy + its .sha256.
      3. If the GitHub CLI (gh) is authenticated, creates/updates the release
         "vX.Y.Z" and uploads all four Windows assets (versioned installer +
         sidecar, Setup-Latest.exe + sidecar). Otherwise prints the exact
         manual steps.

    The -Latest copy is what the README "direct download" link and the
    updater's API-free fallback (releases/latest/download/...) point at, so it
    must ship with every release.

    The tag MUST be v<version> so updater.is_newer() compares correctly.
#>
param(
    # Skip the pre-release test gate (e.g. re-uploading assets for a build that
    # already passed). The full suite is still the expectation before a release.
    [switch]$SkipTests
)
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

# --- 0. test gate --------------------------------------------------------
# Same idea as the macOS CI: a quick, deterministic slice of the suite must be
# green before anything is built or published. (-SkipTests to bypass.)
if (-not $SkipTests) {
    $gate = @(
        "tests\smoke_test.py",
        "tests\feature_audit_test.py",
        "tests\cross_platform_test.py",
        "tests\spec_parity_test.py",
        "tests\icons_test.py",
        "tests\responsive_dpi_test.py",
        "tests\single_instance_test.py",
        "tests\download_resume_test.py",
        "tests\help_legal_test.py",
        "tests\docs_sync_test.py"         # release notes / Help / Terms / Privacy in sync
    )
    Write-Host "Running pre-release test gate ($($gate.Count) suites)..." -ForegroundColor Cyan
    # run_suite.py gives each suite a timeout and a throw-away settings file,
    # so the gate never rewrites the developer's real DocToolkit.ini.
    $names = $gate | ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_) }
    & python (Join-Path $Root "tests\run_suite.py") --timeout 600 @names
    if ($LASTEXITCODE -ne 0) {
        throw "Test gate failed (exit $LASTEXITCODE). Fix it or re-run with -SkipTests."
    }
    Write-Host "Test gate passed." -ForegroundColor Green
}

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

# Stable, version-less copy (+ sidecar) — always re-derived from THIS build's
# installer so it can never lag behind or point at a previous version.
$LatestName = "MICO360-DocToolkit-Setup-Latest.exe"
$Latest = Join-Path (Split-Path -Parent $Installer) $LatestName
Copy-Item -LiteralPath $Installer -Destination $Latest -Force
$LatestHash = (Get-FileHash -Algorithm SHA256 -Path $Latest).Hash.ToLower()
if ($LatestHash -ne $Hash) { throw "Setup-Latest.exe does not match the $Version installer" }
$LatestSidecar = "$Latest.sha256"
"$LatestHash  $LatestName" | Out-File -FilePath $LatestSidecar -Encoding ascii -NoNewline
$Assets = @($Installer, $Sidecar, $Latest, $LatestSidecar)
foreach ($f in $Assets) {
    if (-not (Test-Path -LiteralPath $f)) { throw "Release asset missing: $f" }
}

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
        & gh release create $Tag @Assets --title "$Tag" @notesArg
    } else {
        Write-Host "Release $Tag exists; uploading/replacing assets." -ForegroundColor Yellow
        & gh release upload $Tag @Assets --clobber
    }
    if ($LASTEXITCODE -ne 0) { throw "gh release failed (exit $LASTEXITCODE)" }
    Write-Host "Released $Tag." -ForegroundColor Green
} else {
    Write-Host "GitHub CLI (gh) not found. Do it manually:" -ForegroundColor Yellow
    Write-Host "  1. Install gh from https://cli.github.com and run: gh auth login" -ForegroundColor Yellow
    Write-Host "  2. gh release create $Tag `"$Installer`" `"$Sidecar`" `"$Latest`" `"$LatestSidecar`" --title $Tag --generate-notes" -ForegroundColor Yellow
    Write-Host "  -- or on github.com: Releases > Draft a new release > tag '$Tag', attach:" -ForegroundColor Yellow
    foreach ($f in $Assets) { Write-Host "       $f" -ForegroundColor Yellow }
}

Write-Host "Done." -ForegroundColor Green
