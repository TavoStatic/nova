from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Callable

import kidney
import nova_core
import nova_safety_envelope
import work_tree
from nova_safety_envelope import select_patch_candidate_definition_paths
from services.nova_patching import archive_preview_report as service_archive_preview_report
from services.nova_patching import bulk_archive_superseded_previews as service_bulk_archive_superseded_previews
from services.nova_patching import bulk_reject_orphaned_previews as service_bulk_reject_orphaned_previews
from services.nova_patching import patch_preview_summaries as service_patch_preview_summaries
from services.autonomy_orchestrator import AUTONOMY_ORCHESTRATOR_SERVICE
from services.autonomy_execution_gate import AUTONOMY_EXECUTION_GATE_SERVICE
from services.control_work_trees import CONTROL_WORK_TREES_SERVICE
from services.core_steward import build_core_steward_payload as service_build_core_steward_payload
from services.nova_control_action_dispatcher import NOVA_CONTROL_ACTION_DISPATCHER, autonomy_advisory_action_types
from services.nova_runtime_context import AUTONOMY_ORCHESTRATOR_LEDGER_FILE
from services.subconscious_work_tree_triage import SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE
from services.test_session_control import TEST_SESSION_CONTROL_SERVICE
from services.work_tree_signal_ingestion import WORK_TREE_SIGNAL_INGESTION_SERVICE
from work_tree_contracts import BranchStatus, TaskStatus


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
TEST_SESSIONS_ROOT = RUNTIME_DIR / "test_sessions"
TEST_SESSION_RUNNER_PY = ROOT / "scripts" / "run_test_session.py"
STATE_FILE = RUNTIME_DIR / "autonomy_maintenance_state.json"
MAINT_LOG = RUNTIME_DIR / "autonomy_maintenance.log"
AUTONOMY_ORCHESTRATOR_LEDGER = AUTONOMY_ORCHESTRATOR_LEDGER_FILE
LATEST_SUBCONSCIOUS = RUNTIME_DIR / "subconscious_runs" / "latest.json"
GENERATED_DEFS = TEST_SESSIONS_ROOT / "generated_definitions"
UPDATES_DIR = ROOT / "updates"

AUTO_APPLY_THRESHOLD = 0.90
PATCH_QUEUE_TREE_TITLE = "Patch Queue: governed review and apply"
PATCH_QUEUE_TREE_KIND = "patch_queue"
PATCH_QUEUE_TREE_SOURCE = "autonomy_maintenance"
PATCH_QUEUE_SOURCE_TYPE = "patch_queue_preview"
PATCH_QUEUE_BUCKET = "patch_queue"
PATCH_QUEUE_ALLOWED_TOOLS = ["patch_preview_approve", "patch_preview_apply", "patch_rollback", "read", "find"]
PATCH_QUEUE_EXECUTE_TOOLS = ["patch_preview_approve", "patch_preview_apply", "patch_rollback"]
PATCH_QUEUE_REVIEW_TOOLS = ["read", "find"]
PATCH_QUEUE_MAX_STEPS = 3
GENERATED_QUEUE_TREE_TITLE = "Generated Queue: governed self-repair"
GENERATED_QUEUE_TREE_KIND = "generated_queue"
GENERATED_QUEUE_TREE_SOURCE = "autonomy_maintenance"
GENERATED_QUEUE_SOURCE_TYPE = "generated_queue_item"
GENERATED_QUEUE_BUCKET = "generated_queue"
GENERATED_QUEUE_ALLOWED_TOOLS = ["generated_queue_run", "read", "find", "queue_status"]
GENERATED_QUEUE_EXECUTE_TOOLS = ["generated_queue_run"]
GENERATED_QUEUE_REVIEW_TOOLS = ["read", "find", "queue_status"]
GENERATED_QUEUE_MAX_STEPS = 4
ACTIVE_WORK_TREE_EXECUTE_TOOLS = ["health", "system_check", "queue_status", "pulse", "read", "ls", "find"]
ACTIVE_WORK_TREE_MAX_TREES = 8
ACTIVE_WORK_TREE_MAX_STEPS = 8
LEGACY_PATCH_UPDATE_TOOLS = {"patch_apply", "patch_rollback", "update_now"}
COMPLETE_TREE_VISIBLE_KEEP = 12
COMPLETE_TREE_ARCHIVE_MIN_AGE_SEC = 0
COMPLETE_TREE_PROTECTED_KINDS = {"patch_queue", "generated_queue", "signal_ingestion"}
EMPTY_ACTIVE_TREE_ARCHIVE_MIN_AGE_SEC = 3600
STALE_CLI_ACTIVE_TREE_ARCHIVE_MIN_AGE_SEC = 12 * 3600
STALE_CLI_ACTIVE_TREE_MAX_BRANCHES = 5
STALE_CLI_ACTIVE_TREE_MAX_OPEN_TASKS = 2
PROMOTED_PATCH_ENTRY_PREFIX = "runtime/test_sessions/promoted/"
PATCH_MANIFEST_NAME = "nova_patch.json"


def _append_log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} | {message}"
    print(line, flush=True)
    MAINT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(MAINT_LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _append_autonomy_orchestrator_ledger(row: dict) -> None:
    AUTONOMY_ORCHESTRATOR_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTONOMY_ORCHESTRATOR_LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row or {}), ensure_ascii=True) + "\n")


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _guard_health_for_orchestrator() -> dict:
    pid_file = RUNTIME_DIR / "guard_pid.json"
    lock_file = RUNTIME_DIR / "guard.lock"
    stop_file = RUNTIME_DIR / "guard.stop"
    pid = 0
    pid_live = False
    if pid_file.exists():
        try:
            payload = json.loads(pid_file.read_text(encoding="utf-8"))
            pid = int((payload or {}).get("pid", 0) or 0)
            if pid > 0:
                try:
                    import psutil

                    pid_live = bool(psutil.pid_exists(pid))
                except Exception:
                    pid_live = False
        except Exception:
            pid = 0

    status = "stopped"
    if pid_live:
        status = "running"
    elif stop_file.exists():
        status = "stopping"
    elif lock_file.exists() or pid_file.exists():
        status = "boot_timeout"
    return {
        "running": bool(pid_live),
        "status": status,
        "pid": pid or None,
        "lock_exists": lock_file.exists(),
        "stop_flag": stop_file.exists(),
    }


def _preflight_checks_for_orchestrator() -> list:
    try:
        import doctor as doctor_module

        return list(doctor_module.run_preflight() or [])
    except Exception:
        return []


def _core_steward_for_orchestrator(state: dict, kidney_summary: dict) -> dict:
    runtime_health = nova_core._core_health_runtime_health()
    pulse_payload = nova_core.build_pulse_payload()
    return service_build_core_steward_payload(
        preflight_checks=_preflight_checks_for_orchestrator(),
        runtime_health=runtime_health,
        pulse_payload=pulse_payload if isinstance(pulse_payload, dict) else {},
        autonomy_maintenance=state if isinstance(state, dict) else {},
        kidney_summary=kidney_summary if isinstance(kidney_summary, dict) else {},
    )


def _orchestrator_posture_band(core_steward: dict) -> str:
    score = _safe_int((core_steward or {}).get("score"), 0)
    level = str((core_steward or {}).get("level") or "").strip().lower()
    if level in {"repair", "red"} or score < 70:
        return "red"
    if level in {"watch", "yellow"} or score < 85:
        return "yellow"
    return "green"


def _work_tree_snapshot_for_orchestrator(work_tree_state: dict) -> dict:
    payload = dict(work_tree_state or {}) if isinstance(work_tree_state, dict) else {}
    counts = dict(payload.get("counts") or {}) if isinstance(payload.get("counts"), dict) else {}
    branches: list[dict] = []
    for tree in list(payload.get("trees") or [])[:64]:
        if not isinstance(tree, dict):
            continue
        tree_counts = dict(tree.get("counts") or {}) if isinstance(tree.get("counts"), dict) else {}
        branches.append(
            {
                "branch_id": str(tree.get("active_branch_id") or tree.get("tree_id") or ""),
                "title": str(tree.get("title") or ""),
                "status": str(tree.get("status") or ""),
                "owner": str(tree.get("kind") or ""),
                "age_min": _safe_int(tree.get("age_min") or tree_counts.get("oldest_open_age_min"), 0),
            }
        )
    return {
        "open_count": _safe_int(counts.get("open_tasks") or counts.get("pending") or counts.get("active"), 0),
        "working_count": _safe_int(counts.get("working"), 0),
        "blocked_count": _safe_int(counts.get("blocked"), 0),
        "stale_count": _safe_int(counts.get("stale"), 0),
        "oldest_open_age_min": _safe_int(counts.get("oldest_open_age_min"), 0),
        "branches": branches,
        "source_freshness_sec": 0,
    }


def _steward_posture_for_orchestrator(core_steward: dict) -> dict:
    runtime = dict((core_steward or {}).get("runtime") or {}) if isinstance((core_steward or {}).get("runtime"), dict) else {}
    alerts = list((core_steward or {}).get("alerts") or []) if isinstance((core_steward or {}).get("alerts"), list) else []
    core_state = dict(runtime.get("core_state") or {}) if isinstance(runtime.get("core_state"), dict) else {}
    heartbeat = dict(runtime.get("heartbeat") or {}) if isinstance(runtime.get("heartbeat"), dict) else {}
    critical_alerts = 0
    if core_state.get("ok") is False or heartbeat.get("ok") is False:
        critical_alerts += 1
    critical_alerts += sum(
        1
        for alert in alerts
        if "critical" in str(alert or "").strip().lower()
        or "failed" in str(alert or "").strip().lower()
    )
    score = _safe_int((core_steward or {}).get("score"), 0)
    return {
        "health_score": score,
        "alert_count": len(alerts),
        "critical_alerts": critical_alerts,
        "pass_ratio": round(max(0.0, min(1.0, score / 100.0)), 4),
        "posture_band": _orchestrator_posture_band(core_steward),
        "source_freshness_sec": 0,
    }


def _queue_pressure_for_orchestrator(generated_queue: dict, state: dict | None = None) -> dict:
    queue = dict(generated_queue or {}) if isinstance(generated_queue, dict) else {}
    current_state = dict(state or {}) if isinstance(state, dict) else {}
    patch_sync = (
        dict(current_state.get("last_patch_queue_sync") or {})
        if isinstance(current_state.get("last_patch_queue_sync"), dict)
        else {}
    )
    generated_pending = _safe_int(queue.get("open_count") or queue.get("count"), 0)
    generated_actionable = _safe_int(queue.get("actionable_count"), 0)
    generated_blocked = _safe_int(queue.get("blocked_count"), 0)
    patch_apply_ready = _safe_int(patch_sync.get("apply_ready_count"), 0)
    patch_approve_ready = _safe_int(patch_sync.get("approve_ready_count"), 0)
    patch_ready = patch_apply_ready + patch_approve_ready
    pending = generated_pending + patch_ready
    actionable = generated_actionable + patch_ready
    blocked = generated_blocked
    aging = _safe_int(queue.get("drift_count"), 0) + _safe_int(queue.get("warning_count"), 0)
    if actionable > 0 or aging > 0:
        pressure_band = "high"
    elif pending > 0 or blocked > 0:
        pressure_band = "medium"
    else:
        pressure_band = "low"
    return {
        "pending_count": pending,
        "aging_items_count": aging,
        "high_priority_count": actionable,
        "pressure_band": pressure_band,
        "approved_eligible_previews": 0,
        "generated_pending_count": generated_pending,
        "generated_actionable_count": generated_actionable,
        "generated_blocked_count": generated_blocked,
        "patch_apply_ready_count": patch_apply_ready,
        "patch_approve_ready_count": patch_approve_ready,
        "patch_ready_count": patch_ready,
        "source_freshness_sec": 0,
    }


def _runtime_guard_status_for_orchestrator(core_steward: dict, guard_health: dict) -> dict:
    runtime = dict((core_steward or {}).get("runtime") or {}) if isinstance((core_steward or {}).get("runtime"), dict) else {}
    core_state = dict(runtime.get("core_state") or {}) if isinstance(runtime.get("core_state"), dict) else {}
    heartbeat = dict(runtime.get("heartbeat") or {}) if isinstance(runtime.get("heartbeat"), dict) else {}
    core_running = core_state.get("ok")
    if core_running is None:
        core_running = heartbeat.get("ok")
    guard = dict(guard_health or {}) if isinstance(guard_health, dict) else {}
    guard_running = guard.get("running")
    if guard_running is None:
        status = str(guard.get("status") or guard.get("state") or "").strip().lower()
        if status in {"ok", "ready", "healthy", "running", "active"}:
            guard_running = True
        elif status in {"stopped", "inactive", "not_running", "failed", "error", "degraded", "boot_timeout"}:
            guard_running = False
    return {
        "guard_running": guard_running,
        "core_running": core_running,
        "webui_running": True,
        "restart_in_progress": False,
        "stop_flag": bool(guard.get("stop_flag", False)),
        "source_freshness_sec": 0,
    }


def _autonomy_policy_settings() -> dict:
    try:
        policy = nova_core.load_policy()
    except Exception:
        policy = {}
    settings = dict((policy or {}).get("autonomy") or {}) if isinstance((policy or {}).get("autonomy"), dict) else {}
    return settings


def _autonomy_policy_bool(settings: dict, *names: str, default: bool = False) -> bool:
    for name in names:
        if name in settings:
            return bool(settings.get(name))
    return bool(default)


def _autonomy_policy_list(settings: dict, name: str, default: list[str]) -> list[str]:
    value = settings.get(name)
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    return list(default)


def _autonomy_execution_mode(settings: dict | None = None) -> str:
    settings = dict(settings or _autonomy_policy_settings())
    mode = str(settings.get("mode") or settings.get("execution_mode") or "advisory").strip().lower()
    if mode in {"canary", "execute"}:
        return mode
    return "advisory"


def _autonomy_execution_enabled(settings: dict | None = None) -> bool:
    settings = dict(settings or _autonomy_policy_settings())
    if _autonomy_execution_mode(settings) not in {"canary", "execute"}:
        return False
    return _autonomy_policy_bool(settings, "execute_enabled", "execution_enabled", "autonomy_execute_enabled", default=False)


def _legacy_maintenance_execution_enabled(settings: dict | None = None) -> bool:
    settings = dict(settings or _autonomy_policy_settings())
    mode = _autonomy_execution_mode(settings)
    if mode in {"canary", "execute"} and _autonomy_policy_bool(settings, "orchestrator_owns_execution", default=True):
        return _autonomy_policy_bool(settings, "legacy_maintenance_execution_enabled", default=False)
    return _autonomy_policy_bool(settings, "legacy_maintenance_execution_enabled", default=True)


