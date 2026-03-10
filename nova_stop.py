import json
import time
from pathlib import Path
import psutil

ROOT = Path(r"C:\Nova")
RUNTIME = ROOT / "runtime"

STOP_FILE = RUNTIME / "guard.stop"
CORE_STATE = RUNTIME / "core_state.json"

def warn(msg): print(f"[WARN] {msg}", flush=True)
def ok(msg): print(f"[OK]   {msg}", flush=True)

def read_core_pid():
    try:
        data = json.loads(CORE_STATE.read_text(encoding="utf-8"))
        pid = data.get("pid")
        return pid if isinstance(pid, int) and pid > 0 else None
    except Exception:
        return None

def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    STOP_FILE.write_text("stop", encoding="utf-8")
    ok("Sent guard stop signal: runtime/guard.stop")

    pid = read_core_pid()
    if not pid:
        warn("No core PID found")
        ok("Done.")
        return

    if not psutil.pid_exists(pid):
        warn(f"Core pid={pid} not running")
        ok("Done.")
        return

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
