"""Start nova_http and watch for unexpected death."""
from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
from tools import runtime_processes  # noqa: E402


def kill_existing() -> None:
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
        except Exception:
            continue
        if "nova_http.py" in cl:
            print("killing", p.pid, flush=True)
            try:
                p.kill()
            except Exception as exc:
                print("kill fail", exc, flush=True)
    time.sleep(2)


def main() -> None:
    kill_existing()
    out_path = ROOT / "runtime" / "logs" / "nova_http.out.log"
    err_path = ROOT / "runtime" / "logs" / "nova_http.err.log"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = open(out_path, "w", encoding="utf-8")
    err = open(err_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            str(ROOT / ".venv" / "Scripts" / "python.exe"),
            str(ROOT / "nova_http.py"),
            "--host",
            "127.0.0.1",
            "--port",
            "8080",
        ],
        cwd=str(ROOT),
        stdout=out,
        stderr=err,
    )
    print("spawned", proc.pid, flush=True)
    time.sleep(6)
    procs = list(runtime_processes.logical_service_processes(ROOT / "nova_http.py"))
    print("logical", procs, flush=True)
    try:
        print("health", urllib.request.urlopen("http://127.0.0.1:8080/api/health", timeout=5).status, flush=True)
    except Exception as exc:
        print("health fail", exc, flush=True)

    for i in range(24):
        time.sleep(5)
        alive = proc.poll()
        logical = list(runtime_processes.logical_service_processes(ROOT / "nova_http.py"))
        pids = [x.get("pid") for x in logical]
        raw = []
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cl = " ".join(p.info["cmdline"] or [])
            except Exception:
                continue
            if "nova_http.py" in cl:
                raw.append(p.info["pid"])
        try:
            h = urllib.request.urlopen("http://127.0.0.1:8080/api/health", timeout=3).status
        except Exception as exc:
            h = type(exc).__name__
        print(f"t+{(i+1)*5}s poll={alive} logical={pids} raw={raw} health={h}", flush=True)
        if alive is not None and not raw:
            print("DIED", flush=True)
            break

    print("--- err ---", flush=True)
    print(err_path.read_text(encoding="utf-8", errors="replace")[-3000:], flush=True)
    print("--- out ---", flush=True)
    print(out_path.read_text(encoding="utf-8", errors="replace")[-1500:], flush=True)


if __name__ == "__main__":
    main()
