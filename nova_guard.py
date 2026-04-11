import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
NOVA_CORE = ROOT / "nova_core.py"
GUARD_SCRIPT = Path(__file__).resolve()

RUNTIME_DIR = ROOT / "runtime"
LOG_DIR = ROOT / "logs"

LOCK_FILE = RUNTIME_DIR / "guard.lock"
GUARD_PID_FILE = RUNTIME_DIR / "guard_pid.json"
GUARD_LOG = LOG_DIR / "guard.log"
STOP_FILE = RUNTIME_DIR / "guard.stop"
BOOT_HISTORY_FILE = RUNTIME_DIR / "guard_boot_history.json"

CORE_STATE = RUNTIME_DIR / "core_state.json"
CORE_HEARTBEAT = RUNTIME_DIR / "core.heartbeat"

POLL_SECONDS = 2
MAINTENANCE_INTERVAL_SECONDS = 3600
BOOT_TIMEOUT_FLOOR_SECONDS = 20
BOOT_TIMEOUT_MARGIN_SECONDS = 10
BOOT_TIMEOUT_CEILING_SECONDS = 60
BOOT_HISTORY_LIMIT = 20
HEARTBEAT_STALE_SECONDS = 5
TERMINATE_TIMEOUT_SECONDS = 3
RESTART_BASE_DELAY_SECONDS = 2
RESTART_MAX_DELAY_SECONDS = 30

MAINTENANCE_SCRIPT = ROOT / "autonomy_maintenance.py"
MAINTENANCE_LOG = RUNTIME_DIR / "autonomy_maintenance.guard.log"

_LAST_MAINTENANCE_LAUNCH = 0.0
_MAINTENANCE_PROC: Optional[subprocess.Popen] = None

CORE_ARGS = [
    "--heartbeat", str(CORE_HEARTBEAT),
    "--statefile", str(CORE_STATE),
]

STATE_IDLE = "IDLE"
STATE_BOOTING = "BOOTING"
STATE_RUNNING = "RUNNING"
STATE_FAILED = "FAILED"
STATE_RESTART_WAIT = "RESTART_WAIT"


@dataclass
class GuardAttempt:
    pid: Optional[int] = None
    create_time: Optional[float] = None
    started_at: Optional[float] = None
    state: str = STATE_IDLE
    failure_reason: str = ""
    restart_count: int = 0
    next_restart_at: Optional[float] = None
    boot_timeout_seconds: float = BOOT_TIMEOUT_CEILING_SECONDS
    state_seen_at: Optional[float] = None
    heartbeat_seen_at: Optional[float] = None
    resolution_started_at: Optional[float] = None
    resolution_targets: list[tuple[int, float]] = field(default_factory=list)


def _append_identity(targets: list[tuple[int, float]], identity: Optional[tuple[int, float]]) -> list[tuple[int, float]]:
    updated = list(targets or [])
    if identity is None or identity in updated:
        return updated
    updated.append(identity)
    return updated


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


