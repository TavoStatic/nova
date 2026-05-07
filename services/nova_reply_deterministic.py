from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Callable

from services.storage_watch import STORAGE_WATCH_SERVICE


def _is_restart_advice_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    if "restart" not in low:
        return False
    return (
        low.startswith("should i restart")
        or "operator adviser" in low
        or "do not restart anything" in low
    )


def _is_restart_condition_followup(text: str) -> bool:
    low = str(text or "").strip().lower()
    if "restart" not in low:
        return False
    return (
        "one condition" in low
        or "would make restart" in low
        or "restart the right move" in low
    )


def _runtime_pid_from_file(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        for key in ("pid", "process_id"):
            value = payload.get(key)
            if isinstance(value, int) and value > 0:
                return value
            try:
                parsed = int(str(value or "").strip())
            except Exception:
                parsed = 0
            if parsed > 0:
                return parsed
    return None


def _core_heartbeat_age_sec(runtime_dir: Path) -> float | None:
    heartbeat_path = runtime_dir / "core.heartbeat"
    if not heartbeat_path.exists():
        return None
    try:
        return max(0.0, time.time() - heartbeat_path.stat().st_mtime)
    except Exception:
        return None


def _restart_runtime_snapshot(core) -> dict:
    runtime_dir = Path(getattr(core, "RUNTIME_DIR", "runtime"))
    psutil_module = getattr(core, "psutil", None)
    pid_exists_fn = getattr(psutil_module, "pid_exists", None)

    def _alive(pid: int | None) -> bool:
        if not pid or pid <= 0:
            return False
        if callable(pid_exists_fn):
            try:
                return bool(pid_exists_fn(pid))
            except Exception:
                return False
        return True

    guard_pid = _runtime_pid_from_file(runtime_dir / "guard_pid.json")
    core_pid = _runtime_pid_from_file(runtime_dir / "core_state.json")
    heartbeat_age = _core_heartbeat_age_sec(runtime_dir)
    return {
        "guard_running": _alive(guard_pid),
        "core_running": _alive(core_pid),
        "heartbeat_age_sec": heartbeat_age,
        "heartbeat_fresh": heartbeat_age is not None and heartbeat_age <= 5.0,
    }


def _restart_advice_reply(core) -> str:
    snapshot = _restart_runtime_snapshot(core)
    if snapshot["guard_running"] and snapshot["core_running"] and snapshot["heartbeat_fresh"]:
        return (
            "No, not right now. Guard is running, the core appears healthy, "
            "and the core heartbeat is fresh. I would keep watching instead of restarting."
        )
    if snapshot["core_running"] and not snapshot["heartbeat_fresh"]:
        return (
            "Not yet. I would inspect first, because a stale or missing core heartbeat "
            "is a strong restart signal when the core is supposed to be running."
        )
    if not snapshot["core_running"] and snapshot["guard_running"]:
        return (
            "The core does not appear to be running under guard right now. "
            "I would inspect that first before deciding on a manual restart."
        )
    return (
        "I would inspect first before restarting. The clearest restart signal "
        "is a stale or missing core heartbeat while the core is supposed to be running."
    )


def _restart_condition_reply(core) -> str:
    snapshot = _restart_runtime_snapshot(core)
    if snapshot["heartbeat_fresh"]:
        return (
            "One clear restart condition is a stale or missing core heartbeat "
            "while the core is supposed to be running."
        )
    return (
        "A stale or missing core heartbeat while the core is supposed to be running "
        "is the clearest restart condition."
    )


def _is_queue_pressure_triage_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "generated queue" in low
        and "patch queue" in low
        and "work tree" in low
        and "single most important next move" in low
    )


def _is_queue_pressure_justify_followup(text: str) -> bool:
    low = str(text or "").strip().lower()
    return "justify that recommendation" in low and "without pretending" in low


def _is_runtime_audit_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "guard" in low
        and "core" in low
        and "search" in low
        and "maintenance" in low
        and ("live runtime" in low or "live state" in low)
    )


def _is_runtime_audit_evidence_followup(text: str) -> bool:
    low = str(text or "").strip().lower()
    return "what evidence" in low and "worries you" in low


def _is_tool_path_disambiguation_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "patch preview approval" in low
        and ("exact file" in low or "service name" in low)
        and ("find where" in low or "tell me" in low)
    )


def _is_tool_path_safe_step_followup(text: str) -> bool:
    low = str(text or "").strip().lower()
    return "next safe operator step" in low and "without pretending" in low


def _is_maintenance_mode_truth_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "maintenance" in low
        and "guard tick" in low
        and "worker" in low
        and ("live state" in low or "right now" in low)
    )


def _is_maintenance_mode_difference_followup(text: str) -> bool:
    low = str(text or "").strip().lower()
    return "difference" in low and "pretending both modes are active" in low


def _is_storage_watch_truth_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "snapshot storage" in low
        and ("healthy right now" in low or "healthy" in low)
        and "numbers" in low
    )


def _is_storage_watch_warning_followup(text: str) -> bool:
    low = str(text or "").strip().lower()
    return "storage watch" in low and "warning" in low


def _is_heartbeat_forensics_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "heartbeat" in low
        and ("healthy right now" in low or "healthy" in low)
        and ("what proves it" in low or "exactly what proves it" in low)
    )


def _is_heartbeat_artifact_followup(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "heartbeat" in low
        and ("stale again" in low or "goes stale again" in low)
        and ("artifact" in low or "file" in low)
        and ("inspect first" in low or "look at first" in low)
    )


def _is_runtime_artifact_grounding_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "runtime truth" in low
        and "artifact" in low
        and "file" in low
        and ("exact" in low or "which" in low)
    )


