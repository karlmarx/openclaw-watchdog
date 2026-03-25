# launch.ps1
# Opens Windows Terminal Preview with 4 tabs:
#   1. Watchdog  (Python/Rich live dashboard)
#   2. OpenClaw TUI
#   3. Claude Linux (WSL, starts in /home/kmarx)
#   4. Claude Win   (native Windows exe)
#
# Singleton: exits if watchdog is already running.

$wtExe     = "$env:LOCALAPPDATA\Microsoft\WindowsApps\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\wt.exe"
$ps        = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$python    = "C:\Python314\python.exe"
$watchdog  = "C:\Users\50420\.openclaw\watchdog\watchdog.py"
$openclaw  = "C:\Users\50420\AppData\Roaming\npm\openclaw.cmd"
$claudeWin = "C:\Users\50420\.local\bin\claude.exe"
$wsl       = "C:\Windows\System32\wsl.exe"
$pidFile   = "$env:TEMP\openclaw-watchdog.pid"

# ── Singleton guard ───────────────────────────────────────────────────────────
if (Test-Path $pidFile) {
    $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue).Trim()
    if ($oldPid -match '^\d+$') {
        try {
            $proc = Get-Process -Id ([int]$oldPid) -ErrorAction Stop
            Write-Host "Watchdog already running (PID $oldPid). Not spawning again."
            exit 0
        } catch {
            # Process gone — stale pid file
            Remove-Item $pidFile -ErrorAction SilentlyContinue
            Write-Host "Cleared stale PID file ($oldPid)."
        }
    }
}

# ── Validate paths ────────────────────────────────────────────────────────────
foreach ($p in @($wtExe, $ps, $python, $watchdog, $openclaw, $claudeWin, $wsl)) {
    if (-not (Test-Path $p)) {
        Write-Error "Not found: $p"
        exit 1
    }
}

Write-Host "Launching Windows Terminal Preview..."

& $wtExe `
    new-tab --profile "Watchdog" `
        -- $ps -NoProfile -ExecutionPolicy Bypass -Command "& '$python' '$watchdog'" `
    ";" new-tab --profile "OpenClaw TUI" `
        -- $ps -NoProfile -ExecutionPolicy Bypass -Command "& '$openclaw' tui" `
    ";" new-tab --profile "Claude Linux" `
        -- $wsl -d Ubuntu-24.04 --cd /home/kmarx -- bash -ic "~/.local/bin/claude" `
    ";" new-tab --profile "Claude Win" `
        -- $claudeWin

Write-Host "Done. Exit: $LASTEXITCODE"
