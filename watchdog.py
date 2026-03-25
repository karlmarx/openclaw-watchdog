"""
OpenClaw Gateway Watchdog
─────────────────────────
• Polls the gateway every 5 s; restarts if down, retries every 30 s until up.
• Presses Shift every 60 s to keep the screen awake.
• Singleton — exits immediately if another instance is already running.
• Rich live dashboard + log file.
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pyautogui
import pyautogui as pag
from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ── Config ────────────────────────────────────────────────────────────────────
GATEWAY_URL     = "http://127.0.0.1:18789/"
OPENCLAW_CMD    = r"C:\Users\50420\AppData\Roaming\npm\openclaw.cmd"
POLL_INTERVAL   = 5          # seconds between health checks
AWAKE_INTERVAL  = 60         # seconds between Shift keypresses
RETRY_INTERVAL  = 30         # seconds between restart retries
LOG_DIR         = Path(os.environ["LOCALAPPDATA"]) / "openclaw"
LOG_FILE        = LOG_DIR / "gateway-watchdog.log"
STATE_FILE      = LOG_DIR / "watchdog-state.json"
PID_FILE        = Path(tempfile.gettempdir()) / "openclaw-watchdog.pid"
MAX_LOG_BYTES   = 2 * 1024 * 1024  # 2 MB

# ── Singleton guard ───────────────────────────────────────────────────────────
def _is_pid_running(pid: int) -> bool:
    """Check if a PID is actually alive using tasklist."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True, stderr=subprocess.DEVNULL
        )
        return str(pid) in out
    except Exception:
        return False

def _check_singleton() -> None:
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if _is_pid_running(old_pid):
                print(f"Watchdog already running (PID {old_pid}). Exiting.")
                sys.exit(0)
            else:
                # Stale PID — clean it up and continue
                PID_FILE.unlink(missing_ok=True)
        except (ValueError, OSError):
            PID_FILE.unlink(missing_ok=True)
    PID_FILE.write_text(str(os.getpid()))

def _cleanup_pid() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)

def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    # Rotate if too large
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        LOG_FILE.replace(LOG_FILE.with_suffix(".log.old"))
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

# ── Persistent state ──────────────────────────────────────────────────────────
def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"restart_count": 0, "last_restart": None, "last_ok": None, "uptime_since": None}

def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ── Gateway helpers ───────────────────────────────────────────────────────────
def _is_gateway_up() -> bool:
    try:
        req = urllib.request.urlopen(GATEWAY_URL, timeout=4)
        return req.status == 200
    except Exception:
        return False

