from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
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
from services.control_status_surfaces import (
    derive_surfaces_url,
    merge_http_supplement_into_local,
    release_drift_detected,
)
from services.chat_identity import CHAT_IDENTITY_SERVICE
from services.frontdoor_cli_parity import FRONTDOOR_CLI_PARITY_SERVICE
from services.layer_maturity_policy import enrich_status_with_layer_maturity
from services.operator_control import OPERATOR_CONTROL_SERVICE
from services.release_runtime_truth import (
    RELEASE_RUNTIME_TRUTH_SERVICE,
    build_release_runtime_truth_summary,
    enrich_release_status,
    evaluate_http_model_runtime_probe,
)
from services.release_status import RELEASE_STATUS_SERVICE
from services.control_work_trees import CONTROL_WORK_TREES_SERVICE
from services.core_thinning import build_core_thinning_brief as service_build_core_thinning_brief
from services.core_thinning import feed_core_thinning_brief_to_work_tree as service_feed_core_thinning_brief_to_work_tree
from services.core_steward import build_core_steward_payload as service_build_core_steward_payload
from services.nova_control_action_dispatcher import NOVA_CONTROL_ACTION_DISPATCHER, autonomy_advisory_action_types
from services.nova_root_inventory import build_source_root_inventory_payload
from services.runtime_control import RUNTIME_CONTROL_SERVICE
from services.nova_runtime_context import AUTONOMY_ORCHESTRATOR_LEDGER_FILE
from services.nova_runtime_context import OPERATOR_OUTBOX_FILE
from services.nova_runtime_context import RUNTIME_DIR as CONTEXT_RUNTIME_DIR
from services.nova_runtime_context import WORK_TREE_RUN_TRIGGER_FILE
from services.nova_runtime_context import PATCH_QUEUE_RUN_TRIGGER_FILE
from services.nova_runtime_context import runtime_scope_name
from services.nova_wiring_inventory import WIRING_SURFACES
from services.nova_wiring_inventory import build_root_closure_inventory_payload
from services.port_ownership import PORT_OWNERSHIP_SERVICE
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE
from services.runtime_restart_provenance import RUNTIME_RESTART_PROVENANCE_SERVICE
from services.runtime_status import RUNTIME_STATUS_SERVICE
from services.nova_calendar_ingestion import parse_ics_file
from services.nova_temporal_service import NovaTemporalService
from services.subconscious_review_judgment import is_no_owner_root_repair_judgment
from services.subconscious_review_judgment import latest_subconscious_review_judgment_for_branch
from services.subconscious_work_tree_triage import SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE
from services.test_session_control import TEST_SESSION_CONTROL_SERVICE
from services.validation_artifact_truth import VALIDATION_ARTIFACT_TRUTH_SERVICE
from services.work_tree_signal_ingestion import WORK_TREE_SIGNAL_INGESTION_SERVICE
import tools.runtime_processes as runtime_processes
from work_tree_contracts import BranchStatus, TaskStatus


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = CONTEXT_RUNTIME_DIR
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
GUARD_PY = ROOT / "nova_guard.py"
AUTONOMY_MAINTENANCE_PY = ROOT / "autonomy_maintenance.py"
TEST_SESSIONS_ROOT = RUNTIME_DIR / "test_sessions"
TEST_SESSION_RUNNER_PY = ROOT / "scripts" / "run_test_session.py"
STATE_FILE = RUNTIME_DIR / "autonomy_maintenance_state.json"
MAINT_LOG = RUNTIME_DIR / "autonomy_maintenance.log"
REGRESSION_STATUS_FILE = RUNTIME_DIR / "regression_status.json"
REGRESSION_RUNNER = ROOT / "scripts" / "run_regression.py"
AUTONOMY_ORCHESTRATOR_LEDGER = AUTONOMY_ORCHESTRATOR_LEDGER_FILE
OPERATOR_OUTBOX = OPERATOR_OUTBOX_FILE
RESTART_INTENT_PATH = RUNTIME_DIR / "restart_intent.json"
RELEASE_LEDGER_PATH = RUNTIME_DIR / "exports" / "release_packages" / "release_ledger.jsonl"
LATEST_SUBCONSCIOUS = RUNTIME_DIR / "subconscious_runs" / "latest.json"
GENERATED_DEFS = TEST_SESSIONS_ROOT / "generated_definitions"
UPDATES_DIR = RUNTIME_DIR / "updates" if runtime_scope_name() == "validation" else ROOT / "updates"
WORK_TREE_RUN_TRIGGER = WORK_TREE_RUN_TRIGGER_FILE
PATCH_QUEUE_RUN_TRIGGER = PATCH_QUEUE_RUN_TRIGGER_FILE
CONTROL_STATUS_URL = os.environ.get("NOVA_CONTROL_STATUS_URL", "http://127.0.0.1:8080/api/control/status")
CONTROL_STATUS_SURFACES_URL = os.environ.get(
    "NOVA_CONTROL_STATUS_SURFACES_URL",
    derive_surfaces_url(CONTROL_STATUS_URL),
)
SIGNAL_INGESTION_STATUS_MODE = str(
    os.environ.get("NOVA_SIGNAL_INGESTION_STATUS_MODE", "local_first")
).strip().lower()
try:
    CONTROL_STATUS_TIMEOUT_SEC = max(2.0, float(os.environ.get("NOVA_CONTROL_STATUS_TIMEOUT_SEC", "10")))
except Exception:
    CONTROL_STATUS_TIMEOUT_SEC = 10.0
try:
    CONTROL_STATUS_SURFACES_TIMEOUT_SEC = max(
        1.0,
        float(os.environ.get("NOVA_CONTROL_STATUS_SURFACES_TIMEOUT_SEC", "3")),
    )
except Exception:
    CONTROL_STATUS_SURFACES_TIMEOUT_SEC = 3.0

_LAST_KNOWN_RELEASE_DRIFT_STATE = ""

AUTO_APPLY_THRESHOLD = 0.0
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
ACTIVE_WORK_TREE_EXECUTE_TOOLS = [
    "web_fetch",
    "web_search",
    "web_research",
    "web_gather",
    "wikipedia_lookup",
    "stackexchange_search",
    "health",
    "system_check",
    "os_capability",
    "queue_status",
    "phase2_audit",
    "pulse",
    "read",
    "ls",
    "find",
    "pipeline",
    "core_health",
    "core_thinning",
    "release_promotion_judgment",
    "release_validation_run",
    "release_record_validation_outcome",
    "release_rebuild_verify",
    "installer_validation_run",
    "patch_apply",
    "memory_bootstrap_judgment",
    "memory_bootstrap_confirm",
    "memory_identity_bootstrap",
    "subconscious_review_judgment",
    "source_root_judgment",
    "weather_current_location",
    "weather_location",
    "location_coords",
    "screen",
    "camera",
    "temporal_review",
]
ACTIVE_WORK_TREE_MAX_TREES = 8
ACTIVE_WORK_TREE_MAX_STEPS = 8
ACTIVE_WORK_TREE_DEFAULT_DISPATCH_STEPS = 3
WORK_TREE_CYCLE_ATTENTION_STATUSES = {
    "decision_error",
    "evidence_record_failed",
    "execution_failed",
    "governance_blocked",
    "invalid_decision",
    "missing_branch",
    "missing_tool_assignment",
    "no_open_task",
    "no_tool_selected",
    "scope_blocked",
    "tool_failed",
    "verification_failed",
    "wait_for_tools",
}
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


def _validation_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    validation_runtime = RUNTIME_DIR / "validation"
    env["NOVA_TEST_RUNNER"] = "1"
    env.setdefault("NOVA_VALIDATION_RUNTIME_DIR", str(validation_runtime))
    env.setdefault("NOVA_WORK_TREE_DB", str(validation_runtime / "_internal" / "work_tree.db"))
    env.setdefault("NOVA_MEMORY_DB", str(validation_runtime / "nova_memory.sqlite"))
    return env


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


def _publish_operator_notice_from_autonomy(packet: dict, execution: dict) -> dict:
    notice = OPERATOR_OUTBOX_SERVICE.notice_from_autonomy(packet, execution)
    if not notice:
        reconcile_result = OPERATOR_OUTBOX_SERVICE.reconcile_autonomy_notices(
            OPERATOR_OUTBOX,
            active_notices=[],
        )
        return {
            "ok": bool(reconcile_result.get("ok", True)),
            "published": False,
            "reason": "no_operator_notice_needed",
            "staled_count": int(reconcile_result.get("staled_count", 0) or 0),
        }
    try:
        result = OPERATOR_OUTBOX_SERVICE.append_notice(OPERATOR_OUTBOX, **notice)
    except Exception as exc:
        return {"ok": False, "published": False, "reason": f"operator_outbox_failed:{exc}"}
    reconcile_result = OPERATOR_OUTBOX_SERVICE.reconcile_autonomy_notices(
        OPERATOR_OUTBOX,
        active_notices=[notice],
    )
    return {
        "ok": bool(result.get("ok", False)) and bool(reconcile_result.get("ok", True)),
        "published": bool(result.get("ok", False)) and not bool(result.get("deduped", False)),
        "deduped": bool(result.get("deduped", False)),
        "event_id": str((result.get("event") or {}).get("id") or ""),
        "staled_count": int(reconcile_result.get("staled_count", 0) or 0),
    }


def _publish_operator_notices_from_work_tree(work_tree_state: dict) -> dict:
    notices = OPERATOR_OUTBOX_SERVICE.notices_from_work_tree_state(
        work_tree_state,
        executable_tools=ACTIVE_WORK_TREE_EXECUTE_TOOLS,
    )
    reconcile_result = OPERATOR_OUTBOX_SERVICE.reconcile_work_tree_notices(
        OPERATOR_OUTBOX,
        active_notices=notices,
    )
    source_root_reconcile_result = OPERATOR_OUTBOX_SERVICE.reconcile_source_root_judgment_notices(
        OPERATOR_OUTBOX,
        work_tree_state=work_tree_state,
        work_tree_module=work_tree,
    )
    stale_open_reconcile_result = OPERATOR_OUTBOX_SERVICE.reconcile_stale_open_notices(OPERATOR_OUTBOX)
    duplicate_source_reconcile_result = OPERATOR_OUTBOX_SERVICE.reconcile_duplicate_source_notices(OPERATOR_OUTBOX)
    staled_count = (
        int(reconcile_result.get("staled_count", 0) or 0)
        + int(source_root_reconcile_result.get("staled_count", 0) or 0)
        + int(stale_open_reconcile_result.get("staled_count", 0) or 0)
        + int(duplicate_source_reconcile_result.get("staled_count", 0) or 0)
    )
    if not notices:
        return {
            "ok": (
                bool(reconcile_result.get("ok", True))
                and bool(source_root_reconcile_result.get("ok", True))
                and bool(stale_open_reconcile_result.get("ok", True))
                and bool(duplicate_source_reconcile_result.get("ok", True))
            ),
            "published_count": 0,
            "deduped_count": 0,
            "notice_count": 0,
            "staled_count": staled_count,
            "reason": "no_work_tree_operator_requests",
        }

    published = 0
    deduped = 0
    event_ids: list[str] = []
    errors: list[str] = []
    for notice in notices:
        try:
            result = OPERATOR_OUTBOX_SERVICE.append_notice(OPERATOR_OUTBOX, **notice)
        except Exception as exc:
            errors.append(str(exc))
            continue
        if bool(result.get("deduped", False)):
            deduped += 1
            continue
        if bool(result.get("ok", False)):
            published += 1
            event_id = str((result.get("event") or {}).get("id") or "")
            if event_id:
                event_ids.append(event_id)

    return {
        "ok": (
            not errors
            and bool(reconcile_result.get("ok", True))
            and bool(source_root_reconcile_result.get("ok", True))
            and bool(stale_open_reconcile_result.get("ok", True))
            and bool(duplicate_source_reconcile_result.get("ok", True))
        ),
        "published_count": published,
        "deduped_count": deduped,
        "notice_count": len(notices),
        "staled_count": staled_count,
        "event_ids": event_ids,
        "errors": errors[:5],
    }


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


