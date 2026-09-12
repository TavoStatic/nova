from __future__ import annotations

import re
import time
from typing import Any

KEY_FINDING = "recurring_finding_key"
KEY_VERSION = "recurring_finding_version"
KEY_SATISFACTION_STATUS = "recurring_finding_satisfaction_status"
KEY_SATISFACTION_FINGERPRINT = "recurring_finding_satisfaction_fingerprint"
KEY_SATISFIED_AT = "recurring_finding_satisfied_at"
KEY_COMPLETION_ACTION = "recurring_finding_completion_action"
KEY_REOPENED_AT = "recurring_finding_reopened_at"
KEY_REOPENED_REASON = "recurring_finding_reopened_reason"
KEY_PRIOR_SATISFACTION_FINGERPRINT = "recurring_finding_prior_satisfaction_fingerprint"
KEY_PRIOR_SATISFACTION_STATUS = "recurring_finding_prior_satisfaction_status"
KEY_PRIOR_COMPLETION_ACTION = "recurring_finding_prior_completion_action"

BRANCH_LIFECYCLE_KEY = "recurring_finding_lifecycle"

STATUS_OPEN = "open"
STATUS_SATISFIED = "satisfied"

PRODUCTIVE_CLOSURE_ACTIONS = frozenset(
    {
        "removed_unused_wrapper",
    }
)

# Witness actions close the mapping stage only. They do not close wrapper
# pressure and they do not count as extraction.
MAPPING_CLOSURE_ACTIONS = frozenset(
    {
        "witnessed_http_extraction_boundary",
        "mapped_http_extraction_boundary",
    }
)
# Legacy name kept for imports/tests that still say "witness".
WITNESS_CLOSURE_ACTIONS = MAPPING_CLOSURE_ACTIONS
# Extract is a separate stage. These close that stage without claiming the
# HTTP surface was moved. Do not reopen while extraction is unimplemented.
EXTRACT_STAGE_CLOSURE_ACTIONS = frozenset(
    {
        "blocked_http_extraction",
        "operator_do_not_retry",
    }
)

REOPEN_RECURRING_PRESSURE = "recurring_pressure"
REOPEN_ACTIVE_SIGNAL = "active_signal_recurrence"
REOPEN_QUEUE_PRESSURE = "queue_pressure_recurrence"
REOPEN_SEQUENCE_RESTART = "sequence_restart_recurrence"

DECISION_SKIP = "skip"
DECISION_REOPEN = "reopen"
DECISION_SATISFIED = "satisfied"
DECISION_ACTIVE = "active"
DECISION_ACTIVE_UPDATE = "active_update"
DECISION_INACTIVE_RESOLVE = "inactive_resolve"

_LEGACY_ALIASES: dict[str, str] = {
    "core_thinning_order_id": KEY_FINDING,
    "core_thinning_order_version": KEY_VERSION,
    "core_thinning_satisfaction_status": KEY_SATISFACTION_STATUS,
    "core_thinning_satisfaction_key": KEY_SATISFACTION_FINGERPRINT,
    "core_thinning_satisfied_at": KEY_SATISFIED_AT,
    "core_thinning_completion_action": KEY_COMPLETION_ACTION,
    "core_thinning_reopened_at": KEY_REOPENED_AT,
    "core_thinning_reopened_reason": KEY_REOPENED_REASON,
    "core_thinning_prior_satisfaction_key": KEY_PRIOR_SATISFACTION_FINGERPRINT,
    "core_thinning_prior_satisfaction_status": KEY_PRIOR_SATISFACTION_STATUS,
    "core_thinning_prior_completion_action": KEY_PRIOR_COMPLETION_ACTION,
}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text[:120] or "finding"


def fingerprint_from_parts(parts: list[str]) -> str:
    normalized = [_text(part, 160).lower() for part in parts if _text(part, 160)]
    return _slug("|".join(normalized))


def read_task_state(meta: dict[str, Any] | None) -> dict[str, Any]:
    payload = _as_dict(meta)
    state: dict[str, Any] = {}
    for key in (
        KEY_FINDING,
        KEY_VERSION,
        KEY_SATISFACTION_STATUS,
        KEY_SATISFACTION_FINGERPRINT,
        KEY_SATISFIED_AT,
        KEY_COMPLETION_ACTION,
        KEY_REOPENED_AT,
        KEY_REOPENED_REASON,
        KEY_PRIOR_SATISFACTION_FINGERPRINT,
        KEY_PRIOR_SATISFACTION_STATUS,
        KEY_PRIOR_COMPLETION_ACTION,
    ):
        if key in payload:
            state[key] = payload.get(key)
    for legacy_key, canonical_key in _LEGACY_ALIASES.items():
        if canonical_key not in state and legacy_key in payload:
            state[canonical_key] = payload.get(legacy_key)
    try:
        state[KEY_VERSION] = max(0, int(state.get(KEY_VERSION, 0) or 0))
    except Exception:
        state[KEY_VERSION] = 0
    return state


