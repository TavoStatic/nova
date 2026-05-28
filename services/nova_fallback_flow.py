from __future__ import annotations

import re
import time
from typing import Callable

from services.nova_self_evidence_reply import maybe_build_self_evidence_reply
from services.nova_turn_intent_trace import attach_turn_intent_evidence_packet
from services.nova_turn_intent_trace import build_turn_intent_evidence_packet
from services.nova_turn_intent_trace import CONVERSATION_CAN_COMPLETE_WITHOUT_TASK_KEY
from services.nova_turn_intent_trace import CONVERSATION_REPLY_FORM


def _conversation_can_be_complete_without_task(packet: dict | None) -> bool:
    payload = packet if isinstance(packet, dict) else {}
    contract = payload.get("answer_contract") if isinstance(payload.get("answer_contract"), dict) else {}
    return bool(contract.get(CONVERSATION_CAN_COMPLETE_WITHOUT_TASK_KEY))


def _reply_form(packet: dict | None) -> str:
    payload = packet if isinstance(packet, dict) else {}
    contract = payload.get("answer_contract") if isinstance(payload.get("answer_contract"), dict) else {}
    return str(contract.get("reply_form") or "").strip()


def _semantic_status(packet: dict | None) -> str:
    payload = packet if isinstance(packet, dict) else {}
    planner = payload.get("planner_frame") if isinstance(payload.get("planner_frame"), dict) else {}
    semantic = planner.get("semantic_tool_observation") if isinstance(planner.get("semantic_tool_observation"), dict) else {}
    return str(semantic.get("status") or "").strip()


def _tool_evidence_context(tool: str, tool_result: str, *, limit: int = 2500) -> str:
    evidence = str(tool_result or "").strip()
    if not evidence:
        return ""
    tool_name = str(tool or "tool").strip() or "tool"
    return f"TOOL EVIDENCE ({tool_name}; evidence for this turn, not a draft reply):\n{evidence[:limit]}"


def _conversation_generation_context(fallback_context: dict | None, packet: dict | None) -> str:
    context = fallback_context if isinstance(fallback_context, dict) else {}
    payload = packet if isinstance(packet, dict) else {}
    conversation = payload.get("conversation_frame") if isinstance(payload.get("conversation_frame"), dict) else {}
    lines = [
        "NOVA INTERNAL REPLY FORM:",
        f"- reply_form: {CONVERSATION_REPLY_FORM}",
        "- evidence_scope: current_conversation",
    ]
    if str(conversation.get("previous_assistant_turn") or "").strip():
        lines.append("- recent_assistant_turn: available")
    rendered = "\n".join(lines)
    chat_context = str(context.get("chat_context") or "").strip()
    state_context = str(context.get("state_context") or "").strip()
    tool_context = str(context.get("tool_evidence_context") or "").strip()
    include_session_state = _semantic_status(packet) == "tool_evidence_available"
    blocks = [rendered] if rendered else []
    if chat_context:
        blocks.append(f"RECENT CHAT CONTEXT:\n{chat_context}")
    if tool_context:
        blocks.append(tool_context)
    if state_context and include_session_state:
        blocks.append(f"SESSION EVIDENCE:\n{state_context}")
    return "\n\n".join(blocks)


def _remove_trailing_question(reply: str) -> str:
    text = str(reply or "").strip()
    if not text.endswith("?"):
        return text
    cleaned = re.sub(r"(?s)(?:^|\s+)[^\n.!?]*\?\s*$", "", text).strip()
    return cleaned or text


def _complete_thoughts(text: str) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    thoughts: list[str] = []
    start = 0
    for match in re.finditer(r"[.!?][\"')\]]*(?=\s|$)", value):
        thought = value[start : match.end()].strip()
        if thought:
            thoughts.append(thought)
        start = match.end()
    tail = value[start:].strip()
    if tail:
        thoughts.append(tail)
    return thoughts