def _core_steward_for_orchestrator(state: dict, kidney_summary: dict, guard_health: dict | None = None) -> dict:
    runtime_health = nova_core._core_health_runtime_health()
    pulse_payload = nova_core.build_pulse_payload()
    autonomy_state = dict(state or {}) if isinstance(state, dict) else {}
    guard = dict(guard_health or {}) if isinstance(guard_health, dict) else {}
    guard_running = bool(guard.get("running", False))
    runtime_worker = dict(autonomy_state.get("runtime_worker") or {}) if isinstance(autonomy_state.get("runtime_worker"), dict) else {}
    worker_active = bool(runtime_worker.get("active", False))
    if guard_running and not worker_active:
        autonomy_state["maintenance_scheduler_active"] = True
        autonomy_state["maintenance_scheduler_mode"] = "guard_tick"
        autonomy_state["maintenance_scheduler_status"] = "guard_scheduled"
    elif worker_active:
        autonomy_state["maintenance_scheduler_active"] = True
        autonomy_state["maintenance_scheduler_mode"] = "worker_loop"
        autonomy_state["maintenance_scheduler_status"] = "running"
    return service_build_core_steward_payload(
        preflight_checks=_preflight_checks_for_orchestrator(),
        runtime_health=runtime_health,
        pulse_payload=pulse_payload if isinstance(pulse_payload, dict) else {},
        autonomy_maintenance=autonomy_state,
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


def _active_work_candidate_tool(candidate: dict) -> str:
    next_step = candidate.get("next_step") if isinstance(candidate.get("next_step"), dict) else {}
    return str(next_step.get("recommended_tool") or "").strip()


def _active_work_candidate_branch(candidate: dict) -> dict:
    next_step = candidate.get("next_step") if isinstance(candidate.get("next_step"), dict) else {}
    return {
        "branch_id": str(next_step.get("branch_id") or candidate.get("active_branch_id") or candidate.get("tree_id") or ""),
        "title": str(next_step.get("branch_title") or candidate.get("active_branch_title") or candidate.get("title") or ""),
        "task_id": str(next_step.get("task_id") or ""),
        "task_title": str(next_step.get("task_title") or ""),
        "status": str(candidate.get("status") or ""),
        "owner": str(candidate.get("kind") or ""),
        "age_min": _safe_int(candidate.get("age_min") or 0, 0),
        "recommended_tool": str(next_step.get("recommended_tool") or ""),
        "tree_id": str(candidate.get("tree_id") or ""),
        "tree_title": str(candidate.get("title") or ""),
        "executable": _active_work_candidate_tool(candidate) in ACTIVE_WORK_TREE_EXECUTE_TOOLS,
    }


def _work_tree_node_is_operator_hold(node: dict) -> bool:
    status_text = str(node.get("status") or "").strip().lower()
    if status_text != "blocked":
        return False
    source_type = str(node.get("source_type") or "").strip().lower()
    work_class = str(node.get("work_class") or "").strip().lower()
    payload = node.get("source_payload") if isinstance(node.get("source_payload"), dict) else {}
    if source_type == "memory_health" and work_class == "governance_pressure":
        origin = payload.get("memory_bootstrap_origin") if isinstance(payload.get("memory_bootstrap_origin"), dict) else {}
        bootstrap = payload.get("memory_bootstrap") if isinstance(payload.get("memory_bootstrap"), dict) else {}
        origin_status = str(origin.get("status") or bootstrap.get("origin_status") or "").strip().lower()
        return origin_status == "pending_operator_confirmation"
    return False


def _work_tree_snapshot_for_orchestrator(work_tree_state: dict, active_work_candidates: list[dict] | None = None) -> dict:
    payload = dict(work_tree_state or {}) if isinstance(work_tree_state, dict) else {}
    counts = dict(payload.get("counts") or {}) if isinstance(payload.get("counts"), dict) else {}
    branches: list[dict] = []
    observing_count = 0
    latent_root_signal_count = 0
    operator_hold_count = 0
    active_candidates_provided = active_work_candidates is not None
    active_candidates = [dict(item) for item in list(active_work_candidates or []) if isinstance(item, dict)]
    if active_candidates:
        branches = [_active_work_candidate_branch(candidate) for candidate in active_candidates[:64]]
    else:
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
                    "recommended_tool": "",
                    "tree_id": str(tree.get("tree_id") or ""),
                    "tree_title": str(tree.get("title") or ""),
                    "executable": False,
                }
            )
            for node in list(tree.get("nodes") or []):
                if not isinstance(node, dict):
                    continue
                status_text = str(node.get("status") or "").strip().lower()
                resolution_text = str(node.get("resolution_state") or "").strip().lower()
                operator_hold = _work_tree_node_is_operator_hold(node)
                if operator_hold:
                    operator_hold_count += 1
                if status_text == "blocked" and resolution_text == "observing":
                    observing_count += 1
                    if (
                        not operator_hold
                        and
                        str(node.get("source_type") or "").strip().lower() == "subconscious"
                        and str(node.get("work_class") or "").strip().lower() == "candidate_review"
                    ):
                        latent_root_signal_count += 1
    active_executable_count = sum(1 for branch in branches if bool(branch.get("executable")))
    return {
        "open_count": _safe_int(counts.get("open_tasks") or counts.get("pending") or counts.get("active"), 0),
        "working_count": _safe_int(counts.get("working"), 0),
        "blocked_count": _safe_int(counts.get("blocked"), 0),
        "observing_count": observing_count,
        "latent_root_signal_count": latent_root_signal_count,
        "operator_hold_count": operator_hold_count,
        "stale_count": _safe_int(counts.get("stale"), 0),
        "oldest_open_age_min": _safe_int(counts.get("oldest_open_age_min"), 0),
        "active_candidate_count": len(active_candidates) if active_candidates_provided else -1,
        "active_executable_count": active_executable_count if active_candidates_provided else -1,
        "active_unsafe_count": max(0, len(active_candidates) - active_executable_count) if active_candidates_provided else -1,
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
    queue_status = str(queue.get("status") or "").strip().lower()
    if "open_count" in queue:
        generated_pending = _safe_int(queue.get("open_count"), 0)
    elif queue_status in {"clear", "empty", "ok"}:
        generated_pending = 0
    else:
        generated_pending = _safe_int(queue.get("count"), 0)
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


def _autonomy_maintenance_for_orchestrator(core_steward: dict) -> dict:
    maintenance = (
        dict((core_steward or {}).get("autonomy_maintenance") or {})
        if isinstance((core_steward or {}).get("autonomy_maintenance"), dict)
        else {}
    )
    return {
        "worker_status": str(maintenance.get("worker_status") or "").strip().lower(),
        "worker_active": bool(maintenance.get("worker_active", False)),
        "worker_stale_identity": bool(maintenance.get("worker_stale_identity", False)),
        "scheduler_active": bool(maintenance.get("scheduler_active", False)),
        "scheduler_mode": str(maintenance.get("scheduler_mode") or "").strip().lower(),
        "scheduler_status": str(maintenance.get("scheduler_status") or "").strip().lower(),
        "source_freshness_sec": 0,
    }


def _autonomy_policy_settings() -> dict:
    try:
        policy = nova_core.load_policy()
    except Exception:
        policy = {}
    settings = dict((policy or {}).get("autonomy") or {}) if isinstance((policy or {}).get("autonomy"), dict) else {}
    return settings


def _temporal_policy_settings() -> dict:
    try:
        policy = nova_core.load_policy()
    except Exception:
        policy = {}
    settings = dict((policy or {}).get("temporal") or {}) if isinstance((policy or {}).get("temporal"), dict) else {}
    return settings


def _temporal_feed_paths(settings: dict | None = None) -> list[str]:
    temporal = dict(settings or _temporal_policy_settings())
    raw_paths = temporal.get("ics_paths") if isinstance(temporal.get("ics_paths"), list) else []
    if not raw_paths:
        single = str(temporal.get("ics_path") or "").strip()
        if single:
            raw_paths = [single]
    out: list[str] = []
    for item in raw_paths:
        text = str(item or "").strip()
        if not text:
            continue
        path = Path(text)
        if not path.is_absolute():
            path = ROOT / path
        out.append(str(path.resolve()))
    return out


def _temporal_feed_for_signal_ingestion(state: dict) -> dict:
    feed = dict(state.get("last_temporal_feed") or {}) if isinstance(state.get("last_temporal_feed"), dict) else {}
    surfaced = [
        dict(item)
        for item in list(feed.get("surfaced_pressures") or [])
        if isinstance(item, dict)
    ]
    return {
        "temporal_enabled": bool(feed.get("enabled", False)),
        "temporal_feed_status": str(feed.get("status") or ""),
        "temporal_feed_last_run_at": str(feed.get("ran_at") or ""),
        "temporal_feed_source_count": int(feed.get("source_count", 0) or 0),
        "temporal_feed_event_count": int(feed.get("event_count", 0) or 0),
        "temporal_feed_surfaced_count": int(feed.get("surfaced_count", len(surfaced)) or 0),
        "temporal_feed_error_count": int(feed.get("error_count", 0) or 0),
        "temporal_pressure": surfaced,
    }


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
    if mode in {"canary", "execute"} and _autonomy_policy_bool(settings, "orchestrator_owns_execution", default=False):
        return _autonomy_policy_bool(settings, "legacy_maintenance_execution_enabled", default=False)
    return _autonomy_policy_bool(settings, "legacy_maintenance_execution_enabled", default=True)


def _policy_snapshot_for_orchestrator() -> dict:
    settings = _autonomy_policy_settings()
    advisory_actions = list(autonomy_advisory_action_types())
    requires_ack_default = ["update_now_dry_run"]
    mode = _autonomy_execution_mode(settings)
    execute_enabled = _autonomy_execution_enabled(settings)
    try:
        full_policy = nova_core.load_policy()
    except Exception:
        full_policy = {}
    layers = full_policy.get("layers") if isinstance(full_policy.get("layers"), dict) else {}
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
        "layers": layers,
        "active_work_tree_max_steps_per_cycle": _safe_int(
            settings.get("active_work_tree_max_steps_per_cycle"),
            ACTIVE_WORK_TREE_DEFAULT_DISPATCH_STEPS,
        ),
        "active_work_tree_max_trees_per_cycle": _safe_int(
            settings.get("active_work_tree_max_trees_per_cycle"),
            ACTIVE_WORK_TREE_MAX_TREES,
        ),
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


def _subconscious_terminal_no_repair_for_source_key(source_key: str) -> dict:
    clean_key = str(source_key or "").strip()
    if not clean_key:
        return {}
    for tree in work_tree.list_trees():
        for branch in work_tree.list_tree_branches(tree.tree_id):
            if str(getattr(branch, "source_key", "") or "").strip() != clean_key:
                continue
            if str(getattr(branch, "source_type", "") or "").strip().lower() != "subconscious":
                continue
            judgment = latest_subconscious_review_judgment_for_branch(work_tree, branch.branch_id)
            if is_no_owner_root_repair_judgment(judgment):
                return {
                    "branch_id": str(getattr(branch, "branch_id", "") or ""),
                    "classification": str(judgment.get("classification") or ""),
                    "verdict": str(judgment.get("verdict") or ""),
                }
    return {}


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


def _subconscious_triage_signals_for_work_tree(
    *,
    state: dict | None,
    generated_queue: dict | None,
    latest_report: dict | None,
    kidney_summary: dict | None = None,
    limit: int = 8,
) -> list[dict]:
    queue = dict(generated_queue or {}) if isinstance(generated_queue, dict) else {}
    report = dict(latest_report or {}) if isinstance(latest_report, dict) else {}
    if not report:
        return []
    runtime_context = _triage_runtime_context_for_orchestrator(state, queue, kidney_summary)
    signals: list[tuple[tuple[object, ...], dict]] = []
    for family in [dict(item) for item in list(report.get("families") or []) if isinstance(item, dict)]:
        priorities = list(family.get("training_priorities") or []) if isinstance(family.get("training_priorities"), list) else []
        for priority in [dict(item) for item in priorities if isinstance(item, dict)]:
            signal = _triage_signal_from_priority(family, priority, runtime_context)
            payload = dict(signal.get("payload") or {}) if isinstance(signal.get("payload"), dict) else {}
            if not payload:
                continue
            gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)
            if not bool(gate.get("approved")):
                continue
            payload["review_gate"] = dict(gate)
            payload["source_freshness_sec"] = _safe_int(report.get("_source_freshness_sec"), 0)
            signal["payload"] = payload
            source_key = WORK_TREE_SIGNAL_INGESTION_SERVICE.source_key_for_signal(signal)
            if _subconscious_terminal_no_repair_for_source_key(source_key):
                continue
            signals.append(
                (
                    (
                        -_safe_float(payload.get("robustness"), 0.0),
                        str(payload.get("target_seam") or ""),
                        str(payload.get("signal") or ""),
                        str(payload.get("family_id") or ""),
                    ),
                    signal,
                )
            )
    signals.sort(key=lambda item: item[0])
    return [signal for _rank, signal in signals[: max(0, int(limit or 0))]]


def _wiring_surface_status_keys(surface_id: str) -> tuple[str, ...]:
    for surface in WIRING_SURFACES:
        if str(surface.surface_id or "").strip() == surface_id:
            return tuple(surface.status_keys)
    return ()


def _probe_local_ollama_health() -> dict:
    try:
        ollama_health = nova_core.ollama_health_payload(timeout=1.0)
    except Exception as exc:
        ollama_health = {
            "ok": False,
            "server_ok": False,
            "status": "local_ollama_probe_failed",
            "info": str(exc),
            "tags_ok": False,
            "chat_route_ok": False,
            "model_available": False,
            "api_contract_status": "local_probe_failed",
        }
    return dict(ollama_health) if isinstance(ollama_health, dict) else {}


