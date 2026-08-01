# Builds Lia into a standalone Windows app.
#
#   powershell -ExecutionPolicy Bypass -File LIA\build_exe.ps1
#
# Produces dist\Lia\Lia.exe -- double-clickable, no console, no Python needed on
# the machine. Ollama still has to be installed and running; the language model
# is far too large to bundle.
#
# Takes several minutes. onnxruntime, ctranslate2 and Whisper are all big.

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

Write-Host "Building Lia..." -ForegroundColor Cyan

$pyinstaller = @(
    '-m', 'PyInstaller',
    '--noconfirm',
    '--clean',
    '--windowed',                       # no console window
    '--name', 'Lia',
    '--collect-all', 'piper',           # includes espeak-ng-data
    '--collect-all', 'pysilero_vad',    # includes the VAD onnx model
    '--collect-all', 'faster_whisper',
    '--collect-all', 'onnxruntime',
    '--collect-all', 'ctranslate2',
    '--collect-all', 'sounddevice',
    '--collect-all', 'soundfile',
    '--hidden-import', 'pystray._win32',
    '--hidden-import', 'comtypes',
    '--paths', 'LIA',
    'LIA\app.py'
)

& python @pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$dist = Join-Path $root 'dist\Lia'

# Voices live beside the exe so you can still drop your own in without rebuilding.
$voicesSrc = Join-Path $PSScriptRoot 'voices'
$voicesDst = Join-Path $dist 'voices'
if (Test-Path $voicesSrc) {
    Copy-Item $voicesSrc $voicesDst -Recurse -Force
    Write-Host "Copied voices -> $voicesDst"
}

# The library lives beside the exe too, so you can drop new PDFs in without
# rebuilding. Only seeded if it isn't already there -- never overwrite reading
# material you've since added.
$libSrc = Join-Path $PSScriptRoot 'library'
$libDst = Join-Path $dist 'library'
if ((Test-Path $libSrc) -and -not (Test-Path $libDst)) {
    Copy-Item $libSrc $libDst -Recurse -Force
    Write-Host "Copied library -> $libDst"
}

# Bring her memories along if she already has some.
$db = Join-Path $root 'lia_memory.db'
if ((Test-Path $db) -and -not (Test-Path (Join-Path $dist 'lia_memory.db'))) {
    Copy-Item $db $dist
    Write-Host "Copied lia_memory.db -> $dist"
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  $dist\Lia.exe"
Write-Host ""
Write-Host "Add to startup with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install -Exe"
