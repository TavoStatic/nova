from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "1.0.0"
LAST_ASSISTANT_REPEATS_KEY = "last_assistant_repeats_earlier_assistant"
CONVERSATION_CAN_COMPLETE_WITHOUT_TASK_KEY = "conversation_can_be_complete_without_task"
CONVERSATION_REPLY_FORM = "conversation_turn"


def _compact_text(value: object, *, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _normal_turns(turns: object) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    if not isinstance(turns, list):
        return normalized
    for raw in turns:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        role = str(raw[0] or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        normalized.append((role, str(raw[1] or "")))
    return normalized


def _previous_assistant_turn(turns: list[tuple[str, str]], current_text: str) -> str:
    prior_turns = list(turns)
    if prior_turns:
        last_role, last_text = prior_turns[-1]
        if last_role == "user" and _compact_text(last_text, limit=1000) == _compact_text(current_text, limit=1000):
            prior_turns = prior_turns[:-1]
    for role, content in reversed(prior_turns):
        if role == "assistant" and str(content or "").strip():
            return _compact_text(content, limit=900)
    return ""


def _last_assistant_repeats_earlier_assistant(turns: list[tuple[str, str]], current_text: str) -> bool:
    prior_turns = list(turns)
    if prior_turns:
        last_role, last_text = prior_turns[-1]
        if last_role == "user" and _compact_text(last_text, limit=1000) == _compact_text(current_text, limit=1000):
            prior_turns = prior_turns[:-1]
    assistant_turns = [
        _compact_text(content, limit=1000).casefold()
        for role, content in prior_turns
        if role == "assistant" and _compact_text(content, limit=1000)
    ]
    if len(assistant_turns) < 2:
        return False
    return assistant_turns[-1] in set(assistant_turns[:-1])


def _safe_confidence(payload: dict[str, Any]) -> float:
    try:
        value = float(payload.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value))


def _semantic_tool_observation(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else payload
    if not isinstance(intent, dict):
        return {}
    out: dict[str, Any] = {
        "tool": str(intent.get("tool") or "").strip(),
        "args": [str(item).strip() for item in list(intent.get("args") or []) if str(item).strip()]
        if isinstance(intent.get("args"), list)
        else [],
        "confidence": _safe_confidence(intent),
        "reason": _compact_text(intent.get("reason") or "", limit=240),
        "evidence_need": str(intent.get("evidence_need") or "").strip(),
        "answer_target": str(intent.get("answer_target") or "").strip(),
        "source": str(intent.get("source") or "").strip(),
    }
    status = str(payload.get("status") or "").strip()
    if status:
        out["status"] = status
    duration_ms = payload.get("duration_ms")
    if isinstance(duration_ms, int):
        out["duration_ms"] = duration_ms
    return {key: value for key, value in out.items() if value not in ("", [], None)}


def _semantic_conversation_scope(semantic_observation: dict[str, Any]) -> bool:
    return (
        str(semantic_observation.get("answer_target") or "").strip() == "current_conversation"
        and str(semantic_observation.get("evidence_need") or "").strip() == "conversation"
        and str(semantic_observation.get("tool") or "").strip() in {"", "none"}
    )


def build_turn_intent_evidence_packet(
    *,
    text: str,
    turns: list[tuple[str, str]] | None,
    pending_action: dict | None = None,
    fallback_context: dict | None = None,
    semantic_tool_observation: dict | None = None,
    planner_decision: str = "",
    tool: str = "",
    tool_result: str = "",
) -> dict[str, Any]:
    normalized_turns = _normal_turns(turns or [])
    context = fallback_context if isinstance(fallback_context, dict) else {}
    pending = pending_action if isinstance(pending_action, dict) else {}
    tool_output = str(tool_result or "").strip()
    semantic_observation = _semantic_tool_observation(semantic_tool_observation)

    evidence_items = [
        {
            "name": "current_user_turn",
            "available": bool(str(text or "").strip()),
            "chars": len(str(text or "")),
        },
        {
            "name": "recent_chat_context",
            "available": bool(str(context.get("chat_context") or "").strip()),
            "chars": len(str(context.get("chat_context") or "")),
        },
        {
            "name": "session_state_context",
            "available": bool(str(context.get("state_context") or "").strip()) or bool(pending),
            "chars": len(str(context.get("state_context") or "")),
        },
        {
            "name": "learning_context",
            "available": bool(str(context.get("learning_context") or "").strip()),
            "chars": len(str(context.get("learning_context") or "")),
        },
        {
            "name": "confirmed_identity_context",
            "available": bool(context.get("identity_used")),
            "chars": int(context.get("identity_chars") or 0),
        },
        {
            "name": "operational_self_context",
            "available": bool(context.get("operational_identity_used")),
            "chars": int(context.get("operational_identity_chars") or 0),
        },
        {
            "name": "tool_result",
            "available": bool(tool_output),
            "chars": len(tool_output),
        },
    ]

    conversation_scope = _semantic_conversation_scope(semantic_observation)
    return {
        "schema": "nova.turn_intent_evidence",
        "version": SCHEMA_VERSION,
        "trace_authority": "hypothesis_only",
        "answer_authority": "available_evidence",
        "current_turn": _compact_text(text, limit=900),
        "conversation_frame": {
            "turn_count": len(normalized_turns),
            "current_user_turn_is_latest": bool(normalized_turns and normalized_turns[-1][0] == "user"),
            "previous_assistant_turn": _previous_assistant_turn(normalized_turns, text),
            LAST_ASSISTANT_REPEATS_KEY: _last_assistant_repeats_earlier_assistant(normalized_turns, text),
        },
        "planner_frame": {
            "decision": str(planner_decision or "").strip(),
            "tool": str(tool or "").strip(),
            "semantic_tool_observation": semantic_observation,
        },
        "available_evidence": evidence_items,
        "answer_contract": {
            "infer_intent_from_turn_and_conversation": True,
            "trace_is_route_authority": False,
            "evidence_is_claim_authority": True,
            "tool_route_requires_external_evidence_gap": True,
            CONVERSATION_CAN_COMPLETE_WITHOUT_TASK_KEY: conversation_scope,
            "reply_form": CONVERSATION_REPLY_FORM if conversation_scope else "evidence_bound_reply",
        },
    }


def render_turn_intent_evidence_packet(packet: dict[str, Any] | None) -> str:
    if not isinstance(packet, dict) or not packet:
        return ""
    conversation = packet.get("conversation_frame") if isinstance(packet.get("conversation_frame"), dict) else {}
    planner = packet.get("planner_frame") if isinstance(packet.get("planner_frame"), dict) else {}
    semantic = planner.get("semantic_tool_observation") if isinstance(planner.get("semantic_tool_observation"), dict) else {}
    evidence_items = [item for item in list(packet.get("available_evidence") or []) if isinstance(item, dict)]
    available = {
        str(item.get("name") or "").strip(): item
        for item in evidence_items
        if bool(item.get("available")) and str(item.get("name") or "").strip()
    }

    lines = [
        "NOVA INTERNAL EVIDENCE SUMMARY (private context; do not mention this section to the user):",
        "- Infer the user's goal from the current turn and recent conversation.",
        "- Route observations are advisory only; evidence decides what claims are supportable.",
        "- The current user turn is the answer target; prior assistant turns are transcript evidence, not draft replies.",
    ]
    previous = _compact_text(conversation.get("previous_assistant_turn") or "", limit=500)
    if previous:
        lines.append("- A prior assistant reply is available in the recent transcript.")
    if "recent_chat_context" in available:
        lines.append("- Recent chat context is available.")
    if "session_state_context" in available:
        lines.append("- Session state context is available.")
    if "learning_context" in available:
        lines.append("- Learning context is available.")
    if "confirmed_identity_context" in available:
        lines.append("- Confirmed Nova identity evidence is available.")
    if "operational_self_context" in available:
        lines.append("- Operational Nova self evidence is available.")
    if "tool_result" in available:
        lines.append("- A real tool result is available.")
    semantic_status = str(semantic.get("status") or "").strip()
    semantic_tool = str(semantic.get("tool") or "").strip()
    contract = packet.get("answer_contract") if isinstance(packet.get("answer_contract"), dict) else {}
    if bool(contract.get(CONVERSATION_CAN_COMPLETE_WITHOUT_TASK_KEY)):
        lines.append(
            "- The current turn is conversation-scoped; do not convert it into a task, help flow, confirmation loop, or closing question."
        )
    if semantic_status and semantic_status != "none":
        suffix = f" for {semantic_tool}" if semantic_tool else ""
        lines.append(f"- A tool route observation was recorded{suffix}, but it is not answer authority.")
    return "\n".join(lines)


def attach_turn_intent_evidence_packet(retrieved_context: str, packet: dict[str, Any] | None) -> str:
    rendered = render_turn_intent_evidence_packet(packet)
    context = str(retrieved_context or "").strip()
    if rendered and context:
        return f"{rendered}\n\n{context}"
    return rendered or context