def _ollama_status_fields_from_health(ollama_health: dict) -> dict:
    health = dict(ollama_health or {})
    server_ok = bool(health.get("server_ok", health.get("ok", False)))
    return {
        "ollama_api_up": server_ok,
        "ollama_server_ok": server_ok,
        "ollama_chat_ready": bool(health.get("ok", False)),
        "ollama_health": dict(health),
        "ollama_health_status": str(health.get("status") or ""),
        "ollama_health_info": str(health.get("info") or ""),
        "ollama_tags_ok": bool(health.get("tags_ok", False)),
        "ollama_chat_route_ok": bool(health.get("chat_route_ok", False)),
        "ollama_version": str(health.get("version") or ""),
        "ollama_version_ok": bool(health.get("version_ok", False)),
        "ollama_version_status": int(health.get("version_status", 0) or 0),
        "ollama_api_contract_status": str(health.get("api_contract_status") or ""),
        "ollama_configured_model": str(health.get("chat_model") or ""),
        "ollama_model_available": bool(health.get("model_available", False)),
        "ollama_model_status": str(health.get("model_status") or ""),
        "ollama_available_models": list(health.get("available_models") or []),
    }


def _probe_local_port_ownership() -> dict:
    try:
        import psutil

        payload = PORT_OWNERSHIP_SERVICE.payload(psutil_module=psutil)
        return dict(payload) if isinstance(payload, dict) else {"status": "local_probe_failed"}
    except Exception as exc:
        return {"status": "local_probe_failed", "error": str(exc)}


def _apply_local_model_runtime_status(payload: dict, *, only_missing: bool = True) -> dict:
    result = dict(payload or {})
    required_keys = _wiring_surface_status_keys("model_runtime")
    missing_keys = [key for key in required_keys if key not in result]
    if only_missing and not missing_keys:
        return result

    ollama_fields = (
        "ollama_health",
        "ollama_api_up",
        "ollama_version",
        "ollama_api_contract_status",
        "ollama_chat_route_ok",
    )
    if not only_missing or any(key in missing_keys for key in ollama_fields):
        updates = _ollama_status_fields_from_health(_probe_local_ollama_health())
        for key, value in updates.items():
            if not only_missing or key not in result:
                result[key] = value

    if not only_missing or "port_ownership" in missing_keys:
        if not only_missing or "port_ownership" not in result:
            result["port_ownership"] = _probe_local_port_ownership()
    return result


def _apply_local_frontdoor_cli_surfaces(payload: dict, *, only_missing: bool = True) -> dict:
    result = dict(payload or {})
    surface_keys = (
        "backend_commands",
        "backend_command_count",
        "frontdoor_cli_status",
        "cli_http_parity",
    )
    missing_keys = [key for key in surface_keys if key not in result]
    if only_missing and not missing_keys:
        return result
    surfaces = FRONTDOOR_CLI_PARITY_SERVICE.build_surfaces(
        root=ROOT,
        load_backend_commands_fn=lambda limit: OPERATOR_CONTROL_SERVICE.load_backend_commands(
            OPERATOR_CONTROL_SERVICE.backend_command_deck_path(ROOT),
            limit=limit,
        ),
    )
    for key in surface_keys:
        if not only_missing or key not in result:
            result[key] = surfaces.get(key)
    return result


def _probe_local_http_api_metrics() -> tuple[int, int]:
    try:
        import nova_http

        return (
            int(getattr(nova_http, "_HTTP_REQUESTS_TOTAL", 0) or 0),
            int(getattr(nova_http, "_HTTP_ERRORS_TOTAL", 0) or 0),
        )
    except Exception:
        return 0, 0


def _probe_local_chat_login_enabled() -> bool:
    try:
        chat_users_path = CHAT_IDENTITY_SERVICE.chat_users_path(RUNTIME_DIR)
        users = CHAT_IDENTITY_SERVICE.chat_users(
            chat_users_path=chat_users_path,
            environ=os.environ,
        )
        return bool(CHAT_IDENTITY_SERVICE.chat_login_enabled(chat_users_fn=lambda: users))
    except Exception:
        return False


def _apply_local_operator_control_surfaces(payload: dict, *, only_missing: bool = True) -> dict:
    result = dict(payload or {})
    required_keys = _wiring_surface_status_keys("operator_control")
    missing_keys = [key for key in required_keys if key not in result]
    if only_missing and not missing_keys:
        return result

    if not only_missing or "operator_macros" in missing_keys:
        if not only_missing or "operator_macros" not in result:
            result["operator_macros"] = OPERATOR_CONTROL_SERVICE.load_operator_macros(
                OPERATOR_CONTROL_SERVICE.operator_macros_path(ROOT),
                limit=24,
            )

    if not only_missing or "backend_commands" in missing_keys:
        if not only_missing or "backend_commands" not in result:
            commands = OPERATOR_CONTROL_SERVICE.load_backend_commands(
                OPERATOR_CONTROL_SERVICE.backend_command_deck_path(ROOT),
                limit=80,
            )
            result["backend_commands"] = commands
            if not only_missing or "backend_command_count" not in result:
                result["backend_command_count"] = len(commands)

    if not only_missing or any(key in missing_keys for key in ("operator_outbox", "operator_outbox_open_count")):
        outbox = OPERATOR_OUTBOX_SERVICE.summary(OPERATOR_OUTBOX, limit=20)
        if not only_missing or "operator_outbox" not in result:
            result["operator_outbox"] = outbox
        if not only_missing or "operator_outbox_open_count" not in result:
            result["operator_outbox_open_count"] = int(outbox.get("open_count", 0) or 0)
    return result


def _apply_local_http_api_control_surfaces(payload: dict, *, only_missing: bool = True) -> dict:
    result = dict(payload or {})
    required_keys = _wiring_surface_status_keys("http_api_control")
    missing_keys = [key for key in required_keys if key not in result]
    if only_missing and not missing_keys:
        return result

    if not only_missing or any(key in missing_keys for key in ("requests_total", "errors_total")):
        requests_total, errors_total = _probe_local_http_api_metrics()
        if not only_missing or "requests_total" not in result:
            result["requests_total"] = requests_total
        if not only_missing or "errors_total" not in result:
            result["errors_total"] = errors_total

    if not only_missing or "chat_login_enabled" in missing_keys:
        if not only_missing or "chat_login_enabled" not in result:
            result["chat_login_enabled"] = _probe_local_chat_login_enabled()
    return result


def _apply_local_source_root_status_surfaces(payload: dict, *, only_missing: bool = True) -> dict:
    result = dict(payload or {})
    if not only_missing or "source_root_inventory" not in result:
        result["source_root_inventory"] = result.get("source_root_inventory") or {}
    for key in ("last_intent", "last_planner_decision", "last_route_summary"):
        if not only_missing or key not in result:
            result[key] = str(result.get(key) or "")
    try:
        if (
            not only_missing
            or not isinstance(result.get("source_root_inventory"), dict)
            or int((result.get("source_root_inventory") or {}).get("root_count", 0) or 0) == 0
        ):
            src = build_source_root_inventory_payload()
            if isinstance(src, dict):
                result["source_root_inventory"] = src
    except Exception:
        pass
    return result


def _refresh_root_closure_inventory_surfaces(payload: dict) -> dict:
    result = dict(payload or {})
    try:
        root_closure = build_root_closure_inventory_payload(result)
        result["root_closure_inventory"] = root_closure
        result["root_closure_inventory_ok"] = bool(root_closure.get("ok", False))
        result["root_closure_inventory_gap_count"] = int(root_closure.get("gap_count", 0) or 0)
        result["root_closure_inventory_gap_roots"] = list(root_closure.get("gap_roots") or [])
    except Exception:
        result["root_closure_inventory"] = {"ok": True, "gap_count": 0, "gap_roots": [], "roots": []}
        result["root_closure_inventory_ok"] = True
        result["root_closure_inventory_gap_count"] = 0
        result["root_closure_inventory_gap_roots"] = []
    if "self_repair_closure_inventory" not in result:
        result["self_repair_closure_inventory"] = {"ok": True, "gap_count": 0, "gap_roots": [], "roots": []}
        result["self_repair_closure_inventory_ok"] = True
        result["self_repair_closure_inventory_gap_count"] = 0
    return result


def _apply_layer_maturity_to_status_payload(payload: dict) -> dict:
    try:
        policy = nova_core.load_policy()
    except Exception:
        policy = {}
    enriched = enrich_status_with_layer_maturity(dict(payload or {}), policy=policy)
    return enriched


def _enrich_signal_ingestion_status_payload(payload: dict, *, only_missing: bool = True) -> dict:
    enriched = _apply_local_model_runtime_status(payload, only_missing=only_missing)
    enriched = _apply_local_frontdoor_cli_surfaces(enriched, only_missing=only_missing)
    enriched = _apply_local_operator_control_surfaces(enriched, only_missing=only_missing)
    enriched = _apply_local_http_api_control_surfaces(enriched, only_missing=only_missing)
    enriched = _apply_local_source_root_status_surfaces(enriched, only_missing=only_missing)
    enriched = _refresh_root_closure_inventory_surfaces(enriched)
    return _apply_layer_maturity_to_status_payload(enriched)


def _fetch_control_status_json(url: str, *, timeout_sec: float, read_limit: int) -> dict | None:
    clean_url = str(url or "").strip()
    if not clean_url:
        return None
    try:
        request = urllib.request.Request(clean_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=float(timeout_sec)) as response:
            raw = response.read(max(1, int(read_limit)))
        live = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None
    return dict(live) if isinstance(live, dict) else None


def _invalidate_control_status_caches_lazy() -> None:
    try:
        import nova_http

        nova_http._invalidate_control_status_cache()
    except Exception:
        pass


def _maybe_invalidate_control_status_cache_for_release_drift(release_status: dict | None) -> None:
    global _LAST_KNOWN_RELEASE_DRIFT_STATE
    payload = dict(release_status or {}) if isinstance(release_status, dict) else {}
    state = str(payload.get("latest_readiness_state") or payload.get("status") or "").strip()
    if not state or state == _LAST_KNOWN_RELEASE_DRIFT_STATE:
        return
    _LAST_KNOWN_RELEASE_DRIFT_STATE = state
    if release_drift_detected(payload):
        _invalidate_control_status_caches_lazy()


def _live_control_status_payload_http_full(fallback_payload: dict) -> dict:
    fallback = dict(fallback_payload or {})
    live = _fetch_control_status_json(
        CONTROL_STATUS_URL,
        timeout_sec=CONTROL_STATUS_TIMEOUT_SEC,
        read_limit=2_000_000,
    )
    if live is None:
        return _local_dependency_payload_for_signal_ingestion(fallback)
    merged = {**fallback, **live}
    fallback_maintenance = fallback.get("autonomy_maintenance") if isinstance(fallback.get("autonomy_maintenance"), dict) else {}
    live_maintenance = live.get("autonomy_maintenance") if isinstance(live.get("autonomy_maintenance"), dict) else {}
    if fallback_maintenance:
        merged["autonomy_maintenance"] = {**dict(live_maintenance or {}), **dict(fallback_maintenance or {})}
    _maybe_invalidate_control_status_cache_for_release_drift(
        live.get("release_status") if isinstance(live.get("release_status"), dict) else {}
    )
    merged["signal_ingestion_status_source"] = "control_status_http"
    return _enrich_signal_ingestion_status_payload(merged, only_missing=True)


def _live_control_status_payload_http_surfaces(fallback_payload: dict) -> dict:
    fallback = dict(fallback_payload or {})
    live = _fetch_control_status_json(
        CONTROL_STATUS_SURFACES_URL,
        timeout_sec=CONTROL_STATUS_SURFACES_TIMEOUT_SEC,
        read_limit=512_000,
    )
    if live is None:
        return _local_dependency_payload_for_signal_ingestion(fallback)
    merged = {**fallback, **live}
    fallback_maintenance = fallback.get("autonomy_maintenance") if isinstance(fallback.get("autonomy_maintenance"), dict) else {}
    live_maintenance = live.get("autonomy_maintenance") if isinstance(live.get("autonomy_maintenance"), dict) else {}
    if fallback_maintenance:
        merged["autonomy_maintenance"] = {**dict(live_maintenance or {}), **dict(fallback_maintenance or {})}
    _maybe_invalidate_control_status_cache_for_release_drift(
        live.get("release_status") if isinstance(live.get("release_status"), dict) else {}
    )
    merged["signal_ingestion_status_source"] = "control_status_http_surfaces"
    return _enrich_signal_ingestion_status_payload(merged, only_missing=True)