def _policy_snapshot_for_orchestrator() -> dict:
    settings = _autonomy_policy_settings()
    advisory_actions = list(autonomy_advisory_action_types())
    requires_ack_default = ["update_now_dry_run"]
    mode = _autonomy_execution_mode(settings)
    execute_enabled = _autonomy_execution_enabled(settings)
    return {
        "autonomy_enabled": _autonomy_policy_bool(settings, "enabled", "autonomy_enabled", default=True),
        "mode": mode,
        "allow_execute_mode": bool(execute_enabled),
        "execute_enabled": bool(execute_enabled),
        "allowed_actions": _autonomy_policy_list(settings, "allowed_actions", advisory_actions),
        "blocked_actions": _autonomy_policy_list(settings, "blocked_actions", []),
        "execute_allowed_actions": _autonomy_policy_list(settings, "execute_allowed_actions", []),
        "execute_allowed_action_groups": _autonomy_policy_list(settings, "execute_allowed_action_groups", []),
        "execute_blocked_actions": _autonomy_policy_list(settings, "execute_blocked_actions", []),
        "canary_allowed_actions": _autonomy_policy_list(settings, "canary_allowed_actions", []),
        "canary_allowed_action_groups": _autonomy_policy_list(settings, "canary_allowed_action_groups", []),
        "quiet_hours_active": False,
        "requires_operator_ack_for": _autonomy_policy_list(settings, "requires_operator_ack_for", requires_ack_default),
        "operator_ack_present": bool(settings.get("operator_ack_present", False)),
        "confidence_threshold": _safe_float(settings.get("confidence_threshold"), 0.55),
        "execute_min_confidence": _safe_float(settings.get("execute_min_confidence", settings.get("confidence_threshold")), 0.55),
        "cooldown_sec": _safe_int(settings.get("cooldown_sec"), 180),
        "orchestrator_owns_execution": _autonomy_policy_bool(settings, "orchestrator_owns_execution", default=False),
        "legacy_maintenance_execution_enabled": _legacy_maintenance_execution_enabled(settings),
        "source_freshness_sec": 0,
    }


def _latest_subconscious_report_for_triage() -> dict:
    try:
        if not LATEST_SUBCONSCIOUS.exists():
            return {}
        stat = LATEST_SUBCONSCIOUS.stat()
        report = json.loads(LATEST_SUBCONSCIOUS.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            return {}
        report["_source_freshness_sec"] = max(0, int(time.time() - stat.st_mtime))
        return report
    except Exception:
        return {}


def _triage_runtime_context_for_orchestrator(state: dict | None, generated_queue: dict, kidney_summary: dict | None) -> dict:
    current_state = dict(state or {}) if isinstance(state, dict) else {}
    queue = dict(generated_queue or {}) if isinstance(generated_queue, dict) else {}
    work_tree_cycle = (
        dict(current_state.get("last_work_tree_cycle") or {})
        if isinstance(current_state.get("last_work_tree_cycle"), dict)
        else {}
    )
    last_generated_run = (
        dict(current_state.get("last_generated_queue_run") or {})
        if isinstance(current_state.get("last_generated_queue_run"), dict)
        else {}
    )
    kidney_state = dict(kidney_summary or {}) if isinstance(kidney_summary, dict) else {}
    return {
        "last_regression_status": str(current_state.get("last_regression_status") or "").strip(),
        "generated_queue_status": str(queue.get("status") or last_generated_run.get("status") or "").strip(),
        "queue_open_count": _safe_int(queue.get("open_count"), _safe_int(last_generated_run.get("queue_open_count"), 0)),
        "work_tree_status": str(work_tree_cycle.get("status") or "").strip(),
        "work_tree_executed_count": _safe_int(work_tree_cycle.get("executed_count"), 0),
        "work_tree_tree_count": _safe_int(work_tree_cycle.get("tree_count"), 0),
        "kidney_mode": str(kidney_state.get("mode") or current_state.get("kidney_mode") or "").strip(),
        "kidney_candidate_count": _safe_int(kidney_state.get("candidate_count"), 0),
    }


def _max_score(scores: dict, key: str, score: float) -> None:
    clean_key = str(key or "").strip()
    if not clean_key:
        return
    scores[clean_key] = round(max(_safe_float(scores.get(clean_key), 0.0), max(0.0, min(1.0, float(score or 0.0)))), 4)


def _triage_signal_from_priority(family: dict, priority: dict, runtime_context: dict) -> dict:
    family_id = str(family.get("family_id") or priority.get("family_id") or "").strip()
    target_seam = str(priority.get("seam") or priority.get("target_seam") or family.get("target_seam") or "").strip()
    signal_name = str(priority.get("signal") or priority.get("signal_name") or "").strip()
    suggested_test_name = str(priority.get("suggested_test_name") or priority.get("test_name") or "").strip()
    rationale = str(priority.get("rationale") or "").strip()
    urgency = str(priority.get("urgency") or "medium").strip() or "medium"
    robustness = _safe_float(priority.get("robustness", priority.get("robustness_score")), 0.0)
    if not target_seam or not signal_name:
        return {}
    return SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
        family_id=family_id,
        target_seam=target_seam,
        signal_name=signal_name,
        suggested_test_name=suggested_test_name,
        rationale=rationale,
        urgency=urgency,
        robustness=robustness,
        variation_results=list(family.get("variation_results") or []) if isinstance(family.get("variation_results"), list) else [],
        runtime_context=runtime_context,
    )


def _triage_lane_key(payload: dict) -> str:
    seam = str(payload.get("target_seam") or "").strip().lower()
    family_id = str(payload.get("family_id") or "").strip().lower()
    if "patch" in seam or "patch" in family_id:
        return "patch_queue"
    return "generated_queue"


def _queue_owner_hints(generated_queue: dict) -> dict:
    queue = dict(generated_queue or {}) if isinstance(generated_queue, dict) else {}
    owner_by_branch: dict[str, dict] = {}
    seen: set[str] = set()
    queue_items = []
    if isinstance(queue.get("next_item"), dict):
        queue_items.append(dict(queue.get("next_item") or {}))
    queue_items.extend([dict(item) for item in list(queue.get("items") or []) if isinstance(item, dict)][:20])
    for item in queue_items:
        file_name = str(item.get("file") or "").strip()
        if not file_name or file_name in seen:
            continue
        seen.add(file_name)
        highest_priority = item.get("highest_priority")
        priority = dict(highest_priority) if isinstance(highest_priority, dict) else {}
        if not priority and isinstance(item.get("training_priorities"), list) and item.get("training_priorities"):
            first_priority = (item.get("training_priorities") or [{}])[0]
            priority = dict(first_priority) if isinstance(first_priority, dict) else {}
        seam = str(priority.get("seam") or priority.get("target_seam") or "").strip()
        signal_name = str(priority.get("signal") or "").strip()
        if not seam and not signal_name:
            continue
        owner = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.classify_owner(signal_name, seam)
        owner_by_branch[f"generated:{file_name}"] = {
            "source": "generated_queue",
            "file": file_name,
            "preferred_owner": str(owner.get("preferred_owner") or "").strip(),
            "route_hint": str(owner.get("route_hint") or "").strip(),
            "target_seam": seam,
            "signal": signal_name,
            "robustness": _safe_float(priority.get("robustness", priority.get("robustness_score")), 0.0),
        }
    return owner_by_branch


def _triage_hints_for_orchestrator(
    core_steward: dict,
    generated_queue: dict,
    *,
    latest_report: dict | None = None,
    state: dict | None = None,
    kidney_summary: dict | None = None,
) -> dict:
    pulse = dict((core_steward or {}).get("pulse") or {}) if isinstance((core_steward or {}).get("pulse"), dict) else {}
    queue = dict(generated_queue or {}) if isinstance(generated_queue, dict) else {}
    fallback_score = _safe_float(pulse.get("fallback_overuse_score"), 0.0)
    drift_score = min(1.0, _safe_int(queue.get("drift_count"), 0) / 10.0)
    report_source = latest_report if latest_report is not None else _latest_subconscious_report_for_triage()
    report = dict(report_source or {}) if isinstance(report_source, dict) else {}
    source_freshness_sec = _safe_int(report.get("_source_freshness_sec"), 0)
    runtime_context = _triage_runtime_context_for_orchestrator(state, queue, kidney_summary)

    likely_owner_by_branch = _queue_owner_hints(queue)
    seam_pressure_scores = {
        "fallback_overuse": fallback_score,
        "generated_queue_drift": drift_score,
    }
    owner_pressure_scores: dict[str, float] = {}
    lane_pressure_scores: dict[str, float] = {}
    review_contract_pressure_scores: dict[str, float] = {}
    top_candidates: list[dict] = []
    approved_review_count = 0
    rejected_review_count = 0

    for family in [dict(item) for item in list(report.get("families") or []) if isinstance(item, dict)]:
        priorities = list(family.get("training_priorities") or []) if isinstance(family.get("training_priorities"), list) else []
        for priority in [dict(item) for item in priorities if isinstance(item, dict)]:
            signal = _triage_signal_from_priority(family, priority, runtime_context)
            payload = dict(signal.get("payload") or {}) if isinstance(signal.get("payload"), dict) else {}
            if not payload:
                continue
            gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)
            robustness = _safe_float(payload.get("robustness"), 0.0)
            seam = str(payload.get("target_seam") or "").strip()
            signal_name = str(payload.get("signal") or "").strip()
            owner = str(payload.get("preferred_owner") or "").strip()
            review_contract = str(payload.get("review_contract") or "").strip()
            lane_key = _triage_lane_key(payload)
            approved = bool(gate.get("approved"))
            if approved:
                approved_review_count += 1
                _max_score(lane_pressure_scores, lane_key, robustness)
                _max_score(lane_pressure_scores, "generated_queue", robustness)
                _max_score(owner_pressure_scores, owner, robustness)
                _max_score(review_contract_pressure_scores, review_contract, robustness)
            else:
                rejected_review_count += 1
            _max_score(seam_pressure_scores, seam or signal_name, robustness)
            branch_key = f"subconscious:{str(payload.get('family_id') or '').strip()}:{seam}:{signal_name}"
            likely_owner_by_branch[branch_key] = {
                "source": "subconscious_work_tree_triage",
                "preferred_owner": owner,
                "route_hint": str(payload.get("route_hint") or "").strip(),
                "review_contract": review_contract,
                "target_seam": seam,
                "signal": signal_name,
                "robustness": round(robustness, 4),
                "gate_status": str(gate.get("status") or "").strip(),
                "approved": approved,
            }
            top_candidates.append(
                {
                    "family_id": str(payload.get("family_id") or "").strip(),
                    "target_seam": seam,
                    "signal": signal_name,
                    "preferred_owner": owner,
                    "route_hint": str(payload.get("route_hint") or "").strip(),
                    "review_contract": review_contract,
                    "lane": lane_key,
                    "robustness": round(robustness, 4),
                    "urgency": str(payload.get("urgency") or "").strip(),
                    "gate_status": str(gate.get("status") or "").strip(),
                    "approved": approved,
                    "suggested_test_name": str(payload.get("suggested_test_name") or "").strip(),
                    "next_task": str(signal.get("next_task") or "").strip(),
                }
            )

    top_candidates.sort(
        key=lambda item: (
            0 if bool(item.get("approved")) else 1,
            -_safe_float(item.get("robustness"), 0.0),
            str(item.get("target_seam") or ""),
            str(item.get("signal") or ""),
        )
    )
    confidence_basis = [
        _safe_float(item.get("robustness"), 0.0)
        for item in top_candidates
        if bool(item.get("approved"))
    ]
    confidence = round(max(0.6, min(1.0, sum(confidence_basis) / len(confidence_basis))) if confidence_basis else 0.6, 4)
    return {
        "likely_owner_by_branch": likely_owner_by_branch,
        "seam_pressure_scores": seam_pressure_scores,
        "owner_pressure_scores": owner_pressure_scores,
        "lane_pressure_scores": lane_pressure_scores,
        "review_contract_pressure_scores": review_contract_pressure_scores,
        "top_triage_candidates": top_candidates[:8],
        "approved_review_count": approved_review_count,
        "rejected_review_count": rejected_review_count,
        "confidence": confidence,
        "source": "subconscious_work_tree_triage" if top_candidates else "core_steward_pulse",
        "source_freshness_sec": source_freshness_sec,
    }


def _last_action_context_for_orchestrator(state: dict) -> dict:
    last_execution = (
        dict((state or {}).get("last_autonomy_execution") or {})
        if isinstance((state or {}).get("last_autonomy_execution"), dict)
        else {}
    )
    last_orchestrator = (
        dict((state or {}).get("last_autonomy_orchestrator") or {})
        if isinstance((state or {}).get("last_autonomy_orchestrator"), dict)
        else {}
    )
    action = dict(last_orchestrator.get("action") or {}) if isinstance(last_orchestrator.get("action"), dict) else {}
    now_epoch = time.time()
    cooldown_until = _safe_float(last_execution.get("cooldown_until_epoch"), 0.0)
    cooldown_remaining = max(0, int(cooldown_until - now_epoch)) if cooldown_until else 0
    execution_action_type = str(last_execution.get("action_type") or "").strip()
    return {
        "last_action_type": execution_action_type or str(action.get("act") or ""),
        "last_target_id": str(last_execution.get("target_id") or ""),
        "last_action_at_utc": str(last_execution.get("created_at_utc") or last_orchestrator.get("created_at_utc") or last_orchestrator.get("ts") or ""),
        "cooldown_active": bool(cooldown_remaining > 0),
        "cooldown_remaining_sec": cooldown_remaining,
        "last_result": str(last_execution.get("result") or "unknown"),
        "source_freshness_sec": 0,
    }


def _autonomy_orchestrator_input_envelope(
    *,
    state: dict,
    core_steward: dict,
    work_tree_state: dict,
    generated_queue: dict,
    guard_health: dict,
    latest_report: dict | None = None,
    kidney_summary: dict | None = None,
    policy_snapshot: dict | None = None,
) -> dict:
    return {
        "cycle_id": f"autonomy-maintenance-{time.strftime('%Y%m%d%H%M%S')}",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "work_tree_snapshot": _work_tree_snapshot_for_orchestrator(work_tree_state),
        "steward_posture": _steward_posture_for_orchestrator(core_steward),
        "queue_pressure": _queue_pressure_for_orchestrator(generated_queue, state),
        "runtime_guard_status": _runtime_guard_status_for_orchestrator(core_steward, guard_health),
        "policy_snapshot": dict(policy_snapshot or _policy_snapshot_for_orchestrator()),
        "triage_hints": _triage_hints_for_orchestrator(
            core_steward,
            generated_queue,
            latest_report=latest_report,
            state=state,
            kidney_summary=kidney_summary,
        ),
        "last_action_context": _last_action_context_for_orchestrator(state),
    }