def _normalize_identity_path(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return os.path.normcase(os.path.normpath(text))


def _guard_command_identity() -> dict:
    return {
        "executable": str(VENV_PY),
        "script": str(GUARD_SCRIPT),
    }


def _cmdline_matches_identity(cmdline: list[str], command: dict) -> bool:
    normalized = [_normalize_identity_path(arg) for arg in list(cmdline or []) if str(arg or "").strip()]
    if not normalized:
        return False
    expected_executable = _normalize_identity_path(str(command.get("executable") or ""))
    expected_script = _normalize_identity_path(str(command.get("script") or ""))
    executable_matches = not expected_executable or normalized[0] == expected_executable
    script_matches = not expected_script or any(arg == expected_script for arg in normalized[1:])
    return executable_matches and script_matches


def _process_identity(pid: int) -> Optional[tuple[int, float]]:
    create_time = _process_create_time(pid)
    if create_time is None:
        return None
    return int(pid), float(create_time)


def _current_guard_identity_payload() -> dict:
    pid = os.getpid()
    identity = _process_identity(pid)
    if identity is None:
        raise RuntimeError(f"Unable to determine guard create_time for pid={pid}")
    return {
        "pid": pid,
        "create_time": identity[1],
        "command": _guard_command_identity(),
        "ts": ts(),
    }


def _lock_belongs_to_live_guard(data: Optional[dict]) -> bool:
    if not isinstance(data, dict):
        return False
    pid = int(data.get("pid", 0) or 0)
    create_time = data.get("create_time")
    command = data.get("command")
    if pid <= 0 or not isinstance(create_time, (int, float)) or not isinstance(command, dict):
        return False
    try:
        process = psutil.Process(pid)
        if abs(float(process.create_time()) - float(create_time)) >= 1.0:
            return False
        return _cmdline_matches_identity(process.cmdline(), command)
    except Exception:
        return False


def _write_guard_lock(path: Path, payload: dict) -> None:
    with open(path, "x", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True)


def acquire_lock_or_exit():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = _current_guard_identity_payload()

    for _attempt in range(2):
        try:
            _write_guard_lock(LOCK_FILE, payload)
            atomic_write_json(GUARD_PID_FILE, payload)
            return
        except FileExistsError:
            data = read_json(LOCK_FILE) or {}
            other_pid = int(data.get("pid", 0) or 0)
            if _lock_belongs_to_live_guard(data):
                log(f"[GUARD] Another guard is already running (pid={other_pid}). Exiting.")
                sys.exit(0)
            remove_file(LOCK_FILE)
            remove_file(GUARD_PID_FILE)
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


def _process_create_time(pid: int) -> Optional[float]:
    try:
        return float(psutil.Process(pid).create_time())
    except Exception:
        return None


def _sync_attempt_create_time(attempt: GuardAttempt) -> None:
    if attempt.pid is None or attempt.create_time is not None:
        return
    attempt.create_time = _process_create_time(attempt.pid)


def _attempt_is_alive(attempt: GuardAttempt) -> bool:
    if attempt.pid is None:
        return False
    _sync_attempt_create_time(attempt)
    if attempt.create_time is None:
        return False
    return pid_matches_create_time(attempt.pid, attempt.create_time)


def _clear_core_runtime_artifacts() -> None:
    remove_file(CORE_STATE)
    remove_file(CORE_HEARTBEAT)


def _boot_history() -> list[dict]:
    data = read_json(BOOT_HISTORY_FILE)
    return list(data) if isinstance(data, list) else []


def _derive_boot_timeout_seconds() -> float:
    observed = []
    for item in _boot_history():
        if not isinstance(item, dict) or not item.get("success"):
            continue
        total = item.get("total_observed_s")
        if isinstance(total, (int, float)) and total > 0:
            observed.append(float(total))
    if not observed:
        return float(BOOT_TIMEOUT_CEILING_SECONDS)
    measured_max = max(observed[-BOOT_HISTORY_LIMIT:])
    return float(
        max(
            BOOT_TIMEOUT_FLOOR_SECONDS,
            min(BOOT_TIMEOUT_CEILING_SECONDS, measured_max + BOOT_TIMEOUT_MARGIN_SECONDS),
        )
    )


def _boot_observation_entry(attempt: GuardAttempt, *, success: bool, reason: str) -> Optional[dict]:
    if attempt.started_at is None:
        return None
    now = time.time()
    return {
        "ts": now,
        "success": bool(success),
        "reason": str(reason or ""),
        "total_observed_s": round(now - attempt.started_at, 3),
        "state_seen_after_s": round(attempt.state_seen_at - attempt.started_at, 3) if attempt.state_seen_at is not None else None,
        "heartbeat_seen_after_s": round(attempt.heartbeat_seen_at - attempt.started_at, 3) if attempt.heartbeat_seen_at is not None else None,
        "boot_timeout_seconds": round(float(attempt.boot_timeout_seconds or 0.0), 3),
    }


def _record_boot_observation(attempt: GuardAttempt, *, success: bool, reason: str) -> None:
    entry = _boot_observation_entry(attempt, success=success, reason=reason)
    if entry is None:
        return
    history = _boot_history()
    history.append(entry)
    history = history[-BOOT_HISTORY_LIMIT:]
    atomic_write_json(BOOT_HISTORY_FILE, history)
    log(
        "[GUARD] Boot metrics: "
        f"success={entry['success']} reason={entry['reason'] or 'n/a'} "
        f"state_after={entry['state_seen_after_s']}s heartbeat_after={entry['heartbeat_seen_after_s']}s "
        f"total={entry['total_observed_s']}s window={entry['boot_timeout_seconds']}s"
    )


def _state_matches_identity(state: Optional[dict], pid: Optional[int], create_time: Optional[float]) -> bool:
    if state is None or pid is None or create_time is None:
        return False
    if state.get("pid") != pid:
        return False
    return abs(float(state.get("create_time") or 0.0) - float(create_time)) < 1.0


def _owned_process_identities(attempt: GuardAttempt) -> list[tuple[int, float]]:
    identities: list[tuple[int, float]] = []
    seen: set[tuple[int, float]] = set()

    roots = list(attempt.resolution_targets or [])
    current_identity = _process_identity(attempt.pid) if attempt.pid is not None else None
    roots = _append_identity(roots, current_identity)

    for pid, create_time in roots:
        if (pid, create_time) not in seen:
            identities.append((pid, create_time))
            seen.add((pid, create_time))
        if not pid_matches_create_time(pid, create_time):
            continue
        try:
            root = psutil.Process(pid)
        except Exception:
            continue
        processes = [root]
        try:
            processes.extend(root.children(recursive=True))
        except Exception:
            pass
        for process in processes:
            try:
                identity = (int(process.pid), float(process.create_time()))
            except Exception:
                continue
            if identity in seen:
                continue
            seen.add(identity)
            identities.append(identity)
    return identities


def _identity_in_process_tree(root_identity: tuple[int, float], target_identity: tuple[int, float]) -> bool:
    root_pid, root_create_time = root_identity
    target_pid, target_create_time = target_identity
    if (root_pid, root_create_time) == (target_pid, target_create_time):
        return True
    if not pid_matches_create_time(root_pid, root_create_time):
        return False
    try:
        root = psutil.Process(root_pid)
        for process in root.children(recursive=True):
            try:
                if process.pid == target_pid and abs(float(process.create_time()) - float(target_create_time)) < 1.0:
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _adopt_runtime_identity_from_state(attempt: GuardAttempt, state: Optional[dict]) -> bool:
    if state is None:
        return False
    state_pid = state.get("pid")
    state_create_time = state.get("create_time")
    if not isinstance(state_pid, int) or state_pid <= 0 or not isinstance(state_create_time, (int, float)):
        return False
    state_identity = (int(state_pid), float(state_create_time))
    if attempt.pid is not None and attempt.create_time is not None and _state_matches_identity(state, attempt.pid, attempt.create_time):
        return True

    candidate_roots = list(attempt.resolution_targets or [])
    current_identity = _process_identity(attempt.pid) if attempt.pid is not None else None
    candidate_roots = _append_identity(candidate_roots, current_identity)

    if not any(_identity_in_process_tree(root_identity, state_identity) for root_identity in candidate_roots):
        return False

    previous_identity = current_identity
    attempt.resolution_targets = _append_identity(candidate_roots, state_identity)
    attempt.pid = state_identity[0]
    attempt.create_time = state_identity[1]
    if previous_identity is not None and previous_identity != state_identity:
        log(
            f"[GUARD] Adopted runtime child pid={attempt.pid} from launcher pid={previous_identity[0]}"
        )
    return True


def _live_identities(identities: list[tuple[int, float]]) -> list[tuple[int, float]]:
    return [identity for identity in list(identities or []) if pid_matches_create_time(identity[0], identity[1])]


def _terminate_identities(identities: list[tuple[int, float]]) -> None:
    live_processes: list[psutil.Process] = []
    for pid, create_time in list(identities or []):
        if not pid_matches_create_time(pid, create_time):
            continue
        try:
            live_processes.append(psutil.Process(pid))
        except Exception:
            continue

    if not live_processes:
        return

    for process in reversed(live_processes):
        try:
            process.terminate()
        except Exception:
            pass
    gone, alive = psutil.wait_procs(live_processes, timeout=TERMINATE_TIMEOUT_SECONDS)
    for process in alive:
        try:
            process.kill()
        except Exception:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=TERMINATE_TIMEOUT_SECONDS)