def _live_control_status_payload_local_first(fallback_payload: dict) -> dict:
    fallback = dict(fallback_payload or {})
    local = _local_dependency_payload_for_signal_ingestion(fallback)
    live = _fetch_control_status_json(
        CONTROL_STATUS_SURFACES_URL,
        timeout_sec=CONTROL_STATUS_SURFACES_TIMEOUT_SEC,
        read_limit=512_000,
    )
    if live is None:
        local["signal_ingestion_status_source"] = "local_dependency_probe"
        return local
    merged = merge_http_supplement_into_local(local, live)
    fallback_maintenance = fallback.get("autonomy_maintenance") if isinstance(fallback.get("autonomy_maintenance"), dict) else {}
    live_maintenance = live.get("autonomy_maintenance") if isinstance(live.get("autonomy_maintenance"), dict) else {}
    if fallback_maintenance:
        merged["autonomy_maintenance"] = {**dict(live_maintenance or {}), **dict(fallback_maintenance or {})}
    _maybe_invalidate_control_status_cache_for_release_drift(
        live.get("release_status") if isinstance(live.get("release_status"), dict) else {}
    )
    merged["signal_ingestion_status_source"] = "local_first_with_http_surfaces"
    return _enrich_signal_ingestion_status_payload(merged, only_missing=True)


def _live_control_status_payload_for_signal_ingestion(fallback_payload: dict) -> dict:
    mode = SIGNAL_INGESTION_STATUS_MODE
    if mode in {"http", "http_full", "full"}:
        return _live_control_status_payload_http_full(fallback_payload)
    if mode in {"http_surfaces", "surfaces"}:
        return _live_control_status_payload_http_surfaces(fallback_payload)
    if mode in {"local", "local_only"}:
        return _local_dependency_payload_for_signal_ingestion(fallback_payload)
    return _live_control_status_payload_local_first(fallback_payload)


def _local_dependency_payload_for_signal_ingestion(fallback_payload: dict) -> dict:
    payload = dict(fallback_payload or {})
    payload["signal_ingestion_status_source"] = "local_dependency_probe"
    return _enrich_signal_ingestion_status_payload(payload, only_missing=False)


def _local_release_status_for_signal_ingestion() -> dict:
    try:
        source_root = ROOT
        try:
            RELEASE_LEDGER_PATH.resolve().relative_to((RUNTIME_DIR / "exports" / "release_packages").resolve())
        except Exception:
            source_root = None
        return RELEASE_STATUS_SERVICE.status_payload(
            RELEASE_LEDGER_PATH,
            limit=8,
            source_root=source_root,
            artifact_kind="package-zip",
        )
    except Exception:
        return {}


def _probe_http_model_runtime_surfaces() -> dict:
    http_payload = _fetch_control_status_json(
        CONTROL_STATUS_SURFACES_URL,
        timeout_sec=CONTROL_STATUS_SURFACES_TIMEOUT_SEC,
        read_limit=512_000,
    )
    if http_payload is None:
        return {
            "ok": False,
            "required_key_count": 0,
            "present_key_count": 0,
            "missing_keys": [],
            "present_keys": [],
            "source": "http_surfaces",
            "skipped": True,
            "reason": "http_surfaces_unreachable",
        }
    probe = evaluate_http_model_runtime_probe(http_payload)
    probe["skipped"] = False
    return probe


def _apply_release_runtime_truth_to_status_payload(
    status_payload: dict,
    *,
    state: dict | None = None,
) -> dict:
    result = dict(status_payload or {})
    release = result.get("release_status") if isinstance(result.get("release_status"), dict) else {}
    if not release:
        release = _local_release_status_for_signal_ingestion()
    else:
        release = enrich_release_status(release)
    result["release_status"] = release
    truth = build_release_runtime_truth_summary(release)
    result["release_runtime_truth"] = truth
    probe = _probe_http_model_runtime_surfaces()
    result["http_model_runtime_probe"] = probe
    result["http_model_runtime_probe_ok"] = bool(probe.get("ok"))
    result["http_model_runtime_missing_keys"] = list(probe.get("missing_keys") or [])
    if state is not None:
        state["last_http_model_runtime_probe"] = dict(probe)
        state["last_release_runtime_truth"] = dict(truth)
    return result


def _validation_artifact_truth_payload_for_signal_ingestion() -> dict:
    try:
        truth = VALIDATION_ARTIFACT_TRUTH_SERVICE.payload(
            runtime_dir=RUNTIME_DIR,
            regression_status_path=REGRESSION_STATUS_FILE,
        )
    except Exception as exc:
        truth = {
            "ok": False,
            "status": "validation_artifact_truth_unavailable",
            "current_window_failure_count": 0,
            "current_window_llm_unavailable_count": 0,
            "hidden_by_green_regression": False,
            "latest_failure": {},
            "failures": [],
            "error": str(exc),
            "rationale": "Maintenance could not read validation action artifacts directly.",
        }
    if not isinstance(truth, dict):
        truth = {"ok": True, "status": "not_available"}
    return {
        "validation_artifact_truth": dict(truth),
        "validation_artifact_truth_ok": bool(truth.get("ok", True)),
        "validation_artifact_truth_status": str(truth.get("status") or ""),
        "validation_artifact_failure_count": _safe_int(
            truth.get("current_window_failure_count", truth.get("failure_count", 0)),
            0,
        ),
        "validation_artifact_llm_unavailable_count": _safe_int(
            truth.get("current_window_llm_unavailable_count", truth.get("llm_unavailable_count", 0)),
            0,
        ),
        "validation_artifact_hidden_by_green_regression": bool(truth.get("hidden_by_green_regression", False)),
        "validation_artifact_latest_failure": (
            dict(truth.get("latest_failure") or {})
            if isinstance(truth.get("latest_failure"), dict)
            else {}
        ),
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
        "last_target_step_id": str(last_execution.get("target_step_id") or ""),
        "last_action_at_utc": str(last_execution.get("created_at_utc") or last_orchestrator.get("created_at_utc") or last_orchestrator.get("ts") or ""),
        "cooldown_active": bool(cooldown_remaining > 0),
        "cooldown_remaining_sec": cooldown_remaining,
        "last_result": str(last_execution.get("result") or "unknown"),
        "source_freshness_sec": 0,
    }


def _layer_maturity_snapshot_for_orchestrator(state: dict) -> dict:
    snapshot = dict(state.get("last_layer_maturity_snapshot") or {})
    if snapshot:
        return snapshot
    return {
        "release_runtime_truth": dict(state.get("last_release_runtime_truth") or {}),
        "release_status": {},
        "root_closure_inventory": {},
        "capabilities_registered": {},
    }


def _autonomy_orchestrator_input_envelope(
    *,
    state: dict,
    core_steward: dict,
    work_tree_state: dict,
    generated_queue: dict,
    guard_health: dict,
    active_work_candidates: list[dict] | None = None,
    latest_report: dict | None = None,
    kidney_summary: dict | None = None,
    policy_snapshot: dict | None = None,
) -> dict:
    return {
        "cycle_id": f"autonomy-maintenance-{time.strftime('%Y%m%d%H%M%S')}",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "work_tree_snapshot": _work_tree_snapshot_for_orchestrator(work_tree_state, active_work_candidates),
        "steward_posture": _steward_posture_for_orchestrator(core_steward),
        "queue_pressure": _queue_pressure_for_orchestrator(generated_queue, state),
        "runtime_guard_status": _runtime_guard_status_for_orchestrator(core_steward, guard_health),
        "autonomy_maintenance": _autonomy_maintenance_for_orchestrator(core_steward),
        "policy_snapshot": dict(policy_snapshot or _policy_snapshot_for_orchestrator()),
        "layer_maturity_snapshot": _layer_maturity_snapshot_for_orchestrator(state),
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
    work_tree_state = CONTROL_WORK_TREES_SERVICE.payload(
        list_visual_trees_fn=work_tree.list_visual_trees,
        limit=64,
    )
    generated_queue = _generated_work_queue(limit=200)
    guard_health = _guard_health_for_orchestrator()
    core_steward = _core_steward_for_orchestrator(state, kidney_summary, guard_health=guard_health)
    policy_snapshot = _policy_snapshot_for_orchestrator()
    latest_report = _latest_subconscious_report_for_triage()
    active_work_candidates = _active_work_tree_candidates(ACTIVE_WORK_TREE_MAX_TREES)
    requested_mode = "execute" if bool(policy_snapshot.get("execute_enabled")) else "advisory"
    AUTONOMY_ORCHESTRATOR_SERVICE.set_mode(requested_mode, policy_snapshot)
    packet = AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_next_action(
        _autonomy_orchestrator_input_envelope(
            state=state,
            core_steward=core_steward,
            work_tree_state=work_tree_state,
            generated_queue=generated_queue,
            guard_health=guard_health,
            active_work_candidates=active_work_candidates,
            latest_report=latest_report,
            kidney_summary=kidney_summary,
            policy_snapshot=policy_snapshot,
        ),
    )
    execution = _execute_autonomy_recommendation(state, packet, policy_snapshot)
    ledger = dict(packet.get("ledger") or {}) if isinstance(packet.get("ledger"), dict) else {}
    ledger_row = dict(ledger.get("row") or {}) if isinstance(ledger.get("row"), dict) else {}
    ledger_status = "not_requested"
    if ledger_row:
        ledger_row["execution"] = _compact_autonomy_execution_for_ledger(execution)
        ledger_row["execution_result"] = str(execution.get("result") or "")
        ledger_row["execution_action_type"] = str(execution.get("action_type") or "")
        try:
            _append_autonomy_orchestrator_ledger(dict(ledger_row))
            ledger_status = "recorded"
        except Exception as exc:
            ledger_status = f"record_failed:{exc}"
    packet["ledger"] = {
        "status": ledger_status,
        "row": ledger_row,
    }
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
    operator_notice = _publish_operator_notice_from_autonomy(packet, execution)
    state["last_operator_outbox_notice"] = operator_notice
    packet["operator_notice"] = operator_notice
    work_tree_operator_notices = _publish_operator_notices_from_work_tree(work_tree_state)
    state["last_operator_outbox_work_tree_notices"] = work_tree_operator_notices
    packet["operator_work_tree_notices"] = work_tree_operator_notices
    return packet


_SUBCONSCIOUS_PACK_TIMEOUT_SEC = 900
_TEMPORAL_DEFAULT_POLL_INTERVAL_SEC = 900
_TEMPORAL_MIN_POLL_INTERVAL_SEC = 60
_TEMPORAL_DEFAULT_SURFACE_MIN_SCORE = 45.0
_TEMPORAL_DEFAULT_MAX_SURFACE_EVENTS = 8


def _elapsed_sec(start: float) -> float:
    try:
        return round(max(0.0, time.monotonic() - float(start)), 2)
    except Exception:
        return 0.0


def _subconscious_pack_timeout_sec() -> int:
    try:
        return max(1, int(_SUBCONSCIOUS_PACK_TIMEOUT_SEC))
    except Exception:
        return 1


def _run_subconscious_pack() -> tuple[bool, str]:
    label = "phase1_auto"
    cmd = [str(VENV_PY), str(ROOT / "subconscious_runner.py"), "--label", label]
    timeout = _subconscious_pack_timeout_sec()
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
        elapsed = _elapsed_sec(t0)
        _append_log(f"subconscious_pack_duration_sec={elapsed}")
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            return False, output[-2000:]
        return True, output[-2000:]
    except subprocess.TimeoutExpired as exc:
        elapsed = _elapsed_sec(t0)
        _append_log(f"subconscious_pack_duration_sec={elapsed} status=timeout timeout_sec={timeout}")
        output = ((getattr(exc, "stdout", "") or "") + "\n" + (getattr(exc, "stderr", "") or "")).strip()
        detail = f"subconscious_runner.py timed out after {timeout} seconds (elapsed_sec={elapsed})"
        if output:
            detail = f"{detail}\n{output[-2000:]}"
        return False, detail[-2000:]
    except Exception as exc:
        elapsed = _elapsed_sec(t0)
        _append_log(f"subconscious_pack_duration_sec={elapsed} status=exception")
        return False, str(exc)


def _run_temporal_feed_pass(state: dict) -> dict:
    temporal_settings = _temporal_policy_settings()
    enabled = bool(temporal_settings.get("enabled", False))
    source_paths = _temporal_feed_paths(temporal_settings)
    interval_sec = max(
        _TEMPORAL_MIN_POLL_INTERVAL_SEC,
        _safe_int(temporal_settings.get("poll_interval_sec"), _TEMPORAL_DEFAULT_POLL_INTERVAL_SEC),
    )
    surface_min_score = max(
        0.0,
        min(100.0, _safe_float(temporal_settings.get("surface_min_score"), _TEMPORAL_DEFAULT_SURFACE_MIN_SCORE)),
    )
    max_surface_events = max(
        1,
        _safe_int(temporal_settings.get("max_surface_events"), _TEMPORAL_DEFAULT_MAX_SURFACE_EVENTS),
    )
    previous = dict(state.get("last_temporal_feed") or {}) if isinstance(state.get("last_temporal_feed"), dict) else {}
    previous_epoch = _safe_float(previous.get("ran_epoch"), 0.0)
    now_epoch = time.time()

    if enabled and previous_epoch > 0 and (now_epoch - previous_epoch) < float(interval_sec):
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "skipped_cadence",
            "enabled": True,
            "source_paths": source_paths,
            "source_count": len(source_paths),
            "interval_sec": int(interval_sec),
            "surface_min_score": float(surface_min_score),
            "max_surface_events": int(max_surface_events),
            "ran_at": str(previous.get("ran_at") or ""),
            "ran_epoch": float(previous_epoch),
            "next_run_sec": max(0, int(float(interval_sec) - (now_epoch - previous_epoch))),
            "event_count": int(previous.get("event_count", 0) or 0),
            "surfaced_count": int(previous.get("surfaced_count", 0) or 0),
            "error_count": int(previous.get("error_count", 0) or 0),
            "surfaced_pressures": [
                dict(item)
                for item in list(previous.get("surfaced_pressures") or [])
                if isinstance(item, dict)
            ][:max_surface_events],
            "errors": [
                dict(item)
                for item in list(previous.get("errors") or [])
                if isinstance(item, dict)
            ][:5],
        }
        state["last_temporal_feed"] = payload
        return payload

    if not enabled:
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "disabled",
            "enabled": False,
            "source_paths": source_paths,
            "source_count": len(source_paths),
            "interval_sec": int(interval_sec),
            "surface_min_score": float(surface_min_score),
            "max_surface_events": int(max_surface_events),
            "event_count": 0,
            "surfaced_count": 0,
            "error_count": 0,
            "surfaced_pressures": [],
            "errors": [],
            "ran_at": _patch_queue_timestamp(),
            "ran_epoch": float(now_epoch),
        }
        state["last_temporal_feed"] = payload
        return payload

    if not source_paths:
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "misconfigured_no_source_paths",
            "enabled": True,
            "source_paths": [],
            "source_count": 0,
            "interval_sec": int(interval_sec),
            "surface_min_score": float(surface_min_score),
            "max_surface_events": int(max_surface_events),
            "event_count": 0,
            "surfaced_count": 0,
            "error_count": 1,
            "surfaced_pressures": [],
            "errors": [{"path": "", "error": "temporal_missing_ics_paths"}],
            "ran_at": _patch_queue_timestamp(),
            "ran_epoch": float(now_epoch),
        }
        state["last_temporal_feed"] = payload
        return payload

    service = NovaTemporalService()
    event_count = 0
    surfaced_pressures: list[dict] = []
    errors: list[dict] = []
    for source_path in source_paths:
        try:
            events = parse_ics_file(source_path, source="calendar")
        except Exception as exc:
            errors.append({"path": source_path, "error": str(exc)})
            continue

        event_count += len(events)
        for pressure in service.assess_many(events):
            if _safe_float(pressure.final_score, 0.0) < float(surface_min_score):
                continue
            row = pressure.to_dict()
            row["source_path"] = source_path
            surfaced_pressures.append(row)

    surfaced_pressures.sort(
        key=lambda row: (
            -_safe_float(row.get("final_score"), 0.0),
            str(((row.get("event") if isinstance(row.get("event"), dict) else {}).get("start") or "")),
            str(((row.get("event") if isinstance(row.get("event"), dict) else {}).get("title") or "")),
        )
    )
    surfaced_pressures = surfaced_pressures[:max_surface_events]

    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok" if not errors else ("partial" if surfaced_pressures or event_count else "failed"),
        "enabled": True,
        "source_paths": source_paths,
        "source_count": len(source_paths),
        "interval_sec": int(interval_sec),
        "surface_min_score": float(surface_min_score),
        "max_surface_events": int(max_surface_events),
        "event_count": int(event_count),
        "surfaced_count": len(surfaced_pressures),
        "error_count": len(errors),
        "surfaced_pressures": surfaced_pressures,
        "errors": errors[:5],
        "ran_at": _patch_queue_timestamp(),
        "ran_epoch": float(now_epoch),
    }
    state["last_temporal_feed"] = payload
    return payload


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


