# Adds or removes Lia from Windows startup, so she's already there when you
# open your laptop.
#
#   powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install
#   powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 remove
#   powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 status
#
# Installs the tray app by default (no window at all). Use -Console to start her
# in a terminal instead, if you want to type to her as well as talk.

param(
    [ValidateSet('install', 'remove', 'status')]
    [string]$Action = 'status',

    [switch]$Console,

    [switch]$Exe
)

$startup  = [Environment]::GetFolderPath('Startup')
$linkPath = Join-Path $startup 'Lia.lnk'
$root     = Split-Path $PSScriptRoot -Parent

function Get-Pythonw {
    # pythonw.exe runs without opening a console window.
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { return $null }
    $candidate = Join-Path (Split-Path $python -Parent) 'pythonw.exe'
    if (Test-Path $candidate) { return $candidate }
    return $null
}

switch ($Action) {
    'install' {
        $shell = New-Object -ComObject WScript.Shell
        $link  = $shell.CreateShortcut($linkPath)

        if ($Exe) {
            # NB: not $exe -- PowerShell variable names are case-insensitive, so
            # that would collide with the -Exe switch parameter above.
            $exePath = Join-Path $root 'dist\Lia\Lia.exe'
            if (-not (Test-Path $exePath)) {
                Write-Host "Cannot find $exePath" -ForegroundColor Red
                Write-Host "Build it first: powershell -ExecutionPolicy Bypass -File LIA\build_exe.ps1"
                exit 1
            }
            $link.TargetPath       = $exePath
            $link.WorkingDirectory = Split-Path $exePath -Parent
            $mode = 'packaged app (Lia.exe)'
        }
        elseif ($Console) {
            $bat = Join-Path $PSScriptRoot 'start_lia.bat'
            if (-not (Test-Path $bat)) {
                Write-Host "Cannot find $bat" -ForegroundColor Red
                exit 1
            }
            $link.TargetPath = $bat
            $mode = 'console'
        }
        else {
            $pythonw = Get-Pythonw
            if (-not $pythonw) {
                Write-Host "Could not find pythonw.exe next to python.exe." -ForegroundColor Red
                Write-Host "Re-run with -Console to install the terminal version instead."
                exit 1
            }
            $link.TargetPath  = $pythonw
            $link.Arguments   = '"' + (Join-Path $PSScriptRoot 'app.py') + '"'
            $link.WindowStyle = 7            # minimised, no console
            $mode = 'tray app (no window)'
        }

        if (-not $link.WorkingDirectory) { $link.WorkingDirectory = $root }
        $link.Description = 'Lia - local companion'
        $link.Save()

        Write-Host "Installed as $mode." -ForegroundColor Green
        Write-Host "  $linkPath"
        Write-Host "She'll start automatically the next time you log in."
    }

    'remove' {
        if (Test-Path $linkPath) {
            Remove-Item $linkPath -Force
            Write-Host "Removed. Lia will no longer start automatically." -ForegroundColor Green
        }
        else {
            Write-Host "Nothing to remove -- autostart isn't installed."
        }
    }

    'status' {
        if (Test-Path $linkPath) {
            $shell = New-Object -ComObject WScript.Shell
            $link = $shell.CreateShortcut($linkPath)
            Write-Host "Autostart is ON" -ForegroundColor Green
            Write-Host "  target: $($link.TargetPath) $($link.Arguments)"
        }
        else {
            Write-Host "Autostart is OFF. Run with 'install' to turn it on."
        }
    }
}
