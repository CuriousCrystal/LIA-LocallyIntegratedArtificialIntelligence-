# Builds Lia into a standalone Windows app.
#
#   powershell -ExecutionPolicy Bypass -File LIA\build_exe.ps1
#
# Produces dist\Lia\Lia.exe -- double-clickable, no console, no Python needed on
# the machine. Ollama still has to be installed and running; the language model
# is far too large to bundle.
#
# Builds into a staging folder first and swaps at the end. Lia is usually
# installed in Startup, so a half-written dist\Lia is something Windows will
# happily try to launch -- which fails with "Failed to import encodings module".
# The live app stays untouched until the new one is complete.

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$dist    = Join-Path $root 'dist\Lia'
$staging = Join-Path $root 'dist\_staging'

Write-Host "Building Lia (the running app stays up until this succeeds)..." -ForegroundColor Cyan

if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }

$pyinstaller = @(
    '-m', 'PyInstaller',
    '--noconfirm',
    '--clean',
    '--windowed',                       # no console window
    '--name', 'Lia',
    '--distpath', $staging,
    '--workpath', (Join-Path $root 'build'),
    '--collect-all', 'piper',           # includes espeak-ng-data
    '--collect-all', 'pysilero_vad',    # includes the VAD onnx model
    '--collect-all', 'faster_whisper',
    '--collect-all', 'onnxruntime',
    '--collect-all', 'ctranslate2',
    '--collect-all', 'sounddevice',
    '--collect-all', 'soundfile',
    '--collect-all', 'winsdk',          # Windows media control (SMTC)
    '--collect-all', 'pycaw',           # system volume control (Core Audio)
    '--hidden-import', 'pystray._win32',
    '--hidden-import', 'comtypes',
    '--paths', 'LIA',
    'LIA\app.py'
)

& python @pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed -- the existing app is untouched" }

$new = Join-Path $staging 'Lia'
if (-not (Test-Path (Join-Path $new 'Lia.exe'))) {
    throw "Build produced no Lia.exe -- the existing app is untouched"
}

# Voices live beside the exe so you can drop your own in without rebuilding.
$voicesSrc = Join-Path $PSScriptRoot 'voices'
if (Test-Path $voicesSrc) { Copy-Item $voicesSrc (Join-Path $new 'voices') -Recurse -Force }

# Carry across whatever the live app already had, so nothing you've added or
# said is lost in the swap.
foreach ($keep in @('library', 'lia_memory.db')) {
    $existing = Join-Path $dist $keep
    $seed     = Join-Path $PSScriptRoot $keep
    $rootSeed = Join-Path $root $keep
    if (Test-Path $existing)      { Copy-Item $existing (Join-Path $new $keep) -Recurse -Force }
    elseif (Test-Path $seed)      { Copy-Item $seed     (Join-Path $new $keep) -Recurse -Force }
    elseif (Test-Path $rootSeed)  { Copy-Item $rootSeed (Join-Path $new $keep) -Recurse -Force }
}

# --- swap: this is the only moment the app is unavailable ---

$running = Get-Process Lia -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "Stopping the running Lia to swap it..." -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Seconds 3
}

if (Test-Path $dist) {
    $freed = $false
    foreach ($attempt in 1..8) {
        try { Remove-Item $dist -Recurse -Force -ErrorAction Stop; $freed = $true; break }
        catch {
            if ($attempt -eq 1) {
                # Ollama's workers get launched as children of the app and
                # inherit its folder, holding handles inside it.
                Write-Host "Folder locked -- stopping Ollama workers..." -ForegroundColor Yellow
                Get-Process llama-server, ollama -ErrorAction SilentlyContinue | Stop-Process -Force
            }
            Start-Sleep -Seconds 4
        }
    }
    if (-not $freed) {
        Write-Host "Could not replace dist\Lia -- the new build is waiting in dist\_staging\Lia" -ForegroundColor Red
        exit 1
    }
}

Move-Item $new $dist
Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  $dist\Lia.exe"
Write-Host ""
Write-Host "Add to startup with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install -Exe"
