from __future__ import annotations

from typing import Any

from services.autonomy_orchestrator import SPEC_DECISION_RECOMMEND_ACTION
from services.nova_control_action_dispatcher import is_autonomy_advisory_action


EXECUTION_MODE_ADVISORY = "advisory"
EXECUTION_MODE_CANARY = "canary"
EXECUTION_MODE_EXECUTE = "execute"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    return text[: max(1, int(limit or 160))]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _action_set(value: Any) -> set[str]:
    return {_safe_text(item, 120) for item in _as_list(value) if _safe_text(item, 120)}


class AutonomyExecutionGateService:
    """Authorize one orchestrator recommendation for governed runtime dispatch."""

    @staticmethod
    def _policy_mode(policy_snapshot: dict[str, Any]) -> str:
        mode = _safe_text(policy_snapshot.get("mode") or policy_snapshot.get("execution_mode"), 40).lower()
        if mode in {EXECUTION_MODE_CANARY, EXECUTION_MODE_EXECUTE}:
            return mode
        return EXECUTION_MODE_ADVISORY

    @staticmethod
    def _execute_enabled(policy_snapshot: dict[str, Any]) -> bool:
        return bool(
            policy_snapshot.get("execute_enabled")
            or policy_snapshot.get("execution_enabled")
            or policy_snapshot.get("autonomy_execute_enabled")
        )

    @staticmethod
    def _execute_allowed_actions(policy_snapshot: dict[str, Any], mode: str) -> set[str]:
        configured = _action_set(policy_snapshot.get("execute_allowed_actions"))
        if not configured and mode == EXECUTION_MODE_CANARY:
            configured = _action_set(policy_snapshot.get("canary_allowed_actions"))
        if "*" in configured:
            return {"*"}
        return configured

    def evaluate(
        self,
        decision_packet: dict[str, Any],
        policy_snapshot: dict[str, Any],
        *,
        last_execution_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        packet = _as_dict(decision_packet)
        policy = _as_dict(policy_snapshot)
        last_execution = _as_dict(last_execution_context)
        mode = self._policy_mode(policy)
        checks: dict[str, str] = {}
        refusal_reasons: list[str] = []

        if mode not in {EXECUTION_MODE_CANARY, EXECUTION_MODE_EXECUTE}:
            checks["mode_allows_execution"] = "fail"
            refusal_reasons.append("execution_mode_advisory")
            return self._result(False, "deferred", mode, checks, refusal_reasons, "Execution mode is advisory.")
        checks["mode_allows_execution"] = "pass"

        if not self._execute_enabled(policy):
            checks["execute_enabled"] = "fail"
            refusal_reasons.append("execution_disabled")
            return self._result(False, "blocked", mode, checks, refusal_reasons, "Autonomy execution is disabled by policy.")
        checks["execute_enabled"] = "pass"

        if packet.get("decision_type") != SPEC_DECISION_RECOMMEND_ACTION:
            checks["decision_recommends_action"] = "fail"
            refusal_reasons.append("decision_not_recommend_action")
            return self._result(False, "deferred", mode, checks, refusal_reasons, "No recommended action is available to execute.")
        checks["decision_recommends_action"] = "pass"

        packet_refusals = [_safe_text(item, 120) for item in _as_list(packet.get("refusal_reasons")) if _safe_text(item, 120)]
        if packet_refusals:
            checks["decision_refusal_reasons_clear"] = "fail"
            refusal_reasons.extend(["decision_has_refusal_reasons", *packet_refusals])
            return self._result(False, "blocked", mode, checks, refusal_reasons, "Decision still carries refusal reasons.")
        checks["decision_refusal_reasons_clear"] = "pass"

        action = _as_dict(packet.get("recommended_action"))
        action_type = _safe_text(action.get("action_type"), 120)
        target_id = _safe_text(action.get("target_id"), 160)
        if not action_type or not is_autonomy_advisory_action(action_type):
            checks["dispatcher_catalog_action"] = "fail"
            refusal_reasons.append("action_not_dispatcher_owned")
            return self._result(False, "blocked", mode, checks, refusal_reasons, "Recommended action is not dispatcher-owned.")
        checks["dispatcher_catalog_action"] = "pass"

        allowed_actions = self._execute_allowed_actions(policy, mode)
        if "*" not in allowed_actions and action_type not in allowed_actions:
            checks["execute_action_allowed"] = "fail"
            refusal_reasons.append("action_not_execute_allowed")
            return self._result(False, "blocked", mode, checks, refusal_reasons, "Recommended action is not enabled for execution.")
        blocked_actions = _action_set(policy.get("execute_blocked_actions")) | _action_set(policy.get("blocked_actions"))
        if action_type in blocked_actions or "*" in blocked_actions:
            checks["execute_action_allowed"] = "fail"
            refusal_reasons.append("action_execute_blocked")
            return self._result(False, "blocked", mode, checks, refusal_reasons, "Recommended action is blocked by policy.")
        checks["execute_action_allowed"] = "pass"

        confidence = _as_float(packet.get("confidence"), 0.0)
        threshold = _as_float(policy.get("execute_min_confidence") or policy.get("confidence_threshold"), 0.55)
        if confidence < threshold:
            checks["confidence_threshold"] = "fail"
            refusal_reasons.append("confidence_below_execute_threshold")
            return self._result(False, "deferred", mode, checks, refusal_reasons, "Recommendation confidence is below execution threshold.")
        checks["confidence_threshold"] = "pass"

        ack_required = bool(action.get("requires_ack", False))
        ack_required_for = _action_set(policy.get("requires_operator_ack_for"))
        if action_type in ack_required_for or "*" in ack_required_for:
            ack_required = True
        operator_ack_present = bool(policy.get("operator_ack_present") or last_execution.get("operator_ack_present"))
        if ack_required and not operator_ack_present:
            checks["operator_ack"] = "fail"
            refusal_reasons.append("operator_ack_required")
            return self._result(False, "deferred", mode, checks, refusal_reasons, "Operator acknowledgement is required before execution.")
        checks["operator_ack"] = "pass"

        cooldown_active = bool(last_execution.get("cooldown_active", False))
        last_action_type = _safe_text(last_execution.get("last_action_type"), 120)
        last_target_id = _safe_text(last_execution.get("last_target_id"), 160)
        if cooldown_active and (not last_action_type or last_action_type == action_type) and (not last_target_id or last_target_id == target_id):
            checks["cooldown"] = "fail"
            refusal_reasons.append("cooldown_active")
            return self._result(False, "deferred", mode, checks, refusal_reasons, "Cooldown is still active for this action.")
        checks["cooldown"] = "pass"

        payload = {
            "action": action_type,
            "_source": "autonomy_orchestrator",
            "cycle_id": _safe_text(packet.get("cycle_id"), 120),
            "target_kind": _safe_text(action.get("target_kind"), 80),
            "target_id": target_id,
            "reason_code": _safe_text(action.get("reason_code"), 120),
        }
        return {
            "allow_execute": True,
            "status": "allowed",
            "mode": mode,
            "reason": "execution_allowed",
            "refusal_reasons": [],
            "policy_checks": checks,
            "action_type": action_type,
            "target_id": target_id,
            "dispatch_payload": payload,
            "confidence": confidence,
            "cooldown_sec": int(_as_float(action.get("cooldown_sec"), _as_float(policy.get("cooldown_sec"), 180))),
            "explain_text": "Recommendation passed autonomy execution gate.",
        }

    @staticmethod
    def _result(
        allow_execute: bool,
        status: str,
        mode: str,
        checks: dict[str, str],
        refusal_reasons: list[str],
        explain_text: str,
    ) -> dict[str, Any]:
        return {
            "allow_execute": bool(allow_execute),
            "status": status,
            "mode": mode,
            "reason": refusal_reasons[0] if refusal_reasons else "",
            "refusal_reasons": list(dict.fromkeys(refusal_reasons)),
            "policy_checks": dict(checks),
            "action_type": "",
            "target_id": "",
            "dispatch_payload": {},
            "confidence": 0.0,
            "cooldown_sec": 0,
            "explain_text": explain_text,
        }


AUTONOMY_EXECUTION_GATE_SERVICE = AutonomyExecutionGateService()