def _compact_report_summary(report: dict) -> dict:
    return {
        "run_id": str((report or {}).get("run_id") or ""),
        "status": str((report or {}).get("status") or ""),
        "session_path": str((report or {}).get("session_path") or ""),
        "report_path": str((report or {}).get("report_path") or ""),
    }


def _compact_work_queue_summary(work_queue: dict) -> dict:
    items = []
    for item in list((work_queue or {}).get("items") or [])[:8]:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "file": str(item.get("file") or ""),
                "latest_status": str(item.get("latest_status") or ""),
                "actionable": bool(item.get("actionable", False)),
                "blocked_reason": str(item.get("blocked_reason") or ""),
            }
        )
    next_item = dict((work_queue or {}).get("next_item") or {})
    return {
        "status": str((work_queue or {}).get("status") or ""),
        "count": int((work_queue or {}).get("count", 0) or 0),
        "open_count": int((work_queue or {}).get("open_count", 0) or 0),
        "actionable_count": int((work_queue or {}).get("actionable_count", 0) or 0),
        "blocked_count": int((work_queue or {}).get("blocked_count", 0) or 0),
        "next_file": str(next_item.get("file") or ""),
        "blocked_reason_counts": dict((work_queue or {}).get("blocked_reason_counts") or {})
        if isinstance((work_queue or {}).get("blocked_reason_counts"), dict)
        else {},
        "blocked_files": list((work_queue or {}).get("blocked_files") or [])
        if isinstance((work_queue or {}).get("blocked_files"), list)
        else [],
        "items": items,
    }


def _compact_generated_queue_execution_extra(extra: dict | None) -> dict:
    data = dict(extra or {}) if isinstance(extra, dict) else {}
    definitions = [dict(item) for item in list(data.get("definitions") or []) if isinstance(item, dict)]
    return {
        "selected": dict(data.get("selected") or {}) if isinstance(data.get("selected"), dict) else {},
        "runner_message": str(data.get("runner_message") or ""),
        "latest_report": _compact_report_summary(dict(data.get("latest_report") or {})),
        "reports": [_compact_report_summary(dict(item)) for item in list(data.get("reports") or [])[:3] if isinstance(item, dict)],
        "work_queue": _compact_work_queue_summary(dict(data.get("work_queue") or {})),
        "definition_count": len(definitions),
        "definition_files": [str(item.get("file") or "") for item in definitions[:12]],
    }


def _compact_tool_result_summary(result: object) -> dict:
    if isinstance(result, dict):
        summary = {}
        for key in ("ok", "status", "result", "message", "artifact", "report_path", "failure_reason", "readiness_state", "ready_to_ship", "promoted"):
            if key in result:
                summary[key] = result.get(key)
        return summary
    text = str(result or "")
    if not text:
        return {}
    return {
        "text_preview": text[:500],
        "text_length": len(text),
    }


def _compact_work_tree_history(history: list[dict] | None, *, limit: int = 8) -> list[dict]:
    compact: list[dict] = []
    for item in list(history or [])[: max(1, int(limit or 8))]:
        if not isinstance(item, dict):
            continue
        row = {
            "action": str(item.get("action") or ""),
            "tree_id": str(item.get("tree_id") or ""),
            "tree_title": str(item.get("tree_title") or ""),
            "branch_id": str(item.get("branch_id") or ""),
            "branch_title": str(item.get("branch_title") or ""),
            "task_id": str(item.get("task_id") or ""),
            "task_title": str(item.get("task_title") or ""),
            "tool": str(item.get("tool") or item.get("recommended_tool") or ""),
            "evidence_id": str(item.get("evidence_id") or item.get("failure_evidence_id") or ""),
            "reason": str(item.get("reason") or ""),
        }
        if "tool_args" in item:
            row["tool_args"] = list(item.get("tool_args") or [])[:8] if isinstance(item.get("tool_args"), list) else item.get("tool_args")
        if "tool_result" in item:
            row["tool_result_summary"] = _compact_tool_result_summary(item.get("tool_result"))
        compact.append({key: value for key, value in row.items() if value not in ("", [], {})})
    return compact


def _compact_work_tree_cycle_payload(cycle: dict | None) -> dict:
    data = dict(cycle or {}) if isinstance(cycle, dict) else {}
    compact = {
        "ts": str(data.get("ts") or ""),
        "status": str(data.get("status") or ""),
        "tree_count": _safe_int(data.get("tree_count"), 0),
        "attempted_count": _safe_int(data.get("attempted_count"), 0),
        "executed_count": _safe_int(data.get("executed_count"), 0),
        "history_count": _safe_int(data.get("history_count"), len(list(data.get("history") or [])) if isinstance(data.get("history"), list) else 0),
        "processed_tree_count": _safe_int(data.get("processed_tree_count"), 0),
        "skipped_tree_count": _safe_int(data.get("skipped_tree_count"), 0),
        "last_action": str(data.get("last_action") or ""),
        "processed": list(data.get("processed") or [])[:8] if isinstance(data.get("processed"), list) else [],
        "skipped": list(data.get("skipped") or [])[:8] if isinstance(data.get("skipped"), list) else [],
    }
    if isinstance(data.get("history"), list):
        compact["history"] = _compact_work_tree_history(data.get("history"))
    if isinstance(data.get("core_thinning_sync"), dict):
        compact["core_thinning_sync"] = dict(data.get("core_thinning_sync") or {})
    return {key: value for key, value in compact.items() if value not in ("", [], {})}


def _compact_autonomy_execution_extra(action_type: str, extra: dict | None) -> dict:
    if action_type == "generated_queue_run_next":
        return _compact_generated_queue_execution_extra(extra)
    if action_type in {"active_work_tree_run_next", "patch_queue_run_next"}:
        data = dict(extra or {}) if isinstance(extra, dict) else {}
        if isinstance(data.get("cycle"), dict):
            data["cycle"] = _compact_work_tree_cycle_payload(data.get("cycle"))
        return data
    return dict(extra or {}) if isinstance(extra, dict) else {}


def _compact_autonomy_execution_for_ledger(execution: dict | None) -> dict:
    data = dict(execution or {}) if isinstance(execution, dict) else {}
    events = []
    for event in list(data.get("events") or [])[:8]:
        if not isinstance(event, dict):
            continue
        payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}
        events.append(
            {
                "act": str(event.get("act") or ""),
                "status": str(event.get("status") or ""),
                "detail": str(event.get("detail") or ""),
                "target_kind": str(payload.get("target_kind") or ""),
                "target_id": str(payload.get("target_id") or ""),
                "target_step_id": str(payload.get("target_step_id") or ""),
                "reason_code": str(payload.get("reason_code") or ""),
            }
        )
    compact = {
        "ts": str(data.get("ts") or ""),
        "created_at_utc": str(data.get("created_at_utc") or ""),
        "mode": str(data.get("mode") or ""),
        "gate_status": str(data.get("gate_status") or ""),
        "gate_reason": str(data.get("gate_reason") or ""),
        "action_type": str(data.get("action_type") or ""),
        "target_id": str(data.get("target_id") or ""),
        "target_step_id": str(data.get("target_step_id") or ""),
        "allowed": bool(data.get("allowed", False)),
        "result": str(data.get("result") or ""),
        "ok": bool(data.get("ok", False)),
        "message": str(data.get("message") or ""),
        "refusal_reasons": list(data.get("refusal_reasons") or []),
        "cooldown_sec": _safe_int(data.get("cooldown_sec"), 0),
        "events": events,
    }
    extra = dict(data.get("extra") or {}) if isinstance(data.get("extra"), dict) else {}
    if isinstance(extra.get("cycle"), dict):
        compact["cycle"] = _compact_work_tree_cycle_payload(extra.get("cycle"))
    elif extra:
        compact["extra"] = extra
    return {key: value for key, value in compact.items() if value not in ("", [], {})}


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


def _maintenance_logical_service_processes(script_path: Path, root_pid: int | None = None) -> list[dict]:
    del root_pid
    return runtime_processes.logical_service_processes(script_path)


def _maintenance_cached_logical_service_processes(
    script_path: Path,
    *,
    cache_key: str = "",
    max_age_seconds: float = 0.0,
) -> list[dict]:
    del cache_key, max_age_seconds
    return _maintenance_logical_service_processes(script_path)


def _maintenance_select_logical_process(
    processes: list[dict],
    *,
    pid: int | None = None,
    create_time: float | None = None,
) -> dict | None:
    return runtime_processes.select_logical_process(processes, pid=pid, create_time=create_time)


def _maintenance_prune_orphaned_guard_artifacts(
    _logical_processes: list[dict],
    _pid: int | None,
    _pid_live: bool,
) -> None:
    return None


def _maintenance_guard_status_payload() -> dict:
    try:
        import psutil

        return RUNTIME_STATUS_SERVICE.guard_status_payload(
            runtime_dir=RUNTIME_DIR,
            guard_py=GUARD_PY,
            include_fallback_scan=True,
            pid_exists_fn=psutil.pid_exists,
            cached_logical_service_processes_fn=_maintenance_cached_logical_service_processes,
            logical_service_processes_fn=_maintenance_logical_service_processes,
            prune_orphaned_guard_artifacts_fn=_maintenance_prune_orphaned_guard_artifacts,
            select_logical_process_fn=_maintenance_select_logical_process,
            process_scan_cache_ttl_seconds=2.0,
        )
    except Exception as exc:
        return {"running": False, "status": "unavailable", "error": str(exc)}