def _run_autonomy_orchestrator_advisory(state: dict, kidney_summary: dict) -> dict:
    core_steward = _core_steward_for_orchestrator(state, kidney_summary)
    work_tree_state = CONTROL_WORK_TREES_SERVICE.payload(
        list_visual_trees_fn=work_tree.list_visual_trees,
        limit=64,
    )
    generated_queue = _generated_work_queue(limit=200)
    guard_health = _guard_health_for_orchestrator()
    policy_snapshot = _policy_snapshot_for_orchestrator()
    latest_report = _latest_subconscious_report_for_triage()
    requested_mode = "execute" if bool(policy_snapshot.get("execute_enabled")) else "advisory"
    AUTONOMY_ORCHESTRATOR_SERVICE.set_mode(requested_mode, policy_snapshot)
    packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_next_action(
        _autonomy_orchestrator_input_envelope(
            state=state,
            core_steward=core_steward,
            work_tree_state=work_tree_state,
            generated_queue=generated_queue,
            guard_health=guard_health,
            latest_report=latest_report,
            kidney_summary=kidney_summary,
            policy_snapshot=policy_snapshot,
        ),
        record_ledger_fn=_append_autonomy_orchestrator_ledger,
    )
    execution = _execute_autonomy_recommendation(state, packet, policy_snapshot)
    recommended_action = dict(packet.get("recommended_action") or {}) if isinstance(packet.get("recommended_action"), dict) else {}
    state["last_autonomy_orchestrator"] = {
        "ts": str(((packet.get("ledger") or {}).get("row") or {}).get("ts") or ""),
        "created_at_utc": str(packet.get("created_at_utc") or ""),
        "mode": str(packet.get("mode") or ""),
        "decision_type": str(packet.get("decision_type") or ""),
        "decision": str(packet.get("decision") or ""),
        "recommended_action": recommended_action,
        "confidence": _safe_float(packet.get("confidence"), 0.0),
        "action": dict(packet.get("action") or {}),
        "reason": str(packet.get("reason") or ""),
        "explain_text": str(packet.get("explain_text") or ""),
        "rejection_reasons": list(packet.get("rejection_reasons") or []),
        "ledger_status": str((packet.get("ledger") or {}).get("status") or ""),
        "execution": execution,
    }
    packet["execution"] = execution
    return packet


def _run_subconscious_pack() -> tuple[bool, str]:
    label = "phase1_auto"
    cmd = [str(VENV_PY), str(ROOT / "subconscious_runner.py"), "--label", label]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            return False, output[-2000:]
        return True, output[-2000:]
    except Exception as exc:
        return False, str(exc)


def _available_test_session_definitions(limit: int = 80) -> list[dict]:
    return TEST_SESSION_CONTROL_SERVICE.available_test_session_definitions(
        TEST_SESSION_CONTROL_SERVICE.all_test_session_definition_roots(
            base_dir=ROOT,
            runtime_dir=RUNTIME_DIR,
        ),
        limit=limit,
    )


def _resolve_test_session_definition(session_name: str) -> Path | None:
    return TEST_SESSION_CONTROL_SERVICE.resolve_test_session_definition(
        session_name,
        _available_test_session_definitions(500),
    )


def _test_session_report_summaries(limit: int = 24) -> list[dict]:
    return TEST_SESSION_CONTROL_SERVICE.test_session_report_summaries(TEST_SESSIONS_ROOT, limit=limit)


def _generated_work_queue(limit: int = 24) -> dict:
    definitions = _available_test_session_definitions(500)
    return TEST_SESSION_CONTROL_SERVICE.generated_work_queue(
        definitions,
        _test_session_report_summaries(max(200, len(definitions) * 2)),
        limit=limit,
        runtime_dir=RUNTIME_DIR,
    )


def _run_test_session_definition(session_file: str) -> tuple[bool, str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.run_test_session_definition(
        session_file,
        runner_path=TEST_SESSION_RUNNER_PY,
        venv_python=VENV_PY,
        base_dir=ROOT,
        resolve_definition_fn=_resolve_test_session_definition,
        available_definitions_fn=_available_test_session_definitions,
        report_summaries_fn=_test_session_report_summaries,
        subprocess_run=subprocess.run,
    )


def _run_next_generated_work_queue_item() -> tuple[bool, str, dict]:
    return TEST_SESSION_CONTROL_SERVICE.run_next_generated_work_queue_item(
        generated_work_queue_fn=_generated_work_queue,
        run_test_session_definition_fn=_run_test_session_definition,
    )


def _record_generated_queue_run(state: dict, ok: bool, msg: str, extra: dict | None = None) -> dict:
    selected = dict((extra or {}).get("selected") or {})
    latest_report = dict((extra or {}).get("latest_report") or {})
    work_queue = dict((extra or {}).get("work_queue") or {})
    if not selected and isinstance(work_queue.get("next_item"), dict):
        selected = dict(work_queue.get("next_item") or {})
    raw_msg = str(msg or "")
    if str(work_queue.get("status") or "").strip():
        status = str(work_queue.get("status") or "").strip()
    elif raw_msg == "generated_work_queue_clear":
        status = "clear"
    elif raw_msg == "generated_work_queue_blocked":
        status = "blocked"
    else:
        status = "ok" if ok else "failed"
    payload = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "message": str(msg or ""),
        "selected_file": str(selected.get("file") or ""),
        "selected_status": str(selected.get("latest_status") or ""),
        "latest_report_status": str(latest_report.get("status") or ""),
        "latest_report_run_id": str(latest_report.get("run_id") or ""),
        "queue_open_count": int(work_queue.get("open_count", 0) or 0),
        "queue_actionable_count": int(work_queue.get("actionable_count", 0) or 0),
        "queue_blocked_count": int(work_queue.get("blocked_count", 0) or 0),
        "queue_blocked_reason_counts": dict(work_queue.get("blocked_reason_counts") or {}) if isinstance(work_queue.get("blocked_reason_counts"), dict) else {},
        "queue_blocked_files": list(work_queue.get("blocked_files") or []) if isinstance(work_queue.get("blocked_files"), list) else [],
        "queue_count": int(work_queue.get("count", 0) or 0),
    }
    state["last_generated_queue_run"] = payload
    return payload


class _MaintenancePatchControlService:
    @staticmethod
    def patch_control_state(*_args, **_kwargs) -> dict:
        return {"ok": False, "status": "unavailable", "source": "autonomy_maintenance"}

    @staticmethod
    def patch_preview_show(*_args, **_kwargs) -> tuple[bool, str, dict, str]:
        return False, "patch_preview_show_unavailable_in_maintenance", {}, "patch_preview_show_unavailable_in_maintenance"

    @staticmethod
    def patch_preview_decision(*_args, **_kwargs) -> tuple[bool, str, dict, str]:
        return False, "patch_preview_decision_unavailable_in_maintenance", {}, "patch_preview_decision_unavailable_in_maintenance"

    @staticmethod
    def patch_preview_apply(*_args, **_kwargs) -> tuple[bool, str, dict, str]:
        return False, "patch_preview_apply_unavailable_in_maintenance", {}, "patch_preview_apply_unavailable_in_maintenance"

    @staticmethod
    def patch_preview_entry(*_args, **_kwargs) -> dict:
        return {}


def _unsupported_control_action(payload: dict) -> tuple[bool, str, dict, str]:
    action = str((payload or {}).get("_action") or (payload or {}).get("action") or "control_action").strip()
    msg = f"{action}_unavailable_in_autonomy_maintenance"
    return False, msg, {}, msg


def _maintenance_pulse_status_action(_payload: dict) -> tuple[bool, str, dict, str]:
    try:
        pulse = nova_core.build_pulse_payload()
    except Exception as exc:
        msg = f"pulse_status_failed:{exc}"
        return False, msg, {}, msg
    return True, "pulse_status_ok", {"pulse": pulse if isinstance(pulse, dict) else {}}, "pulse_status_ok"


def _maintenance_generated_queue_run_next_action(_payload: dict) -> tuple[bool, str, dict, str]:
    return TEST_SESSION_CONTROL_SERVICE.generated_queue_run_next_action(
        run_next_generated_work_queue_item_fn=_run_next_generated_work_queue_item,
    )


def _maintenance_generated_queue_investigate_action(_payload: dict) -> tuple[bool, str, dict, str]:
    return False, "generated_queue_investigate_requires_http_session_scope", {}, "generated_queue_investigate_requires_http_session_scope"


def _maintenance_patch_queue_run_next_action(_payload: dict, state: dict) -> tuple[bool, str, dict, str]:
    try:
        cycle = _run_patch_queue_work_tree_cycle(state, max_steps=1)
    except Exception as exc:
        msg = f"patch_queue_run_next_failed:{exc}"
        return False, msg, {}, msg
    status = str((cycle or {}).get("status") or "unknown").strip() or "unknown"
    msg = f"patch_queue_run_next_{status}"
    return status not in {"failed", "error"}, msg, {"cycle": cycle if isinstance(cycle, dict) else {}}, msg


def _maintenance_active_work_tree_run_next_action(_payload: dict, state: dict) -> tuple[bool, str, dict, str]:
    try:
        cycle = _run_active_work_tree_cycle(state, max_steps=1)
    except Exception as exc:
        msg = f"active_work_tree_run_next_failed:{exc}"
        return False, msg, {}, msg
    status = str((cycle or {}).get("status") or "unknown").strip() or "unknown"
    msg = f"active_work_tree_run_next_{status}"
    return status not in {"failed", "error"}, msg, {"cycle": cycle if isinstance(cycle, dict) else {}}, msg


def _dispatch_autonomy_control_action(action_type: str, payload: dict, events: list[dict], state: dict | None = None) -> tuple[bool, str, dict]:
    runtime_state = state if isinstance(state, dict) else {}

    def _record_event(act: str, status: str, detail: str, event_payload: dict) -> None:
        events.append(
            {
                "act": str(act or ""),
                "status": str(status or ""),
                "detail": str(detail or ""),
                "payload": dict(event_payload or {}) if isinstance(event_payload, dict) else {},
            }
        )

    return NOVA_CONTROL_ACTION_DISPATCHER.dispatch_control_action(
        str(action_type or ""),
        dict(payload or {}),
        patch_control_service=_MaintenancePatchControlService(),
        patch_status_payload_fn=lambda: {"ok": False, "status": "unavailable"},
        patch_preview_summaries_fn=lambda _limit=40: [],
        patch_action_readiness_payload_fn=lambda _patch: {"ready": False},
        patch_preview_target_fn=lambda _payload, _previews=None: {},
        show_preview_fn=lambda _target: {},
        approve_preview_fn=lambda _target, note="": False,
        reject_preview_fn=lambda _target, note="": False,
        patch_apply_fn=lambda *_args, **_kwargs: {"ok": False, "error": "patch_apply_unavailable_in_maintenance"},
        updates_dir=UPDATES_DIR,
        refresh_status_action_fn=_unsupported_control_action,
        device_location_update_action_fn=_unsupported_control_action,
        device_location_clear_action_fn=_unsupported_control_action,
        patch_preview_list_action_fn=_unsupported_control_action,
        pulse_status_action_fn=_maintenance_pulse_status_action,
        update_now_dry_run_action_fn=_unsupported_control_action,
        update_now_confirm_action_fn=_unsupported_control_action,
        update_now_cancel_action_fn=_unsupported_control_action,
        runtime_artifact_show_action_fn=_unsupported_control_action,
        guard_control_action_fn=_unsupported_control_action,
        core_runtime_action_fn=_unsupported_control_action,
        autonomy_runtime_action_fn=_unsupported_control_action,
        test_session_run_action_fn=_unsupported_control_action,
        generated_pack_run_action_fn=_unsupported_control_action,
        generated_queue_run_next_action_fn=_maintenance_generated_queue_run_next_action,
        generated_queue_investigate_action_fn=_maintenance_generated_queue_investigate_action,
        patch_queue_run_next_action_fn=lambda event_payload: _maintenance_patch_queue_run_next_action(event_payload, runtime_state),
        active_work_tree_run_next_action_fn=lambda event_payload: _maintenance_active_work_tree_run_next_action(event_payload, runtime_state),
        real_world_task_create_action_fn=_unsupported_control_action,
        backend_command_list_action_fn=_unsupported_control_action,
        backend_command_run_action_fn=_unsupported_control_action,
        operator_prompt_action_fn=lambda event_payload: (False, "operator_prompt_unavailable_in_maintenance", {}, "operator_prompt_unavailable_in_maintenance", event_payload),
        session_delete_action_fn=_unsupported_control_action,
        policy_allow_action_fn=_unsupported_control_action,
        policy_remove_action_fn=_unsupported_control_action,
        web_mode_action_fn=_unsupported_control_action,
        memory_scope_set_action_fn=_unsupported_control_action,
        search_provider_action_fn=_unsupported_control_action,
        search_provider_toggle_action_fn=_unsupported_control_action,
        search_endpoint_set_action_fn=_unsupported_control_action,
        search_provider_priority_set_action_fn=_unsupported_control_action,
        search_endpoint_probe_action_fn=_unsupported_control_action,
        chat_user_list_action_fn=_unsupported_control_action,
        chat_user_upsert_action_fn=_unsupported_control_action,
        chat_user_delete_action_fn=_unsupported_control_action,
        pipeline_note_append_action_fn=_unsupported_control_action,
        pipeline_create_action_fn=_unsupported_control_action,
        pipeline_start_action_fn=_unsupported_control_action,
        pipeline_pause_action_fn=_unsupported_control_action,
        pipeline_update_action_fn=_unsupported_control_action,
        pipeline_population_upsert_action_fn=_unsupported_control_action,
        pipeline_archive_action_fn=_unsupported_control_action,
        self_check_action_fn=_unsupported_control_action,
        export_capabilities_snapshot_fn=lambda: (False, "export_capabilities_unavailable_in_maintenance", {}),
        export_ledger_summary_action_fn=lambda _payload: (False, "export_ledger_summary_unavailable_in_maintenance", {}),
        export_diagnostics_bundle_action_fn=lambda _payload: (False, "export_diagnostics_bundle_unavailable_in_maintenance", {}),
        tail_log_action_fn=lambda _payload: (False, "tail_log_unavailable_in_maintenance", {}),
        metrics_action_fn=lambda _payload: (False, "metrics_unavailable_in_maintenance", {}),
        inspect_environment_fn=lambda: {},
        format_report_fn=lambda _data: "",
        policy_audit_fn=lambda _limit=30: "",
        record_control_action_event_fn=_record_event,
        invalidate_control_status_cache_fn=lambda: None,
    )


def _execute_autonomy_recommendation(state: dict, packet: dict, policy_snapshot: dict) -> dict:
    last_context = _last_action_context_for_orchestrator(state)
    gate = AUTONOMY_EXECUTION_GATE_SERVICE.evaluate(
        packet,
        policy_snapshot,
        last_execution_context=last_context,
    )
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "ts": _patch_queue_timestamp(),
        "created_at_utc": created_at,
        "mode": str(gate.get("mode") or ""),
        "gate_status": str(gate.get("status") or ""),
        "gate_reason": str(gate.get("reason") or ""),
        "action_type": str(gate.get("action_type") or ""),
        "target_id": str(gate.get("target_id") or ""),
        "allowed": bool(gate.get("allow_execute")),
        "result": "blocked",
        "refusal_reasons": list(gate.get("refusal_reasons") or []),
        "policy_checks": dict(gate.get("policy_checks") or {}),
    }
    if not bool(gate.get("allow_execute")):
        state["last_autonomy_execution_gate"] = payload
        return payload

    events: list[dict] = []
    action_type = str(gate.get("action_type") or "").strip()
    ok, msg, extra = _dispatch_autonomy_control_action(action_type, dict(gate.get("dispatch_payload") or {}), events, state)
    if action_type == "generated_queue_run_next":
        _record_generated_queue_run(state, ok, msg, extra)
    cooldown_sec = max(0, _safe_int(gate.get("cooldown_sec"), 0))
    payload.update(
        {
            "result": "success" if ok else "failed",
            "ok": bool(ok),
            "message": str(msg or ""),
            "extra": extra if isinstance(extra, dict) else {},
            "events": events,
            "cooldown_sec": cooldown_sec,
            "cooldown_until_epoch": time.time() + cooldown_sec if cooldown_sec else 0.0,
        }
    )
    state["last_autonomy_execution_gate"] = dict(payload)
    state["last_autonomy_execution"] = payload
    return payload


