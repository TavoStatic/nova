"""Keep operator webui alive. Detached, restarts on death.

Usage:
  .venv\\Scripts\\python.exe scripts\\webui_watchdog.py
  .venv\\Scripts\\python.exe scripts\\webui_watchdog.py --once
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "runtime" / "logs" / "webui_watchdog.log"
LAUNCHER = ROOT / "scripts" / "start_webui_detached.py"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
HEALTH_URL = "http://127.0.0.1:8080/api/health"


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n"
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(line, end="", flush=True)


def healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except Exception:
        return False


def start_webui() -> None:
    if not PY.exists() or not LAUNCHER.exists():
        _log("launcher prerequisites missing")
        return
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [str(PY), str(LAUNCHER), "--host", "127.0.0.1", "--port", "8080"],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    _log("start_webui_detached launched")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    _log("watchdog start")
    while True:
        if healthy():
            _log("health=ok")
        else:
            _log("health=down — restarting webui")
            start_webui()
            time.sleep(6)
            _log(f"health_after_start={'ok' if healthy() else 'still_down'}")
        if args.once:
            return 0 if healthy() else 1
        time.sleep(max(5.0, float(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())