def _maintenance_start_guard() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.start_guard(
        venv_python=Path(VENV_PY),
        guard_py=GUARD_PY,
        runtime_dir=RUNTIME_DIR,
        base_dir=ROOT,
        guard_status_fn=_maintenance_guard_status_payload,
        restart_intent_path=RESTART_INTENT_PATH,
        restart_provenance_service=RUNTIME_RESTART_PROVENANCE_SERVICE,
        subprocess_module=subprocess,
        os_name=os.name,
    )


def _maintenance_guard_control_action(payload: dict) -> tuple[bool, str, dict, str]:
    action = str((payload or {}).get("_action") or (payload or {}).get("action") or "").strip().lower()
    if action == "guard_status":
        return RUNTIME_CONTROL_SERVICE.guard_status_action(
            guard_status_payload_fn=_maintenance_guard_status_payload,
        )
    if action == "guard_start":
        return RUNTIME_CONTROL_SERVICE.guard_start_action(
            start_guard_fn=_maintenance_start_guard,
            guard_status_payload_fn=_maintenance_guard_status_payload,
        )
    return _unsupported_control_action(payload)


def _maintenance_autonomy_maintenance_summary() -> dict:
    return _load_state()


def _maintenance_start_autonomy_maintenance_worker() -> tuple[bool, str]:
    return RUNTIME_CONTROL_SERVICE.start_autonomy_maintenance_worker(
        venv_python=Path(VENV_PY),
        maintenance_py=AUTONOMY_MAINTENANCE_PY,
        state_path=STATE_FILE,
        base_dir=ROOT,
        interval_sec=300,
        runtime_processes_module=runtime_processes,
        subprocess_module=subprocess,
        os_name=os.name,
    )


def _maintenance_autonomy_runtime_action(payload: dict) -> tuple[bool, str, dict, str]:
    action = str((payload or {}).get("_action") or (payload or {}).get("action") or "").strip().lower()
    if action == "autonomy_maintenance_start":
        return RUNTIME_CONTROL_SERVICE.autonomy_maintenance_start_action(
            start_autonomy_maintenance_worker_fn=_maintenance_start_autonomy_maintenance_worker,
            autonomy_maintenance_summary_fn=_maintenance_autonomy_maintenance_summary,
        )
    return _unsupported_control_action(payload)


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


def _maintenance_generated_queue_investigate_action(_payload: dict, state: dict) -> tuple[bool, str, dict, str]:
    max_steps = _safe_int((_payload or {}).get("max_steps"), 1)
    max_trees = _safe_int((_payload or {}).get("max_trees"), 1)
    try:
        cycle = _run_active_work_tree_cycle(
            state,
            max_steps=max(1, min(max_steps, ACTIVE_WORK_TREE_MAX_STEPS)),
            max_trees=max(1, min(max_trees, ACTIVE_WORK_TREE_MAX_TREES)),
        )
    except Exception as exc:
        msg = f"generated_queue_investigate_failed:{exc}"
        return False, msg, {}, msg
    status = str((cycle or {}).get("status") or "unknown").strip() or "unknown"
    msg = f"generated_queue_investigate_{status}"
    return _work_tree_cycle_dispatch_ok(status), msg, {"cycle": cycle if isinstance(cycle, dict) else {}}, msg


def _work_tree_cycle_dispatch_ok(status: str) -> bool:
    clean = str(status or "").strip().lower()
    return clean not in WORK_TREE_CYCLE_ATTENTION_STATUSES and clean not in {"failed", "error"}


def _maintenance_patch_queue_run_next_action(_payload: dict, state: dict) -> tuple[bool, str, dict, str]:
    try:
        cycle = _run_patch_queue_work_tree_cycle(state, max_steps=1)
    except Exception as exc:
        msg = f"patch_queue_run_next_failed:{exc}"
        return False, msg, {}, msg
    status = str((cycle or {}).get("status") or "unknown").strip() or "unknown"
    msg = f"patch_queue_run_next_{status}"
    return _work_tree_cycle_dispatch_ok(status), msg, {"cycle": cycle if isinstance(cycle, dict) else {}}, msg


def _maintenance_active_work_tree_run_next_action(_payload: dict, state: dict) -> tuple[bool, str, dict, str]:
    max_steps = _safe_int((_payload or {}).get("max_steps"), ACTIVE_WORK_TREE_DEFAULT_DISPATCH_STEPS)
    max_trees = _safe_int((_payload or {}).get("max_trees"), ACTIVE_WORK_TREE_MAX_TREES)
    raw_target_id = str((_payload or {}).get("target_id") or "").strip()
    target_task_id = str((_payload or {}).get("target_step_id") or "").strip()
    target_branch_id = raw_target_id if (raw_target_id.startswith("branch_") or target_task_id) else ""
    try:
        cycle_kwargs = {
            "max_steps": max(1, min(max_steps, ACTIVE_WORK_TREE_MAX_STEPS)),
            "max_trees": max(1, min(max_trees, ACTIVE_WORK_TREE_MAX_TREES)),
        }
        if target_branch_id or target_task_id:
            cycle_kwargs["target_branch_id"] = target_branch_id
            cycle_kwargs["target_task_id"] = target_task_id
        cycle = _run_active_work_tree_cycle(
            state,
            **cycle_kwargs,
        )
    except Exception as exc:
        msg = f"active_work_tree_run_next_failed:{exc}"
        return False, msg, {}, msg
    status = str((cycle or {}).get("status") or "unknown").strip() or "unknown"
    msg = f"active_work_tree_run_next_{status}"
    return _work_tree_cycle_dispatch_ok(status), msg, {"cycle": cycle if isinstance(cycle, dict) else {}}, msg


def _maintenance_codegen_run_action(_payload: dict, _state: dict) -> tuple[bool, str, dict, str]:
    """Generate a preview code artifact for a declared capability gap branch."""
    from services.codegen_patch_bridge import validate_codegen_preview, bridge_codegen_to_patch
    from services.codegen_memory_recorder import CODEGEN_MEMORY_RECORDER_SERVICE
    from tools.codegen_tool import CodegenTool
    from tools.base_tool import ToolContext
    import time as _time

    payload = dict(_payload or {})
    target_id = str(payload.get("target_id") or "").strip()

    # Pull capability details from the gap branch when available
    gap_name = str(payload.get("capability_name") or "").strip()
    gap_purpose = str(payload.get("purpose") or "").strip()
    if not gap_name and target_id:
        try:
            branch = work_tree.get_branch(target_id)
            if branch is not None:
                src = dict(branch.source_payload or {}) if isinstance(branch.source_payload, dict) else {}
                gap_name = str(
                    src.get("capability_name") or src.get("primary_capability") or ""
                ).strip()
                gap_purpose = str(src.get("purpose") or branch.title or "").strip()
        except Exception:
            pass

    if not gap_name:
        gap_name = "nova_capability_extension"
    if not gap_purpose:
        gap_purpose = f"Implement missing Nova capability: {gap_name}"

    safe_name = gap_name.replace(":", "_").replace("/", "_")[:60]
    spec = {
        "name": safe_name,
        "purpose": gap_purpose,
        "files": [
            {
                "path": f"services/{safe_name}.py",
                "kind": "module",
                "intent": f"Service module implementing {safe_name} for Nova",
            }
        ],
    }

    try:
        ctx = ToolContext(
            policy={
                "tools_enabled": {"codegen": True},
                "codegen": {"enabled": True},
            },
            is_admin=True,
        )
        preview_json = CodegenTool().run({"action": "preview", "spec": spec}, ctx)
        preview = json.loads(preview_json)
    except Exception as exc:
        msg = f"codegen_run_tool_failed:{exc}"
        return False, msg, {}, msg

    ok_val, reason, parsed = validate_codegen_preview(preview)
    if not ok_val:
        msg = f"codegen_run_preview_invalid:{reason}"
        return False, msg, {}, msg

    codegen_id = f"codegen_run_{int(_time.time())}"
    patch_artifact = bridge_codegen_to_patch(parsed, codegen_id=codegen_id, operator_id="autonomy_maintenance")
    patch_id = str(patch_artifact.get("patch_id") or "")

    try:
        CODEGEN_MEMORY_RECORDER_SERVICE.record_pattern(
            capability_name=safe_name,
            spec_string=json.dumps(spec, sort_keys=True),
            generated_code=gap_purpose,
            test_code="",
        )
    except Exception:
        pass

    msg = f"codegen_run_ok:{safe_name}"
    _append_log(f"codegen_run capability={safe_name} patch_id={patch_id} branch={target_id or 'unspecified'}")
    return True, msg, {"patch_id": patch_id, "capability_name": safe_name, "codegen_id": codegen_id}, msg


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
        guard_control_action_fn=_maintenance_guard_control_action,
        core_runtime_action_fn=_unsupported_control_action,
        autonomy_runtime_action_fn=_maintenance_autonomy_runtime_action,
        test_session_run_action_fn=_unsupported_control_action,
        generated_pack_run_action_fn=_unsupported_control_action,
        generated_queue_run_next_action_fn=_maintenance_generated_queue_run_next_action,
        generated_queue_investigate_action_fn=lambda event_payload: _maintenance_generated_queue_investigate_action(event_payload, runtime_state),
        patch_queue_run_next_action_fn=lambda event_payload: _maintenance_patch_queue_run_next_action(event_payload, runtime_state),
        active_work_tree_run_next_action_fn=lambda event_payload: _maintenance_active_work_tree_run_next_action(event_payload, runtime_state),
        codegen_run_action_fn=lambda event_payload: _maintenance_codegen_run_action(event_payload, runtime_state),
        leah_build_run_next_action_fn=lambda event_payload: _maintenance_codegen_run_action(event_payload, runtime_state),
        real_world_task_create_action_fn=_unsupported_control_action,
        backend_command_list_action_fn=_unsupported_control_action,
        backend_command_run_action_fn=_unsupported_control_action,
        operator_prompt_action_fn=lambda event_payload: (False, "operator_prompt_unavailable_in_maintenance", {}, "operator_prompt_unavailable_in_maintenance", event_payload),
        operator_outbox_respond_action_fn=_unsupported_control_action,
        operator_outbox_status_action_fn=_unsupported_control_action,
        session_delete_action_fn=_unsupported_control_action,
        policy_allow_action_fn=_unsupported_control_action,
        policy_remove_action_fn=_unsupported_control_action,
        web_mode_action_fn=_unsupported_control_action,
        memory_scope_set_action_fn=_unsupported_control_action,
        server_side_settings_action_fn=_unsupported_control_action,
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
        "target_step_id": str(gate.get("target_step_id") or ""),
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
            "extra": _compact_autonomy_execution_extra(action_type, extra),
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


def _orchestrator_executed_lane_cycle(packet: dict, action_type: str) -> dict:
    execution = dict((packet or {}).get("execution") or {}) if isinstance((packet or {}).get("execution"), dict) else {}
    if str(execution.get("action_type") or "").strip() != str(action_type or "").strip():
        return {}
    extra = dict(execution.get("extra") or {}) if isinstance(execution.get("extra"), dict) else {}
    cycle = dict(extra.get("cycle") or {}) if isinstance(extra.get("cycle"), dict) else {}
    if not cycle:
        return {}
    cycle.setdefault("orchestrator_owned", True)
    cycle.setdefault("orchestrator_action_type", str(action_type or "").strip())
    return cycle


def _runtime_worker_loop_identity_live(worker_state: dict) -> bool:
    pid = _safe_int((worker_state or {}).get("pid"), 0)
    if pid <= 0:
        return False
    try:
        import psutil

        process = psutil.Process(pid)
        recorded_create_time = (worker_state or {}).get("create_time")
        if recorded_create_time not in (None, ""):
            try:
                if abs(float(process.create_time()) - float(recorded_create_time)) > 1.0:
                    return False
            except Exception:
                return False
        cmdline = [str(part or "").strip().lower() for part in list(process.cmdline() or [])]
    except Exception:
        return False
    joined_cmdline = " ".join(cmdline)
    return "--loop" in cmdline and "autonomy_maintenance.py" in joined_cmdline


def _clear_non_loop_runtime_worker_state(state: dict, *, timestamp_fn: Callable[[], str] | None = None) -> bool:
    worker_state = dict((state or {}).get("runtime_worker") or {})
    if not worker_state:
        return False
    if _runtime_worker_loop_identity_live(worker_state):
        return False

    had_identity = bool(
        worker_state.get("pid")
        or worker_state.get("create_time")
        or worker_state.get("active")
        or worker_state.get("stale_identity")
    )
    if not had_identity:
        return False

    prior_status = str(worker_state.get("last_cycle_status") or "").strip().lower()
    worker_state["active"] = False
    worker_state["stale_identity"] = False
    worker_state["cleared_stale_identity"] = True
    worker_state["pid"] = None
    worker_state["create_time"] = None
    if prior_status in {"", "running", "ok", "success"}:
        worker_state["last_cycle_status"] = "stopped"
    worker_state["stopped_at"] = (timestamp_fn or _patch_queue_timestamp)()
    worker_state["stale_identity_cleared_at"] = worker_state["stopped_at"]
    worker_state["stopped_reason"] = "one_shot_cycle_not_worker_loop"
    state["runtime_worker"] = worker_state
    return True


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
    del files
    return False


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
    # Generated definition-only packs should stay in review flow, not auto-apply.
    if _zip_contains_only_promoted_patch_entries(zip_path):
        return "skipped_generated_definitions_require_review"

    preview_out = nova_core.patch_preview(str(zip_path), write_report=False)
    if "Status: eligible" not in str(preview_out):
        return f"preview_not_eligible: {str(preview_out).strip()[:300]}"

    preview_out = nova_core.patch_preview(str(zip_path), write_report=True)
    apply_out = nova_core.execute_patch_action("apply", str(zip_path), is_admin=True)
    return str(apply_out or "")


