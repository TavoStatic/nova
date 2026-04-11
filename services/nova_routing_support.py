from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional

import requests


ROUTING_INTENT_PROMPT = """\
Classify the user message into exactly one routing intent. Reply with the label only — no explanation.

Labels:
weather_lookup   – user wants current conditions, temperature, rain, forecast, or whether to dress for outdoors
web_research     – user wants online research on a topic
web_search       – user wants a quick web search
store_fact       – user is telling a personal fact to remember
set_location     – user is providing their location or zip code
general_chat     – everything else

User message: {text}
Label:"""


def last_assistant_turn_text(turns: Optional[list[tuple[str, str]]]) -> str:
    for role, text in reversed(list(turns or [])):
        if str(role or "").strip().lower() == "assistant":
            return str(text or "").strip()
    return ""


def looks_like_affirmative_followup(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    return (
        normalized in {"yes", "yeah", "yea", "sure", "okay", "ok", "please", "do that", "go ahead"}
        or normalized.startswith("yes ")
        or normalized.startswith("yeah ")
        or normalized.startswith("yea ")
        or normalized.startswith("please ")
        or "do that" in normalized
    )


def looks_like_shared_location_reference(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(text).strip(" .,!?")
    if not normalized:
        return False
    return (
        normalized in {"our location", "our location nova", "same location", "shared location"}
        or (("your" in normalized or "our" in normalized) and "location" in normalized)
        or "that location" in normalized
        or normalized in {"there", "same place"}
    )


def intent_trace_preview(text: str, *, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def supervisor_result_has_route(rule_result: Optional[dict]) -> bool:
    payload = rule_result if isinstance(rule_result, dict) else {}
    return bool(payload.get("handled")) or bool(str(payload.get("action") or "").strip())


def dev_mode_enabled() -> bool:
    raw = str(os.environ.get("NOVA_DEV_MODE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def looks_like_open_fallback_turn(
    text: str,
    *,
    is_explicit_command_like_fn: Callable[[str], bool],
    is_location_request_fn: Callable[[str], bool],
    normalize_turn_text_fn: Callable[[str], str],
    is_peims_broad_query_fn: Callable[[str], bool],
    is_local_knowledge_topic_query_fn: Callable[[str], bool],
) -> bool:
    candidate = str(text or "").strip()
    if not candidate:
        return False
    if is_explicit_command_like_fn(candidate):
        return False
    if is_location_request_fn(candidate):
        return False
    normalized = normalize_turn_text_fn(candidate)
    if normalized in {
        "weather",
        "weather now",
        "weather current",
        "weather today",
        "current weather",
        "what's the weather",
        "what is the weather",
        "what is the weather now",
        "what's the weather now",
    }:
        return False
    if is_peims_broad_query_fn(candidate) or is_local_knowledge_topic_query_fn(candidate):
        return False
    if normalized in {
        "tell me something",
        "tell me anything",
        "say something",
        "say anything",
    }:
        return False
    if re.match(r"^(hi|hello|hey)\b", normalized, flags=re.I):
        return True
    if candidate.endswith("?"):
        return True
    if len(normalized.split()) >= 3:
        return True
    return normalized.startswith((
        "how ",
        "why ",
        "what ",
        "who ",
        "can you ",
        "could you ",
        "would you ",
        "tell me ",
        "explain ",
        "help ",
        "show me ",
        "compare ",
        "recap ",
        "summarize ",
    ))


def normalize_bypass_phrase(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> str:
    return normalize_turn_text_fn(text).strip(" .,!?:;\t\r\n")


def classify_supervisor_bypass(
    text: str,
    *,
    normalize_bypass_phrase_fn: Callable[[str], str],
    allowed_supervisor_bypasses: tuple[dict[str, object], ...],
    looks_like_open_fallback_turn_fn: Callable[[str], bool],
) -> dict:
    normalized = normalize_bypass_phrase_fn(text)
    if not normalized:
        return {"allowed": False, "category": "unlisted", "reason": "empty"}
    for item in allowed_supervisor_bypasses:
        phrases = item.get("phrases")
        if isinstance(phrases, set) and normalized in phrases:
            return {
                "allowed": True,
                "category": str(item.get("category") or "fallback.allowlisted"),
                "reason": "allowlisted_bypass",
                "normalized_input": normalized,
            }
    if looks_like_open_fallback_turn_fn(text):
        return {
            "allowed": True,
            "category": "intentional_fallback.open_fulfillment_or_model",
            "reason": "open_fallback_candidate",
            "normalized_input": normalized,
        }
    return {
        "allowed": False,
        "category": "unlisted",
        "reason": "not_allowlisted",
        "normalized_input": normalized,
    }


def supervisor_candidate_trace(rule_result: Optional[dict]) -> list[dict]:
    candidates = []
    for raw in list((rule_result or {}).get("candidates") or [])[:12]:
        if not isinstance(raw, dict):
            continue
        item = {
            "rule_name": str(raw.get("rule_name") or "").strip(),
            "priority": int(raw.get("priority", 100)),
            "handled": bool(raw.get("handled")),
        }
        action = str(raw.get("action") or "").strip()
        if action:
            item["action"] = action
        intent = str(raw.get("intent") or "").strip()
        if intent:
            item["intent"] = intent
        if bool(raw.get("rewrite")):
            item["rewrite"] = True
        if bool(raw.get("state_update")):
            item["state_update"] = True
        rule_error = str(raw.get("rule_error") or "").strip()
        if rule_error:
            item["rule_error"] = rule_error[:160]
        candidates.append(item)
    return candidates


def supervisor_phase_record(
    rule_result: Optional[dict],
    *,
    phase: str,
    supervisor_result_has_route_fn: Callable[[Optional[dict]], bool],
    supervisor_candidate_trace_fn: Callable[[Optional[dict]], list[dict]],
) -> dict:
    payload = rule_result if isinstance(rule_result, dict) else {}
    return {
        "phase": str(phase or "unknown").strip().lower() or "unknown",
        "handled": bool(supervisor_result_has_route_fn(payload)),
        "rule_name": str(payload.get("matched_rule_name") or payload.get("rule_name") or "").strip(),
        "intent": str(payload.get("intent") or "").strip(),
        "action": str(payload.get("action") or "").strip(),
        "priority": int(payload.get("priority", 100)) if str(payload.get("priority") or "").strip() else None,
        "candidates": supervisor_candidate_trace_fn(payload),
    }


def build_routing_decision(
    text: str,
    *,
    entry_point: str,
    intent_result: Optional[dict] = None,
    handle_result: Optional[dict] = None,
    final_owner: str = "pending",
    allowed_bypass: bool = False,
    allowed_bypass_category: str = "",
    bypass_reason: str = "",
    reply_contract: str = "",
    reply_outcome: Optional[dict] = None,
    turn_acts: Optional[list[str]] = None,
    intent_trace_preview_fn: Callable[[str], str],
    supervisor_phase_record_fn: Callable[..., dict],
) -> dict:
    outcome = reply_outcome if isinstance(reply_outcome, dict) else {}
    acts = [str(item).strip() for item in list(turn_acts or []) if str(item).strip()]
    return {
        "input_preview": intent_trace_preview_fn(text),
        "entry_point": str(entry_point or "unknown").strip().lower() or "unknown",
        "intent_phase": supervisor_phase_record_fn(intent_result, phase="intent"),
        "handle_phase": supervisor_phase_record_fn(handle_result, phase="handle"),
        "final_owner": str(final_owner or "pending").strip().lower() or "pending",
        "allowed_bypass": bool(allowed_bypass),
        "allowed_bypass_category": str(allowed_bypass_category or "").strip(),
        "bypass_reason": str(bypass_reason or "").strip(),
        "reply_contract": str(reply_contract or "").strip(),
        "reply_outcome_kind": str(outcome.get("kind") or "").strip(),
        "turn_acts": acts,
    }


def finalize_routing_decision(
    routing_decision: Optional[dict],
    *,
    planner_decision: str = "",
    reply_contract: str = "",
    reply_outcome: Optional[dict] = None,
    turn_acts: Optional[list[str]] = None,
) -> dict:
    payload = dict(routing_decision or {})
    if not payload:
        return {}
    intent_phase = payload.get("intent_phase") if isinstance(payload.get("intent_phase"), dict) else {}
    handle_phase = payload.get("handle_phase") if isinstance(payload.get("handle_phase"), dict) else {}
    final_owner = str(payload.get("final_owner") or "").strip().lower()
    if final_owner in {"", "pending"}:
        if bool(intent_phase.get("handled")):
            final_owner = "supervisor_intent"
        elif bool(handle_phase.get("handled")):
            final_owner = "supervisor_handle"
        elif str(planner_decision or "").strip().lower() in {
            "llm_fallback",
            "respond",
            "run_tool",
            "command",
            "ask_clarify",
            "grounded_lookup",
            "truth_hierarchy",
            "blocked_low_confidence",
            "policy_block",
            "conversation_followup",
        }:
            final_owner = "fallback"
        else:
            final_owner = "core_legacy"
    payload["final_owner"] = final_owner
    if reply_contract:
        payload["reply_contract"] = str(reply_contract).strip()
    outcome = reply_outcome if isinstance(reply_outcome, dict) else {}
    if outcome:
        payload["reply_outcome_kind"] = str(outcome.get("kind") or payload.get("reply_outcome_kind") or "").strip()
    acts = turn_acts if isinstance(turn_acts, list) else payload.get("turn_acts")
    payload["turn_acts"] = [str(item).strip() for item in acts if str(item).strip()] if isinstance(acts, list) else []
    return payload


def supervisor_bypass_warning(
    text: str,
    *,
    entry_point: str,
    routing_decision: Optional[dict] = None,
    intent_trace_preview_fn: Callable[[str], str],
) -> str:
    where = str(entry_point or "unknown").strip().lower() or "unknown"
    category = str((routing_decision or {}).get("allowed_bypass_category") or "").strip()
    if where == "http" and category.startswith("intentional_fallback."):
        warning = (
            "[INFO] Open fallback - learning invitation active"
            f" [{where}] {intent_trace_preview_fn(text)}"
        )
    else:
        warning = (
            "[WARN] Turn bypassed supervisor intent phase — this will be an error soon"
            f" [{where}] {intent_trace_preview_fn(text)}"
        )
    if category:
        warning += f" [{category}]"
    return warning


def handle_supervisor_bypass(
    text: str,
    *,
    entry_point: str,
    routing_decision: Optional[dict] = None,
    classify_supervisor_bypass_fn: Callable[[str], dict],
    supervisor_bypass_warning_fn: Callable[..., str],
    dev_mode_enabled_fn: Callable[[], bool],
    intent_trace_preview_fn: Callable[[str], str],
) -> str:
    classification = classify_supervisor_bypass_fn(text)
    if isinstance(routing_decision, dict):
        routing_decision["allowed_bypass"] = bool(classification.get("allowed"))
        routing_decision["allowed_bypass_category"] = str(classification.get("category") or "").strip()
        routing_decision["bypass_reason"] = str(classification.get("reason") or "").strip()
        routing_decision["final_owner"] = "fallback"
    warning = supervisor_bypass_warning_fn(text, entry_point=entry_point, routing_decision=routing_decision)
    if dev_mode_enabled_fn() and not bool(classification.get("allowed")):
        detail = routing_decision if isinstance(routing_decision, dict) else classification
        raise RuntimeError(f"Bypass detected: {intent_trace_preview_fn(text)} :: {json.dumps(detail, ensure_ascii=True, sort_keys=True)}")
    return warning


def should_warn_supervisor_bypass(
    text: str,
    *,
    looks_like_open_fallback_turn_fn: Callable[[str], bool],
    is_explicit_command_like_fn: Callable[[str], bool],
    is_location_request_fn: Callable[[str], bool],
    normalize_turn_text_fn: Callable[[str], str],
    is_peims_broad_query_fn: Callable[[str], bool],
    is_local_knowledge_topic_query_fn: Callable[[str], bool],
) -> bool:
    candidate = str(text or "").strip()
    if not candidate:
        return False
    if looks_like_open_fallback_turn_fn(candidate):
        return False
    if is_explicit_command_like_fn(candidate):
        return False
    if is_location_request_fn(candidate):
        return False
    normalized = normalize_turn_text_fn(candidate)
    if normalized in {
        "weather",
        "weather now",
        "weather current",
        "weather today",
        "current weather",
        "what's the weather",
        "what is the weather",
        "what is the weather now",
        "what's the weather now",
    }:
        return False
    if is_peims_broad_query_fn(candidate) or is_local_knowledge_topic_query_fn(candidate):
        return False
    return True


def should_clarify_unlabeled_numeric_turn(
    text: str,
    *,
    pending_action: Optional[dict] = None,
    current_state: Optional[dict] = None,
    get_saved_location_text_fn: Callable[[], str],
) -> bool:
    raw = str(text or "").strip()
    if not re.fullmatch(r"\d{5}", raw):
        return False
    state = current_state if isinstance(current_state, dict) else {}
    if str(state.get("kind") or "").strip() in {"numeric_reference", "numeric_reference_clarify"} and str(state.get("value") or "").strip() == raw:
        return False
    action = pending_action if isinstance(pending_action, dict) else {}
    if str(action.get("kind") or "") == "weather_lookup" and str(action.get("status") or "") == "awaiting_location":
        return False
    try:
        return bool(str(get_saved_location_text_fn() or "").strip())
    except Exception:
        return True


def runtime_set_location_intent(
    text: str,
    *,
    pending_action: Optional[dict] = None,
    get_saved_location_text_fn: Callable[[], str],
) -> Optional[dict[str, object]]:
    raw = str(text or "").strip()
    if not re.fullmatch(r"\d{5}", raw):
        return None
    action = pending_action if isinstance(pending_action, dict) else {}
    if str(action.get("kind") or "") == "weather_lookup" and str(action.get("status") or "") == "awaiting_location":
        return None
    try:
        if str(get_saved_location_text_fn() or "").strip():
            return None
    except Exception:
        pass
    return {
        "handled": True,
        "intent": "set_location",
        "rule_name": "set_location_zip",
        "matched_rule_name": "set_location_zip",
        "location_value": raw,
        "location_kind": "zip",
        "location_ack_kind": "fact_only",
    }


def llm_classify_routing_intent(
    text: str,
    turns: Optional[list[tuple[str, str]]] = None,
    *,
    live_ollama_calls_allowed_fn: Callable[[], bool],
    chat_model_fn: Callable[[], str],
    ollama_base: str,
    get_saved_location_text_fn: Callable[[], str],
) -> Optional[dict[str, object]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    if not live_ollama_calls_allowed_fn():
        return None
    try:
        prompt = ROUTING_INTENT_PROMPT.format(text=raw[:500])
        payload = {
            "model": chat_model_fn(),
            "stream": False,
            "options": {"temperature": 0.0, "top_p": 1.0, "num_predict": 8},
            "messages": [{"role": "user", "content": prompt}],
        }
        response = requests.post(
            f"{ollama_base}/api/chat",
            json=payload,
            timeout=8,
        )
        response.raise_for_status()
        label = str(response.json().get("message", {}).get("content") or "").strip().lower()
        label = re.sub(r"[^a-z_]", "", (label.split() or [""])[0])
    except Exception:
        return None

    if label == "weather_lookup":
        saved_location = ""
        try:
            saved_location = str(get_saved_location_text_fn() or "").strip()
        except Exception:
            pass
        if saved_location:
            return {
                "handled": True,
                "intent": "weather_lookup",
                "rule_name": "weather_lookup",
                "matched_rule_name": "weather_lookup",
                "weather_mode": "current_location",
                "location_value": saved_location,
            }
        return {
            "handled": True,
            "intent": "weather_lookup",
            "rule_name": "weather_lookup",
            "matched_rule_name": "weather_lookup",
            "weather_mode": "clarify",
        }
    return None


def unlabeled_numeric_turn_reply(text: str) -> str:
    value = str(text or "").strip()
    return f"What does {value} refer to?"


def numeric_reference_guess_reply(value: str) -> str:
    clean = str(value or "").strip()
    return f"I don't know what {clean} refers to yet. Tell me what it refers to."


def numeric_reference_binding_reply(value: str, referent: str) -> str:
    clean_value = str(value or "").strip()
    clean_referent = str(referent or "").strip().rstrip(".!?")
    return f"Understood. In this chat, {clean_value} refers to {clean_referent}."


def emit_supervisor_intent_trace(
    intent_result: dict,
    *,
    user_text: str = "",
    intent_trace_preview_fn: Callable[[str], str],
) -> None:
    intent = str((intent_result or {}).get("intent") or "intent").strip().lower() or "intent"
    rule = str((intent_result or {}).get("matched_rule_name") or (intent_result or {}).get("rule_name") or "").strip()
    reason = ""

    if intent == "store_fact":
        reason = str((intent_result or {}).get("fact_text") or user_text).strip()
    elif intent == "set_location":
        reason = str((intent_result or {}).get("location_value") or user_text).strip()
    elif intent == "apply_correction":
        reason = str((intent_result or {}).get("user_correction_text") or user_text).strip()
    elif intent == "session_summary":
        reason = str((intent_result or {}).get("target") or "current_session_only").strip()
    else:
        reason = str(user_text or "").strip()

    label = rule or "supervisor"
    detail = intent_trace_preview_fn(reason)
    if detail:
        print(f"[INTENT] {intent} :: {label} :: {detail}", flush=True)
        return
    print(f"[INTENT] {intent} :: {label}", flush=True)