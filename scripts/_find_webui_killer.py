"""Start webui via production launcher and detect death + recent terminators."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def http_pids() -> list[dict]:
    rows = []
    for p in psutil.process_iter(["pid", "ppid", "cmdline", "create_time", "name"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "nova_http.py" in cl:
            rows.append(
                {
                    "pid": p.info["pid"],
                    "ppid": p.info.get("ppid"),
                    "create_time": p.info.get("create_time"),
                    "parent_name": "",
                }
            )
    for row in rows:
        try:
            parent = psutil.Process(int(row["ppid"] or 0))
            row["parent_name"] = parent.name()
            row["parent_cmdline"] = " ".join(parent.cmdline() or [])[:160]
        except Exception:
            pass
    return rows


def health() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/api/health", timeout=2) as r:
            return str(r.status)
    except Exception as e:
        return type(e).__name__


def kill_all_http() -> None:
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "nova_http.py" in cl:
            try:
                psutil.Process(p.info["pid"]).kill()
            except Exception:
                pass
    time.sleep(2)


def main() -> int:
    print("time", datetime.now().isoformat(timespec="seconds"), flush=True)
    print("BEFORE kill existing", http_pids(), flush=True)
    kill_all_http()

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    launcher = ROOT / "scripts" / "start_webui_detached.py"
    # production path
    r = subprocess.run(
        [str(py), str(launcher), "--host", "127.0.0.1", "--port", "8080"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    print("launcher rc", r.returncode, "out", r.stdout, "err", r.stderr, flush=True)

    # map known system processes
    print("system processes of interest:", flush=True)
    for p in psutil.process_iter(["pid", "cmdline", "name"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
            name = p.info.get("name") or ""
        except Exception:
            continue
        if any(x in cl.lower() or x in name.lower() for x in ("nova_guard", "autonomy_maintenance", "nova_core", "guard")):
            print(f"  {p.info['pid']} {name} {cl[:140]}", flush=True)

    seen = set()
    dead_at = None
    for i in range(90):
        time.sleep(1)
        pids = http_pids()
        h = health()
        key = tuple(sorted(x["pid"] for x in pids))
        if key not in seen:
            print(f"t+{i+1}s NEW pids={pids} health={h}", flush=True)
            seen.add(key)
        elif i % 10 == 0:
            print(f"t+{i+1}s pids={key} health={h}", flush=True)
        if i >= 5 and not pids:
            dead_at = i + 1
            print(f"DIED at t+{dead_at}s health={h}", flush=True)
            break
        if i >= 20 and h == "200" and pids:
            print("STABLE 20s+", flush=True)
            # keep watching to 90 for late death
    else:
        print("still alive after 90s", flush=True)

    # recent autonomy log lines
    log = ROOT / "runtime" / "autonomy_maintenance.guard.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        print("--- last autonomy webui lines ---", flush=True)
        for line in lines[-30:]:
            if "webui" in line.lower() or "nova_http" in line.lower():
                print(line[:240], flush=True)

    state = ROOT / "runtime" / "autonomy_maintenance_state.json"
    if state.exists():
        data = json.loads(state.read_text(encoding="utf-8"))
        print("last_operator_webui_ensure", data.get("last_operator_webui_ensure"), flush=True)
        print("operator_webui_degraded_count", data.get("operator_webui_degraded_count"), flush=True)

    print("FINAL pids", http_pids(), "health", health(), flush=True)
    return 0 if health() == "200" else 1


if __name__ == "__main__":
    raise SystemExit(main())