def _restart_gateway() -> None:
    _log("Restarting gateway…")
    try:
        result = subprocess.run(
            [OPENCLAW_CMD, "gateway", "restart"],
            capture_output=True, text=True, timeout=30
        )
        _log(f"Restart stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            _log(f"Restart stderr: {result.stderr.strip()}")
    except Exception as exc:
        _log(f"Restart error: {exc}")

# ── Rich dashboard ────────────────────────────────────────────────────────────
console = Console()

STATUS_EMOJI = {True: "[bold green]● UP[/]", False: "[bold red]● DOWN[/]"}

def _fmt_ts(iso: str | None) -> str:
    if not iso:
        return "[dim]—[/]"
    dt = datetime.fromisoformat(iso)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def _fmt_ago(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso)
    delta = int((datetime.now() - dt).total_seconds())
    if delta < 60:
        return f"[dim]{delta}s ago[/]"
    elif delta < 3600:
        return f"[dim]{delta // 60}m ago[/]"
    else:
        h, m = divmod(delta // 60, 60)
        return f"[dim]{h}h {m}m ago[/]"

def _build_panel(
    state: dict,
    gateway_up: bool,
    mode: str,               # "watching" | "recovering" | "retrying"
    next_check_in: int,
    next_awake_in: int,
    log_lines: list[str],
) -> Panel:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Status table
    status_table = Table(box=box.ROUNDED, expand=True, show_header=False, padding=(0, 1))
    status_table.add_column("Key",   style="bold cyan", width=22)
    status_table.add_column("Value", style="white")

    status_table.add_row("Gateway",       STATUS_EMOJI[gateway_up])
    status_table.add_row("Mode",          f"[yellow]{mode}[/]")
    status_table.add_row("Last OK",       f"{_fmt_ts(state['last_ok'])}  {_fmt_ago(state['last_ok'])}")
    status_table.add_row("Last Restart",  f"{_fmt_ts(state['last_restart'])}  {_fmt_ago(state['last_restart'])}")
    status_table.add_row("Restart Count", f"[bold magenta]{state['restart_count']}[/]")
    status_table.add_row("Next check in", f"[cyan]{next_check_in}s[/]")
    status_table.add_row("Awake ping in", f"[blue]{next_awake_in}s[/]")
    status_table.add_row("Log file",      f"[dim]{LOG_FILE}[/]")

    # ── Recent log
    log_table = Table(box=box.SIMPLE, expand=True, show_header=True, padding=(0, 1))
    log_table.add_column("Recent activity", style="dim white")
    for line in log_lines[-8:]:
        log_table.add_row(line.strip())

    layout = Layout()
    layout.split_column(
        Layout(status_table, name="status", size=12),
        Layout(log_table,    name="log",    minimum_size=5),
    )

    title = Text.assemble(
        ("🔧 OpenClaw Gateway Watchdog  ", "bold white"),
        (now, "dim"),
    )
    return Panel(layout, title=Align(title, align="center"), border_style="cyan", box=box.HEAVY)

# ── Main loop ─────────────────────────────────────────────────────────────────
def main() -> None:
    _check_singleton()
    import atexit
    atexit.register(_cleanup_pid)

    state = _load_state()
    _log("Watchdog started")

    gateway_up   = False
    mode         = "watching"
    log_lines: list[str] = []

    last_poll_ts  = 0.0
    last_awake_ts = 0.0
    tick          = 0

    def add_log(msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        log_lines.append(f"[{ts}] {msg}")
        _log(msg)

    with Live(console=console, refresh_per_second=2, screen=True) as live:
        while True:
            now = time.monotonic()

            # ── Awake keypress
            if now - last_awake_ts >= AWAKE_INTERVAL:
                try:
                    pag.press("shift")
                    add_log("↑ Shift pressed (screen awake)")
                except Exception as exc:
                    add_log(f"⚠ pyautogui error: {exc}")
                last_awake_ts = now

            # ── Gateway poll
            if now - last_poll_ts >= POLL_INTERVAL:
                was_up    = gateway_up
                gateway_up = _is_gateway_up()
                last_poll_ts = now

                if gateway_up:
                    state["last_ok"] = datetime.now().isoformat()
                    if not was_up:
                        add_log("✅ Gateway is UP")
                    mode = "watching"
                else:
                    if was_up or tick == 0:
                        add_log("❌ Gateway is DOWN — initiating recovery")
                        mode = "recovering"
                        _restart_gateway()
                        state["restart_count"] += 1
                        state["last_restart"] = datetime.now().isoformat()
                        _save_state(state)
                        last_poll_ts = now  # reset so retry waits RETRY_INTERVAL
                        mode = "retrying"
                    else:
                        add_log(f"⏳ Still down — retrying in {RETRY_INTERVAL}s")
                        _restart_gateway()
                        state["restart_count"] += 1
                        state["last_restart"] = datetime.now().isoformat()
                        _save_state(state)

                _save_state(state)

            # ── Compute countdown values for display
            next_check  = max(0, int(POLL_INTERVAL  - (time.monotonic() - last_poll_ts)))
            next_awake  = max(0, int(AWAKE_INTERVAL - (time.monotonic() - last_awake_ts)))

            live.update(_build_panel(state, gateway_up, mode, next_check, next_awake, log_lines))

            tick += 1
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _log("Watchdog stopped by user")
        console.print("\n[yellow]Watchdog stopped.[/]")
