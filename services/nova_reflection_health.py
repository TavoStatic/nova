from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional


def detect_repeated_tool_intent_without_execution(
    *,
    records: Optional[list[dict]] = None,
    limit: int = 20,
    recent_action_ledger_records_fn: Callable[[int], list[dict]],
    tool_intent_labels: dict[str, str],
    record_requested_tool_clarification_fn: Callable[[dict], bool],
    record_completed_tool_execution_fn: Callable[[dict], bool],
) -> dict:
    recent = records if isinstance(records, list) else recent_action_ledger_records_fn(limit)
    counts: dict[str, dict[str, int]] = {}
    for rec in recent:
        if not isinstance(rec, dict):
            continue
        intent = str(rec.get("intent") or "").strip()
        if intent not in tool_intent_labels:
            continue
        if record_requested_tool_clarification_fn(rec):
            continue
        bucket = counts.setdefault(intent, {"selected": 0, "completed": 0})
        bucket["selected"] += 1
        if record_completed_tool_execution_fn(rec):
            bucket["completed"] += 1

    best_intent = ""
    best_gap = 0
    best_selected = 0
    best_completed = 0
    for intent, bucket in counts.items():
        selected = int(bucket.get("selected", 0) or 0)
        completed = int(bucket.get("completed", 0) or 0)
        gap = selected - completed
        if selected >= 2 and gap > best_gap:
            best_intent = intent
            best_gap = gap
            best_selected = selected
            best_completed = completed

    if not best_intent:
        return {"class": "", "intent": "", "selected": 0, "completed": 0, "summary": ""}

    label = tool_intent_labels.get(best_intent, best_intent)
    return {
        "class": "repeated_tool_intent_without_execution",
        "intent": best_intent,
        "selected": best_selected,
        "completed": best_completed,
        "summary": f"{label} selected {best_selected} times, execution completed {best_completed} times.",
    }


def top_repeated_correction_class(
    *,
    records: Optional[list[dict]] = None,
    limit: int = 20,
    recent_action_ledger_records_fn: Callable[[int], list[dict]],
) -> dict:
    recent = records if isinstance(records, list) else recent_action_ledger_records_fn(limit)
    counts: dict[str, int] = {}
    for rec in recent:
        trace = rec.get("route_trace") if isinstance(rec, dict) else None
        if not isinstance(trace, list):
            continue
        for step in trace:
            if not isinstance(step, dict):
                continue
            stage = str(step.get("stage") or "").strip()
            outcome = str(step.get("outcome") or "").strip()
            detail = str(step.get("detail") or "").strip()
            if stage == "llm_postprocess" and outcome == "self_corrected" and detail:
                counts[detail] = int(counts.get(detail, 0)) + 1
            elif stage == "claim_gate" and outcome == "adjusted":
                key = detail or "claim_gate_adjusted"
                counts[key] = int(counts.get(key, 0)) + 1

    if not counts:
        return {"class": "", "count": 0}
    reason, count = max(counts.items(), key=lambda item: item[1])
    return {"class": reason, "count": int(count)}


def count_unsupported_claim_blocks_recently(
    *,
    records: Optional[list[dict]] = None,
    limit: int = 20,
    recent_action_ledger_records_fn: Callable[[int], list[dict]],
) -> int:
    recent = records if isinstance(records, list) else recent_action_ledger_records_fn(limit)
    count = 0
    for rec in recent:
        trace = rec.get("route_trace") if isinstance(rec, dict) else None
        if not isinstance(trace, list):
            continue
        for step in trace:
            if not isinstance(step, dict):
                continue
            stage = str(step.get("stage") or "").strip()
            outcome = str(step.get("outcome") or "").strip()
            detail = str(step.get("detail") or "").strip().lower()
            if stage == "claim_gate" and outcome == "adjusted":
                count += 1
            if stage == "llm_postprocess" and outcome == "self_corrected" and detail == "autonomy_guard":
                count += 1
    return count


def unsupported_claims_blocked_recently(
    *,
    records: Optional[list[dict]] = None,
    limit: int = 20,
    count_unsupported_claim_blocks_recently_fn: Callable[..., int],
) -> bool:
    return count_unsupported_claim_blocks_recently_fn(records=records, limit=limit) > 0


def count_routing_overrides_recently(
    *,
    records: Optional[list[dict]] = None,
    limit: int = 20,
    recent_action_ledger_records_fn: Callable[[int], list[dict]],
) -> int:
    recent = records if isinstance(records, list) else recent_action_ledger_records_fn(limit)
    count = 0
    for rec in recent:
        trace = rec.get("route_trace") if isinstance(rec, dict) else None
        if not isinstance(trace, list):
            continue
        for step in trace:
            if not isinstance(step, dict):
                continue
            stage = str(step.get("stage") or "").strip()
            outcome = str(step.get("outcome") or "").strip()
            if stage == "routing_override" and outcome == "enabled":
                count += 1
                break
    return count


