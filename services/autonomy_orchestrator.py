from __future__ import annotations

from datetime import datetime, timezone
import time
import uuid
from typing import Any, Callable

from services.nova_control_action_dispatcher import (
    autonomy_advisory_action_catalog,
    autonomy_advisory_action_types,
    is_autonomy_advisory_action,
)
from services.core_steward_contracts import AUTONOMY_MAINTENANCE_NOT_RUNNING_REASON
from services.layer_maturity_policy import orchestrator_codegen_action_allowed
from services.nova_mission import NOVA_MISSION_SERVICE


DECISION_RECOMMEND_ACTION = "recommend_action"
DECISION_DEFER_WITH_REASON = "defer_with_reason"
DECISION_BLOCK_WITH_REASON = "block_with_reason"

ALLOWED_DECISIONS = {
    DECISION_RECOMMEND_ACTION,
    DECISION_DEFER_WITH_REASON,
    DECISION_BLOCK_WITH_REASON,
}

SPEC_DECISION_RECOMMEND_ACTION = "RecommendAction"
SPEC_DECISION_DEFER = "Defer"
SPEC_DECISION_BLOCK = "Block"

ALLOWED_SPEC_DECISIONS = {
    SPEC_DECISION_RECOMMEND_ACTION,
    SPEC_DECISION_DEFER,
    SPEC_DECISION_BLOCK,
}

SPEC_TO_LEGACY_DECISION = {
    SPEC_DECISION_RECOMMEND_ACTION: DECISION_RECOMMEND_ACTION,
    SPEC_DECISION_DEFER: DECISION_DEFER_WITH_REASON,
    SPEC_DECISION_BLOCK: DECISION_BLOCK_WITH_REASON,
}

LEGACY_TO_SPEC_DECISION = {
    legacy: spec
    for spec, legacy in SPEC_TO_LEGACY_DECISION.items()
}

ADVISORY_MODE = "advisory"
EXECUTE_MODE = "execute"
DEFAULT_CYCLE_CADENCE_SEC = 30
DEFAULT_CYCLE_JITTER_PCT = 10
HARD_STALE_THRESHOLD_SEC = 120
SOFT_STALE_THRESHOLD_SEC = 300
DEFAULT_RECOMMENDATION_THRESHOLD = 0.55
MISSION_GREEN_HOLD_PENALTY = 0.35


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ok", "running", "active", "healthy"}:
        return True
    if text in {"0", "false", "no", "n", "stopped", "inactive", "failed", "error", "missing"}:
        return False
    return None


