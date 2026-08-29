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

# Tiny CPU LLM rides next to the exe. Not in git. Not in the PYZ.
# Preferred: SmolLM2-360M-Instruct Q4_K_M (Apache-2.0, ~360M).
# Alternate: Qwen2.5-0.5B-Instruct Q4_K_M (Apache-2.0) if the preferred file 404s.
$LlamaZipUrl = "https://github.com/ggml-org/llama.cpp/releases/download/b10621/llama-b10621-bin-win-cpu-x64.zip"
$LlamaZipSha256 = "0e8b65e650e369f70f8307d890508886f171ef4fb00facccddd4a1b7ffdaca51"
$GgufUrl = "https://huggingface.co/unsloth/SmolLM2-360M-Instruct-GGUF/resolve/391ed11137586e383b1be0fab9acf01d282c2e11/SmolLM2-360M-Instruct-Q4_K_M.gguf"
$GgufSha256 = "16c7f1667fea34bacad196a57b548effcb37614db4ab5677a20c8c7b823b9e63"
$GgufName = "SmolLM2-360M-Instruct-Q4_K_M.gguf"
$GgufAltUrl = "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf"
$GgufAltSha256 = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
$GgufAltName = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
$LlmDir = Join-Path $RepoRoot "dist\BattleBuddy\llm"
$CacheDir = Join-Path $RepoRoot ".llm-cache"

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

function Save-PinnedFile {
    param(
        [string]$Url,
        [string]$Sha256,
        [string]$OutFile
    )
    $want = $Sha256.ToLowerInvariant()
    if ((Test-Path $OutFile) -and ((Get-FileSha256 $OutFile) -eq $want)) {
        Write-Host "Cached $OutFile"
        return
    }
    $parent = Split-Path $OutFile -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -Headers @{
        "User-Agent" = "BattleBuddy-build (local; no account)"
    }
    $got = Get-FileSha256 $OutFile
    if ($got -ne $want) {
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
        throw "SHA256 mismatch for $OutFile. got $got expected $want"
    }
}

function Install-BundledLlm {
    New-Item -ItemType Directory -Force -Path $LlmDir | Out-Null
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    $zipPath = Join-Path $CacheDir "llama-b10621-bin-win-cpu-x64.zip"
    Save-PinnedFile -Url $LlamaZipUrl -Sha256 $LlamaZipSha256 -OutFile $zipPath
    $unzip = Join-Path $CacheDir "llama-b10621-win-cpu-x64"
    if (Test-Path $unzip) {
        Remove-Item $unzip -Recurse -Force
    }
    Expand-Archive -Path $zipPath -DestinationPath $unzip -Force
    $server = Get-ChildItem -Path $unzip -Recurse -Filter "llama-server.exe" | Select-Object -First 1
    if (-not $server) {
        throw "llama-server.exe missing from llama.cpp zip."
    }
    Copy-Item -Path (Join-Path $server.Directory.FullName "*") -Destination $LlmDir -Recurse -Force
    $ggufPath = Join-Path $CacheDir $GgufName
    try {
        Save-PinnedFile -Url $GgufUrl -Sha256 $GgufSha256 -OutFile $ggufPath
        Copy-Item $ggufPath (Join-Path $LlmDir $GgufName) -Force
    } catch {
        Write-Host "Preferred SmolLM2 GGUF failed. Trying Qwen2.5-0.5B alternate."
        $altPath = Join-Path $CacheDir $GgufAltName
        Save-PinnedFile -Url $GgufAltUrl -Sha256 $GgufAltSha256 -OutFile $altPath
        Copy-Item $altPath (Join-Path $LlmDir $GgufAltName) -Force
    }
    if (-not (Test-Path (Join-Path $LlmDir "llama-server.exe"))) {
        throw "llama-server.exe did not land in dist\BattleBuddy\llm."
    }
    Write-Host "Bundled CPU LLM ready in $LlmDir"
}

try {
    Install-BundledLlm
} catch {
    Write-Host "Bundled LLM skipped. ASK still prints the recipe. $_"
}

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