def finding_key_from_meta(meta: dict[str, Any] | None) -> str:
    return _text(read_task_state(meta).get(KEY_FINDING), 160)


def finding_version(meta: dict[str, Any] | None) -> int:
    return int(read_task_state(meta).get(KEY_VERSION, 0) or 0)


def task_finding_key(*, branch_finding_key: str, task_title: str) -> str:
    branch_key = _text(branch_finding_key, 120)
    title = _text(task_title, 120)
    if branch_key and title:
        return f"{branch_key}:{title}"
    return branch_key or title


def task_fingerprint(*, task_title: str, preferred_tool: str = "", extra_parts: list[str] | None = None) -> str:
    parts = [_text(task_title, 160)]
    if preferred_tool:
        parts.append(_text(preferred_tool, 80))
    parts.extend(_text(part, 120) for part in list(extra_parts or []) if _text(part, 120))
    return fingerprint_from_parts(parts)


def initial_task_meta(
    *,
    finding_key: str,
    satisfaction_fingerprint: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = {
        KEY_FINDING: _text(finding_key, 160),
        KEY_VERSION: 1,
        KEY_SATISFACTION_STATUS: STATUS_OPEN,
        KEY_SATISFACTION_FINGERPRINT: _text(satisfaction_fingerprint, 160),
    }
    if isinstance(extra, dict):
        meta.update(extra)
    return meta


def stamp_satisfaction(
    meta: dict[str, Any] | None,
    *,
    satisfaction_fingerprint: str,
    completion_action: str = "",
    ok: bool = True,
) -> dict[str, Any]:
    payload = dict(meta or {})
    if not ok:
        return payload
    payload[KEY_SATISFACTION_STATUS] = STATUS_SATISFIED
    payload[KEY_SATISFACTION_FINGERPRINT] = _text(satisfaction_fingerprint, 160)
    payload[KEY_COMPLETION_ACTION] = _text(completion_action, 120)
    payload[KEY_SATISFIED_AT] = time.strftime("%Y-%m-%d %H:%M:%S")
    return payload


def reopen_task_meta(
    prior_meta: dict[str, Any] | None,
    *,
    finding_key: str,
    satisfaction_fingerprint: str,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prior = read_task_state(prior_meta)
    next_version = int(prior.get(KEY_VERSION, 0) or 0) + 1
    meta = {
        KEY_FINDING: _text(finding_key or prior.get(KEY_FINDING), 160),
        KEY_VERSION: next_version,
        KEY_SATISFACTION_STATUS: STATUS_OPEN,
        KEY_SATISFACTION_FINGERPRINT: _text(satisfaction_fingerprint, 160),
        KEY_REOPENED_AT: time.strftime("%Y-%m-%d %H:%M:%S"),
        KEY_REOPENED_REASON: _text(reason or REOPEN_RECURRING_PRESSURE, 120),
        KEY_PRIOR_SATISFACTION_FINGERPRINT: _text(prior.get(KEY_SATISFACTION_FINGERPRINT), 160),
        KEY_PRIOR_SATISFACTION_STATUS: _text(prior.get(KEY_SATISFACTION_STATUS), 80),
        KEY_PRIOR_COMPLETION_ACTION: _text(prior.get(KEY_COMPLETION_ACTION), 120),
    }
    if isinstance(extra, dict):
        meta.update(extra)
    return meta


def classify_existing_item(
    *,
    item_status: str,
    finding_key: str,
    active_finding_keys: set[str],
    current_fingerprint: str = "",
) -> str:
    key = _text(finding_key, 160)
    status = _text(item_status, 40).lower()
    if not key:
        return DECISION_SKIP
    if status == "dropped":
        return DECISION_SKIP
    if status == "complete":
        if key in active_finding_keys:
            return DECISION_REOPEN
        return DECISION_SATISFIED
    if key in active_finding_keys:
        return DECISION_ACTIVE
    return DECISION_INACTIVE_RESOLVE


def task_has_mapping_closure(meta: dict[str, Any] | None) -> bool:
    state = read_task_state(meta)
    if _text(state.get(KEY_SATISFACTION_STATUS), 40).lower() != STATUS_SATISFIED:
        return False
    return _text(state.get(KEY_COMPLETION_ACTION), 120).lower() in MAPPING_CLOSURE_ACTIONS


def task_is_http_extract(meta: dict[str, Any] | None) -> bool:
    return _text(_as_dict(meta).get("kind"), 80).lower() == "http_surface_extract"


def task_has_extract_stage_closure(meta: dict[str, Any] | None) -> bool:
    if not task_is_http_extract(meta):
        return False
    state = read_task_state(meta)
    action = _text(state.get(KEY_COMPLETION_ACTION), 120).lower()
    if action in EXTRACT_STAGE_CLOSURE_ACTIONS:
        return True
    # Extraction is not implemented. A completed extract stage is terminal
    # until a real extractor exists — cluster persistence is not a retry signal.
    return _text(state.get(KEY_SATISFACTION_STATUS), 40).lower() == STATUS_SATISFIED


def task_has_productive_closure(
    meta: dict[str, Any] | None,
    *,
    current_fingerprint: str = "",
    finding_still_active: bool = False,
) -> bool:
    state = read_task_state(meta)
    if _text(state.get(KEY_SATISFACTION_STATUS), 40).lower() != STATUS_SATISFIED:
        return False
    completion_action = _text(state.get(KEY_COMPLETION_ACTION), 120).lower()
    if completion_action not in PRODUCTIVE_CLOSURE_ACTIONS:
        return False
    # Current source still reports this wrapper — historical removal is not satisfaction.
    if finding_still_active and completion_action == "removed_unused_wrapper":
        return False
    prior_fp = _text(state.get(KEY_SATISFACTION_FINGERPRINT), 160)
    next_fp = _text(current_fingerprint, 160)
    return not next_fp or prior_fp == next_fp


def classify_task_meta(
    *,
    meta: dict[str, Any] | None,
    item_status: str,
    active_finding_keys: set[str],
    current_fingerprint: str = "",
) -> str:
    state = read_task_state(meta)
    key = _text(state.get(KEY_FINDING), 160)
    decision = classify_existing_item(
        item_status=item_status,
        finding_key=key,
        active_finding_keys=active_finding_keys,
        current_fingerprint=current_fingerprint,
    )
    if decision == DECISION_REOPEN and task_has_mapping_closure(meta):
        return DECISION_SATISFIED
    if decision == DECISION_REOPEN and task_has_extract_stage_closure(meta):
        return DECISION_SATISFIED
    if decision == DECISION_REOPEN and task_has_productive_closure(
        meta,
        current_fingerprint=current_fingerprint,
        finding_still_active=key in active_finding_keys,
    ):
        return DECISION_SATISFIED
    if decision != DECISION_ACTIVE or not current_fingerprint:
        return decision
    prior_fp = _text(state.get(KEY_SATISFACTION_FINGERPRINT), 160)
    if prior_fp and prior_fp != _text(current_fingerprint, 160):
        return DECISION_ACTIVE_UPDATE
    return DECISION_ACTIVE


def update_open_fingerprint(
    meta: dict[str, Any] | None,
    *,
    satisfaction_fingerprint: str,
) -> dict[str, Any]:
    payload = dict(meta or {})
    prior_fp = _text(read_task_state(payload).get(KEY_SATISFACTION_FINGERPRINT), 160)
    next_fp = _text(satisfaction_fingerprint, 160)
    if not next_fp or prior_fp == next_fp:
        return payload
    payload[KEY_SATISFACTION_FINGERPRINT] = next_fp
    payload[KEY_SATISFACTION_STATUS] = STATUS_OPEN
    payload[KEY_PRIOR_SATISFACTION_FINGERPRINT] = prior_fp
    try:
        payload[KEY_VERSION] = max(1, int(payload.get(KEY_VERSION, 1) or 1))
    except Exception:
        payload[KEY_VERSION] = 1
    return payload


def summarize_feed_pressure(
    *,
    pressure_count: int,
    feed_result: dict[str, Any] | None,
) -> dict[str, Any]:
    feed = dict(feed_result or {})
    executable = int(feed.get("executable_count", 0) or 0)
    reopened = int(feed.get("reopened_count", 0) or 0)
    satisfied = int(feed.get("satisfied_count", 0) or 0)
    satisfied_active = int(feed.get("satisfied_active_count", satisfied) or 0)
    resolved = int(feed.get("resolved_count", 0) or 0)
    added = int(feed.get("added_count", 0) or 0)
    deduped = int(feed.get("deduped_count", 0) or 0)
    pressure = max(0, int(pressure_count or 0))
    unresolved_pressure = max(0, pressure - satisfied_active)
    pressure_backed_by_executable = unresolved_pressure <= 0 or executable > 0
    lifecycle_gap = ""
    if unresolved_pressure > 0 and executable <= 0:
        lifecycle_gap = "pressure_without_executable_work"
    return {
        "pressure_count": pressure,
        "unresolved_pressure_count": unresolved_pressure,
        "executable_count": executable,
        "reopened_count": reopened,
        "satisfied_count": satisfied,
        "satisfied_active_count": satisfied_active,
        "resolved_count": resolved,
        "added_count": added,
        "deduped_count": deduped,
        "pressure_backed_by_executable": pressure_backed_by_executable,
        "lifecycle_gap": lifecycle_gap,
        "feed_status": _text(feed.get("status"), 80),
    }


def stamp_branch_satisfied(
    source_payload: dict[str, Any] | None,
    *,
    completion_action: str = "",
) -> dict[str, Any]:
    payload = dict(source_payload or {})
    lifecycle = read_branch_lifecycle(payload)
    lifecycle[KEY_SATISFACTION_STATUS] = STATUS_SATISFIED
    lifecycle[KEY_SATISFIED_AT] = time.strftime("%Y-%m-%d %H:%M:%S")
    if completion_action:
        lifecycle[KEY_COMPLETION_ACTION] = _text(completion_action, 120)
    payload[BRANCH_LIFECYCLE_KEY] = lifecycle
    return payload


def read_branch_lifecycle(source_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = _as_dict(source_payload)
    lifecycle = _as_dict(payload.get(BRANCH_LIFECYCLE_KEY))
    if not lifecycle:
        return {}
    try:
        lifecycle[KEY_VERSION] = max(0, int(lifecycle.get(KEY_VERSION, 0) or 0))
    except Exception:
        lifecycle[KEY_VERSION] = 0
    return lifecycle


def attach_branch_lifecycle(source_payload: dict[str, Any] | None, lifecycle: dict[str, Any]) -> dict[str, Any]:
    payload = dict(source_payload or {})
    payload[BRANCH_LIFECYCLE_KEY] = dict(lifecycle or {})
    return payload


def bump_branch_reopen(
    source_payload: dict[str, Any] | None,
    *,
    finding_key: str,
    reason: str,
    satisfaction_fingerprint: str = "",
) -> dict[str, Any]:
    payload = dict(source_payload or {})
    lifecycle = read_branch_lifecycle(payload)
    prior = dict(lifecycle)
    if not prior and finding_key:
        prior[KEY_FINDING] = _text(finding_key, 160)
    next_version = int(prior.get(KEY_VERSION, 0) or 0) + 1
    lifecycle.update(
        {
            KEY_FINDING: _text(finding_key or prior.get(KEY_FINDING) or payload.get("source_key"), 160),
            KEY_VERSION: next_version,
            KEY_SATISFACTION_STATUS: STATUS_OPEN,
            KEY_REOPENED_AT: time.strftime("%Y-%m-%d %H:%M:%S"),
            KEY_REOPENED_REASON: _text(reason or REOPEN_ACTIVE_SIGNAL, 120),
        }
    )
    if satisfaction_fingerprint:
        lifecycle[KEY_SATISFACTION_FINGERPRINT] = _text(satisfaction_fingerprint, 160)
    if prior.get(KEY_SATISFACTION_FINGERPRINT):
        lifecycle[KEY_PRIOR_SATISFACTION_FINGERPRINT] = _text(prior.get(KEY_SATISFACTION_FINGERPRINT), 160)
    if prior.get(KEY_SATISFACTION_STATUS):
        lifecycle[KEY_PRIOR_SATISFACTION_STATUS] = _text(prior.get(KEY_SATISFACTION_STATUS), 80)
    if prior.get(KEY_COMPLETION_ACTION):
        lifecycle[KEY_PRIOR_COMPLETION_ACTION] = _text(prior.get(KEY_COMPLETION_ACTION), 120)
    payload[BRANCH_LIFECYCLE_KEY] = lifecycle
    return payload


def initial_branch_lifecycle(
    source_payload: dict[str, Any] | None,
    *,
    finding_key: str,
    satisfaction_fingerprint: str = "",
) -> dict[str, Any]:
    payload = dict(source_payload or {})
    payload[BRANCH_LIFECYCLE_KEY] = {
        KEY_FINDING: _text(finding_key, 160),
        KEY_VERSION: 1,
        KEY_SATISFACTION_STATUS: STATUS_OPEN,
        KEY_SATISFACTION_FINGERPRINT: _text(satisfaction_fingerprint, 160),
    }
    return payload