# launch.ps1 — Open Windows Terminal Preview with three tabs:
#   Tab 1: OpenClaw Gateway Watchdog (Python/Rich)
#   Tab 2: openclaw tui
#   Tab 3: claude (Claude Code CLI)
#
# Only opens if WT Preview is not already running with this session.
# Designed to be run at login or manually.

$wtExe      = "$env:LOCALAPPDATA\Microsoft\WindowsApps\wt.exe"
$watchdog   = "C:\Users\50420\.openclaw\watchdog\watchdog.py"
$pidFile    = "$env:TEMP\openclaw-watchdog.pid"

# ── Check if watchdog is already running ────────────────────────────────────
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

# ── Launch WT Preview with three tabs ───────────────────────────────────────
# wt.exe command line: each tab separated by `;`
# Using PowerShell profile for consistent font/colour

$tab1 = "new-tab --profile `"Watchdog`" --title `"🔧 Watchdog`" -- powershell -NoProfile -ExecutionPolicy Bypass -Command `"python '$watchdog'; pause`""
$tab2 = "; new-tab --profile `"OpenClaw TUI`" --title `"🦞 OpenClaw`" -- powershell -NoProfile -ExecutionPolicy Bypass -Command `"openclaw tui`""
$tab3 = "; new-tab --profile `"Claude`" --title `"🤖 Claude`" -- powershell -NoProfile -ExecutionPolicy Bypass -Command `"claude`""

Start-Process -FilePath $wtExe -ArgumentList "$tab1 $tab2 $tab3"

Write-Host "Launched Windows Terminal Preview with Watchdog + OpenClaw TUI + Claude tabs."