def _reset_attempt_runtime_fields(attempt: GuardAttempt) -> None:
    attempt.pid = None
    attempt.create_time = None
    attempt.started_at = None
    attempt.failure_reason = ""
    attempt.next_restart_at = None
    attempt.state_seen_at = None
    attempt.heartbeat_seen_at = None
    attempt.resolution_started_at = None
    attempt.resolution_targets = []
    attempt.boot_timeout_seconds = _derive_boot_timeout_seconds()


def spawn_core(reason: str) -> int:
    if not VENV_PY.exists():
        raise FileNotFoundError(f"venv python not found: {VENV_PY}")
    if not NOVA_CORE.exists():
        raise FileNotFoundError(f"nova_core.py not found: {NOVA_CORE}")

    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    log(f"[GUARD] Starting nova_core.py (NEW CONSOLE) because: {reason}")
    process = subprocess.Popen(
        [str(VENV_PY), str(NOVA_CORE), *CORE_ARGS],
        cwd=str(ROOT),
        creationflags=creationflags,
    )
    log(f"[OK] Spawned core pid={process.pid}")
    return int(process.pid)


def start_new_attempt(attempt: GuardAttempt, reason: str) -> None:
    _clear_core_runtime_artifacts()
    pid = spawn_core(reason)
    attempt.pid = pid
    attempt.create_time = _process_create_time(pid)
    attempt.started_at = time.time()
    attempt.state = STATE_BOOTING
    attempt.failure_reason = ""
    attempt.next_restart_at = None
    attempt.boot_timeout_seconds = _derive_boot_timeout_seconds()
    attempt.state_seen_at = None
    attempt.heartbeat_seen_at = None
    attempt.resolution_started_at = None
    attempt.resolution_targets = _append_identity([], _process_identity(pid))
    log(f"[GUARD] Boot observation window set to {attempt.boot_timeout_seconds:.1f}s")