def _is_question_thought(text: str) -> bool:
    value = str(text or "").strip().rstrip("\"')]")
    return value.endswith("?")


def _shape_conversation_scoped_reply(reply: str) -> str:
    text = _remove_trailing_question(reply)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if paragraphs:
        text = paragraphs[0]
    thoughts = _complete_thoughts(text)
    for thought in thoughts:
        if not _is_question_thought(thought):
            return _remove_trailing_question(thought)
    if thoughts:
        return _remove_trailing_question(thoughts[0])
    return _remove_trailing_question(text)


def build_fallback_context(
    *,
    text: str,
    turns,
    build_fallback_context_details_fn: Callable[..., dict],
    action_ledger_add_step: Callable[..., None],
    pending_action: dict | None = None,
    semantic_tool_observation: dict | None = None,
    planner_decision: str = "",
    tool: str = "",
    tool_result: str = "",
) -> dict:
    raw_fallback_context = build_fallback_context_details_fn(text, turns)
    fallback_context = raw_fallback_context if isinstance(raw_fallback_context, dict) else {}
    tool_evidence_context = _tool_evidence_context(tool, tool_result)
    if tool_evidence_context:
        fallback_context = dict(fallback_context)
        fallback_context["tool_evidence_context"] = tool_evidence_context
    retrieved_context = str(fallback_context.get("context") or "")
    if tool_evidence_context:
        retrieved_context = "\n\n".join(part for part in [retrieved_context, tool_evidence_context] if part)
    intent_evidence_packet = build_turn_intent_evidence_packet(
        text=text,
        turns=turns if isinstance(turns, list) else [],
        pending_action=pending_action,
        fallback_context=fallback_context if isinstance(fallback_context, dict) else {},
        semantic_tool_observation=semantic_tool_observation,
        planner_decision=planner_decision,
        tool=tool,
        tool_result=tool_result,
    )
    retrieved_context = attach_turn_intent_evidence_packet(retrieved_context, intent_evidence_packet)
    action_ledger_add_step(
        "memory_context",
        "used" if str(fallback_context.get("learning_context") or "") else "empty",
        memory_used=bool(fallback_context.get("memory_used")),
        identity_used=bool(fallback_context.get("identity_used")),
        operational_identity_used=bool(fallback_context.get("operational_identity_used")),
        knowledge_used=bool(fallback_context.get("knowledge_used")),
        memory_chars=int(fallback_context.get("memory_chars") or 0),
        identity_chars=int(fallback_context.get("identity_chars") or 0),
        operational_identity_chars=int(fallback_context.get("operational_identity_chars") or 0),
        knowledge_chars=int(fallback_context.get("knowledge_chars") or 0),
    )
    chat_ctx = str(fallback_context.get("chat_context") or "")
    if chat_ctx:
        action_ledger_add_step("chat_context", "used", chars=len(chat_ctx))
    session_fact_sheet = str(fallback_context.get("session_fact_sheet") or "")
    if session_fact_sheet:
        action_ledger_add_step("session_fact_sheet", "used", chars=len(session_fact_sheet))
    action_ledger_add_step(
        "turn_intent_evidence",
        "attached",
        trace_authority=str(intent_evidence_packet.get("trace_authority") or ""),
        answer_authority=str(intent_evidence_packet.get("answer_authority") or ""),
    )
    return {
        "retrieved_context": retrieved_context,
        "fallback_context": fallback_context,
        "intent_evidence_packet": intent_evidence_packet,
    }


