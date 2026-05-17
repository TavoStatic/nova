from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional

import requests

ROUTING_TOOL_NAMES = (
    "none",
    "self_status",
    "weather_current_location",
    "weather_location",
    "web_fetch",
    "web_search",
    "web_research",
    "web_gather",
    "wikipedia_lookup",
    "stackexchange_search",
    "queue_status",
    "pulse",
    "system_check",
    "phase2_audit",
    "read",
    "find",
    "ls",
    "screen",
    "camera",
    "location_coords",
    "patch_apply",
    "patch_rollback",
    "update_now",
    "update_now_confirm",
    "update_now_cancel",
    "work_tree_next",
    "work_tree_execute",
    "work_tree_status",
    "work_tree_create",
)


ROUTING_INTENT_PROMPT = (
    "You classify whether a local AI runtime should use a tool for the next user turn.\n"
    "Use the actual goal in the conversation, not keyword matching or surface phrasing.\n"
    "Return JSON only with this shape: "
    '{"tool":"'
    + "|".join(ROUTING_TOOL_NAMES)
    + '",'
    '"args":[],"confidence":0.0,"reason":""}.\n'
    "Tool purposes: self_status reads Nova's live operational condition; weather tools read weather; "
    "web tools retrieve external pages or research; queue_status and pulse read Nova queues and pulse; "
    "system_check reads local runtime checks; read/find/ls inspect local files; screen/camera inspect local input; "
    "patch/update tools operate on governed update flows.\n"
    "Work Tree tools continue, inspect, execute, or create Nova's internal work plan.\n"
    "Choose none when the user is discussing a previous answer, asking why a tool failed, "
    "sharing context, or asking for normal conversation.\n"
    "Choose a tool only when the user goal cannot be answered honestly without that tool."
)


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
    is_student_data_broad_query_fn: Callable[[str], bool],
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
    if is_student_data_broad_query_fn(candidate) or is_local_knowledge_topic_query_fn(candidate):
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
            "allowed": False,
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
    intent_trace_preview_fn: Callable[[str], str] | None = None,
    supervisor_phase_record_fn: Callable[..., dict] | None = None,
    runtime_scope: Optional[dict[str, object]] = None,
) -> dict:
    scope = runtime_scope if isinstance(runtime_scope, dict) else {}
    if intent_trace_preview_fn is None:
        candidate = scope.get("_intent_trace_preview")
        intent_trace_preview_fn = candidate if callable(candidate) else intent_trace_preview
    if supervisor_phase_record_fn is None:
        candidate = scope.get("_supervisor_phase_record")
        supervisor_phase_record_fn = candidate if callable(candidate) else (
            lambda payload, phase: supervisor_phase_record(
                payload,
                phase=phase,
                supervisor_result_has_route_fn=supervisor_result_has_route,
                supervisor_candidate_trace_fn=supervisor_candidate_trace,
            )
        )
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
            "[WARN] Turn bypassed supervisor intent phase â€” this will be an error soon"
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
    is_student_data_broad_query_fn: Callable[[str], bool],
    is_local_knowledge_topic_query_fn: Callable[[str], bool],
) -> bool:
    del (
        text,
        looks_like_open_fallback_turn_fn,
        is_explicit_command_like_fn,
        is_location_request_fn,
        normalize_turn_text_fn,
        is_student_data_broad_query_fn,
        is_local_knowledge_topic_query_fn,
    )
    return False


def should_clarify_unlabeled_numeric_turn(
    text: str,
    *,
    pending_action: Optional[dict] = None,
    current_state: Optional[dict] = None,
    get_saved_location_text_fn: Callable[[], str],
) -> bool:
    del text, pending_action, current_state, get_saved_location_text_fn
    return False


def runtime_set_location_intent(
    text: str,
    *,
    pending_action: Optional[dict] = None,
    get_saved_location_text_fn: Callable[[], str],
) -> Optional[dict[str, object]]:
    del text, pending_action, get_saved_location_text_fn
    return None