def _is_runtime_artifact_safe_step_followup(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        "safest next operator step" in low
        and "without pretending" in low
        and "opened those files" in low
    )


def should_skip_llm_routing_for_deterministic_query(text: str) -> bool:
    return any(
        detector(text)
        for detector in (
            _is_restart_advice_query,
            _is_restart_condition_followup,
            _is_queue_pressure_triage_query,
            _is_queue_pressure_justify_followup,
            _is_runtime_audit_query,
            _is_runtime_audit_evidence_followup,
            _is_maintenance_mode_truth_query,
            _is_maintenance_mode_difference_followup,
            _is_storage_watch_truth_query,
            _is_storage_watch_warning_followup,
            _is_heartbeat_forensics_query,
            _is_heartbeat_artifact_followup,
            _is_runtime_artifact_grounding_query,
            _is_runtime_artifact_safe_step_followup,
            _is_tool_path_disambiguation_query,
            _is_tool_path_safe_step_followup,
        )
    )


def _should_skip_mixed_turn_clarify(text: str) -> bool:
    return any(
        detector(text)
        for detector in (
            _is_runtime_audit_query,
            _is_maintenance_mode_truth_query,
            _is_storage_watch_truth_query,
            _is_storage_watch_warning_followup,
            _is_heartbeat_forensics_query,
            _is_heartbeat_artifact_followup,
            _is_runtime_artifact_grounding_query,
            _is_runtime_artifact_safe_step_followup,
        )
    )


def _queue_status_snapshot(core) -> dict:
    queue_text = ""
    tool_queue_status = getattr(core, "tool_queue_status", None)
    if callable(tool_queue_status):
        try:
            queue_text = str(tool_queue_status() or "")
        except Exception:
            queue_text = ""

    def _extract_count(label: str) -> int:
        match = re.search(rf"- {label}:\s*(\d+)", queue_text, re.IGNORECASE)
        return int(match.group(1)) if match else 0

    next_match = re.search(r"Next item:\s*(.+)", queue_text, re.IGNORECASE)
    status_match = re.search(r"Status:\s*([^\r\n]+)", queue_text, re.IGNORECASE)
    return {
        "open_count": _extract_count("open"),
        "drift_count": _extract_count("drift"),
        "warning_count": _extract_count("warning"),
        "never_run_count": _extract_count("never run"),
        "next_item": str(next_match.group(1)).strip() if next_match else "",
        "status_line": str(status_match.group(1)).strip() if status_match else "",
        "raw": queue_text,
    }


def _work_tree_pressure_snapshot(core) -> dict:
    runtime_dir = Path(getattr(core, "RUNTIME_DIR", "runtime"))
    state_path = runtime_dir / "autonomy_maintenance_state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    last_cycle = dict(payload.get("last_work_tree_cycle") or {}) if isinstance(payload, dict) else {}
    return {
        "status": str(last_cycle.get("status") or "").strip().lower() or "idle",
        "summary": str(last_cycle.get("summary") or "").strip(),
    }


def _queue_pressure_snapshot(core) -> dict:
    patch_payload_fn = getattr(core, "patch_status_payload", None)
    patch_payload = patch_payload_fn() if callable(patch_payload_fn) else {}
    patch_payload = patch_payload if isinstance(patch_payload, dict) else {}
    return {
        "queue": _queue_status_snapshot(core),
        "patch_pending": int(patch_payload.get("review_previews_pending_distinct", 0) or 0),
        "patch_orphaned": int(patch_payload.get("review_previews_orphaned", 0) or 0),
        "patch_apply_ready": int(patch_payload.get("previews_approved_eligible", 0) or 0),
        "work_tree": _work_tree_pressure_snapshot(core),
    }


def _queue_pressure_recommendation(core) -> str:
    snapshot = _queue_pressure_snapshot(core)
    queue = snapshot["queue"]
    work_tree = snapshot["work_tree"]
    next_item = str(queue.get("next_item") or "").strip()
    if int(queue.get("open_count", 0) or 0) > 0 and next_item:
        return (
            f"The single most important next move is to resolve `{next_item}` first, "
            f"because the generated queue still has {int(queue.get('open_count', 0) or 0)} open item(s) "
            f"and {int(queue.get('drift_count', 0) or 0)} active drift case(s). "
            f"Patch pressure is secondary right now ({snapshot['patch_pending']} pending, {snapshot['patch_orphaned']} orphaned, "
            f"{snapshot['patch_apply_ready']} apply-ready), and work tree pressure is {work_tree.get('status') or 'idle'}."
        )
    if snapshot["patch_apply_ready"] > 0:
        return (
            "The single most important next move is to advance the patch queue, "
            f"because there are {snapshot['patch_apply_ready']} apply-ready preview(s) waiting and the generated queue is quiet."
        )
    if snapshot["patch_pending"] > 0 or snapshot["patch_orphaned"] > 0:
        return (
            "The single most important next move is to clean the patch review lane, "
            f"because it still has {snapshot['patch_pending']} pending preview(s) and {snapshot['patch_orphaned']} orphaned preview(s) "
            "even though the generated queue is not leading the pressure."
        )
    return (
        "The single most important next move is to keep watching rather than forcing change, "
        "because the generated queue, patch queue, and work tree all look quiet right now."
    )