def _runtime_state_matches_attempt(attempt: GuardAttempt, state: Optional[dict]) -> bool:
    if state is None or attempt.pid is None:
        return False
    if state.get("pid") != attempt.pid:
        return False
    _sync_attempt_create_time(attempt)
    if attempt.create_time is None:
        return False
    return abs(float(state.get("create_time") or 0.0) - attempt.create_time) < 1.0


def _observe_boot_progress(attempt: GuardAttempt) -> bool:
    if not _attempt_is_alive(attempt):
        return False
    now = time.time()
    state = read_core_state()
    _adopt_runtime_identity_from_state(attempt, state)
    state_matches = _runtime_state_matches_attempt(attempt, state)
    if state_matches and attempt.started_at is not None and attempt.state_seen_at is None:
        attempt.state_seen_at = now
        log(f"[GUARD] Boot progress: matching state after {now - attempt.started_at:.1f}s")
    heartbeat_matches = bool(state_matches and is_heartbeat_fresh())
    if heartbeat_matches and attempt.started_at is not None and attempt.heartbeat_seen_at is None:
        attempt.heartbeat_seen_at = now
        log(f"[GUARD] Boot progress: fresh heartbeat after {now - attempt.started_at:.1f}s")
    return bool(state_matches and heartbeat_matches)