def _skipped_maintenance_execution_payload(state: dict, state_key: str, reason: str, *, tree_count: int = 0) -> dict:
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "skipped",
        "tree_count": int(tree_count or 0),
        "executed_count": 0,
        "reason": str(reason or "orchestrator_owns_execution"),
    }
    state[state_key] = payload
    return payload


def _record_worker_cycle(*, cycle: int, interval_sec: int, status: str, code: int | None = None) -> None:
    state = _load_state()
    worker_state = dict(state.get("runtime_worker") or {})
    worker_pid = os.getpid()
    worker_state["interval_sec"] = max(1, int(interval_sec or 300))
    worker_state["last_cycle"] = max(1, int(cycle or 1))
    worker_state["cycle_count"] = max(int(worker_state.get("cycle_count", 0) or 0), max(1, int(cycle or 1)))
    worker_state["pid"] = int(worker_pid)
    try:
        import psutil

        worker_state["create_time"] = float(psutil.Process(worker_pid).create_time())
    except Exception:
        worker_state["create_time"] = worker_state.get("create_time")
    worker_state["script_path"] = str(Path(__file__).resolve())
    worker_state["active"] = True
    worker_state["stale_identity"] = False
    if status == "running":
        worker_state["last_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        worker_state["last_cycle_status"] = "running"
    else:
        worker_state["last_completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        worker_state["last_cycle_status"] = str(status or "unknown")
        worker_state["last_cycle_code"] = int(code or 0)
    state["runtime_worker"] = worker_state
    _save_state(state)


def _max_fallback_robustness(report: dict) -> float:
    best = 0.0
    for family in list(report.get("families") or []):
        for item in list(family.get("robust_signals") or []):
            if str(item.get("signal") or "").strip() != "fallback_overuse":
                continue
            try:
                score = float(item.get("robustness_score") or 0.0)
            except Exception:
                score = 0.0
            if score > best:
                best = score
    return best


def _build_micro_patch_zip(state: dict) -> Path | None:
    files = select_patch_candidate_definition_paths(GENERATED_DEFS)
    if not files:
        return None

    current_revision = int(nova_core._read_patch_revision() or 0)
    ts = time.strftime("%Y%m%d_%H%M%S")
    zip_path = UPDATES_DIR / f"autonomy_micro_patch_{ts}.zip"
    manifest = {
        "name": f"autonomy_micro_patch_{ts}",
        "notes": "Auto-generated from fallback_overuse robustness pressure.",
        "patch_revision": current_revision + 1,
        "min_base_revision": current_revision,
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for source in files:
            zf.write(source, arcname=f"runtime/test_sessions/promoted/{source.name}")
        zf.writestr("nova_patch.json", json.dumps(manifest, ensure_ascii=True, indent=2))

    state["last_micro_patch_zip"] = str(zip_path)
    return zip_path


def _micro_patch_candidates_require_review(files: list[Path]) -> bool:
    candidates = [Path(item) for item in list(files or []) if Path(item).exists()]
    if not candidates:
        return False
    try:
        generated_root = GENERATED_DEFS.resolve()
        return all(path.resolve().is_relative_to(generated_root) for path in candidates)
    except Exception:
        generated_text = str(GENERATED_DEFS.resolve()).replace("\\", "/").rstrip("/") + "/"
        for path in candidates:
            resolved = str(path.resolve()).replace("\\", "/")
            if not resolved.startswith(generated_text):
                return False
        return True


def _zip_contains_only_promoted_patch_entries(zip_path: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            members = [
                member.filename.replace("\\", "/").lstrip("/")
                for member in archive.infolist()
                if not member.is_dir()
            ]
    except Exception:
        return False
    payload_members = [
        name for name in members
        if name and Path(name).name.lower() != PATCH_MANIFEST_NAME.lower()
    ]
    return bool(payload_members) and all(name.startswith(PROMOTED_PATCH_ENTRY_PREFIX) for name in payload_members)


def _is_patch_preview_definition_only_noop(row: dict) -> bool:
    decision = str((row or {}).get("decision") or "pending").strip().lower() or "pending"
    status = str((row or {}).get("status") or "").strip().lower()
    artifact_state = str((row or {}).get("artifact_state") or "").strip().lower()
    if decision == "rejected" or not status.startswith("eligible") or artifact_state != "ok":
        return False
    added_files = [
        str(item).strip()
        for item in list((row or {}).get("added_files") or [])
        if str(item).strip()
    ]
    non_manifest_added = [
        item for item in added_files
        if Path(item).name.lower() != PATCH_MANIFEST_NAME.lower()
    ]
    skipped_files = [
        str(item).strip()
        for item in list((row or {}).get("skipped_files") or [])
        if str(item).strip()
    ]
    if non_manifest_added:
        return False
    if not skipped_files:
        return False
    return all(item.startswith(PROMOTED_PATCH_ENTRY_PREFIX) for item in skipped_files)


def _is_patch_preview_stale_noneligible(row: dict) -> bool:
    decision = str((row or {}).get("decision") or "pending").strip().lower() or "pending"
    status = str((row or {}).get("status") or "").strip().lower()
    artifact_state = str((row or {}).get("artifact_state") or "").strip().lower()
    if decision == "rejected":
        return False
    if artifact_state != "ok":
        return False
    if not status or status.startswith("eligible"):
        return False
    return status.startswith("rejected:")


def _auto_apply_if_eligible(zip_path: Path) -> str:
    if _zip_contains_only_promoted_patch_entries(zip_path):
        return "skipped_generated_definitions_require_review"

    preview_out = nova_core.patch_preview(str(zip_path), write_report=False)
    if "Status: eligible" not in str(preview_out):
        return f"preview_not_eligible: {str(preview_out).strip()[:300]}"

    if PROMOTED_PATCH_ENTRY_PREFIX in str(preview_out):
        return "skipped_generated_definitions_require_review"

    preview_out = nova_core.patch_preview(str(zip_path), write_report=True)
    apply_out = nova_core.execute_patch_action("apply", str(zip_path), is_admin=True)
    return str(apply_out or "")


def _run_daily_regression_if_due(state: dict) -> str:
    today = time.strftime("%Y-%m-%d")
    if str(state.get("last_regression_date") or "") == today:
        return "daily_regression_skipped_already_ran"

    cmd = [str(VENV_PY), "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "--buffer"]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=5400)
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    summary = "OK" if proc.returncode == 0 else "FAILED"

    state["last_regression_date"] = today
    state["last_regression_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["last_regression_status"] = summary
    state["last_regression_stale"] = False
    state["last_regression_returncode"] = int(proc.returncode)
    state["last_regression_tail"] = output[-2000:]
    return f"daily_regression_{summary.lower()}"


def _sync_signal_intake_work_tree(state: dict) -> dict:
    maintenance_payload = {
        "last_regression_status": str(state.get("last_regression_status") or ""),
        "last_regression_stale": bool(state.get("last_regression_stale", False)),
    }
    status_payload = {
        "alerts": [],
        "self_check_pass_ratio": 1.0,
        "autonomy_maintenance": maintenance_payload,
    }
    results = WORK_TREE_SIGNAL_INGESTION_SERVICE.sync_status_snapshot(status_payload)
    tree = None
    for candidate in work_tree.list_trees():
        meta = dict(getattr(candidate, "meta", {}) or {})
        if str(meta.get("kind") or "").strip().lower() == WORK_TREE_SIGNAL_INGESTION_SERVICE.SIGNAL_TREE_KIND:
            tree = candidate
            break
    active_regression = bool(
        maintenance_payload["last_regression_status"]
        and "pass" not in maintenance_payload["last_regression_status"].lower()
        and maintenance_payload["last_regression_status"].lower() != "ok"
        and not maintenance_payload["last_regression_stale"]
    )
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok",
        "tree_id": str(getattr(tree, "tree_id", "") or ""),
        "tree_title": str(getattr(tree, "title", "") or ""),
        "result_count": len(results),
        "created_count": sum(1 for item in results if str((item or {}).get("action") or "") == "created"),
        "updated_count": sum(1 for item in results if str((item or {}).get("action") or "") == "updated"),
        "reopened_count": sum(1 for item in results if str((item or {}).get("action") or "") == "reopened"),
        "resolved_count": sum(1 for item in results if str((item or {}).get("action") or "") == "resolved"),
        "active_regression_failure": active_regression,
        "last_regression_status": maintenance_payload["last_regression_status"],
        "last_regression_stale": maintenance_payload["last_regression_stale"],
    }
    if results:
        payload["results"] = list(results)
    state["last_signal_ingestion"] = payload
    return payload


def _run_patch_queue_cleanup(state: dict) -> dict:
    before = dict(nova_core.patch_status_payload() or {})
    noop_targets = [
        item for item in service_patch_preview_summaries(
            updates_dir=UPDATES_DIR,
            read_approvals_fn=nova_core._read_approvals,
            limit=max(5000, len(before.get("previews", []) or []), int(before.get("previews_total", 0) or 0)),
        )
        if _is_patch_preview_definition_only_noop(item)
    ]
    noop_rejected: list[str] = []
    noop_failed: list[str] = []
    noop_note = "autonomy maintenance cleanup: no-op definition-only preview does not require patch apply review"
    for item in noop_targets:
        preview_path = str(item.get("path") or item.get("name") or "").strip()
        if not preview_path:
            continue
        ok = nova_core._record_approval(
            preview_path,
            "rejected",
            user=nova_core.get_active_user(),
            note=noop_note,
        )
        if ok:
            noop_rejected.append(str(item.get("name") or preview_path))
        else:
            noop_failed.append(str(item.get("name") or preview_path))
    orphan_result = service_bulk_reject_orphaned_previews(
        updates_dir=UPDATES_DIR,
        read_approvals_fn=nova_core._read_approvals,
        record_approval_fn=nova_core._record_approval,
        get_active_user_fn=nova_core.get_active_user,
        note="autonomy maintenance cleanup: orphaned patch preview references missing patch artifact",
    )
    superseded_result = service_bulk_archive_superseded_previews(
        updates_dir=UPDATES_DIR,
        read_approvals_fn=nova_core._read_approvals,
    )
    rejected_archive_targets = [
        item for item in service_patch_preview_summaries(
            updates_dir=UPDATES_DIR,
            read_approvals_fn=nova_core._read_approvals,
            limit=max(5000, len(before.get("previews", []) or []), int(before.get("previews_total", 0) or 0)),
        )
        if str(item.get("decision") or "").strip().lower() == "rejected"
    ]
    archived_rejected: list[str] = []
    archive_rejected_failed: list[str] = []
    for item in rejected_archive_targets:
        preview_path = str(item.get("path") or item.get("name") or "").strip()
        if not preview_path:
            continue
        result = service_archive_preview_report(preview_path, updates_dir=UPDATES_DIR)
        if bool(result.get("ok")):
            archived_rejected.append(str(item.get("name") or preview_path))
        else:
            archive_rejected_failed.append(str(item.get("name") or preview_path))
    stale_noneligible_targets = [
        item for item in service_patch_preview_summaries(
            updates_dir=UPDATES_DIR,
            read_approvals_fn=nova_core._read_approvals,
            limit=max(5000, len(before.get("previews", []) or []), int(before.get("previews_total", 0) or 0)),
        )
        if _is_patch_preview_stale_noneligible(item)
    ]
    archived_stale_noneligible: list[str] = []
    archive_stale_noneligible_failed: list[str] = []
    for item in stale_noneligible_targets:
        preview_path = str(item.get("path") or item.get("name") or "").strip()
        if not preview_path:
            continue
        result = service_archive_preview_report(preview_path, updates_dir=UPDATES_DIR)
        if bool(result.get("ok")):
            archived_stale_noneligible.append(str(item.get("name") or preview_path))
        else:
            archive_stale_noneligible_failed.append(str(item.get("name") or preview_path))
    after = dict(nova_core.patch_status_payload() or {})
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok" if not noop_failed and not archive_rejected_failed and not archive_stale_noneligible_failed and orphan_result.get("ok") and superseded_result.get("ok") else "failed",
        "noop_rejected_count": len(noop_rejected),
        "noop_failed_count": len(noop_failed),
        "orphan_rejected_count": int(orphan_result.get("count", 0) or 0),
        "orphan_failed_count": len(list(orphan_result.get("failed") or [])),
        "superseded_archived_count": int(superseded_result.get("count", 0) or 0),
        "superseded_failed_count": len(list(superseded_result.get("failed") or [])),
        "rejected_archived_count": len(archived_rejected),
        "rejected_archive_failed_count": len(archive_rejected_failed),
        "stale_noneligible_archived_count": len(archived_stale_noneligible),
        "stale_noneligible_archive_failed_count": len(archive_stale_noneligible_failed),
        "archive_dir": str(superseded_result.get("archive_dir") or ""),
        "review_total_before": int(before.get("review_previews_total", 0) or 0),
        "review_total_after": int(after.get("review_previews_total", 0) or 0),
        "orphaned_before": int(before.get("review_previews_orphaned", 0) or 0),
        "orphaned_after": int(after.get("review_previews_orphaned", 0) or 0),
        "superseded_before": int(before.get("review_previews_superseded_total", 0) or 0),
        "superseded_after": int(after.get("review_previews_superseded_total", 0) or 0),
        "previews_total_before": int(before.get("previews_total", 0) or 0),
        "previews_total_after": int(after.get("previews_total", 0) or 0),
    }
    state["last_patch_cleanup"] = payload
    return payload


def _reevaluate_pending_review_queue(state: dict) -> dict:
    payload = dict(nova_safety_envelope.reevaluate_pending_reviews())
    state["last_pending_review_recheck"] = payload
    return payload


def _patch_queue_execution_policy() -> dict:
    return {
        "allowed_tools": list(PATCH_QUEUE_ALLOWED_TOOLS),
        "require_explicit_allow": True,
    }


def _patch_queue_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _patch_queue_preview_name(row: dict) -> str:
    return str((row or {}).get("name") or (row or {}).get("path") or "").strip()


def _patch_queue_source_key(row: dict) -> str:
    preview_name = _patch_queue_preview_name(row)
    if preview_name:
        return f"patch_preview::{preview_name}"
    return ""


def _is_patch_preview_apply_ready(row: dict) -> bool:
    decision = str((row or {}).get("decision") or "").strip().lower()
    status = str((row or {}).get("status") or "").strip().lower()
    artifact_state = str((row or {}).get("artifact_state") or "").strip().lower()
    min_base_text = str((row or {}).get("min_base_revision") or "").strip()
    current_revision = (row or {}).get("_current_revision", (row or {}).get("current_revision", 0))
    base_compatible = True
    if min_base_text:
        try:
            base_compatible = int(current_revision or 0) == int(min_base_text)
        except Exception:
            base_compatible = True
    return (
        decision == "approved"
        and status.startswith("eligible")
        and artifact_state == "ok"
        and bool((row or {}).get("zip_exists"))
        and base_compatible
    )


def _is_patch_preview_auto_approvable(row: dict) -> bool:
    decision = str((row or {}).get("decision") or "").strip().lower()
    status = str((row or {}).get("status") or "").strip().lower()
    artifact_state = str((row or {}).get("artifact_state") or "").strip().lower()
    preview_kind = str((row or {}).get("preview_kind") or "").strip().lower()
    if decision != "pending":
        return False
    if not status.startswith("eligible"):
        return False
    if artifact_state != "ok":
        return False
    if not bool((row or {}).get("zip_exists")):
        return False
    if preview_kind not in {"autonomy_micro_patch", "teach_proposal"}:
        return False
    min_base_text = str((row or {}).get("min_base_revision") or "").strip()
    patch_revision_text = str((row or {}).get("patch_revision") or "").strip()
    current_revision = (row or {}).get("_current_revision", (row or {}).get("current_revision", 0))
    try:
        current_revision_int = int(current_revision or 0)
    except Exception:
        current_revision_int = 0
    if min_base_text:
        try:
            if int(min_base_text) != current_revision_int:
                return False
        except Exception:
            return False
    if patch_revision_text:
        try:
            if int(patch_revision_text) != current_revision_int + 1:
                return False
        except Exception:
            return False
    return True


def _select_patch_queue_auto_approval_target(review_rows: list[dict], current_revision: int) -> str:
    candidates: list[dict] = []
    for raw_row in review_rows:
        row = dict(raw_row or {})
        row["_current_revision"] = current_revision
        if not _is_patch_preview_auto_approvable(row):
            continue
        candidates.append(row)
    if not candidates:
        return ""

    def _sort_key(row: dict) -> tuple[int, int, str]:
        preview_kind = str((row or {}).get("preview_kind") or "").strip().lower()
        kind_rank = 0 if preview_kind == "autonomy_micro_patch" else 1
        try:
            mtime = int((row or {}).get("mtime", 0) or 0)
        except Exception:
            mtime = 0
        name = _patch_queue_preview_name(row)
        return kind_rank, -mtime, name

    selected = sorted(candidates, key=_sort_key)[0]
    return _patch_queue_source_key(selected)


def _patch_queue_row_mode(row: dict) -> str:
    decision = str((row or {}).get("decision") or "").strip().lower()
    artifact_state = str((row or {}).get("artifact_state") or "").strip().lower()
    if decision == "rejected":
        return "retired"
    if artifact_state and artifact_state != "ok":
        return "orphaned"
    if _is_patch_preview_apply_ready(row):
        return "apply"
    if bool((row or {}).get("_auto_approve_target")) and _is_patch_preview_auto_approvable(row):
        return "approve"
    return "review"


def _patch_queue_branch_title(row: dict) -> str:
    preview_name = _patch_queue_preview_name(row) or "unnamed-preview"
    mode = _patch_queue_row_mode(row)
    if mode == "apply":
        return f"Apply preview: {preview_name}"
    if mode == "approve":
        return f"Approve preview: {preview_name}"
    if mode == "orphaned":
        return f"Resolve orphaned preview: {preview_name}"
    if mode == "retired":
        return f"Retired preview: {preview_name}"
    return f"Review preview: {preview_name}"


def _patch_queue_branch_notes(row: dict) -> str:
    preview_name = _patch_queue_preview_name(row) or "unknown"
    mode = _patch_queue_row_mode(row)
    decision = str((row or {}).get("decision") or "pending").strip().lower() or "pending"
    status = str((row or {}).get("status") or "unknown").strip()
    review_bucket = str((row or {}).get("review_bucket") or "").strip()
    artifact_state = str((row or {}).get("artifact_state") or "unknown").strip()
    artifact_reason = str((row or {}).get("artifact_reason") or "").strip()
    zip_name = str((row or {}).get("zip_name") or "").strip()
    collapsed = int((row or {}).get("collapsed_count", 0) or 0)
    min_base_text = str((row or {}).get("min_base_revision") or "").strip()
    current_revision = str((row or {}).get("_current_revision", (row or {}).get("current_revision", "")) or "").strip()
    lines = [
        f"Preview: {preview_name}",
        f"Decision: {decision}",
        f"Status: {status or 'unknown'}",
        f"Review bucket: {review_bucket or 'n/a'}",
        f"Artifact: {artifact_state or 'unknown'}",
    ]
    if zip_name:
        lines.append(f"Zip: {zip_name}")
    if min_base_text:
        lines.append(f"Required base revision: {min_base_text}")
    if current_revision:
        lines.append(f"Current base revision: {current_revision}")
    if collapsed:
        lines.append(f"Collapsed queue entries: {collapsed}")
    if mode == "approve":
        lines.append("Auto-approval lane: selected as the next governed preview to promote into apply.")
    if decision == "approved" and str(status or "").lower().startswith("eligible") and min_base_text and current_revision:
        try:
            if int(current_revision) < int(min_base_text):
                lines.append("Base compatibility: waiting for the required patch revision before auto-apply.")
        except Exception:
            pass
    if artifact_reason:
        lines.append(f"Artifact note: {artifact_reason}")
    return "\n".join(lines)


def _patch_queue_task_title(row: dict) -> str:
    return f"apply approved preview {_patch_queue_preview_name(row)}"


def _patch_queue_approve_task_title(row: dict) -> str:
    return f"approve pending preview {_patch_queue_preview_name(row)}"


def _patch_queue_review_task_title(row: dict) -> str:
    preview_name = _patch_queue_preview_name(row)
    if _patch_queue_row_mode(row) == "orphaned":
        return f"inspect orphaned preview {preview_name}"
    return f"review pending preview {preview_name}"


def _decide_patch_queue_next_step(tree_id: str, options: list[dict]) -> dict | None:
    candidates: list[tuple[int, int, str, dict]] = []
    for option in list(options or []):
        branch_id = str((option or {}).get("branch_id") or "").strip()
        branch = work_tree.get_branch(branch_id) if branch_id else None
        tool_name = str((option or {}).get("recommended_tool") or "").strip()
        if tool_name not in {"patch_preview_apply", "patch_preview_approve"}:
            continue
        priority = int(getattr(branch, "priority", 0) or 0) if branch is not None else 0
        rank = 0 if tool_name == "patch_preview_apply" else 1
        created_sort = str(getattr(branch, "created_at", "") or "")
        candidates.append((rank, -priority, created_sort, dict(option)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][3]


def _ensure_patch_queue_tree():
    desired_meta = {
        "kind": PATCH_QUEUE_TREE_KIND,
        "source": PATCH_QUEUE_TREE_SOURCE,
        "patch_queue": True,
        "execution_policy": _patch_queue_execution_policy(),
    }
    for tree in work_tree.list_trees():
        meta = dict(getattr(tree, "meta", {}) or {})
        if not (
            bool(meta.get("patch_queue"))
            or str(meta.get("kind") or "").strip().lower() == PATCH_QUEUE_TREE_KIND
            or str(getattr(tree, "title", "") or "").strip().lower().startswith("patch queue:")
        ):
            continue
        changed = False
        merged_meta = dict(meta)
        for key, value in desired_meta.items():
            if merged_meta.get(key) != value:
                merged_meta[key] = value
                changed = True
        if str(tree.title or "") != PATCH_QUEUE_TREE_TITLE:
            tree.title = PATCH_QUEUE_TREE_TITLE
            changed = True
        if changed:
            tree.meta = merged_meta
            tree.updated_at = work_tree._now()
            work_tree.save_tree(tree)
        return tree
    return work_tree.initialize_tree(PATCH_QUEUE_TREE_TITLE, meta=desired_meta)


def _is_patch_queue_managed_branch(tree, branch) -> bool:
    if branch is None or tree is None or branch.branch_id == tree.root_branch_id:
        return False
    if str(getattr(branch, "source_type", "") or "").strip() == PATCH_QUEUE_SOURCE_TYPE:
        return True
    title = str(getattr(branch, "title", "") or "").strip().lower()
    return title.startswith(("apply preview:", "approve preview:", "review preview:", "resolve orphaned preview:", "retired preview:"))


def _find_patch_queue_branch(tree_id: str, source_key: str, preview_name: str, *, open_only: bool) -> object | None:
    tree = work_tree.get_tree(tree_id)
    if tree is None:
        return None
    for branch in work_tree.list_tree_branches(tree_id):
        if not _is_patch_queue_managed_branch(tree, branch):
            continue
        branch_source_key = str(getattr(branch, "source_key", "") or "").strip()
        if branch_source_key != source_key:
            title = str(getattr(branch, "title", "") or "").strip()
            if not preview_name or not title.endswith(preview_name):
                continue
        resolution = str(getattr(branch, "resolution_state", "") or "").strip().lower()
        if open_only and resolution in {"resolved", "retired"}:
            continue
        return branch
    return None


def _complete_open_branch_tasks(branch_id: str) -> int:
    completed = 0
    for task in work_tree.list_branch_tasks(branch_id):
        status = str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
        if status in {"complete", "dropped"}:
            continue
        work_tree.mark_task_complete(task.task_id)
        completed += 1
    return completed


def _apply_patch_queue_branch_state(branch, row: dict, *, first_seen: bool, reopen: bool) -> None:
    now = work_tree._now()
    mode = _patch_queue_row_mode(row)
    preview_name = _patch_queue_preview_name(row)
    branch.title = _patch_queue_branch_title(row)
    branch.bucket = PATCH_QUEUE_BUCKET
    branch.source_type = PATCH_QUEUE_SOURCE_TYPE
    branch.source_key = _patch_queue_source_key(row) or None
    branch.source_payload = dict(row or {})
    branch.last_seen_at = now
    branch.notes = _patch_queue_branch_notes(row)
    branch.evidence_count = 1 if first_seen else int(branch.evidence_count or 0) + 1

    if mode == "apply":
        branch.work_class = "patch_apply"
        branch.actionability = "safe_now"
        branch.resolution_state = "open"
        branch.status = BranchStatus.READY
        branch.priority = 90
        branch.required_tools = []
        branch.allowed_tools = list(PATCH_QUEUE_EXECUTE_TOOLS)
        branch.preferred_tool = "patch_preview_apply"
    elif mode == "approve":
        branch.work_class = "patch_approve"
        branch.actionability = "safe_now"
        branch.resolution_state = "open"
        branch.status = BranchStatus.READY
        branch.priority = 80
        branch.required_tools = []
        branch.allowed_tools = list(PATCH_QUEUE_EXECUTE_TOOLS)
        branch.preferred_tool = "patch_preview_approve"
    elif mode == "orphaned":
        branch.work_class = "patch_orphaned_review"
        branch.actionability = "safe_now"
        branch.resolution_state = "open"
        branch.status = BranchStatus.READY
        branch.priority = 35
        branch.required_tools = []
        branch.allowed_tools = list(PATCH_QUEUE_REVIEW_TOOLS)
        branch.preferred_tool = "find"
    elif mode == "retired":
        branch.work_class = "patch_retired"
        branch.actionability = "dead_end"
        branch.resolution_state = "retired"
        branch.status = BranchStatus.COMPLETE
        branch.priority = 0
        branch.required_tools = []
        branch.allowed_tools = []
        branch.preferred_tool = None
    else:
        branch.work_class = "patch_review"
        branch.actionability = "safe_now"
        branch.resolution_state = "open"
        branch.status = BranchStatus.READY
        branch.priority = 50
        branch.required_tools = []
        branch.allowed_tools = list(PATCH_QUEUE_REVIEW_TOOLS)
        branch.preferred_tool = "find"

    if reopen and branch.status == BranchStatus.COMPLETE and mode != "retired":
        branch.status = BranchStatus.READY if mode in {"apply", "approve", "review", "orphaned"} else BranchStatus.BLOCKED
        branch.resolution_state = "open"

    if mode == "apply" and preview_name:
        desired_task = _patch_queue_task_title(row)
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
            not in {"complete", "dropped"}
        ]
        has_desired_task = any(str(getattr(task, "title", "") or "").strip() == desired_task for task in open_tasks)
        if not has_desired_task:
            _complete_open_branch_tasks(branch.branch_id)
            work_tree.add_task_to_branch(
                branch.branch_id,
                desired_task,
                meta={"patch_preview": preview_name},
            )
        branch.allowed_tools = list(PATCH_QUEUE_EXECUTE_TOOLS)
        branch.preferred_tool = "patch_preview_apply"
    elif mode == "approve" and preview_name:
        desired_task = _patch_queue_approve_task_title(row)
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
            not in {"complete", "dropped"}
        ]
        has_desired_task = any(str(getattr(task, "title", "") or "").strip() == desired_task for task in open_tasks)
        if not has_desired_task:
            _complete_open_branch_tasks(branch.branch_id)
            work_tree.add_task_to_branch(
                branch.branch_id,
                desired_task,
                meta={"patch_preview": preview_name},
            )
        branch.allowed_tools = list(PATCH_QUEUE_EXECUTE_TOOLS)
        branch.preferred_tool = "patch_preview_approve"
    elif mode in {"review", "orphaned"} and preview_name:
        desired_task = _patch_queue_review_task_title(row)
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
            not in {"complete", "dropped"}
        ]
        has_desired_task = any(str(getattr(task, "title", "") or "").strip() == desired_task for task in open_tasks)
        if not has_desired_task:
            _complete_open_branch_tasks(branch.branch_id)
            work_tree.add_task_to_branch(
                branch.branch_id,
                desired_task,
                meta={"patch_preview": preview_name},
            )
    else:
        _complete_open_branch_tasks(branch.branch_id)

    work_tree.touch_branch(branch.branch_id)


def _sync_patch_queue_work_tree(state: dict) -> dict:
    patch_summary = nova_core.patch_status_payload()
    review_rows = list(patch_summary.get("review_previews") or []) if isinstance(patch_summary, dict) else []
    tree = _ensure_patch_queue_tree()
    root_branch = work_tree.get_branch(tree.root_branch_id)
    if root_branch is None:
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "tree_id": tree.tree_id,
            "tree_title": tree.title,
            "reason": "root_branch_missing",
        }
        state["last_patch_queue_sync"] = payload
        return payload

    seen_source_keys: set[str] = set()
    matched_branch_ids: set[str] = set()
    created_count = 0
    updated_count = 0
    reopened_count = 0
    retired_count = 0
    apply_ready_count = 0
    approve_ready_count = 0
    pending_count = 0
    orphaned_count = 0

    current_revision = int((patch_summary or {}).get("current_revision", 0) or 0)
    normalized_rows: list[dict] = []
    has_apply_ready = False
    for raw_row in review_rows:
        row = dict(raw_row or {})
        row["_current_revision"] = current_revision
        normalized_rows.append(row)
        if _is_patch_preview_apply_ready(row):
            has_apply_ready = True
    auto_approve_source_key = ""
    if not has_apply_ready:
        auto_approve_source_key = _select_patch_queue_auto_approval_target(normalized_rows, current_revision)

    for row in normalized_rows:
        row["_auto_approve_target"] = _patch_queue_source_key(row) == auto_approve_source_key
        source_key = _patch_queue_source_key(row)
        preview_name = _patch_queue_preview_name(row)
        if not source_key:
            continue
        seen_source_keys.add(source_key)
        mode = _patch_queue_row_mode(row)
        if mode == "apply":
            apply_ready_count += 1
        elif mode == "approve":
            approve_ready_count += 1
        elif mode == "orphaned":
            orphaned_count += 1
        elif mode != "retired":
            pending_count += 1

        open_branch = _find_patch_queue_branch(tree.tree_id, source_key, preview_name, open_only=True)
        if open_branch is not None:
            _apply_patch_queue_branch_state(open_branch, row, first_seen=False, reopen=False)
            matched_branch_ids.add(open_branch.branch_id)
            updated_count += 1
            continue

        closed_branch = _find_patch_queue_branch(tree.tree_id, source_key, preview_name, open_only=False)
        if closed_branch is not None:
            _apply_patch_queue_branch_state(closed_branch, row, first_seen=False, reopen=True)
            matched_branch_ids.add(closed_branch.branch_id)
            reopened_count += 1
            continue

        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            _patch_queue_branch_title(row),
            PATCH_QUEUE_BUCKET,
            root_branch.branch_id,
        )
        _apply_patch_queue_branch_state(branch, row, first_seen=True, reopen=False)
        matched_branch_ids.add(branch.branch_id)
        created_count += 1

    for branch in work_tree.list_tree_branches(tree.tree_id):
        if not _is_patch_queue_managed_branch(tree, branch):
            continue
        if branch.branch_id in matched_branch_ids:
            continue
        source_key = str(getattr(branch, "source_key", "") or "").strip()
        if source_key and source_key in seen_source_keys:
            continue
        _complete_open_branch_tasks(branch.branch_id)
        branch.status = BranchStatus.COMPLETE
        branch.resolution_state = "resolved"
        branch.priority = 0
        branch.allowed_tools = []
        branch.preferred_tool = None
        existing = str(branch.notes or "").strip()
        retire_note = "No longer present in the distinct patch review queue."
        if retire_note not in existing:
            branch.notes = f"{existing}\n{retire_note}".strip() if existing else retire_note
        branch.last_seen_at = work_tree._now()
        work_tree.touch_branch(branch.branch_id)
        retired_count += 1

    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok",
        "tree_id": tree.tree_id,
        "tree_title": tree.title,
        "review_previews_total": len(review_rows),
        "apply_ready_count": apply_ready_count,
        "approve_ready_count": approve_ready_count,
        "pending_count": pending_count,
        "orphaned_count": orphaned_count,
        "created_count": created_count,
        "updated_count": updated_count,
        "reopened_count": reopened_count,
        "retired_count": retired_count,
    }
    state["last_patch_queue_sync"] = payload
    return payload


