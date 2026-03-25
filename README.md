# openclaw-watchdog

A pretty terminal watchdog for the [OpenClaw](https://openclaw.ai) gateway — keeps it alive, keeps your screen awake, and looks good doing it.

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Rich](https://img.shields.io/badge/rich-TUI-magenta) ![Windows](https://img.shields.io/badge/platform-Windows-lightgrey)

---

## What it does

| Feature | Detail |
|---|---|
| **Gateway health check** | Polls `http://127.0.0.1:18789/` every **5 seconds** |
| **Auto-restart** | Runs `openclaw gateway restart` if down; retries every **30 s** until recovered |
| **Screen awake** | Presses `Shift` every **60 s** via pyautogui to prevent sleep |
| **Singleton** | Won't launch a second instance — safe to call from login/startup |
| **Persistent stats** | Restart count + timestamps survive process restarts (stored in `state.json`) |
| **Log file** | Appends to `%LOCALAPPDATA%\openclaw\gateway-watchdog.log`; auto-rotates at 2 MB |
| **Rich TUI** | Live dashboard with status, counters, countdowns, and recent activity log |

---

## Setup

### 1. Install dependencies

```powershell
pip install rich pyautogui
```

### 2. Add Windows Terminal profiles

Add the three profiles below to your Windows Terminal Preview `settings.json`  
(`%LOCALAPPDATA%\Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json`):

```json
{
  "guid": "{a1b2c3d4-0001-0000-0000-000000000001}",
  "name": "Watchdog",
  "commandline": "powershell -NoProfile -ExecutionPolicy Bypass -Command \"python 'C:\\Users\\50420\\.openclaw\\watchdog\\watchdog.py'; pause\"",
  "colorScheme": "One Half Dark",
  "hidden": false
},
{
  "guid": "{a1b2c3d4-0002-0000-0000-000000000002}",
  "name": "OpenClaw TUI",
  "commandline": "powershell -NoProfile -ExecutionPolicy Bypass -Command \"openclaw tui\"",
  "colorScheme": "Dark+",
  "hidden": false
},
{
  "guid": "{a1b2c3d4-0003-0000-0000-000000000003}",
  "name": "Claude",
  "commandline": "powershell -NoProfile -ExecutionPolicy Bypass -Command \"claude\"",
  "colorScheme": "Tango Dark",
  "hidden": false
}
```

### 3. Auto-launch on login

Add a shortcut to `launch.ps1` in your Windows Startup folder:

```powershell
$startup = [System.Environment]::GetFolderPath("Startup")
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut("$startup\openclaw-watchdog.lnk")
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"C:\Users\50420\.openclaw\watchdog\launch.ps1`""
$shortcut.Save()
```

---

## Files

```
watchdog.py    — Main watchdog + Rich TUI
launch.ps1     — Opens WT Preview with Watchdog / OpenClaw TUI / Claude tabs
README.md      — This file
```

---

## Log & state locations

| File | Purpose |
|---|---|
| `%LOCALAPPDATA%\openclaw\gateway-watchdog.log` | Timestamped event log (auto-rotates) |
| `%LOCALAPPDATA%\openclaw\watchdog-state.json` | Persistent restart count + timestamps |
| `%TEMP%\openclaw-watchdog.pid` | Singleton PID lock |

---

## License

MIT
