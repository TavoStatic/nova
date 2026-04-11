from __future__ import annotations

import json
from typing import Callable

from services import nova_planner_contract


def execute_reply_sequence(
    *,
    turns: list[tuple[str, str]],
    text: str,
    pending_action: dict | None,
    prefer_web_for_data_queries: bool,
    language_mix_spanish_pct: int,
    session,
    trace: Callable[..., None],
    normalize_reply: Callable[[str], str],
    ensure_reply: Callable[[str], str],
    core,
    is_developer_profile_request: Callable[[str], bool],
    developer_profile_reply: Callable[[list[tuple[str, str]], str], str],
    is_location_request: Callable[[str], bool],
    location_reply: Callable[[], str],
    is_web_preferred_data_query: Callable[[str], bool],
    is_session_recap_request: Callable[[str], bool],
    session_recap_reply: Callable[[list[tuple[str, str]], str], str],
    is_assistant_name_query: Callable[[str], bool],
    assistant_name_reply: Callable[[str], str],
    is_developer_full_name_query: Callable[[str], bool],
    developer_full_name_reply: Callable[[], str],
    is_name_origin_question: Callable[[str], bool],
    is_peims_attendance_rules_query: Callable[[str], bool],
    peims_attendance_rules_reply: Callable[[], str],
    is_conversational_clarification: Callable[[str], bool],
    clarification_reply: Callable[[list[tuple[str, str]]], str],
    is_deep_search_followup_request: Callable[[str], bool],
    infer_research_query_from_turns: Callable[[list[tuple[str, str]]], str],
    build_grounded_answer: Callable[[str], str],
    build_local_topic_digest_answer: Callable[[str], str],
    is_groundable_factual_query: Callable[[str], bool],
    developer_color_reply: Callable[[list[tuple[str, str]]], str],
    developer_bilingual_reply: Callable[[list[tuple[str, str]]], str],
    color_reply: Callable[[list[tuple[str, str]]], str],
    animal_reply: Callable[[list[tuple[str, str]]], str],
    ensure_active_work_tree_fn: Callable[[str], str] | None = None,
    planner_before_deterministic_content: bool = False,
    stop_before_llm_fallback: bool = False,
) -> tuple[str, dict]:
    low = text.lower()
    handled_truth, truth_reply, truth_source, truth_grounded = core.truth_hierarchy_answer(text)
    if handled_truth:
        trace("truth_hierarchy", "matched", tool=str(truth_source or ""), grounded=bool(truth_grounded))
        reply = truth_reply
        used_hard_answer = False
        if is_developer_profile_request(text):
            hard = core.hard_answer(text)
            if hard:
                reply = hard
                used_hard_answer = True
            elif reply.lower().startswith("uncertain. no structured identity fact"):
                reply = developer_profile_reply(turns, text)
        elif reply.lower().startswith("uncertain. no structured identity fact"):
            if is_location_request(text):
                reply = location_reply()
            else:
                hard = core.hard_answer(text)
                if hard:
                    reply = hard
                    used_hard_answer = True
        final_reply = ensure_reply(reply) if used_hard_answer else normalize_reply(reply)
        return final_reply, {
            "planner_decision": "truth_hierarchy",
            "tool": str(truth_source or ""),
            "tool_args": {"query": text},
            "tool_result": str(reply or ""),
            "grounded": bool(truth_grounded),
        }
    trace("truth_hierarchy", "not_matched")

    hard = core.hard_answer(text)
    if hard:
        trace("hard_answer", "matched", grounded=True)
        reply = ensure_reply(hard)
        return reply, {
            "planner_decision": "deterministic",
            "tool": "hard_answer",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    trace("hard_answer", "not_matched")

    if planner_before_deterministic_content:
        planner_outcome = nova_planner_contract.maybe_handle_planner_sequence(
            text=text,
            turns=turns,
            pending_action=pending_action,
            prefer_web_for_data_queries=prefer_web_for_data_queries,
            session=session,
            core=core,
            trace=trace,
            normalize_reply=normalize_reply,
            is_web_preferred_data_query=is_web_preferred_data_query,
            ensure_active_work_tree_fn=ensure_active_work_tree_fn,
        )
        if planner_outcome is not None:
            return planner_outcome

    if is_session_recap_request(text):
        trace("deterministic_reply", "matched", detail="session_recap")
        reply = session_recap_reply(turns, text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "session_recap",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if is_assistant_name_query(text):
        trace("deterministic_reply", "matched", detail="assistant_name")
        reply = assistant_name_reply(text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "assistant_name",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if is_developer_full_name_query(text):
        trace("deterministic_reply", "matched", detail="developer_full_name")
        reply = developer_full_name_reply()
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_identity",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if "do you remember our last chat session" in low or "remember our last chat" in low:
        trace("deterministic_reply", "matched", detail="memory_policy_explanation")
        reply = "I remember parts of prior chats only if they were saved to memory; I remember this live session context directly."
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "memory_policy",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if is_name_origin_question(text):
        trace("deterministic_reply", "matched", detail="name_origin_query")
        story = core.get_name_origin_story().strip()
        if story:
            reply = f"Yes. {story}"
        else:
            reply = "I do not have a saved name-origin story yet. You can tell me with: remember this Nova ..."
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "name_origin",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": bool(story),
        }
    if is_peims_attendance_rules_query(text):
        trace("grounded_lookup", "matched", tool="peims_attendance")
        reply = peims_attendance_rules_reply()
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "peims_attendance",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": "[source:" in reply.lower(),
        }
    if is_developer_profile_request(text):
        trace("deterministic_reply", "matched", detail="developer_profile")
        reply = developer_profile_reply(turns, text)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_profile",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if is_conversational_clarification(text):
        trace("deterministic_reply", "matched", detail="clarification_reply")
        reply = clarification_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "clarification_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if is_location_request(text):
        trace("deterministic_reply", "matched", detail="location_reply")
        reply = location_reply()
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "location",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if is_deep_search_followup_request(text):
        inferred = infer_research_query_from_turns(turns)
        query = inferred or text
        grounded = build_grounded_answer(query, max_sources=2)
        if grounded:
            trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": query},
                "tool_result": reply,
                "grounded": True,
            }
        local_grounded = build_local_topic_digest_answer(query)
        if local_grounded:
            trace("grounded_lookup", "matched", tool="local_knowledge")
            reply = local_grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "local_knowledge",
                "tool_args": {"query": query},
                "tool_result": reply,
                "grounded": True,
            }
        trace("grounded_lookup", "missed", tool="web_research")
        reply = "I could not find additional grounded sources right now. Please try: web research <topic>"
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "web_research",
            "tool_args": {"query": query},
            "tool_result": reply,
            "grounded": False,
        }
    if is_groundable_factual_query(text):
        grounded = build_grounded_answer(text, max_sources=2)
        if grounded:
            trace("grounded_lookup", "matched", tool="web_research")
            reply = grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "web_research",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }
        local_grounded = build_local_topic_digest_answer(text)
        if local_grounded:
            trace("grounded_lookup", "matched", tool="local_knowledge")
            reply = local_grounded
            return normalize_reply(reply), {
                "planner_decision": "grounded_lookup",
                "tool": "local_knowledge",
                "tool_args": {"query": text},
                "tool_result": reply,
                "grounded": True,
            }
        trace("grounded_lookup", "missed", tool="web_research")
        reply = "I couldn't find grounded sources for that yet. Please try: web research <your question>"
        return normalize_reply(reply), {
            "planner_decision": "grounded_lookup",
            "tool": "web_research",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": False,
        }
    if core._is_developer_color_lookup_request(text):
        trace("deterministic_reply", "matched", detail="developer_color_reply")
        reply = developer_color_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if core._is_developer_bilingual_request(text):
        trace("deterministic_reply", "matched", detail="developer_bilingual_reply")
        reply = developer_bilingual_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "developer_bilingual_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if core._is_color_lookup_request(text):
        trace("deterministic_reply", "matched", detail="color_reply")
        reply = color_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "color_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }
    if "what animals do i like" in low or "which animals do i like" in low:
        trace("deterministic_reply", "matched", detail="animal_reply")
        reply = animal_reply(turns)
        return normalize_reply(reply), {
            "planner_decision": "deterministic",
            "tool": "animal_reply",
            "tool_args": {"query": text},
            "tool_result": reply,
            "grounded": True,
        }

    planner_outcome = nova_planner_contract.maybe_handle_planner_sequence(
        text=text,
        turns=turns,
        pending_action=pending_action,
        prefer_web_for_data_queries=prefer_web_for_data_queries,
        session=session,
        core=core,
        trace=trace,
        normalize_reply=normalize_reply,
        is_web_preferred_data_query=is_web_preferred_data_query,
        ensure_active_work_tree_fn=ensure_active_work_tree_fn,
    )
    if planner_outcome is not None:
        return planner_outcome

    if stop_before_llm_fallback:
        return "", {"planner_decision": "unhandled"}

    task = core.analyze_request(text, config={"prefer_web_for_data_queries": prefer_web_for_data_queries})
    if not getattr(task, "allow_llm", False):
        trace("policy_gate", "blocked", detail=str(getattr(task, "message", "") or "")[:160])
        reply = str(getattr(task, "message", "") or "")
        return normalize_reply(reply), {
            "planner_decision": "policy_block",
            "tool": "",
            "tool_args": {},
            "tool_result": "",
            "grounded": True,
        }
    trace("policy_gate", "allowed")

    fallback_context = core.build_fallback_context_details(
        text,
        turns,
        conversation_state=getattr(session, "conversation_state", None),
        pending_action=pending_action,
    )
    retrieved = str(fallback_context.get("context") or "")
    trace(
        "memory_context",
        "used" if str(fallback_context.get("learning_context") or "") else "empty",
        memory_used=bool(fallback_context.get("memory_used")),
        knowledge_used=bool(fallback_context.get("knowledge_used")),
        memory_chars=int(fallback_context.get("memory_chars") or 0),
        knowledge_chars=int(fallback_context.get("knowledge_chars") or 0),
    )
    chat_ctx = str(fallback_context.get("chat_context") or "")
    if chat_ctx:
        trace("chat_context", "used", chars=len(chat_ctx))

    session_fact_sheet = str(fallback_context.get("session_fact_sheet") or "")
    if session_fact_sheet:
        trace("session_fact_sheet", "used", chars=len(session_fact_sheet))
    if core.should_block_low_confidence(text, retrieved_context=retrieved):
        trace("low_confidence_gate", "blocked")
        truthful_outcome = core._truthful_limit_outcome(text)
        reply = str(truthful_outcome.get("reply_text") or core._truthful_limit_reply(text))
        return normalize_reply(reply), {
            "planner_decision": "blocked_low_confidence",
            "tool": "",
            "tool_args": {},
            "tool_result": "",
            "grounded": False,
            "reply_contract": str(truthful_outcome.get("reply_contract") or ""),
            "reply_outcome": dict(truthful_outcome),
        }
    trace("llm_fallback", "invoked", retrieved_chars=len(retrieved))
    reply = core.ollama_chat(
        text,
        retrieved_context=retrieved,
        language_mix_spanish_pct=int(language_mix_spanish_pct or 0),
    )
    reply = core.sanitize_llm_reply(reply, "")
    reply_contract = ""
    reply_outcome: dict[str, object] = {}
    claim_gated_reply, claim_gate_changed, claim_gate_reason = core._apply_claim_gate(
        reply,
        evidence_text=retrieved,
        tool_context="",
    )
    if claim_gate_changed:
        trace("claim_gate", "adjusted", claim_gate_reason)
        reply = claim_gated_reply
        if claim_gate_reason == "unsupported_claim_blocked":
            truthful_outcome = core._truthful_limit_outcome(text)
            reply_contract = str(truthful_outcome.get("reply_contract") or "")
            reply_outcome = dict(truthful_outcome)
    if not reply_contract:
        reply = core._attach_learning_invitation(reply)
    return normalize_reply(reply), {
        "planner_decision": "llm_fallback",
        "tool": "",
        "tool_args": {},
        "tool_result": "",
        "grounded": False if not reply else None,
        "reply_contract": reply_contract,
        "reply_outcome": reply_outcome,
    }