def llm_classify_routing_intent(
    text: str,
    turns: Optional[list[tuple[str, str]]] = None,
    *,
    pending_action: Optional[dict] = None,
    return_none_payload: bool = False,
    live_ollama_calls_allowed_fn: Callable[[], bool],
    chat_model_fn: Callable[[], str],
    ollama_base: str,
    get_saved_location_text_fn: Callable[[], str],
    requests_post_fn: Callable[..., object] | None = None,
) -> Optional[dict[str, object]]:
    user_text = str(text or "").strip()
    if not user_text:
        return None
    try:
        if not live_ollama_calls_allowed_fn():
            return None
    except Exception:
        return None

    recent_turns: list[dict[str, str]] = []
    for role, content in list(turns or [])[-8:]:
        role_name = str(role or "").strip().lower()
        if role_name not in {"user", "assistant"}:
            continue
        recent_turns.append({"role": role_name, "content": str(content or "").strip()[:900]})

    pending = pending_action if isinstance(pending_action, dict) else {}
    saved_location = ""
    try:
        saved_location = str(get_saved_location_text_fn() or "").strip()
    except Exception:
        saved_location = ""

    request_payload = {
        "turn": user_text,
        "recent_turns": recent_turns,
        "pending_action": pending,
        "saved_location_available": bool(saved_location),
    }
    payload = {
        "model": chat_model_fn(),
        "stream": False,
        "options": {"temperature": 0.0, "top_p": 0.8},
        "messages": [
            {"role": "system", "content": ROUTING_INTENT_PROMPT},
            {"role": "user", "content": json.dumps(request_payload, ensure_ascii=True)},
        ],
    }

    post = requests_post_fn if callable(requests_post_fn) else requests.post
    try:
        response = post(f"{str(ollama_base or '').rstrip('/')}/api/chat", json=payload, timeout=4.0)
        response.raise_for_status()
        content = str(response.json().get("message", {}).get("content") or "").strip()
    except Exception:
        return None

    return _coerce_tool_intent_payload(
        content,
        user_text=user_text,
        return_none_payload=return_none_payload,
    )


def _coerce_none_payload(parsed: dict[str, object], *, reason: str = "") -> dict[str, object]:
    try:
        confidence = float(parsed.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "tool": "none",
        "args": [],
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(parsed.get("reason") or reason or "").strip()[:240],
        "source": "llm_intent",
    }


def _coerce_tool_intent_payload(
    content: str,
    *,
    user_text: str,
    return_none_payload: bool = False,
) -> Optional[dict[str, object]]:
    raw = str(content or "").strip()
    if not raw:
        return None
    parsed: object
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"tool": raw.strip().lower(), "args": []}
    if not isinstance(parsed, dict):
        return None

    allowed_tools = set(ROUTING_TOOL_NAMES) - {"none"}
    aliases = {
        "nova_status": "self_status",
        "runtime_status": "self_status",
        "internal_status": "self_status",
        "self_report": "self_status",
        "weather_lookup": "weather_current_location",
        "current_weather": "weather_current_location",
        "research": "web_research",
        "wiki": "wikipedia_lookup",
        "stack_overflow": "stackexchange_search",
        "queue": "queue_status",
        "nova_pulse": "pulse",
        "diagnostics": "system_check",
        "general_chat": "none",
        "chat": "none",
        "conversation": "none",
    }
    tool = str(parsed.get("tool") or parsed.get("intent") or "").strip().lower()
    tool = aliases.get(tool, tool)
    if tool in {"", "none", "no_tool"}:
        return _coerce_none_payload(parsed) if return_none_payload else None
    if tool not in allowed_tools:
        return _coerce_none_payload(parsed, reason=f"unsupported_tool:{tool}") if return_none_payload else None

    args_raw = parsed.get("args")
    args = [str(item).strip() for item in list(args_raw or []) if str(item).strip()] if isinstance(args_raw, list) else []
    query = str(parsed.get("query") or parsed.get("url") or parsed.get("location") or parsed.get("path") or "").strip()
    if query and not args:
        args = [query]
    if tool in {"web_search", "web_research", "stackexchange_search"} and not args:
        args = [user_text]
    if tool == "wikipedia_lookup" and not args:
        args = [user_text]
    if tool in {"web_fetch", "web_gather"} and not args:
        url_match = re.search(r"https?://[\w\-\./:?=&%]+", user_text)
        if not url_match:
            return _coerce_none_payload(parsed, reason=f"missing_url:{tool}") if return_none_payload else None
        args = [url_match.group(0)]
    if tool == "weather_location" and not args:
        tool = "weather_current_location"
    if tool in {"read", "find", "location_coords", "patch_apply", "update_now_confirm"} and not args:
        return _coerce_none_payload(parsed, reason=f"missing_args:{tool}") if return_none_payload else None
    if tool == "camera" and not args:
        args = ["what do you see"]

    try:
        confidence = float(parsed.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "tool": tool,
        "args": args,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(parsed.get("reason") or "").strip()[:240],
        "source": "llm_intent",
    }


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

