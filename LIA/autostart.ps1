# Adds or removes Lia from Windows startup, or gives her a Start Menu entry
# you launch by hand instead of a command line.
#
#   powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install
#   powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 remove
#   powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 status
#   powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 pin
#   powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 unpin
#
# Installs the tray app by default (no window at all). Use -Console to start her
# in a terminal instead, if you want to type to her as well as talk. -Exe points
# either shortcut at the packaged dist\Lia\Lia.exe instead of python.

param(
    [ValidateSet('install', 'remove', 'status', 'pin', 'unpin')]
    [string]$Action = 'status',

    [switch]$Console,

    [switch]$Exe
)

$startup    = [Environment]::GetFolderPath('Startup')
$startMenu  = [Environment]::GetFolderPath('Programs')  # per-user Start Menu
$startupLink = Join-Path $startup 'Lia.lnk'
$menuLink    = Join-Path $startMenu 'Lia.lnk'
$root       = Split-Path $PSScriptRoot -Parent

function Get-Pythonw {
    # pythonw.exe runs without opening a console window.
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { return $null }
    $candidate = Join-Path (Split-Path $python -Parent) 'pythonw.exe'
    if (Test-Path $candidate) { return $candidate }
    return $null
}

# Fills in a shortcut's target/arguments/icon for whichever launch mode was
# asked for -- shared by 'install' (Startup) and 'pin' (Start Menu), which
# differ only in *where* the .lnk goes, not what it points at. Returns the
# mode's display name, or $null (having already printed why) on failure.
function Set-LiaShortcutTarget($link) {
    if ($Exe) {
        # NB: not $exe -- PowerShell variable names are case-insensitive, so
        # that would collide with the -Exe switch parameter above.
        $exePath = Join-Path $root 'dist\Lia\Lia.exe'
        if (-not (Test-Path $exePath)) {
            Write-Host "Cannot find $exePath" -ForegroundColor Red
            Write-Host "Build it first: powershell -ExecutionPolicy Bypass -File LIA\build_exe.ps1"
            return $null
        }
        $link.TargetPath       = $exePath
        $link.IconLocation     = $exePath
        $link.WorkingDirectory = Split-Path $exePath -Parent
        return 'packaged app (Lia.exe)'
    }
    elseif ($Console) {
        $bat = Join-Path $PSScriptRoot 'start_lia.bat'
        if (-not (Test-Path $bat)) {
            Write-Host "Cannot find $bat" -ForegroundColor Red
            return $null
        }
        $link.TargetPath = $bat
        return 'console'
    }
    else {
        $pythonw = Get-Pythonw
        if (-not $pythonw) {
            Write-Host "Could not find pythonw.exe next to python.exe." -ForegroundColor Red
            Write-Host "Re-run with -Console to install the terminal version instead."
            return $null
        }
        $link.TargetPath  = $pythonw
        $link.Arguments   = '"' + (Join-Path $PSScriptRoot 'app.py') + '"'
        $link.WindowStyle = 7            # minimised, no console
        $icon = Join-Path $PSScriptRoot 'assets\lia.ico'
        if (Test-Path $icon) { $link.IconLocation = $icon }
        return 'tray app (no window)'
    }
}

switch ($Action) {
    'install' {
        $shell = New-Object -ComObject WScript.Shell
        $link  = $shell.CreateShortcut($startupLink)
        $mode  = Set-LiaShortcutTarget $link
        if (-not $mode) { exit 1 }

        if (-not $link.WorkingDirectory) { $link.WorkingDirectory = $root }
        $link.Description = 'Lia - local companion'
        $link.Save()

        Write-Host "Installed as $mode." -ForegroundColor Green
        Write-Host "  $startupLink"
        Write-Host "She'll start automatically the next time you log in."
    }

    'remove' {
        if (Test-Path $startupLink) {
            Remove-Item $startupLink -Force
            Write-Host "Removed. Lia will no longer start automatically." -ForegroundColor Green
        }
        else {
            Write-Host "Nothing to remove -- autostart isn't installed."
        }
    }

    'status' {
        if (Test-Path $startupLink) {
            $shell = New-Object -ComObject WScript.Shell
            $link = $shell.CreateShortcut($startupLink)
            Write-Host "Autostart is ON" -ForegroundColor Green
            Write-Host "  target: $($link.TargetPath) $($link.Arguments)"
        }
        else {
            Write-Host "Autostart is OFF. Run with 'install' to turn it on."
        }
        if (Test-Path $menuLink) {
            Write-Host "Start Menu entry is present ($menuLink)"
        }
    }

    'pin' {
        # A Start Menu shortcut, not Startup -- something you launch by
        # clicking (Start Menu search finds "Lia" like any installed app)
        # instead of always running when you log in. The two are independent:
        # pin without install if you just want a clickable icon, or both.
        $shell = New-Object -ComObject WScript.Shell
        $link  = $shell.CreateShortcut($menuLink)
        $mode  = Set-LiaShortcutTarget $link
        if (-not $mode) { exit 1 }

        if (-not $link.WorkingDirectory) { $link.WorkingDirectory = $root }
        $link.Description = 'Lia - local companion'
        $link.Save()

        Write-Host "Added to the Start Menu as $mode." -ForegroundColor Green
        Write-Host "  $menuLink"
        Write-Host "Search for `"Lia`" in the Start Menu, or find her there to pin to Start/taskbar."
    }

    'unpin' {
        if (Test-Path $menuLink) {
            Remove-Item $menuLink -Force
            Write-Host "Removed from the Start Menu." -ForegroundColor Green
        }
        else {
            Write-Host "Nothing to remove -- she isn't in the Start Menu."
        }
    }
}