def _queue_pressure_justification(core) -> str:
    snapshot = _queue_pressure_snapshot(core)
    queue = snapshot["queue"]
    next_item = str(queue.get("next_item") or "").strip() or "the head generated item"
    if int(queue.get("open_count", 0) or 0) > 0:
        return (
            f"I recommend starting with `{next_item}` because the generated queue is still the loudest live pressure surface, "
            f"while the patch lane is blocked more by review residue ({snapshot['patch_pending']} pending, {snapshot['patch_orphaned']} orphaned) "
            f"than by an apply-ready change, and the work tree currently reads {snapshot['work_tree'].get('status') or 'idle'}."
        )
    if snapshot["patch_apply_ready"] > 0 or snapshot["patch_pending"] > 0 or snapshot["patch_orphaned"] > 0:
        return (
            f"I recommend focusing on the patch lane because the generated queue is comparatively quiet, "
            f"while the patch surface still shows {snapshot['patch_pending']} pending preview(s), "
            f"{snapshot['patch_orphaned']} orphaned preview(s), and {snapshot['patch_apply_ready']} apply-ready preview(s)."
        )
    return (
        "I recommend observation over intervention because none of the three pressure surfaces is currently signaling urgent work."
    )


def _control_status_snapshot(core, *, timeout: float = 2.0) -> dict | None:
    snapshot_fn = getattr(core, "runtime_audit_snapshot", None)
    if callable(snapshot_fn):
        try:
            payload = snapshot_fn()
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload:
            return dict(payload)

    endpoint = str(getattr(core, "CONTROL_STATUS_URL", "http://127.0.0.1:8080/api/control/status") or "").strip()
    if not endpoint:
        return None
    try:
        with urllib.request.urlopen(endpoint, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    guard_payload = dict(payload.get("guard") or {})
    core_payload = dict(payload.get("core") or {})
    return {
        "source": "control_status_api",
        "control_status_url": endpoint,
        "guard_running": bool(guard_payload.get("running")),
        "guard_status": str(guard_payload.get("status") or ""),
        "guard_pid": int(guard_payload.get("pid", 0) or 0),
        "core_running": bool(core_payload.get("running")),
        "core_status": str(core_payload.get("status") or ""),
        "core_pid": int(core_payload.get("pid", 0) or 0),
        "core_heartbeat_age_sec": core_payload.get("heartbeat_age_sec"),
        "search_ok": bool(payload.get("searxng_ok")),
        "search_note": str(payload.get("searxng_note") or ""),
        "search_endpoint": str(payload.get("search_api_endpoint") or ""),
        "maintenance_active": bool(payload.get("maintenance_scheduler_active")),
        "maintenance_status": str(payload.get("maintenance_scheduler_status") or ""),
        "maintenance_mode": str(payload.get("maintenance_scheduler_mode") or ""),
        "queue_status": str(payload.get("generated_queue_status") or ""),
        "queue_open_count": int(payload.get("queue_open_count", 0) or 0),
        "queue_actionable_count": int(payload.get("queue_actionable_count", 0) or 0),
    }


def _direct_runtime_audit_snapshot(core) -> dict:
    runtime_dir = Path(getattr(core, "RUNTIME_DIR", "runtime"))
    restart_snapshot = _restart_runtime_snapshot(core)

    search_endpoint = ""
    get_search_endpoint_fn = getattr(core, "get_search_endpoint", None)
    if callable(get_search_endpoint_fn):
        try:
            search_endpoint = str(get_search_endpoint_fn() or "").strip()
        except Exception:
            search_endpoint = ""
    probe_search_endpoint_fn = getattr(core, "probe_search_endpoint", None)
    search_probe = {}
    if callable(probe_search_endpoint_fn):
        try:
            search_probe = probe_search_endpoint_fn(search_endpoint, timeout=1.5, persist_repair=False)
        except TypeError:
            try:
                search_probe = probe_search_endpoint_fn(search_endpoint)
            except Exception:
                search_probe = {}
        except Exception:
            search_probe = {}
    search_probe = search_probe if isinstance(search_probe, dict) else {}

    state_path = runtime_dir / "autonomy_maintenance_state.json"
    try:
        maintenance_payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        maintenance_payload = {}
    runtime_worker = dict(maintenance_payload.get("runtime_worker") or {}) if isinstance(maintenance_payload, dict) else {}
    last_generated = dict(maintenance_payload.get("last_generated_queue_run") or {}) if isinstance(maintenance_payload, dict) else {}
    last_work_tree = dict(maintenance_payload.get("last_work_tree_cycle") or {}) if isinstance(maintenance_payload, dict) else {}
    maintenance_status = str(
        runtime_worker.get("last_cycle_status")
        or maintenance_payload.get("maintenance_scheduler_status")
        or last_generated.get("status")
        or last_work_tree.get("status")
        or ""
    ).strip()
    maintenance_mode = str(maintenance_payload.get("maintenance_scheduler_mode") or "").strip()
    queue_status = str(
        maintenance_payload.get("generated_queue_status")
        or last_generated.get("status")
        or ""
    ).strip()

    return {
        "source": "direct_runtime",
        "control_status_url": "",
        "guard_running": bool(restart_snapshot.get("guard_running")),
        "guard_status": "running" if restart_snapshot.get("guard_running") else "stopped",
        "guard_pid": int(_runtime_pid_from_file(runtime_dir / "guard_pid.json") or 0),
        "core_running": bool(restart_snapshot.get("core_running")),
        "core_status": "running" if restart_snapshot.get("core_running") else "stopped",
        "core_pid": int(_runtime_pid_from_file(runtime_dir / "core_state.json") or 0),
        "core_heartbeat_age_sec": restart_snapshot.get("heartbeat_age_sec"),
        "search_ok": bool(search_probe.get("ok")),
        "search_note": str(search_probe.get("note") or ""),
        "search_endpoint": str(search_probe.get("endpoint") or search_endpoint or ""),
        "maintenance_active": bool(runtime_worker.get("active") or restart_snapshot.get("guard_running")),
        "maintenance_status": maintenance_status,
        "maintenance_mode": maintenance_mode,
        "queue_status": queue_status,
        "queue_open_count": int(maintenance_payload.get("queue_open_count", 0) or last_generated.get("queue_open_count", 0) or 0),
        "queue_actionable_count": int(maintenance_payload.get("queue_actionable_count", 0) or last_generated.get("queue_actionable_count", 0) or 0),
    }


def _runtime_audit_snapshot(core) -> dict:
    control_snapshot = _control_status_snapshot(core)
    if isinstance(control_snapshot, dict) and control_snapshot:
        return control_snapshot
    return _direct_runtime_audit_snapshot(core)


def _runtime_audit_status_line(snapshot: dict) -> str:
    guard_healthy = bool(snapshot.get("guard_running")) and str(snapshot.get("guard_status") or "").strip().lower() == "running"
    core_healthy = bool(snapshot.get("core_running")) and str(snapshot.get("core_status") or "").strip().lower() in {"running", "heartbeat_only"}
    search_healthy = bool(snapshot.get("search_ok"))
    maintenance_healthy = bool(snapshot.get("maintenance_active")) and str(snapshot.get("maintenance_status") or "").strip().lower() not in {"", "inactive", "stopped", "failed", "error"}
    return (
        f"Using the current live state, guard is {'healthy' if guard_healthy else 'not healthy'}, "
        f"core is {'healthy' if core_healthy else 'not healthy'}, "
        f"search is {'healthy' if search_healthy else 'not healthy'}, "
        f"and maintenance is {'healthy' if maintenance_healthy else 'not healthy'}."
    )


def _runtime_audit_watch_item(snapshot: dict) -> str:
    heartbeat_age = snapshot.get("core_heartbeat_age_sec")
    try:
        heartbeat_age_value = float(heartbeat_age)
    except Exception:
        heartbeat_age_value = None
    if heartbeat_age_value is None:
        return "I would watch for the core heartbeat proving itself continuously, because I do not have a fresh heartbeat age right now."
    if heartbeat_age_value > 5.0:
        return "I would watch the core heartbeat first, because it is stale enough to become a restart signal."
    if int(snapshot.get("queue_actionable_count", 0) or 0) > 0:
        return (
            f"I would keep an eye on the generated repair queue, because it still has "
            f"{int(snapshot.get('queue_actionable_count', 0) or 0)} actionable item(s) even though the runtime is healthy."
        )
    if not bool(snapshot.get("maintenance_active")):
        return "I would watch the maintenance lane, because it does not look actively scheduled right now."
    return "Nothing in the runtime looks urgent right now; I would just keep watching for heartbeat drift or new generated queue pressure."


def _runtime_audit_reply(core) -> str:
    snapshot = _runtime_audit_snapshot(core)
    heartbeat_age = snapshot.get("core_heartbeat_age_sec")
    heartbeat_text = "unknown"
    if isinstance(heartbeat_age, (int, float)):
        heartbeat_text = f"{int(max(0, heartbeat_age))}s"
    search_endpoint = str(snapshot.get("search_endpoint") or "").strip()
    search_detail = str(snapshot.get("search_note") or "").strip() or ("healthy" if snapshot.get("search_ok") else "not healthy")
    maintenance_status = str(snapshot.get("maintenance_status") or snapshot.get("maintenance_mode") or "unknown").strip()
    queue_actionable = int(snapshot.get("queue_actionable_count", 0) or 0)
    queue_open = int(snapshot.get("queue_open_count", 0) or 0)
    return (
        f"{_runtime_audit_status_line(snapshot)} "
        f"Guard status is `{str(snapshot.get('guard_status') or 'unknown')}`. "
        f"Core status is `{str(snapshot.get('core_status') or 'unknown')}` with heartbeat age `{heartbeat_text}`. "
        f"Search is using `{search_endpoint or 'the configured endpoint'}` and currently reads `{search_detail}`. "
        f"Maintenance status is `{maintenance_status}`. "
        f"The generated queue is `{str(snapshot.get('queue_status') or 'unknown')}` with `{queue_open}` open and `{queue_actionable}` actionable item(s)."
    )


def _runtime_audit_evidence_reply(core) -> str:
    snapshot = _runtime_audit_snapshot(core)
    if str(snapshot.get("source") or "") == "control_status_api":
        lead = (
            f"Evidence I used: the live control payload at `{str(snapshot.get('control_status_url') or '')}`. "
            f"It shows guard=`{str(snapshot.get('guard_status') or 'unknown')}` pid `{int(snapshot.get('guard_pid', 0) or 0)}`, "
            f"core=`{str(snapshot.get('core_status') or 'unknown')}` pid `{int(snapshot.get('core_pid', 0) or 0)}`, "
            f"core heartbeat age `{int(max(0, float(snapshot.get('core_heartbeat_age_sec') or 0)))}s`, "
            f"search endpoint `{str(snapshot.get('search_endpoint') or '')}` with `{str(snapshot.get('search_note') or '') or 'no status'}`, "
            f"and maintenance status `{str(snapshot.get('maintenance_status') or snapshot.get('maintenance_mode') or 'unknown')}`."
        )
    else:
        lead = (
            "Evidence I used: guard/core runtime pid files, the live core heartbeat file, "
            "a direct search endpoint probe, and the latest autonomy maintenance state file."
        )
    return f"{lead} What still worries me: {_runtime_audit_watch_item(snapshot)}"


def _maintenance_mode_snapshot(core) -> dict:
    snapshot = _runtime_audit_snapshot(core)
    mode = str(snapshot.get("maintenance_mode") or "").strip() or "unknown"
    status = str(snapshot.get("maintenance_status") or "").strip() or "unknown"
    active = bool(snapshot.get("maintenance_active"))
    return {
        "mode": mode,
        "status": status,
        "active": active,
    }


def _maintenance_mode_reply(core) -> str:
    snapshot = _maintenance_mode_snapshot(core)
    mode = snapshot["mode"]
    status = snapshot["status"]
    if mode == "worker_loop":
        return (
            f"Right now Nova maintenance is running through a separate worker loop, not through guard tick. "
            f"The live maintenance mode is `{mode}` with status `{status}`."
        )
    if mode == "guard_tick":
        return (
            f"Right now Nova maintenance is running through the guard tick, not through a separate worker loop. "
            f"The live maintenance mode is `{mode}` with status `{status}`."
        )
    return (
        f"Right now Nova maintenance is not actively scheduled through either mode. "
        f"The live maintenance mode is `{mode}` with status `{status}`."
    )


def _maintenance_mode_difference_reply(core) -> str:
    snapshot = _maintenance_mode_snapshot(core)
    mode = snapshot["mode"]
    if mode == "worker_loop":
        current = "Right now only `worker_loop` is active."
    elif mode == "guard_tick":
        current = "Right now only `guard_tick` is active."
    else:
        current = "Right now neither mode looks active."
    return (
        "Guard tick means guard launches maintenance on its supervision tick instead of keeping a separate worker alive. "
        "Worker loop means a dedicated maintenance process keeps cycling on its own schedule. "
        f"{current}"
    )


def _storage_watch_snapshot(core) -> dict:
    snapshot_fn = getattr(core, "storage_watch_snapshot", None)
    if callable(snapshot_fn):
        try:
            payload = snapshot_fn()
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload:
            return dict(payload)
    base_dir = Path(getattr(core, "BASE_DIR", Path.cwd()))
    runtime_dir = Path(getattr(core, "RUNTIME_DIR", base_dir / "runtime"))
    load_policy_fn = getattr(core, "load_policy", None)
    policy = {}
    if callable(load_policy_fn):
        try:
            policy = load_policy_fn() or {}
        except Exception:
            policy = {}
    kidney_config = dict(policy.get("kidney") or {}) if isinstance(policy, dict) else {}
    return STORAGE_WATCH_SERVICE.snapshot(
        base_dir=base_dir,
        runtime_dir=runtime_dir,
        kidney_config=kidney_config,
    )


def _storage_watch_truth_reply(core) -> str:
    snapshot = _storage_watch_snapshot(core)
    status = str(snapshot.get("status") or "unknown")
    total_mb = float(snapshot.get("total_bytes", 0) or 0) / (1024 * 1024)
    patch_count = int(snapshot.get("patch_snapshot_count", 0) or 0)
    kidney_count = int(snapshot.get("kidney_snapshot_count", 0) or 0)
    health = "healthy" if status == "ok" else "not fully healthy"
    return (
        f"Nova's snapshot storage is {health} right now. "
        f"The storage watch is `{status}` with `{patch_count}` patch rollback snapshot(s), "
        f"`{kidney_count}` kidney cleanup snapshot(s), and `{total_mb:.1f}` MB total snapshot storage. "
        f"{str(snapshot.get('note') or '').strip().capitalize()}."
    )


def _storage_watch_warning_reply(core) -> str:
    snapshot = _storage_watch_snapshot(core)
    count_limit = int(snapshot.get("kidney_snapshot_warn_count", 24) or 24)
    total_limit_mb = float(snapshot.get("kidney_snapshot_warn_total_mb", 128) or 128)
    patch_limit = int(snapshot.get("patch_snapshot_warn_count", 3) or 3)
    patch_count = int(snapshot.get("patch_snapshot_count", 0) or 0)
    kidney_count = int(snapshot.get("kidney_snapshot_count", 0) or 0)
    total_mb = float(snapshot.get("total_bytes", 0) or 0) / (1024 * 1024)
    status = str(snapshot.get("status") or "unknown")
    return (
        f"The storage watch warning boundary is crossed if kidney cleanup snapshots rise above `{count_limit}`, "
        f"if total snapshot storage climbs past `{total_limit_mb:.0f}` MB, or if patch rollback snapshots build past `{patch_limit}` retained file(s). "
        f"Right now it is `{status}` with `{patch_count}` patch snapshot(s), `{kidney_count}` kidney snapshot(s), and `{total_mb:.1f}` MB total."
    )


def _runtime_artifact_snapshot(core) -> dict:
    base_dir = Path(getattr(core, "BASE_DIR", Path.cwd()))
    runtime_dir = Path(getattr(core, "RUNTIME_DIR", base_dir / "runtime"))
    logs_dir = base_dir / "logs"
    artifacts = {
        "heartbeat_file": runtime_dir / "core.heartbeat",
        "heartbeat_status_file": runtime_dir / "core_heartbeat_status.json",
        "heartbeat_log_file": runtime_dir / "core_heartbeat.log",
        "core_state_file": runtime_dir / "core_state.json",
        "guard_pid_file": runtime_dir / "guard_pid.json",
        "maintenance_state_file": runtime_dir / "autonomy_maintenance_state.json",
        "maintenance_log_file": runtime_dir / "autonomy_maintenance.log",
        "guard_log_file": logs_dir / "guard.log",
    }
    return {
        "base_dir": base_dir,
        "runtime_dir": runtime_dir,
        "logs_dir": logs_dir,
        "artifacts": artifacts,
        "existing": {name: path.exists() for name, path in artifacts.items()},
    }


def _primary_heartbeat_artifact(snapshot: dict) -> Path:
    artifacts = dict(snapshot.get("artifacts") or {})
    existing = dict(snapshot.get("existing") or {})
    preferred = [
        "heartbeat_status_file",
        "heartbeat_log_file",
        "heartbeat_file",
        "core_state_file",
    ]
    for key in preferred:
        path = artifacts.get(key)
        if isinstance(path, Path) and existing.get(key):
            return path
    for key in preferred:
        path = artifacts.get(key)
        if isinstance(path, Path):
            return path
    return Path("runtime")


def _unique_artifact_paths(snapshot: dict, keys: list[str]) -> list[Path]:
    artifacts = dict(snapshot.get("artifacts") or {})
    paths: list[Path] = []
    seen: set[str] = set()
    for key in keys:
        path = artifacts.get(key)
        if not isinstance(path, Path):
            continue
        path_text = str(path)
        if path_text in seen:
            continue
        seen.add(path_text)
        paths.append(path)
    return paths


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in list(paths or []):
        if not isinstance(path, Path):
            continue
        path_text = str(path)
        if path_text in seen:
            continue
        seen.add(path_text)
        deduped.append(path)
    return deduped


def _format_artifact_paths(paths: list[Path]) -> str:
    rendered = [f"`{str(path)}`" for path in list(paths or []) if isinstance(path, Path)]
    if not rendered:
        return "`runtime`"
    if len(rendered) == 1:
        return rendered[0]
    if len(rendered) == 2:
        return f"{rendered[0]} and {rendered[1]}"
    return f"{', '.join(rendered[:-1])}, and {rendered[-1]}"


def _heartbeat_forensics_reply(core) -> str:
    runtime_snapshot = _runtime_audit_snapshot(core)
    artifact_snapshot = _runtime_artifact_snapshot(core)
    heartbeat_age = runtime_snapshot.get("core_heartbeat_age_sec")
    heartbeat_text = "unknown"
    if isinstance(heartbeat_age, (int, float)):
        heartbeat_text = f"{int(max(0, heartbeat_age))}s"
    heartbeat_fresh = isinstance(heartbeat_age, (int, float)) and float(heartbeat_age) <= 5.0
    status = "healthy" if heartbeat_fresh else "not fully healthy"
    primary_artifact = _primary_heartbeat_artifact(artifact_snapshot)
    evidence_artifacts = [primary_artifact]
    evidence_artifacts.extend(
        _unique_artifact_paths(
            artifact_snapshot,
            ["heartbeat_status_file", "heartbeat_file", "heartbeat_log_file", "core_state_file"],
        )
    )
    evidence_artifacts = _dedupe_paths(evidence_artifacts)[:3]
    return (
        f"Right now Nova's heartbeat looks {status}. "
        f"The live proof I am using is core status `{str(runtime_snapshot.get('core_status') or 'unknown')}`, "
        f"heartbeat age `{heartbeat_text}`, and the runtime heartbeat artifacts "
        f"{_format_artifact_paths(evidence_artifacts)}."
    )


def _heartbeat_artifact_reply(core) -> str:
    artifact_snapshot = _runtime_artifact_snapshot(core)
    primary_artifact = _primary_heartbeat_artifact(artifact_snapshot)
    heartbeat_log = artifact_snapshot["artifacts"].get("heartbeat_log_file")
    core_state = artifact_snapshot["artifacts"].get("core_state_file")
    return (
        f"If the heartbeat goes stale again, I would inspect `{str(primary_artifact)}` first. "
        f"After that I would correlate it with `{str(heartbeat_log)}` and `{str(core_state)}` before deciding on any restart."
    )


def _runtime_artifact_grounding_reply(core) -> str:
    snapshot = _runtime_artifact_snapshot(core)
    artifacts = snapshot["artifacts"]
    primary_heartbeat = _primary_heartbeat_artifact(snapshot)
    return (
        f"I would start with `{str(artifacts['maintenance_state_file'])}`, `{str(primary_heartbeat)}`, "
        f"`{str(artifacts['core_state_file'])}`, and `{str(artifacts['guard_pid_file'])}`. "
        f"For timeline evidence I would pair those with `{str(artifacts['maintenance_log_file'])}` "
        f"and `{str(artifacts['guard_log_file'])}`."
    )


def _runtime_artifact_safe_step_reply(core) -> str:
    snapshot = _runtime_artifact_snapshot(core)
    artifacts = snapshot["artifacts"]
    primary_heartbeat = _primary_heartbeat_artifact(snapshot)
    return (
        f"The safest next operator step is to open `{str(artifacts['maintenance_state_file'])}` "
        f"and `{str(primary_heartbeat)}` read-only first, then correlate them with "
        f"`{str(artifacts['maintenance_log_file'])}` and `{str(artifacts['guard_log_file'])}` "
        "before restarting or editing anything. I am not claiming I already opened those files."
    )


def _tool_path_snapshot(core) -> dict:
    base_dir = Path(getattr(core, "BASE_DIR", Path.cwd()))
    service_path = base_dir / "services" / "nova_patching.py"
    wrapper_path = base_dir / "nova_core.py"
    service_text = ""
    wrapper_text = ""
    try:
        service_text = service_path.read_text(encoding="utf-8")
    except Exception:
        service_text = ""
    try:
        wrapper_text = wrapper_path.read_text(encoding="utf-8")
    except Exception:
        wrapper_text = ""
    return {
        "service_path": service_path,
        "wrapper_path": wrapper_path,
        "service_has_owner": "def approve_preview(" in service_text,
        "wrapper_has_tool": "def tool_patch_preview_approve(" in wrapper_text,
    }


def _tool_path_reply(core) -> str:
    snapshot = _tool_path_snapshot(core)
    if snapshot.get("service_has_owner"):
        return (
            f"Patch preview approval lives in `{snapshot['service_path']}` as `approve_preview(...)`. "
            f"The Nova tool wrapper is `{snapshot['wrapper_path']}` as `tool_patch_preview_approve(...)`."
        )
    if snapshot.get("wrapper_has_tool"):
        return (
            f"The clearest live owner I can confirm is `{snapshot['wrapper_path']}` as `tool_patch_preview_approve(...)`, "
            "and it delegates into the patching service path."
        )
    return "I could not confirm the patch preview approval owner from the current repo snapshot."


def _tool_path_safe_step_reply(core) -> str:
    snapshot = _tool_path_snapshot(core)
    service_path = snapshot["service_path"]
    return (
        f"The next safe operator step is to inspect the target preview report under `updates/previews`, "
        f"then use the governed approval path from `{service_path}` for that exact preview. "
        "I have not changed anything."
    )


def maybe_handle_deterministic_sequence(
    *,
    text: str,
    turns: list[tuple[str, str]],
    low: str,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    is_session_recap_request: Callable[[str], bool],
    session_recap_reply: Callable[[list[tuple[str, str]], str], str],
    is_assistant_name_query: Callable[[str], bool],
    assistant_name_reply: Callable[[str], str],
    is_developer_full_name_query: Callable[[str], bool],
    developer_full_name_reply: Callable[[], str],
    is_name_origin_question: Callable[[str], bool],
    is_student_data_attendance_rules_query: Callable[[str], bool],
    student_data_attendance_rules_reply: Callable[[], str],
    is_developer_profile_request: Callable[[str], bool],
    developer_profile_reply: Callable[[list[tuple[str, str]], str], str],
    is_conversational_clarification: Callable[[str], bool],
    clarification_reply: Callable[[list[tuple[str, str]]], str],
    is_location_request: Callable[[str], bool],
    location_reply: Callable[[], str],
    is_deep_search_followup_request: Callable[[str], bool],
    infer_research_query_from_turns: Callable[[list[tuple[str, str]]], str],
    build_grounded_answer: Callable[[str], str],
    build_local_topic_digest_answer: Callable[[str], str],
    is_groundable_factual_query: Callable[[str], bool],
    developer_color_reply: Callable[[list[tuple[str, str]]], str],
    developer_bilingual_reply: Callable[[list[tuple[str, str]]], str],
    color_reply: Callable[[list[tuple[str, str]]], str],
    animal_reply: Callable[[list[tuple[str, str]]], str],
    core,
    branch_group: str = "all",
) -> tuple[str, dict, str, int] | None:
    if branch_group not in {"all", "operational", "general"}:
        raise ValueError(f"Unsupported branch_group: {branch_group}")

    allow_general = branch_group in {"all", "general"}
    allow_operational = branch_group in {"all", "operational"}

    if allow_general and is_session_recap_request(text):
        trace("deterministic_reply", "matched", detail="session_recap")
        reply = session_recap_reply(turns, text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "session_recap",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "timed", 0
    if allow_general and is_assistant_name_query(text):
        trace("deterministic_reply", "matched", detail="assistant_name")
        reply = assistant_name_reply(text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "assistant_name",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "timed", 0
    if allow_general and is_developer_full_name_query(text):
        trace("deterministic_reply", "matched", detail="developer_full_name")
        reply = developer_full_name_reply()
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_identity",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "timed", 0
    if allow_general and ("do you remember our last chat session" in low or "remember our last chat" in low):
        trace("deterministic_reply", "matched", detail="memory_policy_explanation")
        reply = "I remember parts of prior chats only if they were saved to memory; I remember this live session context directly."
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "memory_policy",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "timed", 0
    if allow_general and is_name_origin_question(text):
        trace("deterministic_reply", "matched", detail="name_origin_query")
        story = core.get_name_origin_story().strip()
        if story:
            reply = f"Yes. {story}"
        else:
            reply = "I do not have a saved name-origin story yet. You can tell me with: remember this Nova ..."
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "name_origin",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": bool(story),
        }, "timed", 0
    if allow_operational and is_student_data_attendance_rules_query(text):
        trace("grounded_lookup", "matched", tool="student_data_attendance")
        reply = student_data_attendance_rules_reply()
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "student_data_attendance",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": "[source:" in reply.lower(),
        }, "timed", 0
    if allow_operational and is_developer_profile_request(text):
        trace("deterministic_reply", "matched", detail="developer_profile")
        reply = developer_profile_reply(turns, text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_profile",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_general and is_conversational_clarification(text):
        trace("deterministic_reply", "matched", detail="clarification_reply")
        reply = clarification_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "clarification_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_general and is_location_request(text):
        trace("deterministic_reply", "matched", detail="location_reply")
        reply = location_reply()
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "location",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_restart_advice_query(text):
        trace("deterministic_reply", "matched", detail="restart_advice")
        reply = _restart_advice_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "runtime_restart_advice",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_restart_condition_followup(text):
        trace("deterministic_reply", "matched", detail="restart_condition")
        reply = _restart_condition_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "runtime_restart_condition",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_queue_pressure_triage_query(text):
        trace("deterministic_reply", "matched", detail="queue_pressure_triage")
        reply = _queue_pressure_recommendation(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "queue_pressure_triage",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_queue_pressure_justify_followup(text):
        trace("deterministic_reply", "matched", detail="queue_pressure_justification")
        reply = _queue_pressure_justification(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "queue_pressure_justification",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_runtime_audit_query(text):
        trace("deterministic_reply", "matched", detail="runtime_audit")
        reply = _runtime_audit_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "runtime_audit",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_runtime_audit_evidence_followup(text):
        trace("deterministic_reply", "matched", detail="runtime_audit_evidence")
        reply = _runtime_audit_evidence_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "runtime_audit_evidence",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_maintenance_mode_truth_query(text):
        trace("deterministic_reply", "matched", detail="maintenance_mode_truth")
        reply = _maintenance_mode_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "maintenance_mode_truth",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_maintenance_mode_difference_followup(text):
        trace("deterministic_reply", "matched", detail="maintenance_mode_difference")
        reply = _maintenance_mode_difference_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "maintenance_mode_difference",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_storage_watch_truth_query(text):
        trace("deterministic_reply", "matched", detail="storage_watch_truth")
        reply = _storage_watch_truth_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "storage_watch_truth",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_storage_watch_warning_followup(text):
        trace("deterministic_reply", "matched", detail="storage_watch_warning")
        reply = _storage_watch_warning_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "storage_watch_warning",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_heartbeat_forensics_query(text):
        trace("deterministic_reply", "matched", detail="heartbeat_forensics")
        reply = _heartbeat_forensics_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "heartbeat_forensics",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_heartbeat_artifact_followup(text):
        trace("deterministic_reply", "matched", detail="heartbeat_artifact")
        reply = _heartbeat_artifact_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "heartbeat_artifact",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_runtime_artifact_grounding_query(text):
        trace("deterministic_reply", "matched", detail="runtime_artifact_grounding")
        reply = _runtime_artifact_grounding_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "runtime_artifact_grounding",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_runtime_artifact_safe_step_followup(text):
        trace("deterministic_reply", "matched", detail="runtime_artifact_safe_step")
        reply = _runtime_artifact_safe_step_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "runtime_artifact_safe_step",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_tool_path_disambiguation_query(text):
        trace("deterministic_reply", "matched", detail="tool_path_disambiguation")
        reply = _tool_path_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "tool_path_disambiguation",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_operational and _is_tool_path_safe_step_followup(text):
        trace("deterministic_reply", "matched", detail="tool_path_safe_step")
        reply = _tool_path_safe_step_reply(core)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "tool_path_safe_step",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_general and is_deep_search_followup_request(text):
        inferred = infer_research_query_from_turns(turns)
        query = inferred or text
        tool_started = time.perf_counter()
        grounded = build_grounded_answer(query, max_sources=2)
        tool_time_ms = int((time.perf_counter() - tool_started) * 1000)
        trace("timing", "completed", "tool_response", duration_ms=tool_time_ms, tool="web_research")
        trace("timing", "completed", "web_search", duration_ms=tool_time_ms, tool="web_research")
        if grounded:
            trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": query},
                "tool_result": reply,
                "grounded": True,
            }, "timed", tool_time_ms
        local_started = time.perf_counter()
        local_grounded = build_local_topic_digest_answer(query)
        tool_time_ms += int((time.perf_counter() - local_started) * 1000)
        trace("timing", "completed", "tool_response", duration_ms=tool_time_ms, tool="local_knowledge")
        if local_grounded:
            trace("grounded_lookup", "matched", tool="local_knowledge")
            reply = local_grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "local_knowledge",
                "tool_args": {"query": query},
                "tool_result": reply,
                "grounded": True,
            }, "timed", tool_time_ms
        trace("grounded_lookup", "missed", tool="web_research")
        reply = "I could not find additional grounded sources right now. Please try: web research <topic>"
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "web_research",
            "tool_args": {"query": query},
            "tool_result": reply,
            "grounded": False,
        }, "timed", tool_time_ms
    if allow_general and is_groundable_factual_query(text):
        tool_started = time.perf_counter()
        grounded = build_grounded_answer(text, max_sources=2)
        tool_time_ms = int((time.perf_counter() - tool_started) * 1000)
        trace("timing", "completed", "tool_response", duration_ms=tool_time_ms, tool="web_research")
        trace("timing", "completed", "web_search", duration_ms=tool_time_ms, tool="web_research")
        if grounded:
            trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }, "logged", tool_time_ms
        local_started = time.perf_counter()
        local_grounded = build_local_topic_digest_answer(text)
        tool_time_ms += int((time.perf_counter() - local_started) * 1000)
        trace("timing", "completed", "tool_response", duration_ms=tool_time_ms, tool="local_knowledge")
        if local_grounded:
            trace("grounded_lookup", "matched", tool="local_knowledge")
            reply = local_grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "local_knowledge",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }, "logged", tool_time_ms
        trace("grounded_lookup", "missed", tool="web_research")
        reply = "I couldn't find grounded sources for that yet. Please try: web research <your question>"
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "web_research",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": False,
        }, "timed", tool_time_ms
    if allow_general and core._is_developer_color_lookup_request(text):
        trace("deterministic_reply", "matched", detail="developer_color_reply")
        reply = developer_color_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_general and core._is_developer_bilingual_request(text):
        trace("deterministic_reply", "matched", detail="developer_bilingual_reply")
        reply = developer_bilingual_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_bilingual_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_general and core._is_color_lookup_request(text):
        trace("deterministic_reply", "matched", detail="color_reply")
        reply = color_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    if allow_general and ("what animals do i like" in low or "which animals do i like" in low):
        trace("deterministic_reply", "matched", detail="animal_reply")
        reply = animal_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "animal_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }, "logged", 0
    return None