def _run_daily_regression_if_due(state: dict) -> str:
    today = time.strftime("%Y-%m-%d")
    if str(state.get("last_regression_date") or "") == today:
        return "daily_regression_skipped_already_ran"

    cmd = [str(VENV_PY), str(REGRESSION_RUNNER), "all"]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=5400,
        env=_validation_subprocess_env(),
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    summary = "OK" if proc.returncode == 0 else "FAILED"

    synced = _sync_regression_status_from_file(state, status_path=REGRESSION_STATUS_FILE)
    if not synced:
        state["last_regression_date"] = today
        state["last_regression_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state["last_regression_status"] = summary
        state["last_regression_stale"] = False
        state["last_regression_returncode"] = int(proc.returncode)
        state["last_regression_source"] = "scripts/run_regression.py"
        state["last_regression_lanes"] = ["all"]
        state["last_regression_tail"] = output[-2000:]
    return f"daily_regression_{summary.lower()}"


def _sync_regression_status_from_file(state: dict, *, status_path: Path = REGRESSION_STATUS_FILE) -> bool:
    try:
        data = json.loads(Path(status_path).read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False

    generated_at = str(data.get("generated_at") or "").strip()
    status = str(data.get("status") or "").strip().upper()
    if not generated_at or not status:
        return False

    current_at = str(state.get("last_regression_at") or "").strip()
    if current_at and generated_at <= current_at:
        return False

    state["last_regression_date"] = str(data.get("date") or generated_at[:10] or time.strftime("%Y-%m-%d"))
    state["last_regression_at"] = generated_at
    state["last_regression_status"] = status
    state["last_regression_stale"] = False
    state["last_regression_returncode"] = _safe_int(data.get("returncode"), 0)
    state["last_regression_source"] = str(data.get("source") or Path(status_path).name)
    state["last_regression_lanes"] = list(data.get("lanes") or []) if isinstance(data.get("lanes"), list) else []
    detail = str(data.get("detail") or "").strip()
    state["last_regression_tail"] = detail or f"{state['last_regression_source']} reported {status}."
    return True


def _sync_signal_intake_work_tree(state: dict, kidney_summary: dict | None = None, temporal_feed: dict | None = None) -> dict:
    maintenance_payload = {
        "last_regression_status": str(state.get("last_regression_status") or ""),
        "last_regression_stale": bool(state.get("last_regression_stale", False)),
    }
    try:
        pulse_payload = nova_core.build_pulse_payload()
    except Exception:
        pulse_payload = {}
    memory_health = pulse_payload.get("memory_health") if isinstance(pulse_payload.get("memory_health"), dict) else {}
    status_payload = {
        "alerts": [],
        "self_check_pass_ratio": 1.0,
        "autonomy_maintenance": maintenance_payload,
        "memory_enabled": bool(nova_core.mem_enabled()),
        "memory_health": memory_health,
        "memory_health_status": str(pulse_payload.get("memory_health_status") or memory_health.get("status") or "unknown"),
        "memory_health_issue_count": int(pulse_payload.get("memory_health_issue_count", memory_health.get("issue_count", 0)) or 0),
        "memory_health_issues": list(pulse_payload.get("memory_health_issues") or []) if isinstance(pulse_payload.get("memory_health_issues"), list) else list(memory_health.get("issues") or []),
        "memory_db_total": int(pulse_payload.get("memory_db_total", 0) or 0),
        "memory_events_log_status": str(pulse_payload.get("memory_events_log_status") or ""),
    }
    if isinstance(temporal_feed, dict):
        state["last_temporal_feed"] = dict(temporal_feed)
    status_payload.update(_temporal_feed_for_signal_ingestion(state))
    status_payload.update(_validation_artifact_truth_payload_for_signal_ingestion())
    status_payload = _live_control_status_payload_for_signal_ingestion(status_payload)
    status_payload = _apply_release_runtime_truth_to_status_payload(status_payload, state=state)
    status_payload = _apply_layer_maturity_to_status_payload(status_payload)
    state["last_layer_maturity_snapshot"] = {
        "layer_maturity": dict(status_payload.get("layer_maturity") or {}),
        "release_runtime_truth": dict(status_payload.get("release_runtime_truth") or {}),
        "release_status": dict(status_payload.get("release_status") or {}),
        "root_closure_inventory": dict(status_payload.get("root_closure_inventory") or {}),
        "capabilities_registered": dict(status_payload.get("capabilities_registered") or {}),
        "capability_gaps": list(status_payload.get("capability_gaps") or []),
        "capability_gaps_actionable": list(status_payload.get("capability_gaps_actionable") or []),
        "suppress_capability_gap_signals": bool(status_payload.get("suppress_capability_gap_signals")),
    }

    # Root fix for lingering governance_pressure branches (e.g. old "source-observed" validation profile tasks):
    # Always feed the current test profile inventory (with source_observed_count etc.) into the status snapshot.
    # This ensures that when _test_profile_inventory_signal_from_status returns None (issue resolved),
    # the resolve_signal_branches is triggered to retire the branch at root, instead of it lingering forever.
    try:
        reg_path = RUNTIME_DIR / "regression_status.json"
        if reg_path.exists():
            reg_data = json.loads(reg_path.read_text(encoding="utf-8"))
            for k, v in reg_data.items():
                if k.startswith("test_profile_"):
                    status_payload[k] = v
    except Exception:
        pass

    results = WORK_TREE_SIGNAL_INGESTION_SERVICE.sync_status_snapshot(status_payload)
    try:
        generated_queue = _generated_work_queue(limit=200)
    except Exception:
        generated_queue = {}
    try:
        latest_report = _latest_subconscious_report_for_triage()
    except Exception:
        latest_report = {}
    subconscious_signals = _subconscious_triage_signals_for_work_tree(
        state=state,
        generated_queue=generated_queue if isinstance(generated_queue, dict) else {},
        latest_report=latest_report if isinstance(latest_report, dict) else {},
        kidney_summary=kidney_summary,
        limit=8,
    )
    active_subconscious_source_keys = {
        WORK_TREE_SIGNAL_INGESTION_SERVICE.source_key_for_signal(signal)
        for signal in subconscious_signals
        if isinstance(signal, dict)
    }
    for signal in subconscious_signals:
        results.append(WORK_TREE_SIGNAL_INGESTION_SERVICE.ingest_signal(signal))
    if isinstance(latest_report, dict) and (latest_report.get("generated_at") or latest_report.get("families")):
        results.extend(
            WORK_TREE_SIGNAL_INGESTION_SERVICE.resolve_inactive_signal_branches(
                signal_class="subconscious_candidate",
                source="subconscious",
                active_source_keys=active_subconscious_source_keys,
                reason="Latest actionable subconscious triage no longer carries this pressure as active repair work.",
                resolution_mode="retire",
            )
        )
    tree = None
    for candidate in work_tree.list_trees():
        meta = dict(getattr(candidate, "meta", {}) or {})
        status = str(getattr(getattr(candidate, "status", ""), "value", getattr(candidate, "status", "")) or "").strip().lower()
        if status == "archived":
            continue
        if str(meta.get("kind") or "").strip().lower() == WORK_TREE_SIGNAL_INGESTION_SERVICE.SIGNAL_TREE_KIND:
            tree = candidate
            break
    active_maintenance_regression = bool(
        maintenance_payload["last_regression_status"]
        and "pass" not in maintenance_payload["last_regression_status"].lower()
        and maintenance_payload["last_regression_status"].lower() != "ok"
        and not maintenance_payload["last_regression_stale"]
    )
    validation_truth = status_payload.get("validation_artifact_truth") if isinstance(status_payload.get("validation_artifact_truth"), dict) else {}
    active_validation_artifact_failure = bool(
        not bool(status_payload.get("validation_artifact_truth_ok", validation_truth.get("ok", True)))
        and _safe_int(
            status_payload.get(
                "validation_artifact_failure_count",
                validation_truth.get("current_window_failure_count", validation_truth.get("failure_count", 0)),
            ),
            0,
        )
        > 0
    )
    active_regression = bool(active_maintenance_regression or active_validation_artifact_failure)
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": "ok",
        "tree_id": str(getattr(tree, "tree_id", "") or ""),
        "tree_title": str(getattr(tree, "title", "") or ""),
        "result_count": len(results),
        "created_count": sum(1 for item in results if str((item or {}).get("action") or "") == "created"),
        "updated_count": sum(1 for item in results if str((item or {}).get("action") or "") == "updated"),
        "reopened_count": sum(1 for item in results if str((item or {}).get("action") or "") == "reopened"),
        "observing_count": sum(1 for item in results if str((item or {}).get("action") or "") == "observing"),
        "resolved_count": sum(1 for item in results if str((item or {}).get("action") or "") == "resolved"),
        "retired_count": sum(1 for item in results if str((item or {}).get("action") or "") == "retired"),
        "subconscious_signal_count": len(subconscious_signals),
        "active_regression_failure": active_regression,
        "active_maintenance_regression_failure": active_maintenance_regression,
        "active_validation_artifact_failure": active_validation_artifact_failure,
        "validation_artifact_truth_status": str(status_payload.get("validation_artifact_truth_status") or validation_truth.get("status") or ""),
        "validation_artifact_failure_count": _safe_int(
            status_payload.get(
                "validation_artifact_failure_count",
                validation_truth.get("current_window_failure_count", validation_truth.get("failure_count", 0)),
            ),
            0,
        ),
        "validation_artifact_llm_unavailable_count": _safe_int(
            status_payload.get(
                "validation_artifact_llm_unavailable_count",
                validation_truth.get("current_window_llm_unavailable_count", validation_truth.get("llm_unavailable_count", 0)),
            ),
            0,
        ),
        "last_regression_status": maintenance_payload["last_regression_status"],
        "last_regression_stale": maintenance_payload["last_regression_stale"],
    }
    report_totals = dict(latest_report.get("totals") or {}) if isinstance(latest_report.get("totals"), dict) else {}
    state["last_subconscious_triage"] = {
        "ts": payload["ts"],
        "status": "ok",
        "latest_generated_at": str(latest_report.get("generated_at") or ""),
        "source_freshness_sec": _safe_int(latest_report.get("_source_freshness_sec"), 0),
        "training_priority_count": _safe_int(report_totals.get("training_priority_count"), 0),
        "robust_signal_count": _safe_int(report_totals.get("robust_signal_count"), 0),
        "script_specific_signal_count": _safe_int(report_totals.get("script_specific_signal_count"), 0),
        "subconscious_signal_count": len(subconscious_signals),
        "active_source_keys": sorted(active_subconscious_source_keys),
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


def _candidate_uses_tool(candidate: dict, tool_name: str) -> bool:
    next_step = candidate.get("next_step") if isinstance(candidate.get("next_step"), dict) else {}
    return str(next_step.get("recommended_tool") or "").strip() == tool_name


def _active_work_tree_target_decider(target_branch_id: str = "", target_task_id: str = ""):
    branch_target = str(target_branch_id or "").strip()
    task_target = str(target_task_id or "").strip()
    if not branch_target and not task_target:
        return None

    def _decide(_tree_id: str, options: list[dict]) -> dict:
        for option in options:
            option_branch_id = str(option.get("branch_id") or "").strip()
            option_task_id = str(option.get("task_id") or "").strip()
            if branch_target and option_branch_id != branch_target:
                continue
            if task_target and option_task_id != task_target:
                continue
            return {
                "branch_id": option_branch_id,
                "task_id": option_task_id,
                "recommended_tool": str(option.get("recommended_tool") or "").strip(),
            }
        return {
            "branch_id": branch_target or "__target_branch_not_available__",
            "task_id": task_target,
            "recommended_tool": "",
        }

    return _decide


def _active_work_tree_failure_aware_decider(tree_id: str, options: list[dict]) -> dict:
    """Prefer options whose tool is not already marked FAILED in the branch tool_state.
    Root fix to avoid repeated tool_failed executions on active work tree tasks.
    """
    del tree_id
    fallback = None
    for option in list(options or []):
        if not isinstance(option, dict):
            continue
        if fallback is None:
            fallback = option
        branch_id = str(option.get("branch_id") or "").strip()
        tool_name = str(option.get("recommended_tool") or "").strip()
        if not branch_id or not tool_name:
            continue
        try:
            branch = work_tree.get_branch(branch_id)
            tool_state = branch.tool_state if branch is not None and isinstance(branch.tool_state, dict) else {}
            status = str((tool_state.get(tool_name) or "")).strip().lower()
            if status == "failed":
                continue
        except Exception:
            pass
        return {
            "branch_id": branch_id,
            "task_id": str(option.get("task_id") or "").strip(),
            "recommended_tool": tool_name,
        }
    chosen = fallback if isinstance(fallback, dict) else {}
    return {
        "branch_id": str(chosen.get("branch_id") or "").strip(),
        "task_id": str(chosen.get("task_id") or "").strip(),
        "recommended_tool": str(chosen.get("recommended_tool") or "").strip(),
    }


def _sync_core_thinning_work_tree(state: dict) -> dict:
    try:
        brief = service_build_core_thinning_brief([ROOT / "nova_core.py", ROOT / "nova_http.py"])
        feed = service_feed_core_thinning_brief_to_work_tree(brief, work_tree_module=work_tree)
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "ok" if bool(feed.get("ok", False)) and bool(brief.get("ok", False)) else "failed",
            "tree_id": str(feed.get("tree_id") or ""),
            "tree_title": str(feed.get("tree_title") or "Core Thinning"),
            "order_count": int(brief.get("order_count", 0) or 0),
            "added_count": int(feed.get("added_count", 0) or 0),
            "deduped_count": int(feed.get("deduped_count", 0) or 0),
            "updated_count": int(feed.get("updated_count", 0) or 0),
            "resolved_count": int(feed.get("resolved_count", 0) or 0),
            "error": str(brief.get("error") or feed.get("error") or ""),
        }
    except Exception as exc:
        payload = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "reason": "core_thinning_sync_failed",
            "error": str(exc),
        }
    state["last_core_thinning_sync"] = payload
    return payload


