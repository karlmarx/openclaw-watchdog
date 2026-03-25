# launch.ps1 - Open Windows Terminal Preview with four tabs:
#   Tab 1: OpenClaw Gateway Watchdog (Python/Rich)
#   Tab 2: openclaw tui
#   Tab 3: Claude (Linux/WSL) - starts in /home/kmarx
#   Tab 4: Claude (Windows)
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
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Write-Host "Removed stale PID file."
}

if (-not (Test-Path $wtExe)) {
    Write-Error "Windows Terminal not found at: $wtExe"
    exit 1
}

$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { $pythonExe = "python" }

Write-Host "Launching Windows Terminal Preview..."

& $wtExe `
    new-tab --profile "Watchdog"      -- powershell -NoProfile -ExecutionPolicy Bypass -Command "$pythonExe `"$watchdog`"" `;`
    new-tab --profile "OpenClaw TUI"  -- powershell -NoProfile -ExecutionPolicy Bypass -Command "openclaw tui" `;`
    new-tab --profile "Claude Linux"  `;`
    new-tab --profile "Claude Win"    -- powershell -NoProfile -ExecutionPolicy Bypass -Command "claude"

Write-Host "Launched. Exit: $LASTEXITCODE"
