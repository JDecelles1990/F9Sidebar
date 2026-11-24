<#
.SYNOPSIS
    Builds a clean, reproducible portable Windows release of F9Sidebar.

.DESCRIPTION
    1. Validates the local .venv and required runtime + PyInstaller packages.
    2. Cleans previous build/ and dist/ directories.
    3. Ensures assets/f9sidebar.ico exists (generating it if needed).
    4. Runs PyInstaller against packaging/F9Sidebar.spec (--onedir, windowed).
    5. Runs post-build sanity checks (no leaked dev data/, no WebEngine bloat,
       required QtAwesome fonts and app icon present).
    6. Packages dist/F9Sidebar into dist/F9Sidebar-v<Version>-win64.zip.

.PARAMETER Version
    Optional release version override. Defaults to database.APP_VERSION.

.PARAMETER SkipZip
    Build only the dist/F9Sidebar folder without creating the .zip archive.
#>
[CmdletBinding()]
param(
    [string]$Version = "",
    [switch]$SkipZip
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$SpecPath = Join-Path $RepoRoot "packaging\F9Sidebar.spec"
$IconPath = Join-Path $RepoRoot "assets\f9sidebar.ico"
$IconScript = Join-Path $RepoRoot "scripts\generate_icon.py"
$BuildDir = Join-Path $RepoRoot "build"
$DistDir = Join-Path $RepoRoot "dist"
$AppDistDir = Join-Path $DistDir "F9Sidebar"

Write-Host "==> F9Sidebar Windows Release Build" -ForegroundColor Cyan
Write-Host "    Repository : $RepoRoot"

# 1. Verify Python virtual environment and dependencies
if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment Python not found at '$PythonExe'. Create .venv and install requirements.txt first."
}

if (-not (Test-Path $SpecPath)) {
    throw "PyInstaller spec file not found at '$SpecPath'."
}

Write-Host "==> Checking Python runtime and build dependencies..." -ForegroundColor Cyan
$depCheckCode = @'
import sys
import PySide6
import qtawesome
import PyInstaller
import database
print('PYTHON=' + sys.version.split()[0])
print('PYSIDE6=' + PySide6.__version__)
print('QTAWESOME=' + qtawesome.__version__)
print('PYINSTALLER=' + PyInstaller.__version__)
print('APP_VERSION=' + database.APP_VERSION)
'@

Push-Location $RepoRoot
try {
    $depOutput = $depCheckCode | & $PythonExe -
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency check failed. Ensure runtime requirements and packaging/requirements-build.txt are installed in .venv: .\.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt"
    }
} finally {
    Pop-Location
}

$meta = @{}
foreach ($line in $depOutput) {
    if ($line -match '^([A-Z0-9_]+)=(.+)$') {
        $meta[$Matches[1]] = $Matches[2].Trim()
    }
}

$DetectedVersion = $meta["APP_VERSION"]
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = $DetectedVersion
} elseif ($Version -ne $DetectedVersion) {
    Write-Warning "Requested -Version '$Version' differs from database.APP_VERSION '$DetectedVersion'."
}

Write-Host "    Python      : $($meta['PYTHON'])"
Write-Host "    PySide6     : $($meta['PYSIDE6'])"
Write-Host "    QtAwesome   : $($meta['QTAWESOME'])"
Write-Host "    PyInstaller : $($meta['PYINSTALLER'])"
Write-Host "    App Version : $Version"

# 2. Ensure app icon exists
if (-not (Test-Path $IconPath)) {
    Write-Host "==> Generating app icon at $IconPath..." -ForegroundColor Cyan
    $prevQpa = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = "offscreen"
        & $PythonExe $IconScript $IconPath
        if ($LASTEXITCODE -ne 0) {
            throw "Icon generation failed with exit code $LASTEXITCODE."
        }
    } finally {
        if ($null -eq $prevQpa) {
            Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
        } else {
            $env:QT_QPA_PLATFORM = $prevQpa
        }
    }
}

# 3. Clean previous build/ and dist/
Write-Host "==> Cleaning previous build/ and dist/ directories..." -ForegroundColor Cyan
foreach ($dir in @($BuildDir, $DistDir)) {
    if (Test-Path $dir) {
        Remove-Item -LiteralPath $dir -Recurse -Force
    }
}