def _run_active_work_tree_cycle(
    state: dict,
    *,
    max_steps: int | None = None,
    max_trees: int | None = None,
    target_branch_id: str = "",
    target_task_id: str = "",
    sync_core_thinning: bool = True,
) -> dict:
    tree_limit = max(1, _safe_int(max_trees, ACTIVE_WORK_TREE_MAX_TREES)) if max_trees is not None else ACTIVE_WORK_TREE_MAX_TREES
    step_limit = max(1, _safe_int(max_steps, ACTIVE_WORK_TREE_MAX_STEPS)) if max_steps is not None else ACTIVE_WORK_TREE_MAX_STEPS
    candidates = _active_work_tree_candidates(tree_limit)
    if target_branch_id or target_task_id:
        target_decider = _active_work_tree_target_decider(target_branch_id, target_task_id)
    else:
        target_decider = _active_work_tree_failure_aware_decider
    core_thinning_sync: dict = {}
    if sync_core_thinning and any(_candidate_uses_tool(candidate, "core_thinning") for candidate in candidates):
        core_thinning_sync = _sync_core_thinning_work_tree(state)
        candidates = _active_work_tree_candidates(tree_limit)
    executed_total = 0
    attempted_total = 0
    full_history: list[dict] = []
    processed: list[dict] = []
    skipped: list[dict] = []
    last_action = ""

    for candidate in candidates:
        if attempted_total >= step_limit:
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
        loop_kwargs = {
            "max_steps": 1,
            "execute_planned_action_fn": nova_core.execute_planned_action,
        }
        if target_decider is not None:
            loop_kwargs["decide_next_step_fn"] = target_decider
        history = work_tree.run_autonomous_loop(tree_id, **loop_kwargs)
        attempted_total += 1
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

    # Root fix for maintenance execution progress: when a tool_failed occurs (evidence already recorded),
    # complete the task so the branch/tree can advance instead of restoring to OPEN and repeating failures.
    # Also surface as "attempted" in status rather than leaving the cycle in tool_failed state.
    for h in full_history:
        if isinstance(h, dict) and str(h.get("action") or "").strip() == "tool_failed":
            tid = str(h.get("task_id") or "").strip()
            if tid:
                try:
                    mark_task_complete(tid)
                except Exception:
                    pass

    if executed_total:
        status = "ok"
    elif any(isinstance(h, dict) and str(h.get("action") or "").strip() == "tool_failed" for h in full_history):
        status = "attempted"
    elif full_history:
        status = last_action or "waiting"
    else:
        status = "idle"
    payload = {
        "ts": _patch_queue_timestamp(),
        "status": status,
        "tree_count": len(candidates),
        "target_branch_id": str(target_branch_id or ""),
        "target_task_id": str(target_task_id or ""),
        "attempted_count": attempted_total,
        "executed_count": executed_total,
        "history_count": len(full_history),
        "processed_tree_count": len(processed),
        "skipped_tree_count": len(skipped),
        "last_action": last_action,
        "processed": processed,
        "skipped": skipped,
    }
    if core_thinning_sync:
        payload["core_thinning_sync"] = core_thinning_sync
    if full_history:
        payload["history"] = _compact_work_tree_history(full_history)
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


def run_once(*, worker_loop: bool = False) -> int:
    cycle_start = time.monotonic()

    def _finish_cycle(code: int, reason: str) -> int:
        _append_log(f"cycle_complete cycle_elapsed_sec={_elapsed_sec(cycle_start)} code={code} reason={reason}")
        return int(code)

    state = _load_state()

    # Check for an HTTP-side trigger requesting an immediate active-work-tree run.
    if WORK_TREE_RUN_TRIGGER.exists():
        try:
            trigger_payload = json.loads(WORK_TREE_RUN_TRIGGER.read_text(encoding="utf-8"))
        except Exception:
            trigger_payload = {}
        try:
            WORK_TREE_RUN_TRIGGER.unlink(missing_ok=True)
        except Exception:
            pass
        _append_log("work_tree_run_trigger_consumed")
        try:
            trigger_cycle = _run_active_work_tree_cycle(state, **{
                k: trigger_payload[k]
                for k in ("max_steps", "max_trees", "target_branch_id", "target_task_id")
                if k in trigger_payload
            })
            _append_log(f"work_tree_run_trigger_cycle status={trigger_cycle.get('status')}")
        except Exception as exc:
            _append_log(f"work_tree_run_trigger_cycle_failed {exc}")
        _save_state(state)
        return _finish_cycle(0, "work_tree_run_trigger_handled")

    # Check for an HTTP-side trigger requesting an immediate patch-queue run.
    if PATCH_QUEUE_RUN_TRIGGER.exists():
        try:
            trigger_payload = json.loads(PATCH_QUEUE_RUN_TRIGGER.read_text(encoding="utf-8"))
        except Exception:
            trigger_payload = {}
        try:
            PATCH_QUEUE_RUN_TRIGGER.unlink(missing_ok=True)
        except Exception:
            pass
        _append_log("patch_queue_run_trigger_consumed")
        try:
            trigger_cycle = _run_patch_queue_work_tree_cycle(state, **{
                k: trigger_payload[k]
                for k in ("max_steps",)
                if k in trigger_payload
            })
            _append_log(f"patch_queue_run_trigger_cycle status={trigger_cycle.get('status')}")
        except Exception as exc:
            _append_log(f"patch_queue_run_trigger_cycle_failed {exc}")
        _save_state(state)
        return _finish_cycle(0, "patch_queue_run_trigger_handled")

    if not worker_loop and _clear_non_loop_runtime_worker_state(state):
        _save_state(state)
        _append_log("runtime_worker_state_cleared one_shot_cycle_not_worker_loop")
    autonomy_settings = _autonomy_policy_settings()
    legacy_execution_enabled = _legacy_maintenance_execution_enabled(autonomy_settings)

    ok, pack_out = _run_subconscious_pack()
    _append_log(f"subconscious_pack={'ok' if ok else 'fail'}")
    if not ok:
        state["last_subconscious_run"] = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "label": "phase1_auto",
            "error": str(pack_out or ""),
        }
        state["last_error"] = pack_out
        _save_state(state)
        _append_log(pack_out)
        return _finish_cycle(1, "subconscious_pack_failed")
    state["last_subconscious_run"] = {
        "ts": _patch_queue_timestamp(),
        "status": "ok",
        "label": "phase1_auto",
        "output_tail": str(pack_out or "")[-2000:],
    }
    state["last_error"] = ""

    if not LATEST_SUBCONSCIOUS.exists():
        state["last_subconscious_run"] = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "label": "phase1_auto",
            "error": "latest_subconscious_missing",
        }
        state["last_error"] = "latest_subconscious_missing"
        _save_state(state)
        _append_log("latest_subconscious_missing")
        return _finish_cycle(1, "latest_subconscious_missing")

    report = json.loads(LATEST_SUBCONSCIOUS.read_text(encoding="utf-8"))
    generated_at = str(report.get("generated_at") or "")
    threshold = float(AUTO_APPLY_THRESHOLD)
    fallback_score = _max_fallback_robustness(report)

    state["auto_apply_threshold"] = threshold
    state["last_generated_at"] = generated_at
    state["last_fallback_overuse_score"] = fallback_score
    totals = dict(report.get("totals") or {}) if isinstance(report.get("totals"), dict) else {}
    state["last_subconscious_run"].update(
        {
            "generated_at": generated_at,
            "family_count": _safe_int(totals.get("family_count"), 0),
            "variation_count": _safe_int(totals.get("variation_count"), 0),
            "training_priority_count": _safe_int(totals.get("training_priority_count"), 0),
            "robust_signal_count": _safe_int(totals.get("robust_signal_count"), 0),
            "script_specific_signal_count": _safe_int(totals.get("script_specific_signal_count"), 0),
        }
    )

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
        temporal_feed = _run_temporal_feed_pass(state)
        _append_log(
            "temporal_feed"
            f" status={temporal_feed.get('status')}"
            f" sources={int(temporal_feed.get('source_count', 0) or 0)}"
            f" events={int(temporal_feed.get('event_count', 0) or 0)}"
            f" surfaced={int(temporal_feed.get('surfaced_count', 0) or 0)}"
            f" errors={int(temporal_feed.get('error_count', 0) or 0)}"
        )
    except Exception as exc:
        temporal_feed = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "enabled": False,
            "source_count": 0,
            "event_count": 0,
            "surfaced_count": 0,
            "error_count": 1,
            "surfaced_pressures": [],
            "errors": [{"path": "", "error": str(exc)}],
        }
        state["last_temporal_feed"] = temporal_feed
        _append_log(f"temporal_feed_failed {exc}")

    try:
        pre_execution_signal_ingestion = _sync_signal_intake_work_tree(
            state,
            kidney_summary=kidney_summary,
            temporal_feed=temporal_feed,
        )
        state["last_pre_execution_signal_ingestion"] = pre_execution_signal_ingestion
        _append_log(
            "pre_execution_signal_ingestion"
            f" status={pre_execution_signal_ingestion.get('status')}"
            f" results={int(pre_execution_signal_ingestion.get('result_count', 0) or 0)}"
            f" resolved={int(pre_execution_signal_ingestion.get('resolved_count', 0) or 0)}"
        )
    except Exception as exc:
        pre_execution_signal_ingestion = {
            "ts": _patch_queue_timestamp(),
            "status": "failed",
            "result_count": 0,
            "resolved_count": 0,
            "error": str(exc),
        }
        state["last_pre_execution_signal_ingestion"] = pre_execution_signal_ingestion
        _append_log(f"pre_execution_signal_ingestion_failed {exc}")

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
            active_work_tree_cycle = _orchestrator_executed_lane_cycle(
                autonomy_orchestrator if isinstance(autonomy_orchestrator, dict) else {},
                "active_work_tree_run_next",
            )
            if active_work_tree_cycle:
                state["last_active_work_tree_cycle"] = active_work_tree_cycle
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
    regression_status_synced = _sync_regression_status_from_file(state)
    if regression_status == "daily_regression_skipped_already_ran" and not regression_status_synced:
        last_regression_status = str(state.get("last_regression_status") or "").strip()
        state["last_regression_stale"] = bool(last_regression_status and "pass" not in last_regression_status.lower() and last_regression_status.lower() != "ok")
    else:
        state["last_regression_stale"] = False
    _append_log(f"{regression_status}{'_synced_status_file' if regression_status_synced else ''}")

    try:
        signal_ingestion = _sync_signal_intake_work_tree(
            state,
            kidney_summary=kidney_summary,
            temporal_feed=temporal_feed,
        )
        _append_log(
            "signal_ingestion"
            f" status={signal_ingestion.get('status')}"
            f" results={int(signal_ingestion.get('result_count', 0) or 0)}"
            f" subconscious={int(signal_ingestion.get('subconscious_signal_count', 0) or 0)}"
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
    return _finish_cycle(0, "ok")


def run_worker(
    *,
    interval_sec: int = 300,
    max_cycles: int = 0,
    continue_on_error: bool = True,
    run_once_fn: Callable[[], int] | None = None,
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
        if run_once_fn is None:
            last_code = int(run_once(worker_loop=True))
        else:
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