def _run_patch_queue_work_tree_cycle(state: dict, *, max_steps: int | None = None) -> dict:
    sync_state = dict(state.get("last_patch_queue_sync") or {})
    tree_id = str(sync_state.get("tree_id") or "").strip()
    if not tree_id:
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "idle",
            "tree_count": 0,
            "executed_count": 0,
            "reason": "patch_queue_tree_missing",
        }
        state["last_work_tree_cycle"] = payload
        return payload

    executed_total = 0
    full_history: list[dict] = []
    last_action = ""
    step_limit = max(1, _safe_int(max_steps, PATCH_QUEUE_MAX_STEPS)) if max_steps is not None else PATCH_QUEUE_MAX_STEPS

    while executed_total < step_limit:
        apply_ready_count = int(sync_state.get("apply_ready_count", 0) or 0)
        approve_ready_count = int(sync_state.get("approve_ready_count", 0) or 0)
        if apply_ready_count + approve_ready_count <= 0:
            if executed_total > 0:
                break
            payload = {
                "ts": _patch_queue_timestamp(),
                "status": "idle",
                "tree_count": 1,
                "executed_count": 0,
                "reason": "no_apply_ready_preview",
                "tree_id": tree_id,
                "tree_title": str(sync_state.get("tree_title") or ""),
                "apply_ready_count": apply_ready_count,
                "approve_ready_count": approve_ready_count,
            }
            state["last_work_tree_cycle"] = payload
            return payload

        history = work_tree.run_autonomous_loop(
            tree_id,
            max_steps=1,
            execute_planned_action_fn=nova_core.execute_planned_action,
            decide_next_step_fn=_decide_patch_queue_next_step,
        )
        full_history.extend(history)
        last_action = str((history[-1] if history else {}).get("action") or "").strip()
        executed = [step for step in history if str(step.get("action") or "").strip() == "executed"]
        executed_total += len(executed)
        if not executed:
            break
        sync_state = _sync_patch_queue_work_tree(state)
        tree_id = str(sync_state.get("tree_id") or tree_id).strip()

    if executed_total:
        status = "ok"
    elif full_history:
        status = last_action or "waiting"
    else:
        status = "idle"
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": status,
        "tree_count": 1,
        "executed_count": executed_total,
        "history_count": len(full_history),
        "last_action": last_action,
        "tree_id": tree_id,
        "tree_title": str(sync_state.get("tree_title") or ""),
        "apply_ready_count": int(sync_state.get("apply_ready_count", 0) or 0),
        "approve_ready_count": int(sync_state.get("approve_ready_count", 0) or 0),
    }
    if full_history:
        payload["history"] = full_history
    state["last_work_tree_cycle"] = payload
    return payload


