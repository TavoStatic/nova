from __future__ import annotations

import json
from pathlib import Path


TOOL_INTENT_LABELS: dict[str, str] = {
    "weather_lookup": "Weather route",
    "web_fetch": "Web fetch route",
    "web_search": "Web search route",
    "web_gather": "Web gather route",
    "web_research": "Web research route",
    "wikipedia_lookup": "Wikipedia route",
    "stackexchange_search": "StackExchange route",
}


def recent_action_ledger_records(action_ledger_dir: Path, limit: int = 20) -> list[dict]:
    try:
        if not action_ledger_dir.exists():
            return []
        files = sorted(action_ledger_dir.glob("*.json"))[-max(1, int(limit)):]
        records: list[dict] = []
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records
    except Exception:
        return []


def latest_action_ledger_record(action_ledger_dir: Path) -> dict:
    try:
        if not action_ledger_dir.exists():
            return {}
        files = sorted(action_ledger_dir.glob("*.json"))
        if not files:
            return {}
        data = json.loads(files[-1].read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def record_completed_tool_execution(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    trace = record.get("route_trace")
    if not isinstance(trace, list):
        return False
    for step in trace:
        if not isinstance(step, dict):
            continue
        stage = str(step.get("stage") or "").strip()
        outcome = str(step.get("outcome") or "").strip()
        if stage == "tool_execution" and outcome == "ok":
            return True
        if stage in {"keyword_tool", "command"} and outcome == "matched" and str(record.get("tool_result") or "").strip():
            return True
    return False


def record_requested_tool_clarification(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    if str(record.get("planner_decision") or "").strip() == "ask_clarify":
        return True
    trace = record.get("route_trace")
    if not isinstance(trace, list):
        return False
    for step in trace:
        if not isinstance(step, dict):
            continue
        stage = str(step.get("stage") or "").strip()
        outcome = str(step.get("outcome") or "").strip()
        if stage == "action_planner" and outcome == "ask_clarify":
            return True
        if stage == "pending_action" and outcome == "awaiting_location":
            return True
        if stage == "finalize" and outcome == "ask_clarify":
            return True
    return False


def detect_repeated_tool_intent_without_execution(
    action_ledger_dir: Path,
    *,
    records: list[dict] | None = None,
    limit: int = 20,
    tool_intent_labels: dict[str, str] | None = None,
) -> dict:
    recent = records if isinstance(records, list) else recent_action_ledger_records(action_ledger_dir, limit=limit)
    labels = dict(tool_intent_labels or TOOL_INTENT_LABELS)
    counts: dict[str, dict[str, int]] = {}
    for rec in recent:
        if not isinstance(rec, dict):
            continue
        intent = str(rec.get("intent") or "").strip()
        if intent not in labels:
            continue
        if record_requested_tool_clarification(rec):
            continue
        bucket = counts.setdefault(intent, {"selected": 0, "completed": 0})
        bucket["selected"] += 1
        if record_completed_tool_execution(rec):
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

    label = labels.get(best_intent, best_intent)
    return {
        "class": "repeated_tool_intent_without_execution",
        "intent": best_intent,
        "selected": best_selected,
        "completed": best_completed,
        "summary": f"{label} selected {best_selected} times, execution completed {best_completed} times.",
    }


def top_repeated_correction_class(
    action_ledger_dir: Path,
    *,
    records: list[dict] | None = None,
    limit: int = 20,
) -> dict:
    recent = records if isinstance(records, list) else recent_action_ledger_records(action_ledger_dir, limit=limit)
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
    action_ledger_dir: Path,
    *,
    records: list[dict] | None = None,
    limit: int = 20,
) -> int:
    recent = records if isinstance(records, list) else recent_action_ledger_records(action_ledger_dir, limit=limit)
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
    action_ledger_dir: Path,
    *,
    records: list[dict] | None = None,
    limit: int = 20,
) -> bool:
    return count_unsupported_claim_blocks_recently(action_ledger_dir, records=records, limit=limit) > 0


def count_routing_overrides_recently(
    action_ledger_dir: Path,
    *,
    records: list[dict] | None = None,
    limit: int = 20,
) -> int:
    recent = records if isinstance(records, list) else recent_action_ledger_records(action_ledger_dir, limit=limit)
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


def record_used_routing_override(record: dict | None) -> bool:
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
    action_ledger_dir: Path,
    *,
    records: list[dict] | None = None,
    limit: int = 20,
    tool_intent_labels: dict[str, str] | None = None,
) -> bool:
    failure = detect_repeated_tool_intent_without_execution(
        action_ledger_dir,
        records=records,
        limit=limit,
        tool_intent_labels=tool_intent_labels,
    )
    return not bool(failure.get("summary"))


def sample_intents_last(
    action_ledger_dir: Path,
    *,
    records: list[dict] | None = None,
    count: int = 5,
) -> list[str]:
    recent = records if isinstance(records, list) else recent_action_ledger_records(action_ledger_dir, limit=max(1, int(count)))
    intents: list[str] = []
    for rec in recent[-max(1, int(count)):]:
        if not isinstance(rec, dict):
            continue
        intent = str(rec.get("intent") or "").strip()
        intents.append(intent or "unknown")
    return intents