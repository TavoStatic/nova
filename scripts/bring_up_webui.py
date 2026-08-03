"""Bring up operator webui and optional watchdog. Exit 0 only when health is OK."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
HTTP = ROOT / "nova_http.py"
WATCHDOG = ROOT / "scripts" / "webui_watchdog.py"
OUT = ROOT / "runtime" / "logs" / "nova_http.out.log"
ERR = ROOT / "runtime" / "logs" / "nova_http.err.log"
HEALTH = "http://127.0.0.1:8080/api/health"
CONTROL = "http://127.0.0.1:8080/control"


def _flags() -> int:
    if sys.platform != "win32":
        return 0
    return (
        subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW
    )


def healthy(url: str = HEALTH, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except Exception:
        return False


def kill_nova_http() -> None:
    try:
        import psutil
    except Exception:
        return
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "nova_http.py" in cl:
            try:
                p.kill()
            except Exception:
                pass
    time.sleep(1.5)


def start_http() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Use DEVNULL for detached life: redirecting to files opened by this
    # short-lived parent has caused the listener to die when the parent exits.
    stamp = ROOT / "runtime" / "logs" / "webui_last_bring_up.txt"
    stamp.write_text(time.strftime("%Y-%m-%d %H:%M:%S") + " start_http\n", encoding="utf-8")
    subprocess.Popen(
        [str(PY), str(HTTP), "--host", "127.0.0.1", "--port", "8080"],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_flags(),
    )


def start_watchdog() -> None:
    try:
        import psutil

        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cl = " ".join(p.info.get("cmdline") or [])
            except Exception:
                continue
            if "webui_watchdog.py" in cl:
                return
    except Exception:
        pass
    subprocess.Popen(
        [str(PY), str(WATCHDOG), "--interval", "20"],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_flags(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Kill existing nova_http first")
    parser.add_argument("--no-watchdog", action="store_true")
    parser.add_argument("--wait-sec", type=float, default=45.0)
    args = parser.parse_args()

    if not PY.exists() or not HTTP.exists():
        print("[FAIL] missing venv python or nova_http.py", file=sys.stderr)
        return 1

    if healthy():
        print("[OK] webui already healthy:", CONTROL)
        if not args.no_watchdog:
            start_watchdog()
        return 0

    if args.force:
        kill_nova_http()

    print("[INFO] starting nova_http (Ollama warm can take 10-20s)...")
    start_http()
    deadline = time.time() + max(15.0, float(args.wait_sec))
    while time.time() < deadline:
        if healthy():
            print("[OK] webui health 200")
            print("[OK]", CONTROL)
            if not args.no_watchdog:
                start_watchdog()
                print("[OK] watchdog armed")
            return 0
        time.sleep(1.0)

    print("[FAIL] webui did not become healthy in time", file=sys.stderr)
    try:
        err_tail = ERR.read_text(encoding="utf-8", errors="replace")[-1500:]
        out_tail = OUT.read_text(encoding="utf-8", errors="replace")[-1500:]
        if err_tail.strip():
            print("--- err ---", file=sys.stderr)
            print(err_tail, file=sys.stderr)
        if out_tail.strip():
            print("--- out ---", file=sys.stderr)
            print(out_tail, file=sys.stderr)
    except Exception:
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