def _boot_succeeded(attempt: GuardAttempt) -> bool:
    return _observe_boot_progress(attempt)


def _boot_failed(attempt: GuardAttempt) -> tuple[bool, str]:
    if not _attempt_is_alive(attempt):
        return True, "boot_pid_missing"
    if attempt.started_at is None:
        return True, "boot_missing_timestamp"
    if (time.time() - attempt.started_at) > float(attempt.boot_timeout_seconds or BOOT_TIMEOUT_CEILING_SECONDS):
        if attempt.state_seen_at is None:
            return True, "boot_timeout_no_state"
        if attempt.heartbeat_seen_at is None:
            return True, "boot_timeout_no_heartbeat"
        return True, "boot_timeout"
    return False, ""


def _runtime_failed(attempt: GuardAttempt) -> tuple[bool, str]:
    if not _attempt_is_alive(attempt):
        return True, "pid_missing"
    state = read_core_state()
    if not _runtime_state_matches_attempt(attempt, state):
        return True, "state_mismatch"
    if not is_heartbeat_fresh():
        return True, "heartbeat_stale"
    return False, ""


def _mark_attempt_failed(attempt: GuardAttempt, reason: str) -> None:
    attempt.state = STATE_FAILED
    attempt.failure_reason = str(reason or "unknown_failure")
    log(f"[GUARD] Core attempt failed: {attempt.failure_reason}")


def _resolve_attempt(attempt: GuardAttempt) -> bool:
    if attempt.resolution_started_at is None:
        attempt.resolution_started_at = time.time()
        attempt.resolution_targets = _owned_process_identities(attempt)
        if attempt.pid is not None and not attempt.resolution_targets and attempt.create_time is not None:
            attempt.resolution_targets = [(attempt.pid, attempt.create_time)]
        if attempt.pid is not None:
            log(
                f"[GUARD] Resolving core pid={attempt.pid}; "
                f"tracked_targets={[pid for pid, _create_time in attempt.resolution_targets]}"
            )

    live_targets = _live_identities(attempt.resolution_targets)
    if live_targets:
        _terminate_identities(live_targets)
    _clear_core_runtime_artifacts()
    remaining_targets = _live_identities(attempt.resolution_targets)
    state_cleared = not _state_matches_identity(read_core_state(), attempt.pid, attempt.create_time)
    heartbeat_cleared = not CORE_HEARTBEAT.exists()
    if remaining_targets or not state_cleared or not heartbeat_cleared:
        return False
    if attempt.pid is not None:
        log(f"[GUARD] Resolution confirmed for core pid={attempt.pid}")
    return True


def _schedule_restart_wait(attempt: GuardAttempt) -> None:
    attempt.restart_count += 1
    delay = min(RESTART_MAX_DELAY_SECONDS, RESTART_BASE_DELAY_SECONDS * (2 ** max(0, attempt.restart_count - 1)))
    attempt.state = STATE_RESTART_WAIT
    attempt.next_restart_at = time.time() + delay
    log(f"[GUARD] Restart wait {delay}s after failure: {attempt.failure_reason}")
    attempt.pid = None
    attempt.create_time = None
    attempt.started_at = None
    attempt.state_seen_at = None
    attempt.heartbeat_seen_at = None
    attempt.resolution_started_at = None
    attempt.resolution_targets = []


def build_initial_attempt() -> GuardAttempt:
    state = read_core_state()
    if not state:
        return GuardAttempt()
    pid = int(state["pid"])
    create_time = float(state["create_time"])
    if not pid_matches_create_time(pid, create_time):
        _clear_core_runtime_artifacts()
        return GuardAttempt()
    attempt = GuardAttempt(
        pid=pid,
        create_time=create_time,
        started_at=time.time(),
        state=STATE_RUNNING if is_heartbeat_fresh() else STATE_FAILED,
        failure_reason="existing_core_unhealthy" if not is_heartbeat_fresh() else "",
        boot_timeout_seconds=_derive_boot_timeout_seconds(),
    )
    if attempt.state == STATE_RUNNING:
        log(f"[GUARD] Adopted running core pid={pid}")
    else:
        log(f"[GUARD] Existing core pid={pid} is unhealthy; resolving before restart")
    return attempt


