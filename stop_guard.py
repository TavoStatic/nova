import json
import time
from pathlib import Path

import psutil

ROOT = Path(r"C:\Nova")
RUNTIME = ROOT / "runtime"

GUARD_STOP = RUNTIME / "guard.stop"
CORE_STATE = RUNTIME / "core_state.json"

def warn(msg): print(f"[WARN] {msg}")
def ok(msg): print(f"[OK]   {msg}")

def read_core_pid():
    try:
        if not CORE_STATE.exists():
            return None
        data = json.loads(CORE_STATE.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0) or 0)
        return pid if pid > 0 else None
    except Exception:
        return None

def main():
    # 1) Deterministic guard stop signal
    RUNTIME.mkdir(parents=True, exist_ok=True)
    GUARD_STOP.write_text(str(time.time()), encoding="utf-8")
    ok("Sent guard stop signal: runtime/guard.stop")

    # 2) Best-effort stop core using statefile (no scanning, no guessing)
    pid = read_core_pid()
    if not pid:
        warn("No core pid found (runtime/core_state.json missing or invalid)")
        ok("Done.")
        return

    if not psutil.pid_exists(pid):
        warn(f"Core not running (pid={pid})")
        ok("Done.")
        return

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