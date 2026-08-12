"""Start webui and report second-by-second liveness."""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]


def kill_http() -> None:
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "nova_http.py" in cl:
            print(f"kill {p.pid}", flush=True)
            try:
                p.kill()
            except Exception as exc:
                print(f"  kill fail: {exc}", flush=True)
    time.sleep(2)


def list_http() -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    for p in psutil.process_iter(["pid", "cmdline", "ppid"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "nova_http.py" in cl:
            rows.append((int(p.info["pid"]), int(p.info.get("ppid") or 0)))
    return rows


def health() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/api/health", timeout=2) as resp:
            return str(resp.status)
    except Exception as exc:
        return type(exc).__name__


def main() -> int:
    kill_http()
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    # Prefer direct start with logs (more reliable than nested detached).
    out = open(ROOT / "runtime" / "logs" / "nova_http.out.log", "w", encoding="utf-8")
    err = open(ROOT / "runtime" / "logs" / "nova_http.err.log", "w", encoding="utf-8")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(
        [str(py), str(ROOT / "nova_http.py"), "--host", "127.0.0.1", "--port", "8080"],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=err,
        creationflags=creationflags,
        close_fds=False,
    )
    print(f"spawned {proc.pid}", flush=True)

    for i in range(45):
        time.sleep(1)
        pids = list_http()
        h = health()
        print(f"t+{i+1}s pids={pids} health={h}", flush=True)
        if i >= 8 and not pids:
            print("GONE early", flush=True)
            err_text = (ROOT / "runtime" / "logs" / "nova_http.err.log").read_text(encoding="utf-8", errors="replace")
            out_text = (ROOT / "runtime" / "logs" / "nova_http.out.log").read_text(encoding="utf-8", errors="replace")
            print("--- err ---", flush=True)
            print(err_text[-3000:], flush=True)
            print("--- out ---", flush=True)
            print(out_text[-2000:], flush=True)
            return 1
        if i >= 8 and h == "200":
            print("STABLE", flush=True)
            print("URL: http://127.0.0.1:8080/control", flush=True)
            return 0
    print("timeout waiting for stability", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
