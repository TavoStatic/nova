from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable, Optional

from services.ops_journal import append_ops_event


def start_action_ledger_record(
    user_input: str,
    *,
    channel: str = "cli",
    session_id: str = "",
    input_source: str = "typed",
    active_subject: str = "",
    infer_turn_intent_fn: Callable[[str], str],
    action_ledger_add_step_fn: Callable[..., None],
) -> dict:
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": str(channel or "cli").strip().lower() or "cli",
        "session_id": str(session_id or "").strip(),
        "input_source": str(input_source or "typed").strip().lower() or "typed",
        "user_input": str(user_input or "").strip(),
        "intent": infer_turn_intent_fn(user_input),
        "planner_decision": "",
        "tool": "",
        "tool_args": {},
        "tool_result": "",
        "final_answer": "",
        "reply_contract": "",
        "reply_outcome": {},
        "turn_acts": [],
        "grounded": False,
        "active_subject": str(active_subject or "").strip(),
        "continuation_used": False,
        "route_trace": [],
    }
    action_ledger_add_step_fn(
        record,
        "input",
        "received",
        channel=str(channel or "cli"),
        input_source=str(input_source or "typed"),
        intent=record.get("intent") or "",
    )
    return record


def write_action_ledger_record(record: dict, *, action_ledger_dir: Path) -> Optional[Path]:
    try:
        action_ledger_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        ms = int((time.time() % 1) * 1000)
        digest = hashlib.sha1(
            str(record.get("user_input", "")).encode("utf-8", errors="ignore")
            + str(time.time_ns()).encode("ascii", errors="ignore")
        ).hexdigest()[:8]
        out = action_ledger_dir / f"{ts}_{ms:03d}_{digest}.json"
        out.write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")
        append_ops_event(
            action_ledger_dir.parent,
            category="action_ledger",
            action="write_record",
            result="ok",
            detail=str(record.get("planner_decision") or "deterministic")[:120],
            payload={
                "path": str(out.name),
                "intent": str(record.get("intent") or "")[:120],
                "tool": str(record.get("tool") or "")[:120],
                "grounded": bool(record.get("grounded")),
            },
        )
        return out
    except Exception:
        append_ops_event(
            action_ledger_dir.parent,
            category="action_ledger",
            action="write_record",
            result="error",
            detail="write_failed",
        )
        return None


def finalize_action_ledger_record(
    record: dict,
    *,
    final_answer: str,
    planner_decision: str = "",
    tool: str = "",
    tool_args: Optional[dict] = None,
    tool_result: str = "",
    grounded: Optional[bool] = None,
    intent: str = "",
    active_subject: str = "",
    continuation_used: Optional[bool] = None,
    reply_contract: str = "",
    reply_outcome: Optional[dict] = None,
    routing_decision: Optional[dict] = None,
    reflection_payload: Optional[dict] = None,
    provider_name_from_tool_fn: Callable[[str], str],
    finalize_routing_decision_fn: Callable[..., Optional[dict]],
    action_ledger_add_step_fn: Callable[..., None],
    action_ledger_route_summary_fn: Callable[[object], str],
    write_action_ledger_record_fn: Callable[[dict], Optional[Path]],
    recent_action_ledger_records_fn: Callable[[int], list[dict]],
    maybe_log_self_reflection_fn: Callable[..., dict],
) -> Optional[Path]:
    rec = dict(record or {})
    if not isinstance(rec.get("route_trace"), list):
        rec["route_trace"] = []
    if intent:
        rec["intent"] = str(intent).strip()
    rec["planner_decision"] = str(planner_decision or rec.get("planner_decision") or "deterministic").strip()
    rec["tool"] = str(tool or rec.get("tool") or "").strip()
    args = tool_args if isinstance(tool_args, dict) else rec.get("tool_args")
    rec["tool_args"] = args if isinstance(args, dict) else {}
    rec["tool_result"] = str(tool_result or rec.get("tool_result") or "")
    rec["final_answer"] = str(final_answer or "")
    rec["reply_contract"] = str(reply_contract or rec.get("reply_contract") or "").strip()
    outcome_payload = reply_outcome if isinstance(reply_outcome, dict) else rec.get("reply_outcome")
    rec["reply_outcome"] = dict(outcome_payload) if isinstance(outcome_payload, dict) else {}
    rec["provider_used"] = str((rec.get("reply_outcome") or {}).get("provider_used") or rec.get("provider_used") or provider_name_from_tool_fn(rec.get("tool") or "")).strip()
    provider_candidates = (rec.get("reply_outcome") or {}).get("provider_candidates") if isinstance(rec.get("reply_outcome"), dict) else rec.get("provider_candidates")
    rec["provider_candidates"] = list(provider_candidates or []) if isinstance(provider_candidates or [], list) else []
    rec["provider_family"] = str((rec.get("reply_outcome") or {}).get("provider_family") or rec.get("provider_family") or rec["provider_used"] or "").strip()
    acts = rec.get("turn_acts")
    rec["turn_acts"] = [str(item).strip() for item in acts if str(item).strip()] if isinstance(acts, list) else []
    finalized_routing_decision = finalize_routing_decision_fn(
        routing_decision if isinstance(routing_decision, dict) else rec.get("routing_decision"),
        planner_decision=rec.get("planner_decision") or "",
        reply_contract=rec.get("reply_contract") or "",
        reply_outcome=rec.get("reply_outcome") if isinstance(rec.get("reply_outcome"), dict) else {},
    )
    if finalized_routing_decision:
        rec["routing_decision"] = finalized_routing_decision
    rec["active_subject"] = str(active_subject or rec.get("active_subject") or "").strip()
    rec["continuation_used"] = bool(rec.get("continuation_used", False)) if continuation_used is None else bool(continuation_used)
    if grounded is None:
        fa = rec["final_answer"].lower()
        tr = rec["tool_result"].strip()
        rec["grounded"] = bool(tr) or "[source:" in fa or "[tool:" in fa
    else:
        rec["grounded"] = bool(grounded)
    if not rec.get("route_trace"):
        action_ledger_add_step_fn(rec, "planner", rec.get("planner_decision") or "deterministic")
    if not any(str((step or {}).get("stage") or "") == "finalize" for step in rec.get("route_trace") or [] if isinstance(step, dict)):
        action_ledger_add_step_fn(
            rec,
            "finalize",
            rec.get("planner_decision") or "deterministic",
            grounded=bool(rec.get("grounded")),
            tool=rec.get("tool") or "",
        )
    rec["route_summary"] = action_ledger_route_summary_fn(rec)
    path = write_action_ledger_record_fn(rec)
    if path is not None:
        all_records = recent_action_ledger_records_fn(1000000)
        recent_for_reflection = all_records[-20:]
        maybe_log_self_reflection_fn(limit=20, every=1, records=recent_for_reflection, total_records=len(all_records), extra_payload=reflection_payload)
    return path