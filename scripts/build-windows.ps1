# Build BattleBuddy.exe (onedir) and, if ISCC.exe exists, BattleBuddy-Setup.exe.
# Build-only: PyInstaller goes in .venv-build. Not a runtime requirement.
# Run on Windows. Does not cross-compile from Linux.

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    Write-Error "Build the Windows exe on Windows. This script does not cross-compile."
    exit 1
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Invoke-HostPython {
    param([string[]]$PythonArgs)
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python @PythonArgs
        if ($LASTEXITCODE -ne 0) { throw "python failed: $PythonArgs" }
        return
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @PythonArgs
        if ($LASTEXITCODE -ne 0) { throw "py -3 failed: $PythonArgs" }
        return
    }
    throw "Python 3.10+ not found. Need it to create .venv-build only."
}

$VenvDir = Join-Path $RepoRoot ".venv-build"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating .venv-build (build-only)."
    Invoke-HostPython -PythonArgs @("-m", "venv", "$VenvDir")
}

Write-Host "Installing PyInstaller into .venv-build (not a runtime dep)."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $VenvPython -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed. Build-only; not added to requirements.txt." }

Write-Host "Building windowed onedir BattleBuddy.exe."
& $VenvPython -m PyInstaller --noconfirm --clean (Join-Path $RepoRoot "BattleBuddy.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$ExePath = Join-Path $RepoRoot "dist\BattleBuddy\BattleBuddy.exe"
if (-not (Test-Path $ExePath)) {
    throw "Build finished but $ExePath is missing."
}
Write-Host "Built $ExePath"

function Find-ISCC {
    $onPath = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    return $null
}

$Iscc = Find-ISCC
if (-not $Iscc) {
    Write-Host "ISCC.exe not found. Skipping installer. Exe is in dist\BattleBuddy\."
    exit 0
}

$Version = & $VenvPython -c "from battlebuddy import __version__; print(__version__)"
$Iss = Join-Path $RepoRoot "installer\BattleBuddy.iss"
Write-Host "Compiling per-user installer (no admin) version $Version."
& $Iscc "/DMyAppVersion=$Version" $Iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed." }

$Setup = Join-Path $RepoRoot "dist\BattleBuddy-Setup.exe"
if (-not (Test-Path $Setup)) {
    throw "ISCC finished but $Setup is missing."
}
Write-Host "Built $Setup"
