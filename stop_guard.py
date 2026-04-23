import json
import time
from pathlib import Path

import psutil
import tools.runtime_processes as runtime_processes

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"

GUARD_STOP = RUNTIME / "guard.stop"
CORE_STATE = RUNTIME / "core_state.json"
CORE_PY = ROOT / "nova_core.py"

def warn(msg): print(f"[WARN] {msg}")
def ok(msg): print(f"[OK]   {msg}")

def read_core_identity():
    if not CORE_STATE.exists():
        return None, None
    pid, create_time, _data = runtime_processes.read_identity_file(CORE_STATE)
    return pid, create_time

def main():
    # 1) Deterministic guard stop signal
    RUNTIME.mkdir(parents=True, exist_ok=True)
    GUARD_STOP.write_text(str(time.time()), encoding="utf-8")
    ok("Sent guard stop signal: runtime/guard.stop")

    # 2) Best-effort stop core using statefile (no scanning, no guessing)
    pid, create_time = read_core_identity()
    if not pid:
        warn("No core pid found (runtime/core_state.json missing or invalid)")
        ok("Done.")
        return

    logical = runtime_processes.logical_service_processes(CORE_PY)
    selected = runtime_processes.select_logical_process(logical, pid=pid, create_time=create_time)
    if selected is None:
        if psutil.pid_exists(pid):
            warn(f"Core state points to stale identity pid={pid}; refusing to stop unrelated process")
        else:
            warn(f"Core not running (pid={pid})")
        ok("Done.")
        return

    pid = int(selected.get("pid") or pid)

    try:
        p = psutil.Process(pid)
        ok(f"Terminating core pid={pid} ...")
        p.terminate()
        try:
            p.wait(timeout=6)
            ok("Core terminated")
        except psutil.TimeoutExpired:
            warn("Core did not exit in time; killing...")
            p.kill()
            ok("Core killed")
    except Exception as e:
        warn(f"Failed to stop core pid={pid}: {e}")

    ok("Done.")

if __name__ == "__main__":
    main()