def supervisor_tick(attempt: GuardAttempt) -> None:
    if attempt.state == STATE_IDLE:
        start_new_attempt(attempt, "initial_start" if attempt.restart_count == 0 else "restart")
        return

    if attempt.state == STATE_BOOTING:
        if _boot_succeeded(attempt):
            attempt.state = STATE_RUNNING
            attempt.failure_reason = ""
            _record_boot_observation(attempt, success=True, reason="running")
            log(f"[GUARD] Core pid={attempt.pid} reached RUNNING state")
            return
        failed, reason = _boot_failed(attempt)
        if failed:
            _record_boot_observation(attempt, success=False, reason=reason)
            _mark_attempt_failed(attempt, reason)
        return

    if attempt.state == STATE_RUNNING:
        failed, reason = _runtime_failed(attempt)
        if failed:
            _mark_attempt_failed(attempt, reason)
        return

    if attempt.state == STATE_FAILED:
        if _resolve_attempt(attempt):
            _schedule_restart_wait(attempt)
        return

    if attempt.state == STATE_RESTART_WAIT:
        if attempt.next_restart_at is None:
            attempt.next_restart_at = time.time() + RESTART_BASE_DELAY_SECONDS
            return
        if time.time() >= attempt.next_restart_at:
            _reset_attempt_runtime_fields(attempt)
            attempt.state = STATE_IDLE


def should_stop() -> bool:
    return STOP_FILE.exists()


def _maintenance_tick() -> None:
    global _LAST_MAINTENANCE_LAUNCH, _MAINTENANCE_PROC

    if not MAINTENANCE_SCRIPT.exists():
        return

    if _MAINTENANCE_PROC is not None:
        code = _MAINTENANCE_PROC.poll()
        if code is None:
            return
        log(f"[GUARD] Maintenance cycle exited with code={code}")
        _MAINTENANCE_PROC = None

    now = time.time()
    if (now - _LAST_MAINTENANCE_LAUNCH) < MAINTENANCE_INTERVAL_SECONDS:
        return

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(MAINTENANCE_LOG, "a", encoding="utf-8") as fh:
            _MAINTENANCE_PROC = subprocess.Popen(
                [str(VENV_PY), str(MAINTENANCE_SCRIPT), "--once"],
                cwd=str(ROOT),
                stdout=fh,
                stderr=subprocess.STDOUT,
            )
        _LAST_MAINTENANCE_LAUNCH = now
        log(f"[GUARD] Maintenance cycle launched pid={_MAINTENANCE_PROC.pid}")
    except Exception as exc:
        log(f"[GUARD] Maintenance launch failed: {exc}")


def main():
    acquire_lock_or_exit()

    log("===================================================")
    log("[GUARD] Nova Guard online (deterministic)")
    log("[GUARD] Policy: single owned core attempt with explicit lifecycle supervision.")
    log(f"[GUARD] ROOT={ROOT}")
    log(f"[GUARD] VENV_PY={VENV_PY}")
    log(f"[GUARD] NOVA_CORE={NOVA_CORE}")
    log("===================================================")

    attempt = build_initial_attempt()

    while True:
        if should_stop():
            log("[GUARD] Stop file detected. Exiting guard.")
            if attempt.state in {STATE_BOOTING, STATE_RUNNING, STATE_FAILED}:
                _resolve_attempt(attempt)
            break
        supervisor_tick(attempt)
        _maintenance_tick()
        time.sleep(POLL_SECONDS)

    remove_file(GUARD_PID_FILE)
    remove_file(LOCK_FILE)
    log("[GUARD] Guard stopped.")


if __name__ == "__main__":
    main()
