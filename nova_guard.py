import os
import sys
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime

import psutil

ROOT = Path(r"C:\Nova")
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
NOVA_CORE = ROOT / "nova_core.py"

RUNTIME_DIR = ROOT / "runtime"
LOG_DIR = ROOT / "logs"

LOCK_FILE = RUNTIME_DIR / "guard.lock"
GUARD_PID_FILE = RUNTIME_DIR / "guard_pid.json"
GUARD_LOG = LOG_DIR / "guard.log"
STOP_FILE = RUNTIME_DIR / "guard.stop"

CORE_STATE = RUNTIME_DIR / "core_state.json"
CORE_HEARTBEAT = RUNTIME_DIR / "core.heartbeat"

POLL_SECONDS = 2
BOOT_GRACE_SECONDS = 15
HEARTBEAT_STALE_SECONDS = 5

CORE_ARGS = [
    "--heartbeat", str(CORE_HEARTBEAT),
    "--statefile", str(CORE_STATE),
]

# Self-heal safety latch
WINDOW_SECONDS = 60
MAX_RESTARTS_IN_WINDOW = 3
FAIL_FILE = RUNTIME_DIR / "core.fail"

_restart_times: list[float] = []


def record_restart_or_failsafe(reason: str) -> bool:
    """Record a restart timestamp. Return True if restart allowed; False if failsafe latched."""
    now = time.time()
    # prune old timestamps
    global _restart_times
    _restart_times = [t for t in _restart_times if (now - t) <= WINDOW_SECONDS]
    _restart_times.append(now)
    if len(_restart_times) > MAX_RESTARTS_IN_WINDOW:
        # latch failsafe
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write_json(FAIL_FILE, {
            "ts": ts(),
            "reason": reason,
            "restarts_in_window": len(_restart_times),
            "window_seconds": WINDOW_SECONDS,
            "action": "failsafe_latched_no_more_restarts"
        })
        log(f"[FAILSAFE] Too many restarts ({len(_restart_times)}). Wrote {FAIL_FILE}")
        return False
    return True

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{ts()} | {msg}"
    print(line, flush=True)
    with open(GUARD_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def atomic_write_json(path: Path, data: dict):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

def read_json(path: Path):
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def remove_file(path: Path):
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass

def _write_guard_lock(path: Path, payload: dict) -> None:
    with open(path, "x", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True)

def acquire_lock_or_exit():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"pid": os.getpid(), "ts": ts()}

    for _attempt in range(2):
        try:
            _write_guard_lock(LOCK_FILE, payload)
            atomic_write_json(GUARD_PID_FILE, payload)
            return
        except FileExistsError:
            data = read_json(LOCK_FILE) or {}
            other_pid = int(data.get("pid", 0) or 0)
            if other_pid > 0 and psutil.pid_exists(other_pid):
                log(f"[GUARD] Another guard is already running (pid={other_pid}). Exiting.")
                sys.exit(0)
            remove_file(LOCK_FILE)
        except Exception as e:
            log(f"[GUARD] Failed to acquire guard lock: {e}")
            sys.exit(1)

    log("[GUARD] Failed to acquire guard lock after stale-lock cleanup.")
    sys.exit(1)

def is_heartbeat_fresh() -> bool:
    try:
        if not CORE_HEARTBEAT.exists():
            return False
        age = time.time() - CORE_HEARTBEAT.stat().st_mtime
        return age <= HEARTBEAT_STALE_SECONDS
    except Exception:
        return False

def read_core_state():
    data = read_json(CORE_STATE)
    if not data:
        return None
    pid = data.get("pid")
    ct = data.get("create_time")
    if not isinstance(pid, int) or pid <= 0:
        return None
    if not isinstance(ct, (int, float)) or ct <= 0:
        return None
    return {"pid": pid, "create_time": float(ct)}

def pid_matches_create_time(pid: int, create_time: float) -> bool:
    try:
        p = psutil.Process(pid)
        return abs(p.create_time() - float(create_time)) < 1.0
    except Exception:
        return False

def spawn_core(reason: str):
    # Check failsafe before spawning
    if not record_restart_or_failsafe(reason):
        log(f"[GUARD] Failsafe engaged; refusing to spawn core (reason={reason}).")
        return None
    if not VENV_PY.exists():
        raise FileNotFoundError(f"venv python not found: {VENV_PY}")
    if not NOVA_CORE.exists():
        raise FileNotFoundError(f"nova_core.py not found: {NOVA_CORE}")

    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    log(f"[GUARD] Starting nova_core.py (NEW CONSOLE) because: {reason}")

    p = subprocess.Popen(
        [str(VENV_PY), str(NOVA_CORE), *CORE_ARGS],
        cwd=str(ROOT),
        creationflags=creationflags
    )
    log(f"[OK] Spawned core pid={p.pid}")
    return p.pid

def should_stop() -> bool:
    return STOP_FILE.exists()

def main():
    acquire_lock_or_exit()

    log("===================================================")
    log("[GUARD] Nova Guard online (deterministic)")
    log("[GUARD] Policy: trust statefile+heartbeat only; no process scanning.")
    log(f"[GUARD] ROOT={ROOT}")
    log(f"[GUARD] VENV_PY={VENV_PY}")
    log(f"[GUARD] NOVA_CORE={NOVA_CORE}")
    log("===================================================")

    spawned_at = None

    st = read_core_state()
    if not st:
        spawned_at = time.time()
        spawn_core("boot:no_state")
    else:
        if not psutil.pid_exists(st["pid"]) or not pid_matches_create_time(st["pid"], st["create_time"]):
            spawned_at = time.time()
            spawn_core("boot:pid_missing")

    while True:
        if should_stop():
            log("[GUARD] Stop file detected. Exiting guard.")
            break

        st = read_core_state()

        if spawned_at is not None and (time.time() - spawned_at) <= BOOT_GRACE_SECONDS:
            time.sleep(POLL_SECONDS)
            continue

        if not st:
            spawned_at = time.time()
            spawn_core("no_state")
            time.sleep(POLL_SECONDS)
            continue

        pid = st["pid"]
        if not psutil.pid_exists(pid) or not pid_matches_create_time(pid, st["create_time"]):
            spawned_at = time.time()
            spawn_core("pid_missing")
            time.sleep(POLL_SECONDS)
            continue

        if not is_heartbeat_fresh():
            spawned_at = time.time()
            spawn_core("heartbeat_stale")
            time.sleep(POLL_SECONDS)
            continue

        time.sleep(POLL_SECONDS)

    remove_file(GUARD_PID_FILE)
    remove_file(LOCK_FILE)
    log("[GUARD] Guard stopped.")

if __name__ == "__main__":
    main()
