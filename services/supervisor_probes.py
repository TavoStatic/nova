from __future__ import annotations

from collections import Counter
import re
from typing import Callable


def status_line(name: str, status: str, message: str) -> str:
    label = str(status or "green").upper()
    clean = str(message or "").strip()
    return f"{label}: {name}" if not clean else f"{label}: {name} - {clean}"


def normalize_decision(
    entry_point: str,
    session_id: str,
    session_summary: dict,
    current_decision: dict,
    *,
    normalize_text_fn: Callable[[str], str],
) -> dict:
    overrides = current_decision.get("overrides_active")
    if not isinstance(overrides, list):
        overrides = session_summary.get("overrides_active") if isinstance(session_summary.get("overrides_active"), list) else []
    pending_action = current_decision.get("pending_action") if isinstance(current_decision.get("pending_action"), dict) else None
    tool_result = str(current_decision.get("tool_result") or "")
    final_answer = str(current_decision.get("final_answer") or current_decision.get("reply_text") or "")
    user_input = str(current_decision.get("user_input") or "")
    turn_acts = current_decision.get("turn_acts")
    if not isinstance(turn_acts, list):
        routing_decision = current_decision.get("routing_decision") if isinstance(current_decision.get("routing_decision"), dict) else {}
        turn_acts = routing_decision.get("turn_acts") if isinstance(routing_decision.get("turn_acts"), list) else []
    return {
        "entry_point": str(entry_point or "unknown").strip().lower() or "unknown",
        "session_id": str(session_id or "").strip() or "default",
        "user_input": user_input,
        "parity_key": normalize_text_fn(user_input),
        "active_subject": str(current_decision.get("active_subject") or session_summary.get("active_subject") or "").strip(),
        "continuation_used": bool(current_decision.get("continuation_used", session_summary.get("continuation_used", False))),
        "planner_decision": str(current_decision.get("planner_decision") or "deterministic").strip() or "deterministic",
        "tool": str(current_decision.get("tool") or "").strip(),
        "tool_result": tool_result,
        "final_answer": final_answer,
        "reply_contract": str(current_decision.get("reply_contract") or "").strip(),
        "reply_outcome_kind": str((current_decision.get("reply_outcome") or {}).get("kind") or "").strip(),
        "turn_acts": [str(item).strip() for item in turn_acts if str(item).strip()] if isinstance(turn_acts, list) else [],
        "pending_action": pending_action,
        "overrides_active": sorted(str(item).strip() for item in overrides if str(item).strip()),
        "grounded": bool(current_decision.get("grounded")) if isinstance(current_decision.get("grounded"), bool) else bool(tool_result.strip()),
        "route_summary": str(current_decision.get("route_summary") or "").strip(),
    }


def recent_issue_names(recent_reflections: list[dict]) -> list[str]:
    names: list[str] = []
    for reflection in recent_reflections[-5:]:
        findings = reflection.get("probe_findings") if isinstance(reflection, dict) else None
        if isinstance(findings, list):
            for item in findings:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "").strip().lower()
                if status not in {"yellow", "red"}:
                    continue
                name = str(item.get("name") or "").strip()
                if name:
                    names.append(name)
            continue
        for line in list(reflection.get("probe_results") or []):
            text = str(line or "").strip()
            match = re.match(r"^(?:YELLOW|RED):\s+([a-z_]+)", text, flags=re.I)
            if match:
                names.append(match.group(1))
    return names


def suggest_hardening(issue: str) -> str:
    name = str(issue or "").strip().lower()
    if name == "pending_action_leak":
        return "auto-clear pending_action after tool success"
    if name == "continuation_drop":
        return "broaden continuation triggers or add a still-on-subject prompt"
    if name == "entrypoint_parity":
        return "compare CLI and HTTP ordering around the last matching input"
    if name == "identity_location_route":
        return "guard identity and location turns from local knowledge retrieval routes"
    if name == "rule_coverage":
        return "add a deterministic handler or tighten fallback gating for factual/tool turns"
    return "review probe details"


def looks_like_identity_location_turn(current: dict) -> bool:
    low = str(current.get("user_input") or "").strip().lower()
    if not low:
        return False
    return any(token in low for token in (
        "what is your location",
        "your current location",
        "your current physical location",
        "where are you",
        "where is nova",
        "his location",
        "where is he",
        "where is gus",
        "gus current location",
    ))


def looks_like_suspicious_fallback(current: dict) -> bool:
    low = str(current.get("user_input") or "").strip().lower()
    if not low:
        return False
    suspicious_terms = (
        "weather",
        "peims",
        "tsds",
        "attendance",
        "domain",
        "policy",
        "fetch",
        "search",
        "research",
        "tool",
        "location",
        "who is",
        "what is",
        "where is",
        "current location",
    )
    return any(term in low for term in suspicious_terms)