def record_used_routing_override(record: Optional[dict]) -> bool:
    trace = record.get("route_trace") if isinstance(record, dict) else None
    if not isinstance(trace, list):
        return False
    for step in trace:
        if not isinstance(step, dict):
            continue
        stage = str(step.get("stage") or "").strip()
        outcome = str(step.get("outcome") or "").strip()
        if stage == "routing_override" and outcome == "enabled":
            return True
    return False


def routing_stable_recently(
    *,
    records: Optional[list[dict]] = None,
    limit: int = 20,
    detect_repeated_tool_intent_without_execution_fn: Callable[..., dict],
) -> bool:
    failure = detect_repeated_tool_intent_without_execution_fn(records=records, limit=limit)
    return not bool(failure.get("summary"))


def sample_intents_last(
    *,
    records: Optional[list[dict]] = None,
    count: int = 5,
    recent_action_ledger_records_fn: Callable[[int], list[dict]],
) -> list[str]:
    recent = records if isinstance(records, list) else recent_action_ledger_records_fn(max(1, int(count)))
    intents: list[str] = []
    for rec in recent[-max(1, int(count)):]:
        if not isinstance(rec, dict):
            continue
        intent = str(rec.get("intent") or "").strip()
        intents.append(intent or "unknown")
    return intents


def append_self_reflection(payload: dict, *, self_reflection_log: Path) -> None:
    try:
        self_reflection_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self_reflection_log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def append_health_snapshot(payload: dict, *, health_log: Path) -> None:
    try:
        health_log.parent.mkdir(parents=True, exist_ok=True)
        with open(health_log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def record_health_snapshot(
    *,
    session_id: str,
    reflection: Optional[dict],
    session_end: bool = False,
    append_health_snapshot_fn: Callable[[dict], None],
) -> None:
    if not isinstance(reflection, dict):
        return
    payload = {
        "session_id": str(session_id or "default").strip() or "default",
        "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "probe_summary": str(reflection.get("probe_summary") or "All green"),
        "flagged_probes": list(reflection.get("probe_results") or []),
        "drift_issues": len(list(reflection.get("probe_results") or [])),
        "entry_point": str(reflection.get("entry_point") or ""),
        "session_end": bool(session_end),
        "suggestions": list(reflection.get("suggestions") or []),
    }
    append_health_snapshot_fn(payload)


def recent_self_reflection_rows(*, limit: int = 3, self_reflection_log: Path) -> list[dict]:
    try:
        if not self_reflection_log.exists():
            return []
        rows: list[dict] = []
        for line in self_reflection_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows[-max(1, int(limit)):]
    except Exception:
        return []


def maybe_log_self_reflection(
    *,
    limit: int = 20,
    every: int = 5,
    records: Optional[list[dict]] = None,
    total_records: Optional[int] = None,
    extra_payload: Optional[dict] = None,
    recent_action_ledger_records_fn: Callable[[int], list[dict]],
    detect_repeated_tool_intent_without_execution_fn: Callable[..., dict],
    top_repeated_correction_class_fn: Callable[..., dict],
    routing_stable_recently_fn: Callable[..., bool],
    count_unsupported_claim_blocks_recently_fn: Callable[..., int],
    count_routing_overrides_recently_fn: Callable[..., int],
    record_used_routing_override_fn: Callable[[Optional[dict]], bool],
    sample_intents_last_fn: Callable[..., list[str]],
    provider_name_from_tool_fn: Callable[[str], str],
    append_self_reflection_fn: Callable[[dict], None],
    record_health_snapshot_fn: Callable[..., None],
    behavior_metrics_update_from_reflection_fn: Callable[[dict, int], None],
) -> dict:
    recent = records if isinstance(records, list) else recent_action_ledger_records_fn(limit)
    if total_records is None:
        total_records = len(recent_action_ledger_records_fn(1000000))
    count_total = int(total_records or 0)
    if count_total <= 0 or count_total % max(1, int(every)) != 0:
        return {}

    failure = detect_repeated_tool_intent_without_execution_fn(records=recent, limit=limit)
    correction = top_repeated_correction_class_fn(records=recent, limit=limit)
    routing_stable = routing_stable_recently_fn(records=recent, limit=limit)
    claims_blocked = count_unsupported_claim_blocks_recently_fn(records=recent, limit=limit)
    routing_overrides = count_routing_overrides_recently_fn(records=recent, limit=limit)
    latest_record = recent[-1] if recent else {}
    continuation_count = sum(1 for rec in recent if isinstance(rec, dict) and bool(rec.get("continuation_used", False)))
    retrieval_continuations = sum(
        1
        for rec in recent
        if isinstance(rec, dict)
        and bool(rec.get("continuation_used", False))
        and str(rec.get("active_subject") or "").startswith("retrieval")
    )
    provider_hits_last_window: dict[str, int] = {}
    for rec in recent:
        if not isinstance(rec, dict):
            continue
        provider = str(rec.get("provider_used") or provider_name_from_tool_fn(rec.get("tool") or "")).strip().lower()
        if not provider:
            continue
        provider_hits_last_window[provider] = int(provider_hits_last_window.get(provider, 0) or 0) + 1
    payload = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "turn_count": count_total,
        "top_repeated_failure_class": str(failure.get("summary") or "none"),
        "top_repeated_correction_class": str(correction.get("class") or "none"),
        "failure_top": {
            "class": str(failure.get("class") or "none"),
            "intent": str(failure.get("intent") or ""),
            "count": max(0, int(failure.get("selected", 0) or 0) - int(failure.get("completed", 0) or 0)),
            "selected": int(failure.get("selected", 0) or 0),
            "completed": int(failure.get("completed", 0) or 0),
            "summary": str(failure.get("summary") or "none"),
        },
        "correction_top": {
            "class": str(correction.get("class") or "none"),
            "count": int(correction.get("count", 0) or 0),
        },
        "routing_stable": bool(routing_stable),
        "unsupported_claims_blocked": bool(claims_blocked),
        "claims_blocked": int(claims_blocked),
        "routing_overrides": int(routing_overrides),
        "routing_override_used_latest_turn": bool(record_used_routing_override_fn(latest_record)),
        "active_subject": str(latest_record.get("active_subject") or ""),
        "continuation_used": bool(latest_record.get("continuation_used", False)),
        "continuations_last_window": int(continuation_count),
        "retrieval_continuations": int(retrieval_continuations),
        "sample_intents_last5": sample_intents_last_fn(records=recent, count=5),
        "provider_hits_last_window": provider_hits_last_window,
        "last_provider_used": str(latest_record.get("provider_used") or provider_name_from_tool_fn(latest_record.get("tool") or "")).strip(),
    }
    if isinstance(extra_payload, dict):
        for key, value in extra_payload.items():
            payload[key] = value
    append_self_reflection_fn(payload)
    if count_total % 10 == 0:
        record_health_snapshot_fn(session_id=str(payload.get("session_id") or "default"), reflection=payload, session_end=False)
    behavior_metrics_update_from_reflection_fn(payload, count_total)
    return payload