def _clamp_float(value: Any, default: float = 0.0) -> float:
    number = _as_float(value, default)
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _safe_text(value: Any, limit: int = 220) -> str:
    return str(value or "").strip()[:limit]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _safe_text(value, 120)
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in list(value.items())[:30]:
            compact[str(key)] = _compact_value(item, depth=depth + 1)
        return compact
    if isinstance(value, list):
        return [_compact_value(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, tuple):
        return [_compact_value(item, depth=depth + 1) for item in list(value)[:20]]
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if value is None:
        return None
    return _safe_text(value, 500)


class AutonomyOrchestratorService:
    """Advisory-only control law for a single governed autonomy cycle."""

    def __init__(self, *, posture_threshold: int = 85) -> None:
        self.posture_threshold = int(posture_threshold)
        self._mode = ADVISORY_MODE
        self._last_decision: dict[str, Any] = {}
        self._decision_history: list[dict[str, Any]] = []
        self._last_cycle_at = ""
        self._cycle_count = 0
        self._error_count = 0
        self._last_error = ""

    @staticmethod
    def _legacy_decision(decision_type: str) -> str:
        return SPEC_TO_LEGACY_DECISION.get(str(decision_type or ""), DECISION_BLOCK_WITH_REASON)

    @staticmethod
    def _spec_decision(decision: str) -> str:
        return LEGACY_TO_SPEC_DECISION.get(str(decision or ""), SPEC_DECISION_BLOCK)

    @staticmethod
    def _legacy_action(action: dict[str, Any] | None) -> dict[str, Any]:
        payload = _as_dict(action)
        if not payload:
            return {}
        return {
            "act": _safe_text(payload.get("action_type"), 120),
            "payload": {
                "target_kind": _safe_text(payload.get("target_kind"), 80),
                "target_id": _safe_text(payload.get("target_id"), 160),
                "target_step_id": _safe_text(payload.get("target_step_id"), 160),
                "target_tree_id": _safe_text(payload.get("target_tree_id"), 160),
                "recommended_tool": _safe_text(payload.get("recommended_tool"), 120),
                "reason_code": _safe_text(payload.get("reason_code"), 120),
                "execution_group": _safe_text(payload.get("execution_group"), 120),
                "preconditions": list(payload.get("preconditions") or []),
                "requires_ack": bool(payload.get("requires_ack", False)),
                "cooldown_sec": _as_int(payload.get("cooldown_sec")),
                "ttl_sec": _as_int(payload.get("ttl_sec")),
                "max_steps": _as_int(payload.get("max_steps")),
                "max_trees": _as_int(payload.get("max_trees")),
            },
            "source": "services.autonomy_orchestrator",
            "reason": _safe_text(payload.get("expected_effect"), 360),
        }

    @staticmethod
    def _freshness_sec(payload: dict[str, Any]) -> int:
        if "source_freshness_sec" not in payload:
            return -1
        return _as_int(payload.get("source_freshness_sec"), -1)

    @staticmethod
    def _source_present(envelope: dict[str, Any], key: str) -> bool:
        return isinstance(envelope.get(key), dict)

    @staticmethod
    def _posture_band(steward_posture: dict[str, Any]) -> str:
        band = _safe_text(steward_posture.get("posture_band"), 40).lower()
        if band in {"green", "yellow", "red"}:
            return band
        score = _as_int(steward_posture.get("health_score"), -1)
        critical_alerts = _as_int(steward_posture.get("critical_alerts"))
        if critical_alerts > 0 or score < 70:
            return "red"
        if score < 85:
            return "yellow"
        return "green"

    @staticmethod
    def _mission_hold_active(mission: dict[str, Any]) -> bool:
        payload = _as_dict(mission)
        if not bool(payload.get("enabled")):
            return False
        if _safe_text(payload.get("mode"), 80).lower() != "steady_state_guard":
            return False
        return _safe_text(payload.get("action"), 40).lower() == "hold"

    @staticmethod
    def _mission_green_hold_active(mission: dict[str, Any]) -> bool:
        return AutonomyOrchestratorService._mission_hold_active(mission)

    @staticmethod
    def _mission_hold_refusal_reasons(mission: dict[str, Any]) -> list[str]:
        payload = _as_dict(mission)
        reasons = ["mission_steady_state_hold"]
        if bool(payload.get("green_cycle", False)):
            reasons.append("mission_green_cycle_hold")
        if _safe_text(payload.get("status"), 80).lower() == "validation_required":
            reasons.append("mission_validation_required_hold")
        for blocker in _as_list(payload.get("truth_blockers"))[:8]:
            code = _safe_text(blocker, 120)
            if code:
                reasons.append(f"mission_truth_blocker:{code}")
        for blocker in _as_list(payload.get("owner_blockers"))[:8]:
            payload_blocker = _as_dict(blocker)
            owner = _safe_text(payload_blocker.get("owner"), 80)
            code = _safe_text(payload_blocker.get("code"), 120)
            if owner and code:
                reasons.append(f"mission_owner_blocker:{owner}:{code}")
        return list(dict.fromkeys(reasons))

    @staticmethod
    def _mission_blocks_advisory_action(
        action_type: str,
        evidence: dict[str, Any],
        *,
        action_context: dict[str, Any] | None = None,
    ) -> bool:
        return NOVA_MISSION_SERVICE.hold_blocks_action(
            action_type,
            mission_snapshot=_as_dict(evidence.get("mission_snapshot")),
            policy_snapshot=_as_dict(evidence.get("policy_snapshot")),
            action_context=_as_dict(action_context),
        )

    @staticmethod
    def _pressure_band(queue_pressure: dict[str, Any]) -> str:
        band = _safe_text(queue_pressure.get("pressure_band"), 40).lower()
        if band in {"low", "medium", "high"}:
            return band
        if _as_int(queue_pressure.get("high_priority_count")) > 0 or _as_int(queue_pressure.get("aging_items_count")) > 0:
            return "high"
        if _as_int(queue_pressure.get("pending_count")) > 0:
            return "medium"
        return "low"

    @staticmethod
    def _runtime_summary(runtime_guard_status: dict[str, Any]) -> dict[str, Any]:
        guard_running = _as_bool_or_none(runtime_guard_status.get("guard_running"))
        core_running = _as_bool_or_none(runtime_guard_status.get("core_running"))
        webui_running = _as_bool_or_none(runtime_guard_status.get("webui_running"))
        return {
            "guard_running": guard_running,
            "core_running": core_running,
            "webui_running": webui_running,
            "restart_in_progress": bool(runtime_guard_status.get("restart_in_progress", False)),
            "stop_flag": bool(runtime_guard_status.get("stop_flag", False)),
        }

    @staticmethod
    def _correlation_ids(input_envelope: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in (
            "work_tree_snapshot",
            "steward_posture",
            "queue_pressure",
            "runtime_guard_status",
            "policy_snapshot",
            "triage_hints",
            "last_action_context",
        ):
            section = _as_dict(input_envelope.get(key))
            for id_key in ("snapshot_id", "correlation_id", "source_id"):
                value = _safe_text(section.get(id_key), 120)
                if value:
                    out[key] = value
                    break
        return out

    def _remember_decision(self, decision: dict[str, Any]) -> None:
        self._last_decision = _compact_value(dict(decision or {}))
        self._last_cycle_at = _safe_text(decision.get("created_at_utc"), 80)
        self._cycle_count += 1
        self._decision_history.append(self._last_decision)
        if len(self._decision_history) > 200:
            self._decision_history = self._decision_history[-200:]

    def get_last_decision(self) -> dict[str, Any]:
        return _compact_value(self._last_decision)

    def get_decision_history(self, limit: int = 20, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = _as_dict(filters)
        rows = list(self._decision_history)
        decision_type = _safe_text(filters.get("decision_type"), 80)
        if decision_type:
            rows = [row for row in rows if _safe_text(_as_dict(row).get("decision_type"), 80) == decision_type]
        action_type = _safe_text(filters.get("action_type"), 120)
        if action_type:
            rows = [
                row
                for row in rows
                if _safe_text(_as_dict(_as_dict(row).get("recommended_action")).get("action_type"), 120) == action_type
            ]
        return [_compact_value(row) for row in rows[-max(1, int(limit or 20)) :]]

    def set_mode(self, mode: str, policy_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        requested = _safe_text(mode, 40).lower()
        policy = _as_dict(policy_snapshot)
        if requested not in {ADVISORY_MODE, EXECUTE_MODE}:
            return {"ok": False, "mode": self._mode, "reason": "invalid_mode"}
        if requested == EXECUTE_MODE:
            execute_allowed = bool(
                policy.get("allow_execute_mode")
                or policy.get("execution_enabled")
                or policy.get("autonomy_execute_enabled")
            )
            if not bool(policy.get("autonomy_enabled", False)) or not execute_allowed:
                return {"ok": False, "mode": self._mode, "reason": "execute_mode_policy_blocked"}
        self._mode = requested
        return {"ok": True, "mode": self._mode, "reason": ""}

    def get_health(self) -> dict[str, Any]:
        return {
            "ok": self._error_count == 0,
            "mode": self._mode,
            "cycle_count": int(self._cycle_count),
            "history_count": len(self._decision_history),
            "last_cycle_at": self._last_cycle_at,
            "last_error": self._last_error,
            "error_count": int(self._error_count),
            "cadence_sec": DEFAULT_CYCLE_CADENCE_SEC,
            "jitter_pct": DEFAULT_CYCLE_JITTER_PCT,
        }

    def _contract_evidence(self, input_envelope: dict[str, Any], *, created_at_utc: str) -> dict[str, Any]:
        work_tree_raw = _as_dict(input_envelope.get("work_tree_snapshot"))
        steward_raw = _as_dict(input_envelope.get("steward_posture"))
        queue_raw = _as_dict(input_envelope.get("queue_pressure"))
        runtime_raw = _as_dict(input_envelope.get("runtime_guard_status"))
        policy_raw = _as_dict(input_envelope.get("policy_snapshot"))
        triage_raw = _as_dict(input_envelope.get("triage_hints"))
        mission_raw = _as_dict(input_envelope.get("mission_snapshot"))
        if not mission_raw:
            mission_raw = _as_dict(triage_raw.get("mission_snapshot"))
        last_action_raw = _as_dict(input_envelope.get("last_action_context"))
        maintenance_raw = _as_dict(input_envelope.get("autonomy_maintenance"))
        layer_maturity_raw = _as_dict(input_envelope.get("layer_maturity_snapshot"))

        branches: list[dict[str, Any]] = []
        for item in _as_list(work_tree_raw.get("branches"))[:40]:
            branch = _as_dict(item)
            if not branch:
                continue
            branches.append(
                {
                    "branch_id": _safe_text(branch.get("branch_id") or branch.get("id"), 120),
                    "title": _safe_text(branch.get("title") or branch.get("name"), 180),
                    "status": _safe_text(branch.get("status"), 80).lower(),
                    "owner": _safe_text(branch.get("owner") or branch.get("likely_owner"), 120),
                    "age_min": _as_int(branch.get("age_min") or branch.get("open_age_min")),
                    "task_id": _safe_text(branch.get("task_id"), 160),
                    "task_title": _safe_text(branch.get("task_title"), 180),
                    "recommended_tool": _safe_text(branch.get("recommended_tool"), 120),
                    "tree_id": _safe_text(branch.get("tree_id"), 120),
                    "tree_title": _safe_text(branch.get("tree_title"), 180),
                    "executable": bool(branch.get("executable", False)),
                }
            )

        policy_autonomy = (
            _as_bool_or_none(policy_raw.get("autonomy_enabled"))
            if "autonomy_enabled" in policy_raw
            else None
        )
        runtime_summary = self._runtime_summary(runtime_raw)
        posture_band = self._posture_band(steward_raw)
        queue_band = self._pressure_band(queue_raw)
        source_presence = {
            "work_tree_snapshot": self._source_present(input_envelope, "work_tree_snapshot"),
            "steward_posture": self._source_present(input_envelope, "steward_posture"),
            "queue_pressure": self._source_present(input_envelope, "queue_pressure"),
            "runtime_guard_status": self._source_present(input_envelope, "runtime_guard_status"),
            "policy_snapshot": self._source_present(input_envelope, "policy_snapshot"),
            "triage_hints": self._source_present(input_envelope, "triage_hints"),
            "last_action_context": self._source_present(input_envelope, "last_action_context"),
            "autonomy_maintenance": self._source_present(input_envelope, "autonomy_maintenance"),
        }
        freshness = {
            "work_tree_snapshot": self._freshness_sec(work_tree_raw),
            "steward_posture": self._freshness_sec(steward_raw),
            "queue_pressure": self._freshness_sec(queue_raw),
            "runtime_guard_status": self._freshness_sec(runtime_raw),
            "policy_snapshot": self._freshness_sec(policy_raw),
            "triage_hints": self._freshness_sec(triage_raw),
            "last_action_context": self._freshness_sec(last_action_raw),
            "autonomy_maintenance": self._freshness_sec(maintenance_raw),
        }
        seam_scores = _as_dict(triage_raw.get("seam_pressure_scores"))
        owner_scores = _as_dict(triage_raw.get("owner_pressure_scores"))
        lane_scores = _as_dict(triage_raw.get("lane_pressure_scores"))
        review_contract_scores = _as_dict(triage_raw.get("review_contract_pressure_scores"))
        max_seam_pressure = 0.0
        for value in seam_scores.values():
            max_seam_pressure = max(max_seam_pressure, _clamp_float(value))
        max_lane_pressure = 0.0
        for value in lane_scores.values():
            max_lane_pressure = max(max_lane_pressure, _clamp_float(value))

        return {
            "generated_at_utc": created_at_utc,
            "source_presence": source_presence,
            "source_freshness_sec": freshness,
            "work_tree_snapshot": {
                "open_count": _as_int(work_tree_raw.get("open_count")),
                "working_count": _as_int(work_tree_raw.get("working_count")),
                "blocked_count": _as_int(work_tree_raw.get("blocked_count")),
                "observing_count": _as_int(work_tree_raw.get("observing_count")),
                "latent_root_signal_count": _as_int(work_tree_raw.get("latent_root_signal_count")),
                "operator_hold_count": _as_int(work_tree_raw.get("operator_hold_count")),
                "stale_count": _as_int(work_tree_raw.get("stale_count")),
                "oldest_open_age_min": _as_int(work_tree_raw.get("oldest_open_age_min")),
                "active_candidate_count": _as_int(work_tree_raw.get("active_candidate_count"), -1),
                "active_executable_count": _as_int(work_tree_raw.get("active_executable_count"), -1),
                "active_unsafe_count": _as_int(work_tree_raw.get("active_unsafe_count"), -1),
                "branches": branches,
                "source_freshness_sec": freshness["work_tree_snapshot"],
            },
            "steward_posture": {
                "health_score": _as_int(steward_raw.get("health_score")),
                "alert_count": _as_int(steward_raw.get("alert_count")),
                "critical_alerts": _as_int(steward_raw.get("critical_alerts")),
                "pass_ratio": _clamp_float(steward_raw.get("pass_ratio")),
                "posture_band": posture_band,
                "source_freshness_sec": freshness["steward_posture"],
            },
            "queue_pressure": {
                "pending_count": _as_int(queue_raw.get("pending_count")),
                "aging_items_count": _as_int(queue_raw.get("aging_items_count")),
                "high_priority_count": _as_int(queue_raw.get("high_priority_count")),
                "pressure_band": queue_band,
                "source_freshness_sec": freshness["queue_pressure"],
                "approved_eligible_previews": _as_int(queue_raw.get("approved_eligible_previews")),
                "generated_pending_count": _as_int(
                    queue_raw.get("generated_pending_count"),
                    _as_int(queue_raw.get("pending_count")),
                ),
                "generated_actionable_count": _as_int(
                    queue_raw.get("generated_actionable_count"),
                    _as_int(queue_raw.get("high_priority_count")),
                ),
                "generated_blocked_count": _as_int(
                    queue_raw.get("generated_blocked_count"),
                    _as_int(queue_raw.get("blocked_count")),
                ),
                "patch_apply_ready_count": _as_int(queue_raw.get("patch_apply_ready_count")),
                "patch_approve_ready_count": _as_int(queue_raw.get("patch_approve_ready_count")),
                "patch_ready_count": _as_int(queue_raw.get("patch_ready_count")),
            },
            "runtime_guard_status": {
                **runtime_summary,
                "source_freshness_sec": freshness["runtime_guard_status"],
            },
            "autonomy_maintenance": {
                "worker_status": _safe_text(maintenance_raw.get("worker_status"), 80).lower(),
                "worker_active": bool(maintenance_raw.get("worker_active", False)),
                "worker_stale_identity": bool(maintenance_raw.get("worker_stale_identity", False)),
                "scheduler_active": bool(maintenance_raw.get("scheduler_active", False)),
                "scheduler_mode": _safe_text(maintenance_raw.get("scheduler_mode"), 80).lower(),
                "scheduler_status": _safe_text(maintenance_raw.get("scheduler_status"), 80).lower(),
                "source_freshness_sec": freshness["autonomy_maintenance"],
            },
            "policy_snapshot": {
                "autonomy_enabled": policy_autonomy,
                "allowed_actions": [
                    _safe_text(item, 120)
                    for item in _as_list(policy_raw.get("allowed_actions"))
                    if _safe_text(item, 120)
                ],
                "blocked_actions": [
                    _safe_text(item, 120)
                    for item in _as_list(policy_raw.get("blocked_actions"))
                    if _safe_text(item, 120)
                ],
                "execute_allowed_action_groups": [
                    _safe_text(item, 120)
                    for item in _as_list(policy_raw.get("execute_allowed_action_groups"))
                    if _safe_text(item, 120)
                ],
                "quiet_hours_active": bool(policy_raw.get("quiet_hours_active", False)),
                "requires_operator_ack_for": [
                    _safe_text(item, 120)
                    for item in _as_list(policy_raw.get("requires_operator_ack_for"))
                    if _safe_text(item, 120)
                ],
                "operator_ack_present": bool(policy_raw.get("operator_ack_present", False)),
                "active_work_tree_max_steps_per_cycle": _as_int(policy_raw.get("active_work_tree_max_steps_per_cycle")),
                "active_work_tree_max_trees_per_cycle": _as_int(policy_raw.get("active_work_tree_max_trees_per_cycle")),
                "layers": _compact_value(_as_dict(policy_raw.get("layers"))),
                "source_freshness_sec": freshness["policy_snapshot"],
            },
            "layer_maturity_snapshot": _compact_value(layer_maturity_raw),
            "triage_hints": {
                "likely_owner_by_branch": _compact_value(_as_dict(triage_raw.get("likely_owner_by_branch"))),
                "seam_pressure_scores": _compact_value(seam_scores),
                "owner_pressure_scores": _compact_value(owner_scores),
                "lane_pressure_scores": _compact_value(lane_scores),
                "review_contract_pressure_scores": _compact_value(review_contract_scores),
                "top_triage_candidates": _compact_value(_as_list(triage_raw.get("top_triage_candidates"))),
                "approved_review_count": _as_int(triage_raw.get("approved_review_count")),
                "rejected_review_count": _as_int(triage_raw.get("rejected_review_count")),
                "max_seam_pressure": round(max_seam_pressure, 4),
                "max_lane_pressure": round(max_lane_pressure, 4),
                "confidence": _clamp_float(triage_raw.get("confidence")),
                "source": _safe_text(triage_raw.get("source"), 120),
                "source_freshness_sec": freshness["triage_hints"],
            },
            "last_action_context": {
                "last_action_type": _safe_text(last_action_raw.get("last_action_type"), 120),
                "last_target_id": _safe_text(last_action_raw.get("last_target_id"), 160),
                "last_target_step_id": _safe_text(last_action_raw.get("last_target_step_id"), 160),
                "last_action_at_utc": _safe_text(last_action_raw.get("last_action_at_utc"), 80),
                "cooldown_active": bool(last_action_raw.get("cooldown_active", False)),
                "cooldown_remaining_sec": _as_int(last_action_raw.get("cooldown_remaining_sec")),
                "last_result": _safe_text(last_action_raw.get("last_result"), 80).lower() or "unknown",
                "operator_ack_present": bool(last_action_raw.get("operator_ack_present", False)),
            },
            "mission_snapshot": {
                "enabled": bool(mission_raw.get("enabled", False)),
                "mode": _safe_text(mission_raw.get("mode"), 80),
                "objective": _safe_text(mission_raw.get("objective"), 200),
                "status": _safe_text(mission_raw.get("status"), 40),
                "action": _safe_text(mission_raw.get("action"), 40),
                "green_cycle": bool(mission_raw.get("green_cycle", False)),
                "headline": _safe_text(mission_raw.get("headline"), 220),
                "truth_ready": bool(mission_raw.get("truth_ready", False)),
                "truth_blockers": list(mission_raw.get("truth_blockers") or []),
                "owner_blockers": _compact_value(_as_list(mission_raw.get("owner_blockers"))),
                "owner_verdicts": _compact_value(_as_list(mission_raw.get("owner_verdicts"))),
                "green_blockers": _compact_value(_as_list(mission_raw.get("green_blockers"))),
                "blocking_owner_count": _as_int(mission_raw.get("blocking_owner_count")),
                "validation_fresh": bool(mission_raw.get("validation_fresh", False)),
                "regression_current": bool(mission_raw.get("regression_current", False)),
                "release_truth_current": bool(mission_raw.get("release_truth_current", False)),
                "core_gate": _compact_value(_as_dict(mission_raw.get("core_gate"))),
                "core_gate_missing_roots": list(mission_raw.get("core_gate_missing_roots") or []),
                "active_work_evidence_current": bool(mission_raw.get("active_work_evidence_current", False)),
                "generated_queue_untested_count": _as_int(mission_raw.get("generated_queue_untested_count")),
                "fresh_gap_signal_count": _as_int(mission_raw.get("fresh_gap_signal_count")),
                "ambient_gap_signal_count": _as_int(mission_raw.get("ambient_gap_signal_count")),
                "actionable_fresh_gap_signal_count": _as_int(mission_raw.get("actionable_fresh_gap_signal_count")),
                "effective_queue_pressure_band": _safe_text(mission_raw.get("effective_queue_pressure_band"), 40),
                "release_stale_ready_count": _as_int(mission_raw.get("release_stale_ready_count")),
                "source": _safe_text(mission_raw.get("source"), 120),
                "source_freshness_sec": self._freshness_sec(mission_raw),
            },
            "correlation_ids": self._correlation_ids(input_envelope),
        }

    @staticmethod
    def _top_triage_candidate(triage: dict[str, Any], *, lane: str | None = None) -> dict[str, Any]:
        lane_key = _safe_text(lane, 80).lower()
        for item in _as_list(triage.get("top_triage_candidates")):
            candidate = _as_dict(item)
            if not candidate:
                continue
            if lane_key and _safe_text(candidate.get("lane"), 80).lower() not in {lane_key, ""}:
                continue
            return candidate
        return {}

    @staticmethod
    def _triage_focus_text(candidate: dict[str, Any]) -> str:
        if not candidate:
            return ""
        seam = _safe_text(candidate.get("target_seam"), 120)
        signal = _safe_text(candidate.get("signal"), 120)
        owner = _safe_text(candidate.get("preferred_owner"), 120)
        if seam and signal and owner:
            return f" Triage focus: {seam}/{signal} owned by {owner}."
        if seam and signal:
            return f" Triage focus: {seam}/{signal}."
        return ""

    @staticmethod
    def _triage_pressure_for_action(action_type: str, evidence: dict[str, Any]) -> float:
        triage = _as_dict(evidence.get("triage_hints"))
        lane_scores = _as_dict(triage.get("lane_pressure_scores"))
        seam_scores = _as_dict(triage.get("seam_pressure_scores"))
        max_seam_pressure = _clamp_float(triage.get("max_seam_pressure"))
        action = _safe_text(action_type, 120)
        if action == "generated_queue_run_next":
            return max(
                _clamp_float(lane_scores.get("generated_queue")),
                _clamp_float(lane_scores.get("subconscious_review")),
                max_seam_pressure * 0.5,
            )
        if action == "patch_queue_run_next":
            patch_pressure = _clamp_float(lane_scores.get("patch_queue"))
            for key, value in seam_scores.items():
                if "patch" in str(key or "").strip().lower():
                    patch_pressure = max(patch_pressure, _clamp_float(value))
            return patch_pressure
        if action == "active_work_tree_run_next":
            return max(
                _clamp_float(lane_scores.get("active_work_tree")),
                _clamp_float(lane_scores.get("work_tree")),
                max_seam_pressure * 0.35,
            )
        if action == "pulse_status":
            return max_seam_pressure
        return 0.0

    @staticmethod
    def _contract_conflicts(evidence: dict[str, Any]) -> list[str]:
        conflicts: list[str] = []
        posture = _as_dict(evidence.get("steward_posture"))
        runtime = _as_dict(evidence.get("runtime_guard_status"))
        work_tree = _as_dict(evidence.get("work_tree_snapshot"))
        queue = _as_dict(evidence.get("queue_pressure"))
        band = _safe_text(posture.get("posture_band"), 40).lower()
        score = _as_int(posture.get("health_score"))

        if band == "green" and score < 85:
            conflicts.append("posture_green_but_health_score_below_green_floor")
        if band == "red" and score >= 85 and _as_int(posture.get("critical_alerts")) <= 0:
            conflicts.append("posture_red_without_score_or_critical_alert_support")
        if band == "green" and runtime.get("core_running") is False:
            conflicts.append("core_runtime_disagrees_with_green_posture")
        if _as_int(work_tree.get("working_count")) > _as_int(work_tree.get("open_count")) and _as_int(work_tree.get("open_count")) > 0:
            conflicts.append("work_tree_working_count_exceeds_open_count")
        if _as_int(queue.get("high_priority_count")) > _as_int(queue.get("pending_count")) and _as_int(queue.get("pending_count")) > 0:
            conflicts.append("queue_high_priority_count_exceeds_pending_count")
        return conflicts

    @staticmethod
    def _contract_action(
        action_type: str,
        *,
        reason_code: str,
        target_id: str | None = None,
        expected_effect: str | None = None,
    ) -> dict[str, Any]:
        catalog = _as_dict(autonomy_advisory_action_catalog().get(action_type))
        return {
            "action_type": action_type,
            "target_kind": _safe_text(catalog.get("target_kind"), 80),
            "target_id": _safe_text(target_id or catalog.get("target_id"), 160),
            "reason_code": _safe_text(reason_code, 120),
            "expected_effect": _safe_text(expected_effect or catalog.get("expected_effect"), 360),
            "preconditions": list(catalog.get("preconditions") or []),
            "requires_ack": bool(catalog.get("requires_ack", False)),
            "cooldown_sec": _as_int(catalog.get("cooldown_sec")),
            "ttl_sec": _as_int(catalog.get("ttl_sec")),
            "max_steps": _as_int(catalog.get("max_steps")),
            "max_trees": _as_int(catalog.get("max_trees")),
            "execution_group": _safe_text(catalog.get("execution_group"), 120),
        }

    @staticmethod
    def _contract_active_work_tree_count(work_tree: dict[str, Any]) -> int:
        executable_count = _as_int(work_tree.get("active_executable_count"), -1)
        if executable_count >= 0:
            return executable_count
        managed_owners = {"patch_queue", "generated_queue", "signal_ingestion", "capability_gap"}
        branches = [_as_dict(branch) for branch in _as_list(work_tree.get("branches")) if isinstance(branch, dict)]
        active_count = 0
        for payload in branches:
            if not payload:
                continue
            status = _safe_text(payload.get("status"), 80).lower()
            if status and status not in {"active", "working", "open", "pending"}:
                continue
            owner = _safe_text(payload.get("owner"), 120).lower()
            if owner in managed_owners:
                continue
            active_count += 1
        if branches:
            return active_count
        if active_count:
            return active_count
        open_count = _as_int(work_tree.get("open_count"))
        working_count = _as_int(work_tree.get("working_count"))
        return max(open_count, working_count)

    def _contract_candidate_actions(self, evidence: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        work_tree = _as_dict(evidence.get("work_tree_snapshot"))
        queue = _as_dict(evidence.get("queue_pressure"))
        runtime = _as_dict(evidence.get("runtime_guard_status"))
        triage = _as_dict(evidence.get("triage_hints"))
        maintenance = _as_dict(evidence.get("autonomy_maintenance"))

        if runtime.get("guard_running") is False:
            candidates.append(
                {
                    "action": self._contract_action("guard_start", reason_code="runtime_guard_stopped"),
                    "source": "runtime_guard_status",
                }
            )

        worker_status = _safe_text(maintenance.get("worker_status"), 80).lower()
        scheduler_active = bool(maintenance.get("scheduler_active", False))
        worker_stale_identity = bool(maintenance.get("worker_stale_identity", False))
        if (
            runtime.get("guard_running") is True
            and not scheduler_active
            and not worker_stale_identity
            and worker_status
            and worker_status not in {"running", "ok"}
        ):
            candidates.append(
                {
                    "action": self._contract_action(
                        "autonomy_maintenance_start",
                        reason_code="maintenance_worker_not_running",
                    ),
                    "source": "autonomy_maintenance",
                }
            )

        pending_count = _as_int(queue.get("generated_pending_count"), _as_int(queue.get("pending_count")))
        actionable_count = _as_int(queue.get("generated_actionable_count"), _as_int(queue.get("high_priority_count")))
        aging_count = _as_int(queue.get("aging_items_count"))
        high_priority_count = _as_int(queue.get("generated_actionable_count"), _as_int(queue.get("high_priority_count")))
        generated_blocked_count = _as_int(queue.get("generated_blocked_count"))
        patch_ready_count = _as_int(queue.get("patch_ready_count"))
        patch_apply_ready = _as_int(queue.get("patch_apply_ready_count"))
        patch_approve_ready = _as_int(queue.get("patch_approve_ready_count"))
        blocked_count = _as_int(work_tree.get("blocked_count"))
        latent_root_signal_count = _as_int(work_tree.get("latent_root_signal_count"))
        operator_hold_count = _as_int(work_tree.get("operator_hold_count"))
        stale_count = _as_int(work_tree.get("stale_count"))
        active_work_count = self._contract_active_work_tree_count(work_tree)
        top_generated_triage = self._top_triage_candidate(triage, lane="generated_queue")
        top_patch_triage = self._top_triage_candidate(triage, lane="patch_queue")
        top_any_triage = self._top_triage_candidate(triage)
        policy = _as_dict(evidence.get("policy_snapshot"))
        concrete_lane_candidate_present = False
        if patch_ready_count > 0:
            concrete_lane_candidate_present = True
            candidates.append(
                {
                    "action": self._contract_action(
                        "patch_queue_run_next",
                        reason_code="patch_queue_ready",
                        expected_effect=(
                            "Advance one governed patch queue step "
                            f"({patch_apply_ready} apply-ready, {patch_approve_ready} approve-ready)."
                            + self._triage_focus_text(top_patch_triage)
                        ),
                    ),
                    "source": "queue_pressure+triage_hints" if top_patch_triage else "queue_pressure",
                    "triage_focus": _compact_value(top_patch_triage),
                }
            )
        generated_has_blockers = generated_blocked_count > 0
        generated_actionable_ready = actionable_count > 0 or (pending_count > 0 and not generated_has_blockers)
        if generated_actionable_ready and not self._mission_blocks_advisory_action("generated_queue_run_next", evidence):
            concrete_lane_candidate_present = True
            candidates.append(
                {
                    "action": self._contract_action(
                        "generated_queue_run_next",
                        reason_code="queue_pressure_actionable",
                        expected_effect=(
                            f"Advance one of {max(pending_count, actionable_count, high_priority_count)} pending governed queue item(s)."
                            + self._triage_focus_text(top_generated_triage or top_any_triage)
                        ),
                    ),
                    "source": "queue_pressure+triage_hints" if (top_generated_triage or top_any_triage) else "queue_pressure",
                    "triage_focus": _compact_value(top_generated_triage or top_any_triage),
                }
            )
        if (
            not self._mission_blocks_advisory_action("generated_queue_investigate", evidence)
            and (
                generated_blocked_count > 0
                or stale_count > 0
                or (aging_count > 0 and pending_count <= 0 and active_work_count <= 0)
            )
        ):
            candidates.append(
                {
                    "action": self._contract_action(
                        "generated_queue_investigate",
                        reason_code="work_tree_or_queue_blocked",
                        expected_effect="Investigate blocked, stale, or aging work before selecting execution.",
                    ),
                    "source": "work_tree_snapshot",
                }
            )

        if active_work_count > 0:
            active_branches = [
                _as_dict(branch)
                for branch in _as_list(work_tree.get("branches"))
                if bool(_as_dict(branch).get("executable", False))
            ]
            selected_active_branch: dict[str, Any] = {}
            selected_active_index = -1
            for index, branch in enumerate(active_branches):
                candidate_branch = _as_dict(branch)
                if not self._mission_blocks_advisory_action(
                    "active_work_tree_run_next",
                    evidence,
                    action_context=candidate_branch,
                ):
                    selected_active_branch = candidate_branch
                    selected_active_index = index
                    break
            if selected_active_branch:
                concrete_lane_candidate_present = True
                catalog = _as_dict(autonomy_advisory_action_catalog().get("active_work_tree_run_next"))
                configured_steps = _as_int(policy.get("active_work_tree_max_steps_per_cycle"), _as_int(catalog.get("max_steps"), 3))
                configured_trees = _as_int(policy.get("active_work_tree_max_trees_per_cycle"), _as_int(catalog.get("max_trees"), 8))
                step_budget = (
                    1
                    if selected_active_index > 0
                    else max(1, min(max(1, active_work_count), max(1, configured_steps)))
                )
                tree_budget = (
                    1
                    if selected_active_index > 0
                    else max(1, min(max(1, active_work_count), max(1, configured_trees)))
                )
                active_branch_title = _safe_text(
                    selected_active_branch.get("title"),
                    180,
                )
                active_branch_id = _safe_text(
                    selected_active_branch.get("branch_id"),
                    160,
                )
                active_branch_tool = _safe_text(
                    selected_active_branch.get("recommended_tool"),
                    120,
                )
                active_task_id = _safe_text(
                    selected_active_branch.get("task_id"),
                    160,
                )
                active_tree_id = _safe_text(
                    selected_active_branch.get("tree_id"),
                    160,
                )
                effect = f"Advance up to {step_budget} governed step(s) from {active_work_count} active Work Tree signal(s)."
                if active_branch_title:
                    effect = f"{effect} First branch: {active_branch_title}."
                action = self._contract_action(
                    "active_work_tree_run_next",
                    reason_code="active_work_tree_ready",
                    target_id=active_branch_id or None,
                    expected_effect=effect,
                )
                if active_task_id:
                    action["target_step_id"] = active_task_id
                if active_branch_tool:
                    action["recommended_tool"] = active_branch_tool
                if active_tree_id:
                    action["target_tree_id"] = active_tree_id
                action["max_steps"] = step_budget
                action["max_trees"] = tree_budget
                if active_branch_tool in {"read", "find", "ls", "health", "system_check", "queue_status", "pulse"}:
                    action["cooldown_sec"] = 0
                candidates.append(
                    {
                        "action": action,
                        "source": "work_tree_snapshot",
                        "triage_focus": {},
                    }
                )


        capability_gap_branches = [
            _as_dict(branch)
            for branch in _as_list(work_tree.get("branches"))
            if isinstance(branch, dict)
            and str(branch.get("kind") or "").strip().lower() == "capability_gap"
            and str(branch.get("status") or "").strip().lower() in {"ready", "open", "pending"}
        ]
        if capability_gap_branches:
            gap_branch = capability_gap_branches[0]
            gap_branch_id = _safe_text(gap_branch.get("branch_id"), 160)
            gap_branch_title = _safe_text(gap_branch.get("title"), 180)
            gap_metadata = _as_dict(gap_branch.get("metadata"))
            gap_payload = _as_dict(gap_branch.get("source_payload"))
            gap_capability = str(
                gap_metadata.get("capability_name")
                or gap_payload.get("primary_capability")
                or gap_payload.get("capability_name")
                or ""
            ).strip()
            gap_execution_group = str(gap_payload.get("execution_group") or "").strip().lower()
            if gap_execution_group == "leah_build" or gap_capability.startswith("leah_"):
                action_type = "leah_build_run_next"
                reason_code = "leah_capability_gap_ready"
                if gap_capability:
                    effect = f"Generate Leah-specific capability work for {gap_capability}. Branch: {gap_branch_title}."
                else:
                    effect = f"Generate Leah-specific capability work. Branch: {gap_branch_title}."
            else:
                action_type = "codegen_run"
                reason_code = "capability_gap_ready"
                if gap_capability:
                    effect = f"Generate code to close capability gap: {gap_capability}. Branch: {gap_branch_title}."
                else:
                    effect = f"Synthesize capability gap specification and generate implementation. Branch: {gap_branch_title}."
            policy_snapshot = _as_dict(evidence.get("policy_snapshot"))
            layer_maturity = _as_dict(evidence.get("layer_maturity_snapshot"))
            status_context = {
                "capability_gaps": list(gap_payload.get("gaps") or []),
                "root_closure_inventory": layer_maturity.get("root_closure_inventory"),
                "release_runtime_truth": layer_maturity.get("release_runtime_truth"),
                "release_status": layer_maturity.get("release_status"),
                "capabilities_registered": layer_maturity.get("capabilities_registered"),
            }
            if (
                not self._mission_blocks_advisory_action(action_type, evidence)
                and orchestrator_codegen_action_allowed(
                    action_type,
                    policy=policy_snapshot,
                    status_payload=status_context,
                    capability_name=gap_capability,
                )
            ):
                candidates.append(
                    {
                        "action": self._contract_action(
                            action_type,
                            reason_code=reason_code,
                            target_id=gap_branch_id or None,
                            expected_effect=effect,
                        ),
                        "source": "work_tree_snapshot",
                        "triage_focus": {},
                    }
                )

        if _as_int(queue.get("approved_eligible_previews")) > 0:
            candidates.append(
                {
                    "action": self._contract_action("update_now_dry_run", reason_code="approved_preview_waiting"),
                    "source": "queue_pressure",
                }
            )

        if (
            not self._mission_blocks_advisory_action("pulse_status", evidence)
            and _as_float(triage.get("max_seam_pressure")) >= 0.75
            and not concrete_lane_candidate_present
        ):
            candidates.append(
                {
                    "action": self._contract_action("pulse_status", reason_code="seam_pressure_elevated"),
                    "source": "triage_hints",
                }
            )
        return candidates

    @staticmethod
    def _score_contract_candidate(candidate: dict[str, Any], evidence: dict[str, Any]) -> tuple[float, dict[str, float]]:
        action = _as_dict(candidate.get("action"))
        catalog = _as_dict(autonomy_advisory_action_catalog().get(_safe_text(action.get("action_type"), 120)))
        queue = _as_dict(evidence.get("queue_pressure"))
        work_tree = _as_dict(evidence.get("work_tree_snapshot"))
        posture = _as_dict(evidence.get("steward_posture"))
        triage = _as_dict(evidence.get("triage_hints"))
        action_type = _safe_text(action.get("action_type"), 120)
        pressure_band = _safe_text(queue.get("pressure_band"), 40).lower()
        posture_band = _safe_text(posture.get("posture_band"), 40).lower()
        urgency = 0.0
        if pressure_band == "high":
            urgency += 0.2
        elif pressure_band == "medium":
            urgency += 0.1
        urgency += min(_as_int(queue.get("high_priority_count")), 3) * 0.04
        urgency += min(_as_int(queue.get("aging_items_count")), 3) * 0.03
        urgency += min(_as_int(work_tree.get("blocked_count")) + _as_int(work_tree.get("stale_count")), 3) * 0.03
        impact = _clamp_float(catalog.get("impact"), 0.5)
        safety_risk = _clamp_float(catalog.get("safety_risk"), 0.0)
        posture_multiplier = {"green": 1.0, "yellow": 0.75, "red": 0.0}.get(posture_band, 0.5)
        triage_pressure = AutonomyOrchestratorService._triage_pressure_for_action(action_type, evidence)
        triage_confidence = _clamp_float(triage.get("confidence"), 0.0)
        triage_bonus = triage_pressure * max(0.5, triage_confidence) * 0.14
        mission_hold_penalty = (
            MISSION_GREEN_HOLD_PENALTY
            if AutonomyOrchestratorService._mission_blocks_advisory_action(
                action_type,
                evidence,
                action_context=action,
            )
            else 0.0
        )
        score = (impact + urgency + triage_bonus - (safety_risk * 0.35) - mission_hold_penalty) * posture_multiplier
        score = _clamp_float(score)
        return round(score, 4), {
            "urgency": round(urgency, 4),
            "expected_impact": round(impact, 4),
            "triage_lane_pressure_bonus": round(triage_bonus, 4),
            "triage_pressure": round(triage_pressure, 4),
            "mission_green_hold_penalty": round(mission_hold_penalty, 4),
            "safety_risk_penalty": round(safety_risk * 0.35, 4),
            "posture_confidence_multiplier": round(posture_multiplier, 4),
        }

    @staticmethod
    def _policy_allowed_actions(policy: dict[str, Any]) -> set[str]:
        allowed = {
            _safe_text(item, 120)
            for item in _as_list(policy.get("allowed_actions"))
            if _safe_text(item, 120)
        }
        if "*" in allowed:
            return set(autonomy_advisory_action_types())
        return allowed

    def _consider_contract_candidates(self, candidates: list[dict[str, Any]], evidence: dict[str, Any]) -> list[dict[str, Any]]:
        policy = _as_dict(evidence.get("policy_snapshot"))
        last_action = _as_dict(evidence.get("last_action_context"))
        allowed_actions = self._policy_allowed_actions(policy)
        blocked_actions = {
            _safe_text(item, 120)
            for item in _as_list(policy.get("blocked_actions"))
            if _safe_text(item, 120)
        }
        ack_required_for = {
            _safe_text(item, 120)
            for item in _as_list(policy.get("requires_operator_ack_for"))
            if _safe_text(item, 120)
        }
        operator_ack_present = bool(policy.get("operator_ack_present") or last_action.get("operator_ack_present"))
        quiet_hours_active = bool(policy.get("quiet_hours_active", False))
        cooldown_active = bool(last_action.get("cooldown_active", False))
        last_action_type = _safe_text(last_action.get("last_action_type"), 120)
        last_target_id = _safe_text(last_action.get("last_target_id"), 160)
        last_target_step_id = _safe_text(last_action.get("last_target_step_id"), 160)

        considered: list[dict[str, Any]] = []
        for candidate in candidates:
            action = _as_dict(candidate.get("action"))
            action_type = _safe_text(action.get("action_type"), 120)
            target_id = _safe_text(action.get("target_id"), 160)
            target_step_id = _safe_text(action.get("target_step_id"), 160)
            reject_reasons: list[str] = []
            if not is_autonomy_advisory_action(action_type):
                reject_reasons.append("action_not_allowed")
            if action_type in blocked_actions:
                reject_reasons.append("action_not_allowed")
            if action_type not in allowed_actions:
                reject_reasons.append("action_not_allowed")
            if action_type in ack_required_for or "*" in ack_required_for:
                action["requires_ack"] = True
            if quiet_hours_active:
                action["requires_ack"] = True
            if bool(action.get("requires_ack", False)) and not operator_ack_present:
                reject_reasons.append("operator_ack_required")
            if (
                cooldown_active
                and (not last_action_type or last_action_type == action_type)
                and (not last_target_id or last_target_id == target_id)
                and (not last_target_step_id or not target_step_id or last_target_step_id == target_step_id)
            ):
                reject_reasons.append("cooldown_active")

            score, score_components = self._score_contract_candidate({"action": action}, evidence)
            considered.append(
                {
                    "action": _compact_value(action),
                    "source": _safe_text(candidate.get("source"), 120),
                    "triage_focus": _compact_value(_as_dict(candidate.get("triage_focus"))),
                    "score": score,
                    "score_components": score_components,
                    "reject_reasons": reject_reasons,
                    "status": "rejected" if reject_reasons else "candidate",
                }
            )
        return considered

    def _contract_decide(
        self,
        *,
        evidence: dict[str, Any],
        candidates_considered: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any], float, list[str], dict[str, str], str]:
        refusal_reasons: list[str] = []
        policy_checks: dict[str, str] = {}
        presence = _as_dict(evidence.get("source_presence"))
        freshness = _as_dict(evidence.get("source_freshness_sec"))
        work_tree = _as_dict(evidence.get("work_tree_snapshot"))
        posture = _as_dict(evidence.get("steward_posture"))
        runtime = _as_dict(evidence.get("runtime_guard_status"))
        policy = _as_dict(evidence.get("policy_snapshot"))

        missing_primary = [
            name
            for name in ("work_tree_snapshot", "steward_posture", "queue_pressure", "runtime_guard_status", "policy_snapshot")
            if not bool(presence.get(name))
        ]
        policy_checks["primary_sources_present"] = "pass" if not missing_primary else "fail"
        if missing_primary:
            refusal_reasons.append("evidence_stale")
            return SPEC_DECISION_DEFER, {}, 0.0, refusal_reasons, policy_checks, (
                "Primary evidence source(s) are missing: " + ", ".join(missing_primary) + "."
            )

        policy_checks["autonomy_enabled"] = "pass" if policy.get("autonomy_enabled") is True else "fail"
        if policy.get("autonomy_enabled") is not True:
            refusal_reasons.append("policy_autonomy_disabled")
            return SPEC_DECISION_BLOCK, {}, 0.0, refusal_reasons, policy_checks, "Autonomy is disabled by policy."

        stale_runtime = _as_int(freshness.get("runtime_guard_status"), -1) < 0 or _as_int(freshness.get("runtime_guard_status"), 0) > HARD_STALE_THRESHOLD_SEC
        stale_posture = _as_int(freshness.get("steward_posture"), -1) < 0 or _as_int(freshness.get("steward_posture"), 0) > HARD_STALE_THRESHOLD_SEC
        policy_checks["runtime_freshness"] = "fail" if stale_runtime else "pass"
        policy_checks["posture_freshness"] = "fail" if stale_posture else "pass"
        if stale_runtime:
            refusal_reasons.append("runtime_evidence_stale")
        if stale_posture:
            refusal_reasons.append("evidence_stale")
        stale_primary = [
            name
            for name in ("work_tree_snapshot", "queue_pressure", "policy_snapshot")
            if _as_int(freshness.get(name), -1) < 0 or _as_int(freshness.get(name), 0) > HARD_STALE_THRESHOLD_SEC
        ]
        policy_checks["primary_freshness"] = "pass" if not stale_primary else "fail"
        if stale_primary and "evidence_stale" not in refusal_reasons:
            refusal_reasons.append("evidence_stale")
        if refusal_reasons:
            return SPEC_DECISION_DEFER, {}, 0.0, refusal_reasons, policy_checks, "Evidence is stale or incomplete for advisory action."

        band = _safe_text(posture.get("posture_band"), 40).lower()
        critical_alerts = _as_int(posture.get("critical_alerts"))
        policy_checks["posture_band"] = "pass" if band != "red" else "fail"
        policy_checks["critical_alerts"] = "pass" if critical_alerts <= 0 else "fail"
        if band == "red":
            refusal_reasons.append("posture_red")
            return SPEC_DECISION_BLOCK, {}, 0.0, refusal_reasons, policy_checks, "Core steward posture is red."
        if critical_alerts > 0:
            refusal_reasons.append("critical_alert_active")
            return SPEC_DECISION_BLOCK, {}, 0.0, refusal_reasons, policy_checks, "Critical steward alert is active."

        guard_running = runtime.get("guard_running")
        core_running = runtime.get("core_running")
        policy_checks["runtime_known"] = "pass" if guard_running is not None and core_running is not None else "fail"
        if guard_running is None or core_running is None:
            refusal_reasons.append("runtime_evidence_stale")
            return SPEC_DECISION_DEFER, {}, 0.0, refusal_reasons, policy_checks, "Guard/core runtime state is unknown."
        if bool(runtime.get("restart_in_progress")) or bool(runtime.get("stop_flag")):
            refusal_reasons.append("runtime_evidence_stale")
            return SPEC_DECISION_DEFER, {}, 0.0, refusal_reasons, policy_checks, "Runtime is stopping or restarting."

        conflicts = self._contract_conflicts(evidence)
        policy_checks["evidence_conflict"] = "pass" if not conflicts else "fail"
        if conflicts:
            refusal_reasons.append("evidence_conflict")
            return SPEC_DECISION_DEFER, {}, 0.0, refusal_reasons + conflicts, policy_checks, "Evidence conflicts require operator review."

        mission_green_hold = self._mission_green_hold_active(_as_dict(evidence.get("mission_snapshot")))
        if not candidates_considered:
            operator_hold_count = _as_int(work_tree.get("operator_hold_count"))
            non_operator_observing = max(0, _as_int(work_tree.get("observing_count")) - operator_hold_count)
            if _as_int(work_tree.get("latent_root_signal_count")) > 0 or non_operator_observing > 0:
                refusal_reasons.append("work_tree_observing_root_truth")
                policy_checks["candidate_available"] = "blocked"
                return (
                    SPEC_DECISION_DEFER,
                    {},
                    0.0,
                    refusal_reasons,
                    policy_checks,
                    "Work Tree has blocked observing root signal(s); closure needs synthesized fix evidence, not a generic maintenance step.",
                )
            if operator_hold_count > 0:
                refusal_reasons.append("operator_hold_pending")
                policy_checks["candidate_available"] = "operator_hold"
                return (
                    SPEC_DECISION_DEFER,
                    {},
                    0.0,
                    refusal_reasons,
                    policy_checks,
                    "Work Tree has operator-held branch(es); no autonomous repair action is available for that hold.",
                )
            if mission_green_hold:
                refusal_reasons.extend(self._mission_hold_refusal_reasons(_as_dict(evidence.get("mission_snapshot"))))
                policy_checks["candidate_available"] = "mission_hold"
                return (
                    SPEC_DECISION_DEFER,
                    {},
                    0.0,
                    refusal_reasons,
                    policy_checks,
                    "Mission steady-state guard: hold without autonomous execution.",
                )
            refusal_reasons.append("no_legal_action")
            policy_checks["candidate_available"] = "fail"
            return SPEC_DECISION_DEFER, {}, 0.0, refusal_reasons, policy_checks, "No governed candidate action was found."
        policy_checks["candidate_available"] = "pass"

        legal_candidates = [
            candidate for candidate in candidates_considered
            if not list(candidate.get("reject_reasons") or [])
        ]
        if not legal_candidates:
            reject_reasons = [
                _safe_text(reason, 120)
                for candidate in candidates_considered
                for reason in list(candidate.get("reject_reasons") or [])
                if _safe_text(reason, 120)
            ]
            unique_reasons = list(dict.fromkeys(reject_reasons))
            if "action_not_allowed" in unique_reasons:
                refusal_reasons.append("action_not_allowed")
                policy_checks["action_allowed"] = "fail"
                return SPEC_DECISION_BLOCK, {}, 0.0, refusal_reasons, policy_checks, "Candidate action is not allowed by policy."
            if "operator_ack_required" in unique_reasons:
                refusal_reasons.append("operator_ack_required")
            elif "cooldown_active" in unique_reasons:
                refusal_reasons.append("cooldown_active")
            else:
                refusal_reasons.append("no_legal_action")
            policy_checks["action_allowed"] = "pass"
            return SPEC_DECISION_DEFER, {}, 0.0, refusal_reasons, policy_checks, "No candidate passed advisory preconditions."

        policy_checks["action_allowed"] = "pass"
        ordered = sorted(
            legal_candidates,
            key=lambda item: (
                -_as_float(item.get("score")),
                _safe_text(_as_dict(item.get("action")).get("action_type"), 120),
            ),
        )
        selected = ordered[0]
        top_score = _as_float(selected.get("score"))
        if len(ordered) > 1 and abs(top_score - _as_float(ordered[1].get("score"))) <= 0.0001:
            refusal_reasons.append("candidate_tie")
            return SPEC_DECISION_DEFER, {}, 0.0, refusal_reasons, policy_checks, "Top candidate scores tied; advisory cycle deferred."
        action = _as_dict(selected.get("action"))
        action_type = _safe_text(action.get("action_type"), 120)
        work_tree_snapshot = _as_dict(evidence.get("work_tree_snapshot"))
        concrete_active_work_tree_step = (
            action_type == "active_work_tree_run_next"
            and _as_int(work_tree_snapshot.get("active_executable_count"), 0) > 0
        )
        if top_score < DEFAULT_RECOMMENDATION_THRESHOLD and not concrete_active_work_tree_step:
            refusal_reasons.append("below_recommendation_threshold")
            policy_checks["recommendation_threshold"] = "fail"
            explain = "No candidate scored above the recommendation threshold."
            if mission_green_hold:
                refusal_reasons.extend(self._mission_hold_refusal_reasons(mission))
                explain = "Mission steady-state guard: hold without autonomous execution."
            return SPEC_DECISION_DEFER, {}, top_score, refusal_reasons, policy_checks, explain
        policy_checks["recommendation_threshold"] = "pass" if top_score >= DEFAULT_RECOMMENDATION_THRESHOLD else "concrete_active_work_tree"

        selected["status"] = "selected"
        return (
            SPEC_DECISION_RECOMMEND_ACTION,
            action,
            top_score,
            [],
            policy_checks,
            _safe_text(action.get("expected_effect"), 360) or "Governed advisory action selected.",
        )

    def _contract_ledger_row(
        self,
        *,
        decision: dict[str, Any],
        candidates_considered: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evidence = _as_dict(decision.get("evidence"))
        posture = _as_dict(evidence.get("steward_posture"))
        queue = _as_dict(evidence.get("queue_pressure"))
        runtime = _as_dict(evidence.get("runtime_guard_status"))
        recommended_action = _as_dict(decision.get("recommended_action"))
        legacy_decision = self._legacy_decision(_safe_text(decision.get("decision_type"), 80))
        legacy_action = self._legacy_action(recommended_action)
        action_summary = (
            {
                "action_type": _safe_text(recommended_action.get("action_type"), 120),
                "target_kind": _safe_text(recommended_action.get("target_kind"), 80),
                "target_id": _safe_text(recommended_action.get("target_id"), 160),
                "target_step_id": _safe_text(recommended_action.get("target_step_id"), 160),
                "reason_code": _safe_text(recommended_action.get("reason_code"), 120),
            }
            if recommended_action
            else {}
        )
        return {
            "cycle_id": _safe_text(decision.get("cycle_id"), 120),
            "timestamp_utc": _safe_text(decision.get("created_at_utc"), 80),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "services.autonomy_orchestrator",
            "mode": _safe_text(decision.get("mode"), 40) or ADVISORY_MODE,
            "decision_type": _safe_text(decision.get("decision_type"), 80),
            "decision": legacy_decision,
            "recommended_action_summary": action_summary,
            "recommended_action": _compact_value(recommended_action),
            "action": legacy_action,
            "confidence": _clamp_float(decision.get("confidence")),
            "posture_band": _safe_text(posture.get("posture_band"), 40),
            "queue_pressure_band": _safe_text(queue.get("pressure_band"), 40),
            "runtime_status_summary": {
                "guard_running": runtime.get("guard_running"),
                "core_running": runtime.get("core_running"),
                "webui_running": runtime.get("webui_running"),
                "restart_in_progress": bool(runtime.get("restart_in_progress", False)),
                "stop_flag": bool(runtime.get("stop_flag", False)),
            },
            "evidence_freshness_summary": _compact_value(evidence.get("source_freshness_sec")),
            "candidates_considered": _compact_value(candidates_considered),
            "candidate_actions": _compact_value(candidates_considered),
            "refusal_reasons": list(decision.get("refusal_reasons") or []),
            "rejection_reasons": list(decision.get("refusal_reasons") or []),
            "policy_checks": _compact_value(decision.get("policy_checks")),
            "explain_text": _safe_text(decision.get("explain_text"), 500),
            "reason": _safe_text(decision.get("explain_text"), 500),
            "evidence": _compact_value(evidence),
            "correlation_ids": _compact_value(_as_dict(evidence.get("correlation_ids"))),
            "mission_snapshot": _compact_value(_as_dict(evidence.get("mission_snapshot"))),
        }

    def evaluate_next_action(
        self,
        input_envelope: dict[str, Any],
        *,
        record_ledger_fn: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        created_at_utc = _utc_now_text()
        cycle_id = _safe_text(_as_dict(input_envelope).get("cycle_id"), 120)
        if not cycle_id:
            cycle_id = f"cycle-{uuid.uuid4().hex[:12]}"
        try:
            envelope = _as_dict(input_envelope)
            evidence = self._contract_evidence(envelope, created_at_utc=created_at_utc)
            candidates = self._contract_candidate_actions(evidence)
            candidates_considered = self._consider_contract_candidates(candidates, evidence)
            decision_type, recommended_action, confidence, refusal_reasons, policy_checks, explain_text = self._contract_decide(
                evidence=evidence,
                candidates_considered=candidates_considered,
            )
            if decision_type not in ALLOWED_SPEC_DECISIONS:
                decision_type = SPEC_DECISION_BLOCK
                recommended_action = {}
                confidence = 0.0
                refusal_reasons = ["invalid_decision_contract"]
                explain_text = "Invalid autonomy decision was blocked by the v0.1 decision contract."

            decision = {
                "cycle_id": cycle_id,
                "decision_type": decision_type,
                "recommended_action": dict(recommended_action) if recommended_action else None,
                "confidence": round(_clamp_float(confidence), 4),
                "evidence": _compact_value(evidence),
                "refusal_reasons": list(refusal_reasons),
                "policy_checks": dict(policy_checks),
                "explain_text": _safe_text(explain_text, 500),
                "created_at_utc": created_at_utc,
                "mode": self._mode,
                "candidates_considered": _compact_value(candidates_considered),
            }
            ledger_row = self._contract_ledger_row(
                decision=decision,
                candidates_considered=candidates_considered,
            )
            ledger_status = "not_requested"
            if record_ledger_fn is not None:
                try:
                    record_ledger_fn(dict(ledger_row))
                    ledger_status = "recorded"
                except Exception as exc:
                    ledger_status = f"record_failed:{exc}"
            decision["ledger"] = {
                "status": ledger_status,
                "row": ledger_row,
            }
            legacy_decision = self._legacy_decision(decision_type)
            decision["decision"] = legacy_decision
            decision["action"] = self._legacy_action(recommended_action)
            decision["reason"] = decision["explain_text"]
            decision["rejection_reasons"] = list(refusal_reasons)
            decision["candidate_actions"] = decision["candidates_considered"]
            self._remember_decision(decision)
            self._last_error = ""
            return decision
        except Exception as exc:
            self._error_count += 1
            self._last_error = str(exc)
            decision = {
                "cycle_id": cycle_id,
                "decision_type": SPEC_DECISION_BLOCK,
                "recommended_action": None,
                "confidence": 0.0,
                "evidence": {},
                "refusal_reasons": ["orchestrator_cycle_failed"],
                "policy_checks": {"decision_contract": "fail"},
                "explain_text": f"Autonomy orchestrator failed: {exc}",
                "created_at_utc": created_at_utc,
                "mode": self._mode,
                "candidates_considered": [],
                "decision": DECISION_BLOCK_WITH_REASON,
                "action": {},
                "reason": f"Autonomy orchestrator failed: {exc}",
                "rejection_reasons": ["orchestrator_cycle_failed"],
            }
            ledger_row = self._contract_ledger_row(decision=decision, candidates_considered=[])
            ledger_status = "not_requested"
            if record_ledger_fn is not None:
                try:
                    record_ledger_fn(dict(ledger_row))
                    ledger_status = "recorded"
                except Exception as ledger_exc:
                    ledger_status = f"record_failed:{ledger_exc}"
            decision["ledger"] = {"status": ledger_status, "row": ledger_row}
            self._remember_decision(decision)
            return decision

    @staticmethod
    def _runtime_ok(section: dict[str, Any]) -> bool | None:
        if not section:
            return None
        if "ok" in section:
            return bool(section.get("ok"))
        status = str(section.get("status") or section.get("state") or "").strip().lower()
        if status in {"ok", "ready", "healthy", "running", "active"}:
            return True
        if status in {"failed", "error", "degraded", "stopped", "missing", "inactive"}:
            return False
        return None

    @staticmethod
    def _guard_state(guard_health: dict[str, Any]) -> dict[str, Any]:
        guard = _as_dict(guard_health)
        if not guard:
            return {"state": "unknown", "ok": None, "info": "guard health unavailable"}
        status = str(guard.get("status") or guard.get("state") or "").strip().lower()
        ok_value = guard.get("ok") if "ok" in guard else None
        running = guard.get("running") if "running" in guard else None
        if ok_value is True or running is True or status in {"ok", "ready", "healthy", "running", "active"}:
            state = "running"
            ok = True
        elif status in {"stopped", "inactive", "not_running"} or running is False:
            state = "stopped"
            ok = False
        elif ok_value is False or status in {"failed", "error", "degraded"}:
            state = "degraded"
            ok = False
        else:
            state = status or "unknown"
            ok = None
        return {
            "state": state,
            "ok": ok,
            "info": _safe_text(guard.get("info") or guard.get("detail") or status or state),
        }

    @staticmethod
    def _queue_summary(queue_pressure: dict[str, Any]) -> dict[str, Any]:
        queue = _as_dict(queue_pressure)
        next_item = _as_dict(queue.get("next_item"))
        return {
            "status": _safe_text(queue.get("status")).lower(),
            "count": _as_int(queue.get("count")),
            "open_count": _as_int(queue.get("open_count")),
            "actionable_count": _as_int(queue.get("actionable_count")),
            "blocked_count": _as_int(queue.get("blocked_count")),
            "drift_count": _as_int(queue.get("drift_count")),
            "warning_count": _as_int(queue.get("warning_count")),
            "never_run_count": _as_int(queue.get("never_run_count")),
            "next_item": _compact_value(next_item),
        }

    @staticmethod
    def _work_tree_summary(work_tree_state: dict[str, Any]) -> dict[str, Any]:
        work_tree = _as_dict(work_tree_state)
        counts = _as_dict(work_tree.get("counts"))
        trees: list[dict[str, Any]] = []
        for item in _as_list(work_tree.get("trees"))[:32]:
            tree = _as_dict(item)
            if not tree:
                continue
            tree_counts = _as_dict(tree.get("counts"))
            trees.append(
                {
                    "tree_id": _safe_text(tree.get("tree_id"), 80),
                    "kind": _safe_text(tree.get("kind"), 80).lower(),
                    "status": _safe_text(tree.get("status"), 80).lower(),
                    "title": _safe_text(tree.get("title"), 160),
                    "active_branch_id": _safe_text(tree.get("active_branch_id"), 80),
                    "counts": _compact_value(tree_counts),
                }
            )
        return {
            "ok": bool(work_tree.get("ok", True)),
            "status": _safe_text(work_tree.get("status")).lower(),
            "counts": {
                "total": _as_int(counts.get("total")),
                "active": _as_int(counts.get("active")),
                "branches": _as_int(counts.get("branches")),
                "open_tasks": _as_int(counts.get("open_tasks")),
                "working": _as_int(counts.get("working")),
                "pending": _as_int(counts.get("pending")),
                "blocked": _as_int(counts.get("blocked")),
                "complete": _as_int(counts.get("complete")),
            },
            "trees": trees,
        }

    @staticmethod
    def _ownership_summary(ownership_hints: Any, queue_pressure: dict[str, Any]) -> dict[str, Any]:
        hints = _as_list(ownership_hints)
        queue = _as_dict(queue_pressure)
        next_item = _as_dict(queue.get("next_item"))
        payload = _as_dict(next_item.get("payload"))
        if payload:
            preferred_owner = _safe_text(payload.get("preferred_owner"))
            route_hint = _safe_text(payload.get("route_hint"))
            review_contract = _safe_text(payload.get("review_contract"))
            if preferred_owner or route_hint or review_contract:
                return {
                    "source": "generated_queue.next_item",
                    "preferred_owner": preferred_owner,
                    "route_hint": route_hint,
                    "review_contract": review_contract,
                }
        for item in hints:
            hint = _as_dict(item)
            if not hint:
                continue
            return {
                "source": _safe_text(hint.get("source") or "ownership_hints"),
                "preferred_owner": _safe_text(hint.get("preferred_owner")),
                "route_hint": _safe_text(hint.get("route_hint")),
                "review_contract": _safe_text(hint.get("review_contract")),
            }
        return {}

AUTONOMY_ORCHESTRATOR_SERVICE = AutonomyOrchestratorService()
