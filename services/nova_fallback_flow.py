from __future__ import annotations

import re
import time
from typing import Callable

from services.nova_self_evidence_reply import maybe_build_self_evidence_reply
from services.nova_turn_intent_trace import attach_turn_intent_evidence_packet
from services.nova_turn_intent_trace import build_turn_intent_evidence_packet
from services.nova_turn_intent_trace import CONVERSATION_CAN_COMPLETE_WITHOUT_TASK_KEY
from services.nova_turn_intent_trace import CONVERSATION_REPLY_FORM


def _conversation_can_be_complete_without_task(packet):
    payload = packet if isinstance(packet, dict) else {}
    contract = payload.get("answer_contract") if isinstance(payload.get("answer_contract"), dict) else {}
    return bool(contract.get(CONVERSATION_CAN_COMPLETE_WITHOUT_TASK_KEY))


def _reply_form(packet):
    payload = packet if isinstance(packet, dict) else {}
    contract = payload.get("answer_contract") if isinstance(payload.get("answer_contract"), dict) else {}
    return str(contract.get("reply_form") or "").strip()


def _semantic_status(packet):
    payload = packet if isinstance(packet, dict) else {}
    planner = payload.get("planner_frame") if isinstance(payload.get("planner_frame"), dict) else {}
    semantic = planner.get("semantic_tool_observation") if isinstance(planner.get("semantic_tool_observation"), dict) else {}
    return str(semantic.get("status") or "").strip()


def _tool_evidence_context(tool, tool_result, *, limit=2500):
    evidence = str(tool_result or "").strip()
    if not evidence:
        return ""
    tool_name = str(tool or "tool").strip() or "tool"
    return "TOOL EVIDENCE ({tool_name}; evidence for this turn, not a draft reply):\n{evidence}".format(
        tool_name=tool_name, evidence=evidence[:limit]
    )


def _conversation_generation_context(fallback_context, packet):
    context = fallback_context if isinstance(fallback_context, dict) else {}
    payload = packet if isinstance(packet, dict) else {}
    conversation = payload.get("conversation_frame") if isinstance(payload.get("conversation_frame"), dict) else {}
    lines = [
        "NOVA INTERNAL REPLY FORM:",
        "- reply_form: {}".format(CONVERSATION_REPLY_FORM),
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
        blocks.append("RECENT CHAT CONTEXT:\n{}".format(chat_context))
    if tool_context:
        blocks.append(tool_context)
    if state_context and include_session_state:
        blocks.append("SESSION EVIDENCE:\n{}".format(state_context))
    return "\n\n".join(blocks)


def _remove_trailing_question(reply):
    text = str(reply or "").strip()
    if not text.endswith("?"):
        return text
    cleaned = re.sub(r"(?s)(?:^|\s+)[^\n.!?]*\?\s*$", "", text).strip()
    return cleaned or text


def _complete_thoughts(text):
    value = str(text or "").strip()
    if not value:
        return []
    thoughts = []
    start = 0
    _pat = re.compile('[.!?][\\"\')\\]]*(?=\\s|$)')
    for match in _pat.finditer(value):
        thought = value[start: match.end()].strip()
        if thought:
            thoughts.append(thought)
        start = match.end()
    tail = value[start:].strip()
    if tail:
        thoughts.append(tail)
    return thoughts


def _is_question_thought(text):
    value = str(text or "").strip().rstrip("\"')]")
    return value.endswith("?")


def _shape_conversation_scoped_reply(reply):
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


def _render_intent_strategy_context(turn_intent, response_strategy):
    intent = turn_intent if isinstance(turn_intent, dict) else {}
    strategy = response_strategy if isinstance(response_strategy, dict) else {}
    level = str(intent.get("level") or "").strip()
    domain = str(intent.get("domain") or "").strip()
    strat = str(strategy.get("strategy") or "").strip()
    claim = str(intent.get("user_claim") or "").strip()
    confidence = float(intent.get("confidence") or 0.0)
    if not level or not strat or confidence < 0.4:
        return ""
    lines = [
        "INTENT UNDERSTANDING:",
        "  User intent level: {level} (domain: {domain}, confidence: {conf:.2f})".format(
            level=level, domain=domain, conf=confidence
        ),
    ]
    if claim:
        lines.append("  User's claim: {}".format(claim))
    strategy_guidance = {
        "accept_and_engage": "User is sharing or making a casual remark. Engage naturally -- do not run a tool unless asked.",
        "confirm_with_data": "User shared something. Your data confirms it. Affirm what they said with the actual data.",
        "correct_with_data": "User shared something. Your data tells a different story. Gently correct with accurate data.",
        "enrich_with_data":  "User shared something. Add relevant data to enrich the conversation.",
        "fulfill":           "User is requesting or commanding. Fulfill the request using available tool data.",
        "clarify":           "Intent is unclear. Ask a single focused question to clarify what the user needs.",
    }.get(strat, "")
    if strategy_guidance:
        lines.append("  Response strategy: {} -- {}".format(strat, strategy_guidance))
    return "\n".join(lines)


def build_fallback_context(
    *,
    text,
    turns,
    build_fallback_context_details_fn,
    action_ledger_add_step,
    pending_action=None,
    semantic_tool_observation=None,
    planner_decision="",
    tool="",
    tool_result="",
    turn_intent=None,
    response_strategy=None,
):
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
    intent_strategy_ctx = _render_intent_strategy_context(turn_intent, response_strategy)
    if intent_strategy_ctx:
        retrieved_context = "\n\n".join(part for part in [retrieved_context, intent_strategy_ctx] if part)
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
    text,
    turns,
    build_fallback_context_details_fn,
    action_ledger_add_step,
    pending_action=None,
    semantic_tool_observation=None,
    planner_decision="",
    tool="",
    tool_result="",
    turn_intent=None,
    response_strategy=None,
):
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
        turn_intent=turn_intent,
        response_strategy=response_strategy,
    )
    return {
        "handled": False,
        "retrieved_context": str(fallback_bundle.get("retrieved_context") or ""),
        "fallback_context": fallback_bundle.get("fallback_context") if isinstance(fallback_bundle.get("fallback_context"), dict) else {},
        "intent_evidence_packet": fallback_bundle.get("intent_evidence_packet") if isinstance(fallback_bundle.get("intent_evidence_packet"), dict) else {},
    }


def finalize_llm_fallback_reply(
    *,
    text,
    raw_user_text,
    input_source,
    retrieved_context,
    language_mix_spanish_pct,
    ollama_chat_fn,
    mem_enabled_fn,
    mem_should_store_fn,
    mem_add_fn,
    strip_mem_leak_fn,
    behavior_record_event_fn,
    action_ledger_add_step,
    preprocess_reply_fn=None,
    ensure_reply_fn,
    intent_evidence_packet=None,
    fallback_context=None,
):
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
