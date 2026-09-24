# Builds Lia into a standalone Windows app.
#
#   powershell -ExecutionPolicy Bypass -File LIA\build_exe.ps1
#
# Produces dist\Lia\Lia.exe -- double-clickable, no console, no Python needed
# on the machine. Chat and speech-to-text are local (Ollama + faster-whisper),
# so there is no API key to set -- but Ollama itself is a separate install
# (ollama.com) that has to be running, and its model (config.py's
# LOCAL_CHAT_MODEL) has to be pulled, on whatever machine runs this exe.
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
    '--collect-all', 'onnxruntime',
    '--collect-all', 'sounddevice',
    '--collect-all', 'webview',         # the VRM avatar window
    '--collect-all', 'faster_whisper',
    '--collect-all', 'ctranslate2',     # faster-whisper's native inference engine
    '--collect-all', 'av',              # faster-whisper's audio decoding
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

# Voices, the avatar's renderer, the tray/window icon source and your notes
# folder all live beside the exe so you can drop in your own without
# rebuilding.
foreach ($folder in @('voices', 'vrm', 'assets', 'notes')) {
    $src = Join-Path $PSScriptRoot $folder
    if (Test-Path $src) { Copy-Item $src (Join-Path $new $folder) -Recurse -Force }
}

# Carry across whatever the live app already had (her log, the avatar
# position). Nothing else persists -- there is no database.
foreach ($keep in @('lia.log', 'vrm_pos.json')) {
    $existing = Join-Path $dist $keep
    $rootSeed = Join-Path $root $keep
    if (Test-Path $existing) { Copy-Item $existing (Join-Path $new $keep) -Force }
    elseif (Test-Path $rootSeed) { Copy-Item $rootSeed (Join-Path $new $keep) -Force }
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
            # Most common cause: the running Lia.exe still holds the folder
            # (antivirus scanning new files can hold it briefly too).
            if ($attempt -eq 1) {
                Write-Host "Folder locked -- is Lia still running or scanning?" -ForegroundColor Yellow
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
