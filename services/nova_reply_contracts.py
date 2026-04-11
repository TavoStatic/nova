from __future__ import annotations

import re
from typing import Callable, Mapping, Optional


REPLY_TEMPLATES: dict[str, str] = {
    "set_location.missing_value": "I need a location value to store.",
    "set_location.observed_zip": "Got it - {location_value} is a ZIP code.",
    "set_location.explicit_location": "Got it - using {location_value} as your location.",
    "correction.recorded": "Got it - I recorded that correction.",
    "correction.pending_replacement": "You're right. I recorded that correction. Send the exact corrected answer if you want me to store the replacement answer.",
    "correction.replacement_applied": "Understood. I corrected that and will use your version going forward.",
    "correction.intent_ack": "Got it - correcting that.",
    "correction.identity_correction": "{learned_message}",
    "store_fact.missing_value": "I need the fact to store.",
    "store_fact.explicit_store": "Learned: {fact_text}",
    "store_fact.prompted_store": "Learned: {fact_text}",
    "store_fact.correctional_store": "Learned correction: {fact_text}",
    "store_fact.declarative_ack": "Noted.",
    "weather_lookup.clarify": "What location should I use for the weather lookup?",
    "weather_lookup.current_location": "{tool_result}",
    "weather_lookup.explicit_location": "{tool_result}",
    "web_research_family.research_prompt": "{tool_result}",
    "web_research_family.deep_search": "{tool_result}",
    "name_origin.story_known": "{reply_text}",
    "name_origin.story_missing": "{reply_text}",
    "name_origin.full_story": "{reply_text}",
    "identity_history.name_origin": "{reply_text}",
    "identity_history.creator_question": "{reply_text}",
    "identity_history.history_recall": "{reply_text}",
    "last_question.recall": "{reply_text}",
    "last_question.empty": "{reply_text}",
    "rules.list": "{reply_text}",
    "open_probe.clarification": "{reply_text}",
    "open_probe.safe_fallback": "{reply_text}",
    "turn.truthful_limit": "{reply_text}",
    "retrieval_followup.selected_result": "{reply_text}",
    "retrieval_followup.continued_results": "{reply_text}",
    "retrieval_followup.meta_summary": "{reply_text}",
    "retrieval_followup.guidance": "{reply_text}",
}


def render_reply(outcome: Optional[dict], *, reply_templates: Optional[Mapping[str, str]] = None) -> str:
    payload = outcome if isinstance(outcome, dict) else {}
    contract = str(payload.get("reply_contract") or "").strip()
    if not contract:
        return "Internal reply error - missing contract."
    templates = dict(reply_templates or REPLY_TEMPLATES)
    template = templates.get(contract)
    if not template:
        return "Internal reply error - missing template."
    try:
        return template.format(**payload)
    except Exception:
        return "Internal reply error - invalid template data."


def attach_reply_outcome(result_payload: Optional[dict], outcome: Optional[dict]) -> None:
    if not isinstance(result_payload, dict) or not isinstance(outcome, dict):
        return
    result_payload["reply_contract"] = str(outcome.get("reply_contract") or "")
    result_payload["reply_outcome"] = dict(outcome)


def resolve_set_location_semantics(intent_result: dict, user_text: str = "") -> dict[str, str]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    location_value = str(payload.get("location_value") or user_text).strip()
    location_kind = str(payload.get("location_kind") or "").strip().lower()
    if location_kind not in {"zip", "place"}:
        location_kind = "zip" if re.fullmatch(r"\d{5}", location_value) else "place"
    ack_kind = str(payload.get("location_ack_kind") or "").strip().lower()
    if ack_kind not in {"fact_only", "confirmed_location"}:
        ack_kind = "fact_only" if location_kind == "zip" else "confirmed_location"
    return {
        "location_value": location_value,
        "location_kind": location_kind,
        "location_ack_kind": ack_kind,
    }