def build_suggestions(context: dict, findings: list[dict]) -> list[str]:
    repeated = Counter(recent_issue_names(list(context.get("recent_reflections") or [])))
    for item in findings:
        status = str(item.get("status") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        if status in {"yellow", "red"} and name:
            repeated[name] += 1
    suggestions: list[str] = []
    for issue, count in repeated.items():
        if count < 3:
            continue
        suggestions.append(f"Repeated {issue} ({count}x) - consider hardening rule: {suggest_hardening(issue)}")
    return suggestions[:3]


def probe_entrypoint_parity(context: dict) -> tuple[str, str]:
    current = context.get("decision") or {}
    previous = context.get("previous_input_decision") or {}
    if not previous:
        return "green", ""
    if str(previous.get("entry_point") or "") == str(current.get("entry_point") or ""):
        return "green", ""
    prev_subject = str(previous.get("active_subject") or "")
    current_subject = str(current.get("active_subject") or "")
    if prev_subject != current_subject:
        return "red", f"Drift: {previous.get('entry_point')} -> {prev_subject or 'none'} vs {current.get('entry_point')} -> {current_subject or 'none'}"
    if bool(previous.get("continuation_used", False)) != bool(current.get("continuation_used", False)):
        return "yellow", f"Continuation mismatch on similar input: {previous.get('entry_point')} -> {bool(previous.get('continuation_used', False))} vs {current.get('entry_point')} -> {bool(current.get('continuation_used', False))}"
    return "green", ""


def probe_continuation_drop(context: dict) -> tuple[str, str]:
    current = context.get("decision") or {}
    previous = context.get("previous_session_decision") or {}
    if not previous:
        return "green", ""
    if not bool(previous.get("continuation_used", False)) or bool(current.get("continuation_used", False)):
        return "green", ""
    previous_subject = str(previous.get("active_subject") or "")
    current_subject = str(current.get("active_subject") or "")
    if previous_subject and previous_subject != current_subject:
        return "yellow", f"Previous turn continued on {previous_subject}, current turn dropped to {current_subject or 'none'}"
    return "green", ""


def probe_pending_action_leak(context: dict) -> tuple[str, str]:
    current = context.get("decision") or {}
    pending = current.get("pending_action")
    if not isinstance(pending, dict) or not pending:
        return "green", ""
    planner_decision = str(current.get("planner_decision") or "")
    tool_result = str(current.get("tool_result") or "").strip()
    if planner_decision in {"run_tool", "command"} and (bool(current.get("grounded", False)) or bool(tool_result)):
        return "red", f"Pending action still set after successful {planner_decision}"
    return "green", ""


def probe_override_consistency(context: dict) -> tuple[str, str]:
    current = context.get("decision") or {}
    current_entry = str(current.get("entry_point") or "")
    current_overrides = tuple(current.get("overrides_active") or [])
    other_entries = context.get("other_entry_overrides") or {}
    for other_entry, other_overrides in other_entries.items():
        if str(other_entry or "") == current_entry:
            continue
        if tuple(other_overrides or ()) != current_overrides:
            return "yellow", f"Override mismatch: {other_entry} -> {list(other_overrides or [])} vs {current_entry} -> {list(current_overrides)}"
    return "green", ""


def probe_thin_answer_frequency(context: dict) -> tuple[str, str]:
    recent = context.get("recent_records") or []
    if not isinstance(recent, list):
        return "green", ""
    count = 0
    for record in recent[-10:]:
        if not isinstance(record, dict):
            continue
        low = str(record.get("final_answer") or "").strip().lower()
        if not low:
            continue
        if any(token in low for token in (
            "i don't have",
            "i do not have",
            "uncertain",
            "not sure",
            "don't yet know",
            "do not yet know",
        )):
            count += 1
    if count > 2:
        return "yellow", f"Thin answers appearing {count} times in the last 10 turns"
    return "green", ""


def probe_identity_location_route(context: dict) -> tuple[str, str]:
    current = context.get("decision") or {}
    if not looks_like_identity_location_turn(current):
        return "green", ""
    rendered = " ".join(str(current.get(field) or "") for field in ("final_answer", "tool_result", "route_summary")).lower()
    if "local knowledge files" in rendered or "[source: knowledge/" in rendered:
        return "red", "Location or identity turn routed to local knowledge retrieval"
    return "green", ""


def probe_rule_coverage(context: dict) -> tuple[str, str]:
    current = context.get("decision") or {}
    if str(current.get("planner_decision") or "") == "llm_fallback":
        if looks_like_suspicious_fallback(current):
            return "red", "Suspicious fallback on a factual or tool-directed turn"
        return "green", ""
    return "green", ""


DEFAULT_SUPERVISOR_PROBES: dict[str, Callable[[dict], tuple[str, str]]] = {
    "entrypoint_parity": probe_entrypoint_parity,
    "continuation_drop": probe_continuation_drop,
    "pending_action_leak": probe_pending_action_leak,
    "override_consistency": probe_override_consistency,
    "thin_answer_frequency": probe_thin_answer_frequency,
    "identity_location_route": probe_identity_location_route,
    "rule_coverage": probe_rule_coverage,
}