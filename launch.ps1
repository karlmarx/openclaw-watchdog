# launch.ps1 - Open Windows Terminal Preview with three tabs:
#   Tab 1: OpenClaw Gateway Watchdog (Python/Rich)
#   Tab 2: openclaw tui
#   Tab 3: claude (Claude Code CLI)
#
# Only opens if watchdog is not already running.

$wtExe    = "$env:LOCALAPPDATA\Microsoft\WindowsApps\wt.exe"
$watchdog = "C:\Users\50420\.openclaw\watchdog\watchdog.py"
$pidFile  = "$env:TEMP\openclaw-watchdog.pid"

# Check if watchdog is already running
if (Test-Path $pidFile) {
    $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue).Trim()
    if ($oldPid -match '^\d+$') {
        $proc = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if ($null -ne $proc -and $proc.Id) {
            Write-Host "Watchdog already running (PID $oldPid). Not spawning a new window."
            exit 0
        }
    }
    # Stale PID file — remove it
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Write-Host "Removed stale PID file."
}

# Figure out which python to use
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { $pythonExe = "python" }
Write-Host "Using python: $pythonExe"

# Test that WT exists
if (-not (Test-Path $wtExe)) {
    Write-Error "Windows Terminal not found at: $wtExe"
    exit 1
}

# Build command strings for each tab
$cmd1 = "$pythonExe `"$watchdog`""
$cmd2 = "openclaw tui"
$cmd3 = "claude"

Write-Host "Launching Windows Terminal Preview..."

# Use wt.exe command-line syntax:
# wt new-tab [options] -- <commandline> ; new-tab [options] -- <commandline> ...
& $wtExe `
    new-tab --profile "Watchdog"    --title "Watchdog"   -- powershell -NoProfile -ExecutionPolicy Bypass -Command $cmd1 `; `
    new-tab --profile "OpenClaw TUI" --title "OpenClaw"  -- powershell -NoProfile -ExecutionPolicy Bypass -Command $cmd2 `; `
    new-tab --profile "Claude"       --title "Claude"    -- powershell -NoProfile -ExecutionPolicy Bypass -Command $cmd3

Write-Host "Done. Exit: $LASTEXITCODE"