def classify_set_location_outcome(intent_result: dict, user_text: str = "") -> dict[str, object]:
    semantics = resolve_set_location_semantics(intent_result, user_text)
    payload = intent_result if isinstance(intent_result, dict) else {}
    location_value = str(semantics.get("location_value") or "").strip()
    if not location_value:
        return {
            "intent": "set_location",
            "kind": "missing_value",
            "reply_contract": "set_location.missing_value",
            "location_value": "",
            "location_kind": str(semantics.get("location_kind") or "").strip().lower(),
            "location_ack_kind": str(semantics.get("location_ack_kind") or "").strip().lower(),
            "user_commitment": "none",
            "state_delta": {},
        }

    location_kind = str(semantics.get("location_kind") or "place").strip().lower()
    ack_kind = str(semantics.get("location_ack_kind") or "confirmed_location").strip().lower()
    rule_name = str(payload.get("rule_name") or "").strip().lower()
    user_commitment = "implied" if rule_name == "set_location_zip" else "explicit"
    outcome_kind = "observed_zip" if location_kind == "zip" or ack_kind == "fact_only" else "explicit_location"
    return {
        "intent": "set_location",
        "kind": outcome_kind,
        "reply_contract": f"set_location.{outcome_kind}",
        "location_value": location_value,
        "location_kind": location_kind,
        "location_ack_kind": ack_kind,
        "user_commitment": user_commitment,
        "state_delta": {"location": location_value},
    }


def classify_correction_outcome(
    *,
    correction_text: str,
    correction_value: str,
    last_assistant: str,
    pending_followup: bool,
    learned_fact: bool = False,
    learned_message: str = "",
    replacement_applied: bool = False,
    replacement_pending: bool = False,
) -> dict[str, object]:
    normalized_value = str(correction_value or "").strip()
    if learned_fact:
        correction_kind = "identity_correction"
        kind = "identity_correction"
        reply_contract = "correction.identity_correction"
    elif replacement_applied:
        correction_kind = "fact_replacement"
        kind = "followup_replacement" if pending_followup else "explicit_replacement"
        reply_contract = "correction.replacement_applied"
    elif replacement_pending:
        correction_kind = "simple_negation"
        kind = "pending_replacement"
        reply_contract = "correction.pending_replacement"
    elif last_assistant:
        correction_kind = "simple_negation"
        kind = "pending_replacement"
        reply_contract = "correction.pending_replacement"
    else:
        correction_kind = "simple_negation"
        kind = "recorded_only"
        reply_contract = "correction.recorded"
    return {
        "intent": "apply_correction",
        "kind": kind,
        "correction_kind": correction_kind,
        "reply_contract": reply_contract,
        "correction_text": str(correction_text or "").strip(),
        "correction_value": normalized_value,
        "learned_message": str(learned_message or "").strip(),
        "target_text": str(last_assistant or "").strip(),
        "pending_followup": bool(pending_followup),
        "state_delta": {"kind": "correction_pending", "target": str(last_assistant or "").strip()} if kind == "pending_replacement" and last_assistant else {},
    }


def classify_store_fact_outcome(
    intent_result: dict,
    user_text: str = "",
    *,
    source: str = "intent",
    storage_performed: bool = False,
) -> dict[str, object]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    fact_text = str(payload.get("fact_text") or user_text).strip()
    requested_kind = str(payload.get("store_fact_kind") or "").strip().lower()
    if requested_kind not in {"explicit_store", "prompted_store", "correctional_store", "declarative_ack"}:
        requested_kind = "declarative_ack" if source == "declarative" else "explicit_store"
    user_commitment = str(payload.get("user_commitment") or "").strip().lower()
    if user_commitment not in {"explicit", "implied", "none"}:
        user_commitment = "implied" if source == "declarative" else "explicit"
    if not fact_text:
        return {
            "intent": "store_fact",
            "kind": "missing_value",
            "reply_contract": "store_fact.missing_value",
            "fact_text": "",
            "user_commitment": "none",
            "storage_performed": False,
            "memory_kind": str(payload.get("memory_kind") or "user_fact").strip() or "user_fact",
            "state_delta": {},
        }

    outcome_kind = requested_kind
    reply_contract = f"store_fact.{outcome_kind}"
    if outcome_kind != "declarative_ack" and not storage_performed:
        outcome_kind = "declarative_ack"
        reply_contract = "store_fact.declarative_ack"

    default_memory_kind = "fact" if source == "declarative" else "user_fact"
    return {
        "intent": "store_fact",
        "kind": outcome_kind,
        "reply_contract": reply_contract,
        "fact_text": fact_text,
        "user_commitment": user_commitment,
        "storage_performed": bool(storage_performed),
        "memory_kind": str(payload.get("memory_kind") or default_memory_kind).strip() or default_memory_kind,
        "state_delta": {},
    }


