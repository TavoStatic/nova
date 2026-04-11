from __future__ import annotations

from typing import Any, Callable, Optional

from services.supervisor_identity_rules import developer_profile_state_rule
from services.supervisor_identity_rules import identity_history_family_rule
from services.supervisor_identity_rules import last_question_recall_rule
from services.supervisor_identity_rules import name_origin_store_rule
from services.supervisor_identity_rules import open_probe_family_rule
from services.supervisor_identity_rules import profile_certainty_rule
from services.supervisor_identity_rules import rules_list_rule
from services.supervisor_identity_rules import session_fact_recall_rule
from services.supervisor_intent_rules import assistant_name_rule
from services.supervisor_intent_rules import capability_query_rule
from services.supervisor_intent_rules import developer_full_name_rule
from services.supervisor_intent_rules import developer_profile_rule
from services.supervisor_intent_rules import name_origin_rule
from services.supervisor_intent_rules import policy_domain_rule
from services.supervisor_intent_rules import self_identity_web_challenge_rule
from services.supervisor_intent_rules import session_summary_rule
from services.supervisor_intent_rules import smalltalk_rule
from services.supervisor_patterns import normalize_text as _normalize_text
from services.supervisor_reflective_rules import apply_correction_rule
from services.supervisor_reflective_rules import reflective_retry_rule
from services.supervisor_routing_rules import location_name_rule
from services.supervisor_routing_rules import location_recall_rule
from services.supervisor_routing_rules import location_weather_rule
from services.supervisor_routing_rules import retrieval_followup_rule
from services.supervisor_routing_rules import self_location_rule
from services.supervisor_routing_rules import set_location_rule
from services.supervisor_routing_rules import store_fact_rule
from services.supervisor_routing_rules import weather_lookup_rule
from services.supervisor_routing_rules import web_research_family_rule


EXPLICIT_INTENT_OWNERSHIP_RULES = frozenset({
    "store_fact",
    "web_research_family",
    "weather_lookup",
    "set_location",
    "capability_query",
    "policy_domain_query",
    "assistant_name",
    "self_identity_web_challenge",
})


EXPLICIT_HANDLE_OWNERSHIP_RULES = frozenset({
    "reflective_retry",
    "profile_certainty",
    "identity_history_family",
    "open_probe_family",
    "session_fact_recall",
    "self_location",
    "location_recall",
    "retrieval_followup",
    "name_origin_store",
    "apply_correction",
    "rules_list",
    "last_question_recall",
})


def default_rule_handlers() -> dict[str, Callable[..., dict[str, Any]]]:
    return {
        "reflective_retry": reflective_retry_rule,
        "profile_certainty": profile_certainty_rule,
        "identity_history_family": identity_history_family_rule,
        "open_probe_family": open_probe_family_rule,
        "session_fact_recall": session_fact_recall_rule,
        "developer_profile_state": developer_profile_state_rule,
        "last_question_recall": last_question_recall_rule,
        "self_location": self_location_rule,
        "rules_list": rules_list_rule,
        "location_recall": location_recall_rule,
        "location_name": location_name_rule,
        "location_weather": location_weather_rule,
        "retrieval_followup": retrieval_followup_rule,
        "name_origin_store": name_origin_store_rule,
        "apply_correction": apply_correction_rule,
        "smalltalk": smalltalk_rule,
        "store_fact": store_fact_rule,
        "web_research_family": web_research_family_rule,
        "weather_lookup": weather_lookup_rule,
        "set_location": set_location_rule,
        "capability_query": capability_query_rule,
        "policy_domain_query": policy_domain_rule,
        "assistant_name": assistant_name_rule,
        "self_identity_web_challenge": self_identity_web_challenge_rule,
        "name_origin": name_origin_rule,
        "developer_full_name": developer_full_name_rule,
        "developer_profile": developer_profile_rule,
        "session_summary": session_summary_rule,
    }


