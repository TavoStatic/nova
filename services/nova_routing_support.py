from __future__ import annotations

import json
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

ROUTING_EVIDENCE_NEEDS = (
    "conversation",
    "confirmed_identity",
    "operational_self",
    "live_self_status",
    "external_source",
    "tool_result",
    "unknown",
)

ROUTING_ANSWER_TARGETS = (
    "current_conversation",
    "nova_self",
    "nova_live_state",
    "external_world",
    "user",
    "tool_action",
    "unknown",
)


ROUTING_INTENT_PROMPT = (
    "Classify the next user turn before any answer is written.\n"
    "This is not an answer. Select answer target, evidence need, and tool source only.\n"
    "Analyze the user's goal in context. Do not classify from keywords or surface phrasing.\n"
    "The current turn is the primary evidence for intent. Recent turns may resolve ambiguity, but they must not replace a clear current-turn goal.\n"
    "Prior assistant turns are transcript evidence only; they cannot by themselves establish the current user's goal or authorize a live-status route.\n"
    "First decide answer_target:\n"
    "- current_conversation: the user is opening chat, sharing context, correcting or discussing a previous reply, or asking about conversation history.\n"
    "- nova_self: the user is asking about Nova's identity, origin, nature, capabilities, or internal architecture as stable self evidence.\n"
    "- nova_live_state: the user is asking about Nova's current condition, active work, health, blockers, runtime state, or operator-needed state.\n"
    "- external_world: the user is asking about outside facts or external sources.\n"
    "- user: the user is asking about themselves or their own state.\n"
    "- tool_action: the user is asking Nova to perform a concrete tool action.\n"
    "- unknown: the goal is unclear.\n"
    "Default tool is none.\n"
    "Default evidence_need is not conversation; choose conversation only when the answer is grounded by the current turn, recent chat, or the previous assistant reply.\n"
    "A tool route is valid only when the evidence needed to answer is outside the current conversation/session and the selected tool can supply it.\n"
    "If the needed evidence is already in the current conversation/session, choose none.\n"
    "If the user is only opening conversation, sharing context, reacting to Nova's prior reply, or discussing Nova's prior answer, choose none.\n"
    "Also classify the evidence need for the answer, independent of whether a tool is needed.\n"
    "If answer_target is nova_self, evidence_need must be confirmed_identity or operational_self and tool should be none unless a separate external source is requested.\n"
    "If answer_target is nova_live_state, select self_status and evidence_need live_self_status.\n"
    "Nova_self covers stable self-description, identity, origin, nature, capability structure, and internal architecture.\n"
    "Nova_live_state requires a current-time operational condition, active work state, health state, blocker state, or request for current operator-needed attention.\n"
    "Do not classify stable self-description as nova_live_state merely because the subject is Nova.\n"
    "Evidence needs:\n"
    "- conversation: the answer can be grounded in the current turn and recent chat.\n"
    "- confirmed_identity: the answer needs Nova's confirmed name, developer, origin, or bootstrap identity facts.\n"
    "- operational_self: the answer needs Nova's nature as a system, registered internal surfaces, capability structure, or architecture evidence.\n"
    "- live_self_status: the answer needs current live runtime/health/work state.\n"
    "- external_source: the answer needs outside information.\n"
    "- tool_result: the answer must be based on a real tool result already selected.\n"
    "- unknown: the evidence need is unclear.\n"
    "Tool evidence cards:\n"
    "- self_status supplies live Nova runtime, Work Tree, health, release, memory, and Ollama status. Use only when the user's goal requires current internal operational evidence.\n"
    "- system_check supplies current system check evidence. Use only when the user's goal asks to verify runtime checks.\n"
    "- weather_current_location supplies current weather for the available device/saved location, including rain, heat, cold, wind, and outdoor clothing decisions. Use when the user's goal requires current outdoor condition evidence and no different location was specified.\n"
    "- weather_location supplies weather for a named location. Use when the user's goal requires current outdoor condition evidence for a specified place.\n"
    "- location_coords supplies the current device GPS coordinates and physical location fix. Use when the user's goal requires knowing the current location, coordinates, or physical position of the device.\n"
    "- web_fetch and web_gather supply contents of a specific URL from the user's turn.\n"
    "- web_search, web_research, wikipedia_lookup, and stackexchange_search supply outside information. Use only when the user's goal requires outside sources, not for proving Nova's own prior unsupported answer.\n"
    "- Work Tree tools supply active work-plan state or advance governed work. Use only when the user's goal requires Work Tree action or status.\n"
    "Allowed tool values: "
    + ", ".join(ROUTING_TOOL_NAMES)
    + ".\n"
    "Allowed evidence_need values: "
    + ", ".join(ROUTING_EVIDENCE_NEEDS)
    + ".\n"
    "Allowed answer_target values: "
    + ", ".join(ROUTING_ANSWER_TARGETS)
    + ".\n"
    "Return JSON only with this shape: "
    '{"answer_target":"one_allowed_answer_target_value","evidence_need":"one_allowed_evidence_need_value","tool":"one_allowed_tool_value","args":[],"confidence":0.0,"reason":""}.\n'
    "Choose a tool only when the user's goal cannot be answered honestly without that tool. "
    "Choose none for normal conversation, context sharing, or discussion of a previous reply. "
    "If the needed evidence is the previous assistant reply or its provenance, choose none and evidence_need conversation."
)