def classify_weather_lookup_outcome(
    intent_result: dict,
    *,
    make_pending_weather_action_fn: Callable[[], dict],
) -> dict[str, object]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    weather_mode = str(payload.get("weather_mode") or "clarify").strip().lower() or "clarify"
    next_state = payload.get("next_state") if isinstance(payload.get("next_state"), dict) else None
    location_value = str(payload.get("location_value") or "").strip()
    if weather_mode == "current_location":
        return {
            "intent": "weather_lookup",
            "kind": "current_location",
            "reply_contract": "weather_lookup.current_location",
            "weather_mode": weather_mode,
            "location_value": "",
            "requires_tool": True,
            "pending_action": None,
            "next_state": next_state,
            "state_delta": next_state or {},
        }
    if weather_mode == "explicit_location" and location_value:
        return {
            "intent": "weather_lookup",
            "kind": "explicit_location",
            "reply_contract": "weather_lookup.explicit_location",
            "weather_mode": weather_mode,
            "location_value": location_value,
            "requires_tool": True,
            "pending_action": None,
            "next_state": next_state,
            "state_delta": next_state or {},
        }
    return {
        "intent": "weather_lookup",
        "kind": "clarify",
        "reply_contract": "weather_lookup.clarify",
        "weather_mode": "clarify",
        "location_value": "",
        "requires_tool": False,
        "pending_action": make_pending_weather_action_fn(),
        "next_state": next_state,
        "state_delta": next_state or {},
    }


def execute_weather_lookup_outcome(
    weather_outcome: dict[str, object],
    *,
    render_reply_fn: Callable[[Optional[dict]], str],
    execute_planned_action_fn: Callable[..., object],
    make_weather_result_state_fn: Callable[..., dict],
    classify_weather_lookup_outcome_fn: Callable[[dict], dict[str, object]],
) -> tuple[str, Optional[dict], dict[str, object]]:
    outcome = dict(weather_outcome or {})
    weather_mode = str(outcome.get("weather_mode") or "clarify").strip().lower() or "clarify"
    next_state = outcome.get("next_state") if isinstance(outcome.get("next_state"), dict) else None
    if weather_mode == "clarify":
        return render_reply_fn(outcome), next_state, outcome

    if weather_mode == "current_location":
        tool_result = execute_planned_action_fn("weather_current_location")
        next_state = make_weather_result_state_fn(weather_mode=weather_mode, tool_result=str(tool_result or ""))
        outcome["next_state"] = next_state
        outcome["state_delta"] = next_state
        outcome["tool_result"] = str(tool_result or "")
        return render_reply_fn(outcome), next_state, outcome

    if weather_mode == "explicit_location":
        location_value = str(outcome.get("location_value") or "").strip()
        if not location_value:
            fallback = classify_weather_lookup_outcome_fn({"weather_mode": "clarify", "next_state": next_state})
            return render_reply_fn(fallback), next_state, fallback
        tool_result = execute_planned_action_fn("weather_location", [location_value])
        next_state = make_weather_result_state_fn(
            weather_mode=weather_mode,
            location_value=location_value,
            tool_result=str(tool_result or ""),
        )
        outcome["next_state"] = next_state
        outcome["state_delta"] = next_state
        outcome["tool_result"] = str(tool_result or "")
        return render_reply_fn(outcome), next_state, outcome

    fallback = classify_weather_lookup_outcome_fn({"weather_mode": "clarify", "next_state": next_state})
    return render_reply_fn(fallback), next_state, fallback