def prepare_fallback_flow(
    *,
    text: str,
    turns,
    build_fallback_context_details_fn: Callable[..., dict],
    action_ledger_add_step: Callable[..., None],
    pending_action: dict | None = None,
    semantic_tool_observation: dict | None = None,
    planner_decision: str = "",
    tool: str = "",
    tool_result: str = "",
) -> dict:
    fallback_bundle = build_fallback_context(
        text=text,
        turns=turns,
        build_fallback_context_details_fn=build_fallback_context_details_fn,
        action_ledger_add_step=action_ledger_add_step,
        pending_action=pending_action,
        semantic_tool_observation=semantic_tool_observation,
        planner_decision=planner_decision,
        tool=tool,
        tool_result=tool_result,
    )
    return {
        "handled": False,
        "retrieved_context": str(fallback_bundle.get("retrieved_context") or ""),
        "fallback_context": fallback_bundle.get("fallback_context") if isinstance(fallback_bundle.get("fallback_context"), dict) else {},
        "intent_evidence_packet": fallback_bundle.get("intent_evidence_packet") if isinstance(fallback_bundle.get("intent_evidence_packet"), dict) else {},
    }


def finalize_llm_fallback_reply(
    *,
    text: str,
    raw_user_text: str,
    input_source: str,
    retrieved_context: str,
    language_mix_spanish_pct: int,
    ollama_chat_fn: Callable[..., str],
    mem_enabled_fn: Callable[[], bool],
    mem_should_store_fn: Callable[[str], bool],
    mem_add_fn: Callable[[str, str, str], None],
    strip_mem_leak_fn: Callable[[str, str], str],
    behavior_record_event_fn: Callable[[str], None],
    action_ledger_add_step: Callable[..., None],
    preprocess_reply_fn: Callable[[str], str] | None = None,
    ensure_reply_fn: Callable[[str], str],
    intent_evidence_packet: dict | None = None,
    fallback_context: dict | None = None,
) -> dict:
    evidence_reply = maybe_build_self_evidence_reply(
        fallback_context=fallback_context,
        intent_evidence_packet=intent_evidence_packet,
    )
    if evidence_reply:
        action_ledger_add_step(
            "self_evidence",
            "answered",
            evidence_need=str((evidence_reply.get("reply_outcome") or {}).get("evidence_need") or ""),
        )
        out = dict(evidence_reply)
        out["reply"] = ensure_reply_fn(str(out.get("reply") or ""))
        return out

    behavior_record_event_fn("llm_fallback")
    action_ledger_add_step("llm_fallback", "invoked", retrieved_chars=len(retrieved_context))

    llm_started = time.perf_counter()
    reply_form = _reply_form(intent_evidence_packet)
    generation_context = retrieved_context
    if reply_form == CONVERSATION_REPLY_FORM:
        generation_context = _conversation_generation_context(fallback_context, intent_evidence_packet)
    ollama_kwargs = {
        "retrieved_context": generation_context,
        "language_mix_spanish_pct": language_mix_spanish_pct,
    }
    if reply_form == CONVERSATION_REPLY_FORM:
        ollama_kwargs["reply_form"] = reply_form
    reply = ollama_chat_fn(text, **ollama_kwargs)
    llm_time_ms = int((time.perf_counter() - llm_started) * 1000)
    post_started = time.perf_counter()
    if callable(preprocess_reply_fn):
        reply = preprocess_reply_fn(reply)
    if _conversation_can_be_complete_without_task(intent_evidence_packet):
        reply = _shape_conversation_scoped_reply(reply)

    if mem_enabled_fn() and mem_should_store_fn(raw_user_text):
        mem_add_fn("chat_user", input_source, raw_user_text)

    clean_reply = strip_mem_leak_fn(reply, retrieved_context)
    planner_decision = "llm_fallback"
    grounded = None
    reply_contract = ""
    reply_outcome = {}
    if isinstance(intent_evidence_packet, dict) and intent_evidence_packet:
        reply_outcome = {
            "kind": "llm_fallback",
            "intent_evidence_packet": dict(intent_evidence_packet),
        }

    return {
        "handled": True,
        "reply": ensure_reply_fn(clean_reply),
        "planner_decision": planner_decision,
        "grounded": grounded,
        "reply_contract": reply_contract,
        "reply_outcome": reply_outcome,
        "llm_time_ms": llm_time_ms,
        "post_time_ms": int((time.perf_counter() - post_started) * 1000),
    }