def _generated_queue_execution_policy() -> dict:
    return {
        "allowed_tools": list(GENERATED_QUEUE_ALLOWED_TOOLS),
        "require_explicit_allow": True,
    }


def _generated_queue_item_file(item: dict) -> str:
    return str((item or {}).get("file") or (item or {}).get("path") or "").strip()


def _generated_queue_source_key(item: dict) -> str:
    session_file = _generated_queue_item_file(item)
    if session_file:
        return f"generated_session::{session_file}"
    return ""


def _generated_queue_priority(item: dict) -> int:
    latest_status = str((item or {}).get("latest_status") or "never_run").strip().lower() or "never_run"
    base = {
        "drift": 95,
        "warning": 85,
        "never_run": 75,
    }.get(latest_status, 65)
    highest = dict((item or {}).get("highest_priority") or {}) if isinstance((item or {}).get("highest_priority"), dict) else {}
    urgency = str(highest.get("urgency") or "").strip().lower()
    bonus = {"high": 4, "medium": 2, "low": 1}.get(urgency, 0)
    return min(99, max(10, base + bonus))


def _generated_queue_branch_title(item: dict) -> str:
    session_file = _generated_queue_item_file(item) or "unknown.json"
    latest_status = str((item or {}).get("latest_status") or "never_run").strip().lower() or "never_run"
    if latest_status == "drift":
        return f"Repair generated session: {session_file}"
    if latest_status == "warning":
        return f"Review generated session: {session_file}"
    return f"Run generated session: {session_file}"


def _generated_queue_branch_notes(item: dict) -> str:
    session_file = _generated_queue_item_file(item) or "unknown.json"
    latest_status = str((item or {}).get("latest_status") or "never_run").strip().lower() or "never_run"
    opportunity_reason = str((item or {}).get("opportunity_reason") or "").strip() or "queued"
    family_id = str((item or {}).get("family_id") or "").strip()
    variation_id = str((item or {}).get("variation_id") or "").strip()
    highest = dict((item or {}).get("highest_priority") or {}) if isinstance((item or {}).get("highest_priority"), dict) else {}
    latest_comparison = dict((item or {}).get("latest_comparison") or {}) if isinstance((item or {}).get("latest_comparison"), dict) else {}
    lines = [
        f"Session file: {session_file}",
        f"Latest status: {latest_status}",
        f"Queue reason: {opportunity_reason}",
    ]
    if family_id:
        lines.append(f"Family: {family_id}")
    if variation_id:
        lines.append(f"Variation: {variation_id}")
    if highest:
        lines.append(
            "Priority: "
            f"{str(highest.get('signal') or 'unknown')} / "
            f"{str(highest.get('seam') or 'unknown')} / "
            f"{str(highest.get('urgency') or 'unknown')}"
        )
        rationale = str(highest.get("rationale") or "").strip()
        if rationale:
            lines.append(f"Rationale: {rationale}")
    diff_count = int(latest_comparison.get("diff_count", 0) or 0)
    flagged_probe_count = int(latest_comparison.get("flagged_probe_count", 0) or 0)
    if diff_count or flagged_probe_count:
        lines.append(f"Latest comparison: diff_count={diff_count}, flagged_probe_count={flagged_probe_count}")
    return "\n".join(lines)


def _generated_queue_task_title(item: dict) -> str:
    return f"run generated session {_generated_queue_item_file(item)}"


def _ensure_generated_queue_tree():
    desired_meta = {
        "kind": GENERATED_QUEUE_TREE_KIND,
        "source": GENERATED_QUEUE_TREE_SOURCE,
        "generated_queue": True,
        "execution_policy": _generated_queue_execution_policy(),
    }
    for tree in work_tree.list_trees():
        meta = dict(getattr(tree, "meta", {}) or {})
        if not (
            bool(meta.get("generated_queue"))
            or str(meta.get("kind") or "").strip().lower() == GENERATED_QUEUE_TREE_KIND
            or str(getattr(tree, "title", "") or "").strip().lower().startswith("generated queue:")
        ):
            continue
        changed = False
        merged_meta = dict(meta)
        for key, value in desired_meta.items():
            if merged_meta.get(key) != value:
                merged_meta[key] = value
                changed = True
        if str(tree.title or "") != GENERATED_QUEUE_TREE_TITLE:
            tree.title = GENERATED_QUEUE_TREE_TITLE
            changed = True
        if changed:
            tree.meta = merged_meta
            tree.updated_at = work_tree._now()
            work_tree.save_tree(tree)
        return tree
    return work_tree.initialize_tree(GENERATED_QUEUE_TREE_TITLE, meta=desired_meta)


def _is_generated_queue_managed_branch(tree, branch) -> bool:
    if branch is None or tree is None or branch.branch_id == tree.root_branch_id:
        return False
    if str(getattr(branch, "source_type", "") or "").strip() == GENERATED_QUEUE_SOURCE_TYPE:
        return True
    title = str(getattr(branch, "title", "") or "").strip().lower()
    return title.startswith(("run generated session:", "review generated session:", "repair generated session:"))


def _find_generated_queue_branch(tree_id: str, source_key: str, session_file: str, *, open_only: bool) -> object | None:
    tree = work_tree.get_tree(tree_id)
    if tree is None:
        return None
    for branch in work_tree.list_tree_branches(tree_id):
        if not _is_generated_queue_managed_branch(tree, branch):
            continue
        branch_source_key = str(getattr(branch, "source_key", "") or "").strip()
        if branch_source_key != source_key:
            title = str(getattr(branch, "title", "") or "").strip()
            if not session_file or not title.endswith(session_file):
                continue
        resolution = str(getattr(branch, "resolution_state", "") or "").strip().lower()
        if open_only and resolution in {"resolved", "retired"}:
            continue
        return branch
    return None


def _apply_generated_queue_branch_state(branch, item: dict, *, first_seen: bool, reopen: bool) -> None:
    now = work_tree._now()
    session_file = _generated_queue_item_file(item)
    branch.title = _generated_queue_branch_title(item)
    branch.bucket = GENERATED_QUEUE_BUCKET
    branch.source_type = GENERATED_QUEUE_SOURCE_TYPE
    branch.source_key = _generated_queue_source_key(item) or None
    branch.source_payload = dict(item or {})
    branch.last_seen_at = now
    branch.notes = _generated_queue_branch_notes(item)
    branch.evidence_count = 1 if first_seen else int(branch.evidence_count or 0) + 1
    branch.work_class = "generated_session_repair"
    branch.actionability = "safe_now"
    branch.resolution_state = "open"
    branch.status = BranchStatus.READY
    branch.priority = _generated_queue_priority(item)
    branch.required_tools = []
    branch.allowed_tools = list(GENERATED_QUEUE_EXECUTE_TOOLS)
    branch.preferred_tool = "generated_queue_run"

    if reopen and branch.status == BranchStatus.COMPLETE:
        branch.status = BranchStatus.READY
        branch.resolution_state = "open"

    if session_file:
        desired_task = _generated_queue_task_title(item)
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").strip().lower()
            not in {"complete", "dropped"}
        ]
        has_desired_task = any(str(getattr(task, "title", "") or "").strip() == desired_task for task in open_tasks)
        if not has_desired_task:
            _complete_open_branch_tasks(branch.branch_id)
            work_tree.add_task_to_branch(
                branch.branch_id,
                desired_task,
                meta={
                    "session_file": session_file,
                    "family_id": str((item or {}).get("family_id") or ""),
                    "variation_id": str((item or {}).get("variation_id") or ""),
                    "latest_status": str((item or {}).get("latest_status") or ""),
                    "opportunity_reason": str((item or {}).get("opportunity_reason") or ""),
                },
            )
    else:
        _complete_open_branch_tasks(branch.branch_id)

    work_tree.touch_branch(branch.branch_id)


def _sync_generated_queue_work_tree(state: dict) -> dict:
    queue_payload = _generated_work_queue(limit=200)
    actionable_items = [
        dict(item or {})
        for item in list(queue_payload.get("items") or [])
        if isinstance(item, dict) and bool(item.get("actionable"))
    ]
    tree = _ensure_generated_queue_tree()
    root_branch = work_tree.get_branch(tree.root_branch_id)
    if root_branch is None:
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "tree_id": tree.tree_id,
            "tree_title": tree.title,
            "reason": "root_branch_missing",
        }
        state["last_generated_queue_sync"] = payload
        return payload

    seen_source_keys: set[str] = set()
    matched_branch_ids: set[str] = set()
    created_count = 0
    updated_count = 0
    reopened_count = 0
    retired_count = 0

    for item in actionable_items:
        source_key = _generated_queue_source_key(item)
        session_file = _generated_queue_item_file(item)
        if not source_key or not session_file:
            continue
        seen_source_keys.add(source_key)

        open_branch = _find_generated_queue_branch(tree.tree_id, source_key, session_file, open_only=True)
        if open_branch is not None:
            _apply_generated_queue_branch_state(open_branch, item, first_seen=False, reopen=False)
            matched_branch_ids.add(open_branch.branch_id)
            updated_count += 1
            continue

        closed_branch = _find_generated_queue_branch(tree.tree_id, source_key, session_file, open_only=False)
        if closed_branch is not None:
            _apply_generated_queue_branch_state(closed_branch, item, first_seen=False, reopen=True)
            matched_branch_ids.add(closed_branch.branch_id)
            reopened_count += 1
            continue

        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            _generated_queue_branch_title(item),
            GENERATED_QUEUE_BUCKET,
            root_branch.branch_id,
        )
        _apply_generated_queue_branch_state(branch, item, first_seen=True, reopen=False)
        matched_branch_ids.add(branch.branch_id)
        created_count += 1

    for branch in work_tree.list_tree_branches(tree.tree_id):
        if not _is_generated_queue_managed_branch(tree, branch):
            continue
        if branch.branch_id in matched_branch_ids:
            continue
        source_key = str(getattr(branch, "source_key", "") or "").strip()
        if source_key and source_key in seen_source_keys:
            continue
        _complete_open_branch_tasks(branch.branch_id)
        branch.status = BranchStatus.COMPLETE
        branch.resolution_state = "resolved"
        branch.priority = 0
        branch.allowed_tools = []
        branch.preferred_tool = None
        existing = str(branch.notes or "").strip()
        retire_note = "No longer actionable in the generated work queue."
        if retire_note not in existing:
            branch.notes = f"{existing}\n{retire_note}".strip() if existing else retire_note
        branch.last_seen_at = work_tree._now()
        work_tree.touch_branch(branch.branch_id)
        retired_count += 1

    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok",
        "tree_id": tree.tree_id,
        "tree_title": tree.title,
        "queue_status": str(queue_payload.get("status") or ""),
        "queue_count": int(queue_payload.get("count", 0) or 0),
        "open_count": int(queue_payload.get("open_count", 0) or 0),
        "actionable_count": int(queue_payload.get("actionable_count", 0) or 0),
        "blocked_count": int(queue_payload.get("blocked_count", 0) or 0),
        "created_count": created_count,
        "updated_count": updated_count,
        "reopened_count": reopened_count,
        "retired_count": retired_count,
        "next_file": str((queue_payload.get("next_item") or {}).get("file") or ""),
    }
    state["last_generated_queue_sync"] = payload
    return payload


