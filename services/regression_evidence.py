from __future__ import annotations

import time
from typing import Any


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def regression_outcome_label(status_label: str) -> str:
    return _text(status_label, 80).upper()


def regression_outcome_failed(status_label: str) -> bool:
    label = regression_outcome_label(status_label).lower()
    if not label:
        return False
    return label != "ok" and "pass" not in label


def regression_outcome_passed(status_label: str) -> bool:
    label = regression_outcome_label(status_label).lower()
    return bool(label) and (label == "ok" or "pass" in label)


def regression_evidence_stale(
    *,
    status_label: str,
    regression_date: str,
    today: str | None = None,
) -> bool:
    """Evidence is stale only when a failed outcome is from a prior calendar day."""
    if not regression_outcome_failed(status_label):
        return False
    observed_date = _text(regression_date, 16)
    current_date = _text(today or time.strftime("%Y-%m-%d"), 16)
    if not observed_date or not current_date:
        return False
    return observed_date < current_date


def regression_failure_is_lock_contention(
    *,
    status_label: str = "",
    failed_tests: list[Any] | None = None,
    failed_lane: str = "",
    tail: str = "",
    detail: str = "",
) -> bool:
    """False FAILED from 'regression already running' is not a real test failure.

    Treating lock contention as regression_failed freezes mission hold forever
    while Work Tree still has climbable work (Nova appears 'stuck').
    """
    if not regression_outcome_failed(status_label):
        return False
    tests = [
        _text(item, 240)
        for item in list(failed_tests or [])
        if _text(item, 240)
    ]
    if tests or _text(failed_lane, 80):
        return False
    blob = f"{_text(tail, 500)} {_text(detail, 500)}".lower()
    return "already running" in blob


def regression_failure_active(
    *,
    status_label: str,
    stale: bool,
    failed_tests: list[Any] | None = None,
    failed_lane: str = "",
    tail: str = "",
) -> bool:
    if not regression_outcome_failed(status_label) or bool(stale):
        return False
    if regression_failure_is_lock_contention(
        status_label=status_label,
        failed_tests=failed_tests,
        failed_lane=failed_lane,
        tail=tail,
    ):
        return False
    return True


def regression_tail_from_payload(payload: dict[str, Any]) -> str:
    detail = _text(payload.get("detail"), 500)
    failed_lane = _text(payload.get("failed_lane"), 80)
    failed_tests = [
        _text(item, 240)
        for item in list(payload.get("failed_tests") or [])
        if _text(item, 240)
    ]
    parts: list[str] = []
    if detail:
        parts.append(detail)
    if failed_lane:
        parts.append(f"lane={failed_lane}")
    if failed_tests:
        parts.append("failed_tests=" + "; ".join(failed_tests[:12]))
    if parts:
        return " | ".join(parts)
    source = _text(payload.get("source"), 120) or "regression_status"
    status = regression_outcome_label(str(payload.get("status") or ""))
    return f"{source} reported {status or 'UNKNOWN'}."


def apply_regression_status_payload(state: dict[str, Any], payload: dict[str, Any]) -> None:
    generated_at = _text(payload.get("generated_at"), 40)
    status = regression_outcome_label(str(payload.get("status") or ""))
    if not generated_at or not status:
        return

    state["last_regression_date"] = _text(payload.get("date") or generated_at[:10] or time.strftime("%Y-%m-%d"), 16)
    state["last_regression_at"] = generated_at
    state["last_regression_status"] = status
    state["last_regression_returncode"] = int(payload.get("returncode", 0) or 0)
    state["last_regression_source"] = _text(payload.get("source"), 160) or "regression_status.json"
    state["last_regression_lanes"] = list(payload.get("lanes") or []) if isinstance(payload.get("lanes"), list) else []
    state["last_regression_failed_lane"] = _text(payload.get("failed_lane"), 80)
    failed_tests = [
        _text(item, 240)
        for item in list(payload.get("failed_tests") or [])
        if _text(item, 240)
    ]
    state["last_regression_failed_tests"] = failed_tests[:24]
    state["last_regression_tail"] = regression_tail_from_payload(payload)
    state["last_regression_stale"] = regression_evidence_stale(
        status_label=status,
        regression_date=str(state.get("last_regression_date") or ""),
    )