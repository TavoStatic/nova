from __future__ import annotations

from typing import Any

OPERATOR_HOLD_BLOCKED_REASONS = frozenset(
    {
        "restart_provenance_operator_attribution_required",
        "source_root_sequence_exhausted_gap_persists",
        "source_root_failed_evidence_operator_judgment_required",
        "operator_response_required",
        "memory_bootstrap_origin_confirmation_pending",
    }
)

OPERATOR_HOLD_TASK_TITLES = frozenset(
    {
        "Hold source-root branch for operator judgment",
        "Wait for operator response or authority assignment on the open outbox item",
    }
)


def _as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def node_is_operator_hold(node: dict[str, Any] | None) -> bool:
    payload = _as_dict(node)
    status_text = _text(payload.get("status"), 80).lower()
    if status_text != "blocked":
        return False

    source_type = _text(payload.get("source_type"), 120).lower()
    work_class = _text(payload.get("work_class"), 120).lower()
    source_payload = _as_dict(payload.get("source_payload"))
    memory_origin = _as_dict(source_payload.get("memory_bootstrap_origin"))
    memory_bootstrap = _as_dict(source_payload.get("memory_bootstrap"))
    if (
        source_type == "memory_health"
        and work_class == "governance_pressure"
        and _text(memory_origin.get("status") or memory_bootstrap.get("origin_status"), 80).lower()
        == "pending_operator_confirmation"
    ):
        return True

    current_task = _as_dict(payload.get("current_task"))
    task_title = _text(current_task.get("title"), 240)
    task_status = _text(current_task.get("status"), 40).lower()
    task_meta = _as_dict(current_task.get("meta"))
    blocked_reason = _text(
        task_meta.get("blocked_reason") or task_meta.get("block_reason"),
        160,
    ).lower()
    if task_status == "blocked" and blocked_reason in OPERATOR_HOLD_BLOCKED_REASONS:
        return True
    if task_title in OPERATOR_HOLD_TASK_TITLES and task_status == "blocked":
        return True

    if (
        source_type == "operator_control"
        and work_class in {"governance_pressure", "operator_requested"}
        and _text(payload.get("actionability"), 40).lower() == "blocked"
    ):
        return True

    return False