def _execute_generated_queue_planned_action(tool: str, args=None):
    tool_name = str(tool or "").strip()
    if tool_name != "generated_queue_run":
        return nova_core.execute_planned_action(tool, args)

    tool_args = list(args) if isinstance(args, (list, tuple)) else ([] if args in {None, ""} else [args])
    session_file = str(tool_args[0] or "").strip() if tool_args else ""
    if not session_file:
        return {"ok": False, "error": "session_file_required"}

    ok, msg, extra = _run_test_session_definition(session_file)
    latest_report = dict((extra or {}).get("latest_report") or {})
    runner_output = str((extra or {}).get("stdout") or "").strip()
    if latest_report:
        return {
            "ok": True,
            "message": str(msg or ""),
            "session_file": session_file,
            "runner_ok": bool(ok),
            "report_status": str(latest_report.get("status") or ""),
            "report_run_id": str(latest_report.get("run_id") or ""),
            "report_path": str(latest_report.get("report_path") or ""),
            "stdout_tail": runner_output[-500:],
        }
    if ok:
        return {
            "ok": True,
            "message": str(msg or ""),
            "session_file": session_file,
            "stdout_tail": runner_output[-500:],
        }
    return {
        "ok": False,
        "error": str(msg or "generated_session_run_failed"),
        "session_file": session_file,
        "stdout_tail": runner_output[-500:],
    }


def _run_generated_queue_work_tree_cycle(state: dict) -> dict:
    sync_state = dict(state.get("last_generated_queue_sync") or {})
    tree_id = str(sync_state.get("tree_id") or "").strip()
    if not tree_id:
        queue_payload = _generated_work_queue(limit=200)
        _record_generated_queue_run(
            state,
            True,
            "generated_work_queue_tree_missing",
            {
                "selected": dict(queue_payload.get("next_item") or {}),
                "work_queue": queue_payload,
            },
        )
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "idle",
            "tree_count": 0,
            "executed_count": 0,
            "reason": "generated_queue_tree_missing",
        }
        state["last_generated_queue_tree_cycle"] = payload
        return payload

    actionable_count = int(sync_state.get("actionable_count", 0) or 0)
    if actionable_count <= 0:
        queue_payload = _generated_work_queue(limit=200)
        _record_generated_queue_run(
            state,
            True,
            "generated_work_queue_clear" if str(queue_payload.get("status") or "") == "clear" else "generated_work_queue_blocked",
            {
                "selected": dict(queue_payload.get("next_item") or {}),
                "work_queue": queue_payload,
            },
        )
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "idle",
            "tree_count": 1,
            "executed_count": 0,
            "reason": "no_actionable_generated_queue_item",
            "tree_id": tree_id,
            "tree_title": str(sync_state.get("tree_title") or ""),
            "actionable_count": int(queue_payload.get("actionable_count", 0) or 0),
            "queue_status": str(queue_payload.get("status") or ""),
        }
        state["last_generated_queue_tree_cycle"] = payload
        return payload

    history = work_tree.run_autonomous_loop(
        tree_id,
        max_steps=GENERATED_QUEUE_MAX_STEPS,
        execute_planned_action_fn=_execute_generated_queue_planned_action,
    )
    executed = [step for step in history if str(step.get("action") or "").strip() == "executed"]
    last_action = str((history[-1] if history else {}).get("action") or "").strip()
    sync_state = _sync_generated_queue_work_tree(state)
    queue_payload = _generated_work_queue(limit=200)
    last_result = dict((executed[-1] if executed else {}).get("tool_result") or {}) if executed else {}
    selected = {"file": str(last_result.get("session_file") or "")} if last_result else dict(queue_payload.get("next_item") or {})
    latest_report = {}
    if last_result:
        latest_report = {
            "status": str(last_result.get("report_status") or ""),
            "run_id": str(last_result.get("report_run_id") or ""),
            "report_path": str(last_result.get("report_path") or ""),
        }
        if latest_report["status"]:
            selected["latest_status"] = latest_report["status"]
    _record_generated_queue_run(
        state,
        True,
        "generated_work_queue_cycle_executed" if executed else "generated_work_queue_cycle_waiting",
        {
            "selected": selected,
            "latest_report": latest_report,
            "work_queue": queue_payload,
        },
    )
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok" if executed else (last_action or "idle"),
        "tree_count": 1,
        "executed_count": len(executed),
        "history_count": len(history),
        "last_action": last_action,
        "tree_id": tree_id,
        "tree_title": str(sync_state.get("tree_title") or ""),
        "actionable_count": int(queue_payload.get("actionable_count", 0) or 0),
        "queue_status": str(queue_payload.get("status") or ""),
        "selected_file": str(selected.get("file") or ""),
    }
    if history:
        payload["history"] = history
    state["last_generated_queue_tree_cycle"] = payload
    return payload


def _active_work_tree_candidates(limit: int = ACTIVE_WORK_TREE_MAX_TREES) -> list[dict]:
    candidates: list[dict] = []
    for payload in work_tree.list_visual_trees(limit=max(int(limit or ACTIVE_WORK_TREE_MAX_TREES) * 4, 16)):
        if not isinstance(payload, dict):
            continue
        if str(payload.get("status") or "").strip().lower() != "active":
            continue
        if str(payload.get("kind") or "").strip().lower() in {PATCH_QUEUE_TREE_KIND, GENERATED_QUEUE_TREE_KIND}:
            continue
        next_step = payload.get("next_step") if isinstance(payload.get("next_step"), dict) else {}
        if not next_step:
            continue
        candidates.append(payload)
        if len(candidates) >= max(1, int(limit or ACTIVE_WORK_TREE_MAX_TREES)):
            break
    return candidates


def _run_active_work_tree_cycle(state: dict, *, max_steps: int | None = None, max_trees: int | None = None) -> dict:
    tree_limit = max(1, _safe_int(max_trees, ACTIVE_WORK_TREE_MAX_TREES)) if max_trees is not None else ACTIVE_WORK_TREE_MAX_TREES
    step_limit = max(1, _safe_int(max_steps, ACTIVE_WORK_TREE_MAX_STEPS)) if max_steps is not None else ACTIVE_WORK_TREE_MAX_STEPS
    candidates = _active_work_tree_candidates(tree_limit)
    executed_total = 0
    full_history: list[dict] = []
    processed: list[dict] = []
    skipped: list[dict] = []
    last_action = ""

    for candidate in candidates:
        if executed_total >= step_limit:
            break
        tree_id = str(candidate.get("tree_id") or "").strip()
        tree_title = str(candidate.get("title") or "").strip()
        next_step = candidate.get("next_step") if isinstance(candidate.get("next_step"), dict) else {}
        tool_name = str(next_step.get("recommended_tool") or "").strip()
        if not tree_id or not tool_name:
            continue
        if tool_name not in ACTIVE_WORK_TREE_EXECUTE_TOOLS:
            skipped.append(
                {
                    "tree_id": tree_id,
                    "tree_title": tree_title,
                    "tool": tool_name,
                    "reason": "tool_not_in_safe_cycle",
                }
            )
            continue
        history = work_tree.run_autonomous_loop(
            tree_id,
            max_steps=1,
            execute_planned_action_fn=nova_core.execute_planned_action,
        )
        full_history.extend(history)
        last_action = str((history[-1] if history else {}).get("action") or "").strip()
        executed = [step for step in history if str(step.get("action") or "").strip() == "executed"]
        executed_total += len(executed)
        processed.append(
            {
                "tree_id": tree_id,
                "tree_title": tree_title,
                "tool": tool_name,
                "executed": len(executed),
                "last_action": last_action,
            }
        )

    if executed_total:
        status = "ok"
    elif full_history:
        status = last_action or "waiting"
    else:
        status = "idle"
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": status,
        "tree_count": len(candidates),
        "executed_count": executed_total,
        "history_count": len(full_history),
        "processed_tree_count": len(processed),
        "skipped_tree_count": len(skipped),
        "last_action": last_action,
        "processed": processed,
        "skipped": skipped,
    }
    if full_history:
        payload["history"] = full_history
    state["last_active_work_tree_cycle"] = payload
    return payload


def _retire_legacy_patch_update_trees(state: dict) -> dict:
    retired: list[dict] = []
    now = work_tree._now()
    reason = "Retired legacy patch/update shell after governed patch queue adoption."
    for candidate in _active_work_tree_candidates(limit=64):
        tree_id = str(candidate.get("tree_id") or "").strip()
        tree_kind = str(candidate.get("kind") or "").strip().lower()
        tree_source = str(candidate.get("source") or "").strip().lower()
        next_step = candidate.get("next_step") if isinstance(candidate.get("next_step"), dict) else {}
        tool_name = str(next_step.get("recommended_tool") or "").strip()
        if not tree_id or tree_kind != "system" or tree_source != "cli":
            continue
        if tool_name not in LEGACY_PATCH_UPDATE_TOOLS:
            continue
        tree = work_tree.get_tree(tree_id)
        if tree is None:
            continue
        dropped_tasks = 0
        for branch in work_tree.list_tree_branches(tree_id):
            existing_notes = str(branch.notes or "").strip()
            if reason not in existing_notes:
                branch.notes = f"{existing_notes}\n{reason}".strip() if existing_notes else reason
            branch.resolution_state = "retired"
            branch.last_seen_at = now
            branch.updated_at = now
            for task in work_tree.list_branch_tasks(branch.branch_id):
                if task.status in {TaskStatus.COMPLETE, TaskStatus.DROPPED}:
                    continue
                task.status = TaskStatus.DROPPED
                task.updated_at = now
                dropped_tasks += 1
        tree.updated_at = now
        work_tree._refresh_tree_state(tree_id, persist=True)
        retired.append(
            {
                "tree_id": tree_id,
                "tree_title": str(tree.title or ""),
                "tool": tool_name,
                "dropped_tasks": dropped_tasks,
            }
        )
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok" if retired else "idle",
        "retired_count": len(retired),
        "retired": retired,
    }
    state["last_legacy_tree_retirement"] = payload
    return payload


def _archive_stale_complete_trees(state: dict) -> dict:
    now = work_tree._now()
    candidates: list[work_tree.WorkTree] = []
    for tree in work_tree.list_trees():
        if tree.status != work_tree.TreeStatus.COMPLETE:
            continue
        meta = dict(tree.meta or {}) if isinstance(tree.meta, dict) else {}
        kind = str(meta.get("kind") or "").strip().lower()
        if kind in COMPLETE_TREE_PROTECTED_KINDS:
            continue
        candidates.append(tree)
    candidates.sort(key=lambda tree: (tree.updated_at, tree.tree_id), reverse=True)
    retained_ids = {tree.tree_id for tree in candidates[: max(0, int(COMPLETE_TREE_VISIBLE_KEEP))]}
    archived: list[dict] = []
    skipped_recent = 0
    reason = "Archived stale complete tree to keep the Scheduled Tree surface focused on current work."
    for tree in candidates:
        if tree.tree_id in retained_ids:
            continue
        age_sec = max(0.0, (now - tree.updated_at).total_seconds())
        if age_sec < float(COMPLETE_TREE_ARCHIVE_MIN_AGE_SEC):
            skipped_recent += 1
            continue
        work_tree.archive_tree(tree.tree_id, reason=reason)
        archived.append(
            {
                "tree_id": tree.tree_id,
                "tree_title": str(tree.title or ""),
                "kind": str((tree.meta or {}).get("kind") or "") if isinstance(tree.meta, dict) else "",
                "source": str((tree.meta or {}).get("source") or "") if isinstance(tree.meta, dict) else "",
                "age_sec": int(age_sec),
            }
        )
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok" if archived else "idle",
        "archived_count": len(archived),
        "retained_count": len(retained_ids),
        "skipped_recent_count": skipped_recent,
        "archived": archived,
    }
    state["last_complete_tree_archive"] = payload
    return payload


def _archive_empty_active_trees(state: dict) -> dict:
    now = work_tree._now()
    archived: list[dict] = []
    skipped_recent = 0
    reason = "Archived empty active tree; it had only a root branch and no tasks."
    for tree in work_tree.list_trees():
        if tree.status != work_tree.TreeStatus.ACTIVE:
            continue
        branches = work_tree.list_tree_branches(tree.tree_id)
        non_root_branches = [branch for branch in branches if branch.branch_id != tree.root_branch_id]
        tasks = work_tree.list_tree_tasks(tree.tree_id)
        if non_root_branches or tasks:
            continue
        age_sec = max(0.0, (now - tree.updated_at).total_seconds())
        if age_sec < float(EMPTY_ACTIVE_TREE_ARCHIVE_MIN_AGE_SEC):
            skipped_recent += 1
            continue
        work_tree.archive_tree(tree.tree_id, reason=reason)
        archived.append(
            {
                "tree_id": tree.tree_id,
                "tree_title": str(tree.title or ""),
                "age_sec": int(age_sec),
            }
        )
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok" if archived else "idle",
        "archived_count": len(archived),
        "skipped_recent_count": skipped_recent,
        "archived": archived,
    }
    state["last_empty_active_tree_archive"] = payload
    return payload


def _archive_stale_cli_active_trees(state: dict) -> dict:
    now = work_tree._now()
    archived: list[dict] = []
    skipped_recent = 0
    skipped_complex = 0
    reason = "Archived stale CLI prompt shell; no longer current operator work."
    for tree in work_tree.list_trees():
        if tree.status != work_tree.TreeStatus.ACTIVE:
            continue
        meta = dict(tree.meta or {}) if isinstance(tree.meta, dict) else {}
        kind = str(meta.get("kind") or "").strip().lower()
        source = str(meta.get("source") or "").strip().lower()
        title = str(tree.title or "").strip()
        if kind != "system" or source != "cli" or not title.lower().startswith("cli:"):
            continue
        age_sec = max(0.0, (now - tree.created_at).total_seconds())
        if age_sec < float(STALE_CLI_ACTIVE_TREE_ARCHIVE_MIN_AGE_SEC):
            skipped_recent += 1
            continue
        branches = work_tree.list_tree_branches(tree.tree_id)
        open_tasks = [
            task for task in work_tree.list_tree_tasks(tree.tree_id)
            if task.status not in {TaskStatus.COMPLETE, TaskStatus.DROPPED}
        ]
        if len(branches) > int(STALE_CLI_ACTIVE_TREE_MAX_BRANCHES) or len(open_tasks) > int(STALE_CLI_ACTIVE_TREE_MAX_OPEN_TASKS):
            skipped_complex += 1
            continue
        work_tree.archive_tree(tree.tree_id, reason=reason)
        archived.append(
            {
                "tree_id": tree.tree_id,
                "tree_title": title,
                "age_sec": int(age_sec),
                "branch_count": len(branches),
                "open_tasks": len(open_tasks),
                "work_identity_key": str(meta.get("work_identity_key") or ""),
            }
        )
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok" if archived else "idle",
        "archived_count": len(archived),
        "skipped_recent_count": skipped_recent,
        "skipped_complex_count": skipped_complex,
        "archived": archived,
    }
    state["last_stale_cli_tree_archive"] = payload
    return payload