def result_is_explicitly_owned(rule_name: str, result: dict[str, Any], *, phase: str) -> bool:
    if not bool(result.get("handled")):
        return False
    if bool(result.get("required_safety_intercept")) or bool(result.get("required_policy_intercept")):
        return True
    if str(result.get("ownership") or "").strip().lower() == "explicit":
        return True

    normalized_rule_name = str(rule_name or "").strip()
    normalized_phase = str(phase or "handle").strip().lower()
    if normalized_phase == "intent":
        return normalized_rule_name in EXPLICIT_INTENT_OWNERSHIP_RULES
    if normalized_phase == "handle":
        return normalized_rule_name in EXPLICIT_HANDLE_OWNERSHIP_RULES
    return False


def register_rule(
    rules: list[dict[str, Any]],
    name: str,
    rule: Callable[..., dict[str, Any]],
    *,
    priority: int = 100,
    phases: tuple[str, ...] = ("handle",),
) -> list[dict[str, Any]]:
    updated_rules = [item for item in rules if str(item.get("name") or "") != str(name or "")]
    updated_rules.append({
        "name": str(name or "").strip(),
        "rule": rule,
        "priority": int(priority),
        "phases": tuple(str(phase or "handle").strip().lower() for phase in phases if str(phase or "").strip()),
    })
    updated_rules.sort(key=lambda item: (int(item.get("priority", 100)), str(item.get("name") or "")))
    return updated_rules


def evaluate_rules(
    rules: list[dict[str, Any]],
    user_text: str,
    *,
    manager: Any = None,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    normalized_user_text = str(user_text or "")
    normalized_manager = {} if manager is None else manager
    normalized_turns = list(turns or [])
    normalized_phase = str(phase or "handle").strip().lower() or "handle"
    normalized_entry_point = str(entry_point or "").strip().lower()
    low = _normalize_text(normalized_user_text)
    turn = len(normalized_turns)
    candidates: list[dict[str, Any]] = []
    for item in rules:
        phases = tuple(item.get("phases") or ())
        if normalized_phase not in phases:
            continue
        rule_name = str(item.get("name") or "")
        try:
            result = item["rule"](
                normalized_user_text,
                low,
                normalized_manager,
                turn,
                turns=list(normalized_turns),
                phase=normalized_phase,
                entry_point=normalized_entry_point,
            )
        except Exception as exc:
            result = {"handled": False, "rule_error": str(exc)}
        if not isinstance(result, dict):
            continue
        explicitly_owned = result_is_explicitly_owned(rule_name, result, phase=normalized_phase)
        candidate = {
            "rule_name": rule_name,
            "priority": int(item.get("priority", 100)),
            "handled": bool(result.get("handled")) and explicitly_owned,
        }
        action = str(result.get("action") or "").strip()
        if action:
            candidate["action"] = action
        intent = str(result.get("intent") or "").strip()
        if intent:
            candidate["intent"] = intent
        if bool(result.get("handled")) and not explicitly_owned:
            candidate["ownership_declined"] = True
        if str(result.get("rewrite_text") or "").strip():
            candidate["rewrite"] = True
        if isinstance(result.get("state_update"), dict):
            candidate["state_update"] = True
        rule_error = str(result.get("rule_error") or "").strip()
        if rule_error:
            candidate["rule_error"] = rule_error[:160]
        candidates.append(candidate)
        if explicitly_owned or str(result.get("rewrite_text") or "").strip() or isinstance(result.get("state_update"), dict):
            payload = dict(result)
            payload["phase"] = normalized_phase
            payload["candidates"] = list(candidates)
            if str(payload.get("rule_name") or "").strip():
                payload["matched_rule_name"] = str(payload.get("rule_name") or "").strip()
            payload["rule_name"] = rule_name
            payload["priority"] = int(item.get("priority", 100))
            if not explicitly_owned:
                payload["handled"] = False
            return payload
    return {"handled": False, "phase": normalized_phase, "candidates": candidates}