def build_turn_reflection(
    session_state,
    *,
    entry_point: str,
    session_id: str,
    current_decision: dict,
    subconscious_service,
    supervisor,
    recent_action_ledger_records_fn: Callable[[int], list[dict]],
    recent_self_reflection_rows_fn: Callable[[int], list[dict]],
    build_training_backlog_summary_fn: Callable[[dict], dict | None],
    build_robust_weakness_summary_fn: Callable[[object], dict | None],
) -> dict:
    session_summary = session_state.reflection_summary()
    session_summary["subconscious_snapshot"] = subconscious_service.get_snapshot(session_state)
    reflection = supervisor.process_turn(
        entry_point=entry_point,
        session_id=session_id,
        session_summary=session_summary,
        current_decision=current_decision,
        recent_records=recent_action_ledger_records_fn(10),
        recent_reflections=recent_self_reflection_rows_fn(3),
    )
    subconscious_training_backlog = build_training_backlog_summary_fn(session_summary["subconscious_snapshot"])
    if isinstance(subconscious_training_backlog, dict):
        reflection["subconscious_training_backlog"] = subconscious_training_backlog
    subconscious_robust_weakness = build_robust_weakness_summary_fn(getattr(session_state, "subconscious_live_family_summary", None))
    if isinstance(subconscious_robust_weakness, dict):
        reflection["subconscious_robust_weakness"] = subconscious_robust_weakness
    subconscious_replan_reasons = list((session_summary["subconscious_snapshot"] or {}).get("replan_reasons") or [])
    if subconscious_replan_reasons:
        reflection["subconscious_replan_reasons"] = subconscious_replan_reasons
    reflection["session_id"] = str(session_id or "default").strip() or "default"
    reflection["entry_point"] = str(entry_point or "unknown").strip().lower() or "unknown"
    session_state.set_last_reflection(reflection)
    return reflection