def intent_trace_preview(text: str, *, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def supervisor_result_has_route(rule_result: Optional[dict]) -> bool:
    payload = rule_result if isinstance(rule_result, dict) else {}
    return bool(payload.get("handled")) or bool(str(payload.get("action") or "").strip())


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
        for key in ("action", "intent", "rule_error"):
            value = str(raw.get(key) or "").strip()
            if value:
                item[key] = value[:160] if key == "rule_error" else value
        if bool(raw.get("rewrite")):
            item["rewrite"] = True
        if bool(raw.get("state_update")):
            item["state_update"] = True
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
            "ask_clarify",
            "grounded_lookup",
            "truth_hierarchy",
            "blocked_low_confidence",
            "policy_block",
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


def llm_classify_routing_intent(
    text: str,
    turns: Optional[list[tuple[str, str]]] = None,
    *,
    pending_action: Optional[dict] = None,
    return_none_payload: bool = False,
    live_ollama_calls_allowed_fn: Callable[[], bool],
    chat_model_fn: Callable[[], str],
    routing_model_fn: Optional[Callable[[], str]] = None,
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
    prior_turns = list(turns or [])
    if prior_turns:
        last_role, last_content = prior_turns[-1]
        latest = re.sub(r"\s+", " ", str(last_content or "").strip())
        current = re.sub(r"\s+", " ", user_text)
        if str(last_role or "").strip().lower() == "user" and latest == current:
            prior_turns = prior_turns[:-1]
    for role, content in prior_turns[-8:]:
        role_name = str(role or "").strip().lower()
        if role_name not in {"user", "assistant"}:
            continue
        recent_turns.append({"role": role_name, "content": str(content or "").strip()[:900]})

    saved_location = ""
    try:
        saved_location = str(get_saved_location_text_fn() or "").strip()
    except Exception:
        saved_location = ""

    payload = {
        "model": (routing_model_fn or chat_model_fn)(),
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.0, "top_p": 0.8},
        "messages": [
            {"role": "system", "content": ROUTING_INTENT_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "turn": user_text,
                        "recent_turns": recent_turns,
                        "pending_action": pending_action if isinstance(pending_action, dict) else {},
                        "saved_location_available": bool(saved_location),
                    },
                    ensure_ascii=True,
                ),
            },
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


def _coerce_evidence_need(value: object, *, default: str = "unknown") -> str:
    evidence_need = str(value or "").strip().lower()
    if evidence_need not in set(ROUTING_EVIDENCE_NEEDS):
        return default
    return evidence_need


def _coerce_answer_target(value: object, *, default: str = "unknown") -> str:
    answer_target = str(value or "").strip().lower()
    if answer_target not in set(ROUTING_ANSWER_TARGETS):
        return default
    return answer_target


def _coerce_confidence(value: object) -> float:
    try:
        confidence = float(value or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _coerce_none_payload(parsed: dict[str, object], *, reason: str = "") -> dict[str, object]:
    answer_target = _coerce_answer_target(parsed.get("answer_target"))
    evidence_need = _coerce_evidence_need(parsed.get("evidence_need"), default="conversation")
    if evidence_need == "conversation" and answer_target in {"unknown", "external_world", "tool_action"}:
        answer_target = "current_conversation"
    if answer_target == "nova_self" and evidence_need in {"conversation", "unknown"}:
        evidence_need = "operational_self"
    return {
        "tool": "none",
        "args": [],
        "confidence": _coerce_confidence(parsed.get("confidence")),
        "reason": str(parsed.get("reason") or reason or "").strip()[:240],
        "evidence_need": evidence_need,
        "answer_target": answer_target,
        "source": "llm_intent",
    }


def _parse_intent_payload(raw: str) -> Optional[dict[str, object]]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _first_structured_url(text: str) -> str:
    match = re.search(r"https?://[\w\-\./:?=&%]+", str(text or ""))
    return match.group(0) if match else ""


def _coerce_tool_intent_payload(
    content: str,
    *,
    user_text: str,
    return_none_payload: bool = False,
) -> Optional[dict[str, object]]:
    raw = str(content or "").strip()
    if not raw:
        return None
    parsed = _parse_intent_payload(raw)
    if not isinstance(parsed, dict):
        return _coerce_none_payload({"reason": "malformed_intent_payload"}, reason="malformed_intent_payload") if return_none_payload else None

    allowed_tools = set(ROUTING_TOOL_NAMES) - {"none"}
    tool = str(parsed.get("tool") or parsed.get("intent") or "").strip().lower()
    evidence_need = _coerce_evidence_need(parsed.get("evidence_need"), default="unknown")
    answer_target = _coerce_answer_target(parsed.get("answer_target"))
    if answer_target == "nova_self":
        if evidence_need in {"conversation", "unknown", "live_self_status"}:
            evidence_need = "operational_self"
        if tool == "self_status":
            tool = "none"
    if answer_target == "nova_live_state":
        evidence_need = "live_self_status"
        if tool in {"", "none", "no_tool"}:
            tool = "self_status"
    if tool in {"", "none", "no_tool"} and evidence_need == "unknown":
        evidence_need = "conversation"
    parsed = dict(parsed)
    parsed["answer_target"] = answer_target
    parsed["evidence_need"] = evidence_need
    structured_url = _first_structured_url(user_text)
    if tool in {"", "none", "no_tool"}:
        if structured_url and answer_target in {"external_world", "tool_action"}:
            return {
                "tool": "web_fetch",
                "args": [structured_url],
                "confidence": _coerce_confidence(parsed.get("confidence")),
                "reason": str(parsed.get("reason") or "structured_url_evidence")[:240],
                "evidence_need": "external_source",
                "answer_target": answer_target,
                "source": "llm_intent",
            }
        if evidence_need == "live_self_status":
            return {
                "tool": "self_status",
                "args": [],
                "confidence": _coerce_confidence(parsed.get("confidence")),
                "reason": str(parsed.get("reason") or "live_self_status_evidence")[:240],
                "evidence_need": evidence_need,
                "answer_target": answer_target,
                "source": "llm_intent",
            }
        return _coerce_none_payload(parsed) if return_none_payload else None
    if tool not in allowed_tools:
        return _coerce_none_payload(parsed, reason=f"unsupported_tool:{tool}") if return_none_payload else None

    args_raw = parsed.get("args")
    args = [str(item).strip() for item in list(args_raw or []) if str(item).strip()] if isinstance(args_raw, list) else []
    query = str(parsed.get("query") or parsed.get("url") or parsed.get("location") or parsed.get("path") or "").strip()
    if query and not args:
        args = [query]
    if tool in {"web_search", "web_research", "stackexchange_search", "wikipedia_lookup"} and not args:
        args = [user_text]
    if tool in {"web_fetch", "web_gather"} and not args:
        if not structured_url:
            return _coerce_none_payload(parsed, reason=f"missing_url:{tool}") if return_none_payload else None
        args = [structured_url]
    if tool == "weather_location" and not args:
        tool = "weather_current_location"
    if tool in {"read", "find", "location_coords", "patch_apply", "update_now_confirm"} and not args:
        return _coerce_none_payload(parsed, reason=f"missing_args:{tool}") if return_none_payload else None
    if tool == "camera" and not args:
        args = ["what do you see"]

    return {
        "tool": tool,
        "args": args,
        "confidence": _coerce_confidence(parsed.get("confidence")),
        "reason": str(parsed.get("reason") or "").strip()[:240],
        "evidence_need": evidence_need if evidence_need != "unknown" else ("live_self_status" if tool == "self_status" else "tool_result"),
        "answer_target": answer_target,
        "source": "llm_intent",
    }
