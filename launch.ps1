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
    $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($oldPid) {
        $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Watchdog already running (PID $oldPid). Not spawning a new window."
            exit 0
        }
    }
}

# Build WT arguments — one string, tabs separated by semicolons
# Using --profile names matching what we added to settings.json
$args = @(
    "new-tab",
    "--profile", "Watchdog",
    "--title", "Watchdog",
    "--",
    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-Command", "python `"$watchdog`"; pause",
    ";",
    "new-tab",
    "--profile", "OpenClaw TUI",
    "--title", "OpenClaw",
    "--",
    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-Command", "openclaw tui",
    ";",
    "new-tab",
    "--profile", "Claude",
    "--title", "Claude",
    "--",
    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-Command", "claude"
)

Write-Host "Launching Windows Terminal Preview..."
Start-Process -FilePath $wtExe -ArgumentList $args
