from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "nova_http.py" in cl or "webui_watchdog.py" in cl:
            try:
                psutil.Process(p.info["pid"]).kill()
            except Exception:
                pass
    time.sleep(2)

    flags = 0
    if sys.platform == "win32":
        flags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
    py = str(ROOT / ".venv" / "Scripts" / "python.exe")
    subprocess.Popen(
        [py, str(ROOT / "nova_http.py"), "--host", "127.0.0.1", "--port", "8080"],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    print("launched", flush=True)

    for i in range(90):
        time.sleep(1)
        pids = []
        for p in psutil.process_iter(["pid", "cmdline", "ppid"]):
            try:
                cl = " ".join(p.info.get("cmdline") or [])
            except Exception:
                continue
            if "nova_http.py" in cl:
                pids.append((p.info["pid"], p.info.get("ppid")))
        try:
            h = urllib.request.urlopen("http://127.0.0.1:8080/api/health", timeout=2).status
        except Exception as e:
            h = type(e).__name__
        print(f"t+{i+1}s pids={pids} health={h}", flush=True)
        if i >= 25 and h == 200 and pids:
            print("OK stable 25s+", flush=True)
            return 0
        if i >= 20 and not pids:
            print("DIED", flush=True)
            return 1
    print("timeout", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
