import json
import time
from pathlib import Path
import psutil
import tools.runtime_processes as runtime_processes

ROOT = Path(r"C:\Nova")
RUNTIME = ROOT / "runtime"

STOP_FILE = RUNTIME / "guard.stop"
CORE_STATE = RUNTIME / "core_state.json"

def warn(msg): print(f"[WARN] {msg}", flush=True)
def ok(msg): print(f"[OK]   {msg}", flush=True)

CORE_PY = ROOT / "nova_core.py"


def read_core_identity():
    pid, create_time, _data = runtime_processes.read_identity_file(CORE_STATE)
    return pid, create_time

def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    STOP_FILE.write_text("stop", encoding="utf-8")
    ok("Sent guard stop signal: runtime/guard.stop")

    pid, create_time = read_core_identity()
    if not pid:
        warn("No core PID found")
        ok("Done.")
        return

    logical = runtime_processes.logical_service_processes(CORE_PY)
    selected = runtime_processes.select_logical_process(logical, pid=pid, create_time=create_time)
    if selected is None:
        if psutil.pid_exists(pid):
            warn(f"Core state points to stale identity pid={pid}; refusing to terminate unrelated process")
        else:
            warn(f"Core pid={pid} not running")
        ok("Done.")
        return

    pid = int(selected.get("pid") or pid)

    try:
        p = psutil.Process(pid)
        ok(f"Terminating core pid={pid} ...")
        p.terminate()
        try:
            p.wait(timeout=8)
        except psutil.TimeoutExpired:
            warn("Core did not terminate in time; killing...")
            p.kill()
        ok("Core terminated")
    except Exception as e:
        warn(f"Could not terminate core: {e}")

    ok("Done.")

if __name__ == "__main__":
    main()