# 4. Run PyInstaller
Write-Host "==> Running PyInstaller (--onedir, windowed)..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistDir `
    --workpath $BuildDir `
    $SpecPath

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

# 5. Post-build sanity checks
Write-Host "==> Running post-build sanity checks..." -ForegroundColor Cyan
$ExePath = Join-Path $AppDistDir "F9Sidebar.exe"
$InternalDir = Join-Path $AppDistDir "_internal"
$BundledIcon = Join-Path $InternalDir "assets\f9sidebar.ico"
$BundledFontsDir = Join-Path $InternalDir "qtawesome\fonts"
$LeakedDataDir = Join-Path $AppDistDir "data"

if (-not (Test-Path $ExePath)) {
    throw "Expected executable not found at '$ExePath'."
}
if (-not (Test-Path $BundledIcon)) {
    throw "Expected bundled icon not found at '$BundledIcon'."
}
if (-not (Test-Path $BundledFontsDir)) {
    throw "Expected QtAwesome fonts directory not found at '$BundledFontsDir'."
}
$ttfCount = (Get-ChildItem -Path $BundledFontsDir -Filter "*.ttf" -File | Measure-Object).Count
$jsonCount = (Get-ChildItem -Path $BundledFontsDir -Filter "*.json" -File | Measure-Object).Count
if ($ttfCount -eq 0 -or $jsonCount -eq 0) {
    throw "QtAwesome fonts directory is incomplete (ttf=$ttfCount, json=$jsonCount)."
}
if (Test-Path $LeakedDataDir) {
    throw "Dev data/ directory was unexpectedly copied into '$LeakedDataDir'!"
}

$unexpectedDlls = @("Qt6WebEngineCore.dll", "Qt6Pdf.dll", "Qt6Quick.dll", "Qt6Qml.dll")
foreach ($dllName in $unexpectedDlls) {
    $leaked = Get-ChildItem -Path $AppDistDir -Recurse -Filter $dllName -ErrorAction SilentlyContinue
    if ($null -ne $leaked) {
        throw "Unexpected $dllName found in build output — check excludes/pruning in packaging/F9Sidebar.spec."
    }
}

$imageFormatsDir = Join-Path $InternalDir "PySide6\plugins\imageformats"
if (-not (Test-Path $imageFormatsDir)) {
    throw "Expected Qt imageformats plugins directory not found at '$imageFormatsDir'."
}
$missingImgPlugins = @(@("qico.dll", "qjpeg.dll", "qgif.dll", "qwebp.dll", "qsvg.dll") | Where-Object {
    -not (Test-Path (Join-Path $imageFormatsDir $_))
})
if ($missingImgPlugins.Count -gt 0) {
    throw "Missing expected Qt image format plugin(s): $($missingImgPlugins -join ', ')"
}

# 6. Create portable release zip archive (using .NET ZipFile for speed & headless/CI compatibility)
$ZipPath = Join-Path $DistDir "F9Sidebar-v$Version-win64.zip"
if (-not $SkipZip) {
    Write-Host "==> Creating portable archive $ZipPath..." -ForegroundColor Cyan
    if (Test-Path $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $AppDistDir,
        $ZipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $true
    )
    if (-not (Test-Path $ZipPath)) {
        throw "Failed to create archive at '$ZipPath'."
    }
}

# 7. Print build summary
$allFiles = @(Get-ChildItem -Path $AppDistDir -Recurse -File)
$folderBytes = ($allFiles | Measure-Object -Property Length -Sum).Sum
$folderMB = [math]::Round($folderBytes / 1MB, 2)
$exeMB = [math]::Round((Get-Item $ExePath).Length / 1MB, 2)

Write-Host ""
Write-Host "==> Build Succeeded!" -ForegroundColor Green
Write-Host "    Portable Folder : $AppDistDir ($folderMB MB across $($allFiles.Count) files)"
Write-Host "    Executable      : $ExePath ($exeMB MB)"
if (-not $SkipZip) {
    $zipMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
    Write-Host "    Release Archive : $ZipPath ($zipMB MB)"
}