def run_once() -> int:
    state = _load_state()
    autonomy_settings = _autonomy_policy_settings()
    legacy_execution_enabled = _legacy_maintenance_execution_enabled(autonomy_settings)

    ok, pack_out = _run_subconscious_pack()
    _append_log(f"subconscious_pack={'ok' if ok else 'fail'}")
    if not ok:
        state["last_error"] = pack_out
        _save_state(state)
        _append_log(pack_out)
        return 1

    if not LATEST_SUBCONSCIOUS.exists():
        _append_log("latest_subconscious_missing")
        return 1

    report = json.loads(LATEST_SUBCONSCIOUS.read_text(encoding="utf-8"))
    generated_at = str(report.get("generated_at") or "")
    threshold = float(state.get("auto_apply_threshold", AUTO_APPLY_THRESHOLD) or AUTO_APPLY_THRESHOLD)
    fallback_score = _max_fallback_robustness(report)

    state["auto_apply_threshold"] = threshold
    state["last_generated_at"] = generated_at
    state["last_fallback_overuse_score"] = fallback_score

    if not legacy_execution_enabled:
        state["last_auto_apply"] = "skipped_orchestrator_owns_execution"
        _append_log("auto_apply_skipped_orchestrator_owns_execution")
    elif fallback_score >= threshold:
        patch_candidates = list(select_patch_candidate_definition_paths(GENERATED_DEFS) or [])
        if not patch_candidates:
            state["last_auto_apply"] = "skipped_no_generated_defs"
            _append_log("auto_apply_skipped_no_generated_defs")
        elif _micro_patch_candidates_require_review(patch_candidates):
            state["last_auto_apply"] = "skipped_generated_definitions_require_review"
            state["last_micro_patch_zip"] = ""
            _append_log(f"auto_apply_skipped_generated_definitions_require_review count={len(patch_candidates)}")
        else:
            zip_path = _build_micro_patch_zip(state)
            if zip_path is None:
                state["last_auto_apply"] = "skipped_no_generated_defs"
                _append_log("auto_apply_skipped_no_generated_defs")
            else:
                apply_result = _auto_apply_if_eligible(zip_path)
                state["last_auto_apply"] = apply_result[:500]
                _append_log(f"auto_apply_result={apply_result[:200]}")
    else:
        state["last_auto_apply"] = "skipped_threshold"
        _append_log(f"auto_apply_skipped_threshold score={fallback_score:.2f} threshold={threshold:.2f}")

    try:
        pending_review_recheck = _reevaluate_pending_review_queue(state)
        _append_log(
            "pending_review_recheck"
            f" status={pending_review_recheck.get('status')}"
            f" reevaluated={int(pending_review_recheck.get('reevaluated_count', 0) or 0)}"
            f" promoted={int(pending_review_recheck.get('moved_promoted_count', 0) or 0)}"
            f" quarantined={int(pending_review_recheck.get('moved_quarantined_count', 0) or 0)}"
            f" pending={int(pending_review_recheck.get('pending_after', 0) or 0)}"
        )
    except Exception as exc:
        pending_review_recheck = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "error": str(exc),
        }
        state["last_pending_review_recheck"] = pending_review_recheck
        _append_log(f"pending_review_recheck_failed {exc}")

    kidney_summary = kidney.run_kidney(logger=lambda message: _append_log(f"[KIDNEY] {message}"))
    state["last_kidney_status"] = {
        "ts": kidney_summary.get("ts"),
        "mode": kidney_summary.get("mode"),
        "candidate_count": kidney_summary.get("candidate_count"),
        "archive_count": kidney_summary.get("archive_count"),
        "delete_count": kidney_summary.get("delete_count"),
        "snapshot_path": kidney_summary.get("snapshot_path"),
    }

    try:
        patch_cleanup = _run_patch_queue_cleanup(state)
        _append_log(
            "patch_queue_cleanup"
            f" status={patch_cleanup.get('status')}"
            f" rejected={int(patch_cleanup.get('orphan_rejected_count', 0) or 0)}"
            f" archived={int(patch_cleanup.get('superseded_archived_count', 0) or 0)}"
            f" review={int(patch_cleanup.get('review_total_before', 0) or 0)}->{int(patch_cleanup.get('review_total_after', 0) or 0)}"
        )
    except Exception as exc:
        patch_cleanup = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "error": str(exc),
        }
        state["last_patch_cleanup"] = patch_cleanup
        _append_log(f"patch_queue_cleanup_failed {exc}")

    try:
        patch_queue_sync = _sync_patch_queue_work_tree(state)
        _append_log(
            "patch_queue_sync"
            f" status={patch_queue_sync.get('status')}"
            f" apply_ready={int(patch_queue_sync.get('apply_ready_count', 0) or 0)}"
            f" created={int(patch_queue_sync.get('created_count', 0) or 0)}"
            f" updated={int(patch_queue_sync.get('updated_count', 0) or 0)}"
        )
    except Exception as exc:
        patch_queue_sync = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "error": str(exc),
        }
        state["last_patch_queue_sync"] = patch_queue_sync
        _append_log(f"patch_queue_sync_failed {exc}")

    try:
        if legacy_execution_enabled:
            work_tree_cycle = _run_patch_queue_work_tree_cycle(state)
        else:
            work_tree_cycle = _skipped_maintenance_execution_payload(
                state,
                "last_work_tree_cycle",
                "orchestrator_owns_execution",
                tree_count=1,
            )
        _append_log(
            "work_tree_cycle"
            f" status={work_tree_cycle.get('status')}"
            f" executed={int(work_tree_cycle.get('executed_count', 0) or 0)}"
            f" trees={int(work_tree_cycle.get('tree_count', 0) or 0)}"
        )
    except Exception as exc:
        work_tree_cycle = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "tree_count": 1,
            "executed_count": 0,
            "error": str(exc),
        }
        state["last_work_tree_cycle"] = work_tree_cycle
        _append_log(f"work_tree_cycle_failed {exc}")

    try:
        generated_queue_sync = _sync_generated_queue_work_tree(state)
        _append_log(
            "generated_queue_sync"
            f" status={generated_queue_sync.get('status')}"
            f" actionable={int(generated_queue_sync.get('actionable_count', 0) or 0)}"
            f" created={int(generated_queue_sync.get('created_count', 0) or 0)}"
            f" updated={int(generated_queue_sync.get('updated_count', 0) or 0)}"
        )
    except Exception as exc:
        generated_queue_sync = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "error": str(exc),
        }
        state["last_generated_queue_sync"] = generated_queue_sync
        _append_log(f"generated_queue_sync_failed {exc}")

    try:
        autonomy_orchestrator = _run_autonomy_orchestrator_advisory(state, kidney_summary)
        _append_log(
            "autonomy_orchestrator"
            f" decision={autonomy_orchestrator.get('decision')}"
            f" action={str((autonomy_orchestrator.get('action') or {}).get('act') or 'none')}"
            f" ledger={str((autonomy_orchestrator.get('ledger') or {}).get('status') or '')}"
            f" execution={str((autonomy_orchestrator.get('execution') or {}).get('result') or '')}"
        )
    except Exception as exc:
        state["last_autonomy_orchestrator"] = {
            "ts": _patch_queue_timestamp(),
            "mode": "advisory",
            "decision": "block_with_reason",
            "action": {},
            "reason": f"autonomy_orchestrator_failed:{exc}",
            "rejection_reasons": ["orchestrator_cycle_failed"],
            "ledger_status": "record_failed",
        }
        _append_log(f"autonomy_orchestrator_failed {exc}")

    try:
        if legacy_execution_enabled:
            generated_queue_cycle = _run_generated_queue_work_tree_cycle(state)
        else:
            generated_queue_cycle = _skipped_maintenance_execution_payload(
                state,
                "last_generated_queue_tree_cycle",
                "orchestrator_owns_execution",
                tree_count=1,
            )
        _append_log(
            "generated_queue_cycle"
            f" status={generated_queue_cycle.get('status')}"
            f" executed={int(generated_queue_cycle.get('executed_count', 0) or 0)}"
            f" actionable={int(generated_queue_cycle.get('actionable_count', 0) or 0)}"
        )
    except Exception as exc:
        generated_queue_cycle = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "tree_count": 1,
            "executed_count": 0,
            "error": str(exc),
        }
        state["last_generated_queue_tree_cycle"] = generated_queue_cycle
        _append_log(f"generated_queue_cycle_failed {exc}")

    try:
        if legacy_execution_enabled:
            active_work_tree_cycle = _run_active_work_tree_cycle(state)
        else:
            active_work_tree_cycle = _skipped_maintenance_execution_payload(
                state,
                "last_active_work_tree_cycle",
                "orchestrator_owns_execution",
                tree_count=0,
            )
        _append_log(
            "active_work_tree_cycle"
            f" status={active_work_tree_cycle.get('status')}"
            f" executed={int(active_work_tree_cycle.get('executed_count', 0) or 0)}"
            f" trees={int(active_work_tree_cycle.get('tree_count', 0) or 0)}"
        )
    except Exception as exc:
        active_work_tree_cycle = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "tree_count": 0,
            "executed_count": 0,
            "error": str(exc),
        }
        state["last_active_work_tree_cycle"] = active_work_tree_cycle
        _append_log(f"active_work_tree_cycle_failed {exc}")

    try:
        complete_tree_archive = _archive_stale_complete_trees(state)
        _append_log(
            "complete_tree_archive"
            f" status={complete_tree_archive.get('status')}"
            f" archived={int(complete_tree_archive.get('archived_count', 0) or 0)}"
            f" retained={int(complete_tree_archive.get('retained_count', 0) or 0)}"
        )
    except Exception as exc:
        complete_tree_archive = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "archived_count": 0,
            "error": str(exc),
        }
        state["last_complete_tree_archive"] = complete_tree_archive
        _append_log(f"complete_tree_archive_failed {exc}")

    try:
        empty_active_tree_archive = _archive_empty_active_trees(state)
        _append_log(
            "empty_active_tree_archive"
            f" status={empty_active_tree_archive.get('status')}"
            f" archived={int(empty_active_tree_archive.get('archived_count', 0) or 0)}"
            f" skipped_recent={int(empty_active_tree_archive.get('skipped_recent_count', 0) or 0)}"
        )
    except Exception as exc:
        empty_active_tree_archive = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "archived_count": 0,
            "error": str(exc),
        }
        state["last_empty_active_tree_archive"] = empty_active_tree_archive
        _append_log(f"empty_active_tree_archive_failed {exc}")

    try:
        stale_cli_tree_archive = _archive_stale_cli_active_trees(state)
        _append_log(
            "stale_cli_tree_archive"
            f" status={stale_cli_tree_archive.get('status')}"
            f" archived={int(stale_cli_tree_archive.get('archived_count', 0) or 0)}"
            f" skipped_recent={int(stale_cli_tree_archive.get('skipped_recent_count', 0) or 0)}"
            f" skipped_complex={int(stale_cli_tree_archive.get('skipped_complex_count', 0) or 0)}"
        )
    except Exception as exc:
        stale_cli_tree_archive = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "archived_count": 0,
            "error": str(exc),
        }
        state["last_stale_cli_tree_archive"] = stale_cli_tree_archive
        _append_log(f"stale_cli_tree_archive_failed {exc}")

    try:
        legacy_tree_retirement = _retire_legacy_patch_update_trees(state)
        _append_log(
            "legacy_tree_retirement"
            f" status={legacy_tree_retirement.get('status')}"
            f" retired={int(legacy_tree_retirement.get('retired_count', 0) or 0)}"
        )
    except Exception as exc:
        legacy_tree_retirement = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "retired_count": 0,
            "error": str(exc),
        }
        state["last_legacy_tree_retirement"] = legacy_tree_retirement
        _append_log(f"legacy_tree_retirement_failed {exc}")

    regression_status = _run_daily_regression_if_due(state)
    if regression_status == "daily_regression_skipped_already_ran":
        last_regression_status = str(state.get("last_regression_status") or "").strip()
        state["last_regression_stale"] = bool(last_regression_status and "pass" not in last_regression_status.lower() and last_regression_status.lower() != "ok")
    else:
        state["last_regression_stale"] = False
    _append_log(regression_status)

    try:
        signal_ingestion = _sync_signal_intake_work_tree(state)
        _append_log(
            "signal_ingestion"
            f" status={signal_ingestion.get('status')}"
            f" results={int(signal_ingestion.get('result_count', 0) or 0)}"
            f" resolved={int(signal_ingestion.get('resolved_count', 0) or 0)}"
            f" active_regression={bool(signal_ingestion.get('active_regression_failure'))}"
        )
    except Exception as exc:
        signal_ingestion = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "result_count": 0,
            "resolved_count": 0,
            "error": str(exc),
        }
        state["last_signal_ingestion"] = signal_ingestion
        _append_log(f"signal_ingestion_failed {exc}")

    _save_state(state)
    return 0


def run_worker(
    *,
    interval_sec: int = 300,
    max_cycles: int = 0,
    continue_on_error: bool = True,
    run_once_fn: Callable[[], int] = run_once,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    normalized_interval = max(1, int(interval_sec or 300))
    normalized_max_cycles = max(0, int(max_cycles or 0))
    cycle = 0
    last_code = 0

    while True:
        cycle += 1
        _record_worker_cycle(cycle=cycle, interval_sec=normalized_interval, status="running")
        _append_log(f"worker_cycle_start cycle={cycle}")
        last_code = int(run_once_fn())
        cycle_status = "ok" if last_code == 0 else "failed"
        _record_worker_cycle(cycle=cycle, interval_sec=normalized_interval, status=cycle_status, code=last_code)
        _append_log(f"worker_cycle_end cycle={cycle} code={last_code}")

        if last_code != 0 and not continue_on_error:
            return last_code
        if normalized_max_cycles and cycle >= normalized_max_cycles:
            return last_code
        sleep_fn(float(normalized_interval))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova Phase 1 autonomy maintenance")
    parser.add_argument("--once", action="store_true", help="Run one maintenance cycle")
    parser.add_argument("--loop", action="store_true", help="Run maintenance continuously")
    parser.add_argument("--interval-sec", type=int, default=300, help="Seconds between maintenance cycles in loop mode")
    parser.add_argument("--max-cycles", type=int, default=0, help="Optional cycle cap for loop mode; 0 means run continuously")
    parser.add_argument("--stop-on-error", action="store_true", help="Exit loop mode after the first failed cycle")
    args = parser.parse_args(argv)
    if args.loop:
        return run_worker(
            interval_sec=args.interval_sec,
            max_cycles=args.max_cycles,
            continue_on_error=not bool(args.stop_on_error),
        )
    if args.once:
        return run_once()
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
