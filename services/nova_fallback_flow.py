from __future__ import annotations

import re
import time
from typing import Callable, Optional


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


def open_probe_reply(
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    normalize_turn_text_fn: Callable[[str], str],
    truthful_limit_reply_fn: Callable[[str], str],
) -> tuple[str, str]:
    normalized = normalize_turn_text_fn(text)
    normalized_key = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized_key = re.sub(r"\s+", " ", normalized_key).strip()
    if normalized_key in {"can you help me a little here", "can you help me here"}:
        return (
            "What kind of help do you want?",
            "safe_fallback",
        )
    if normalized_key in {"what do you think then", "what now", "what next", "okay so what next", "where does that leave us"}:
        return (
            "I don't have enough context to answer that yet. Tell me the topic or decision you want help with, and I'll stay on it.",
            "safe_fallback",
        )
    if any(cue in normalized for cue in ("what are you talking about", "what are you talking", "what ?", "what?")):
        last_assistant = ""
        for role, txt in reversed(list(turns or [])):
            if str(role or "").strip().lower() == "assistant":
                last_assistant = str(txt or "").strip()
                break
        if last_assistant and any(token in last_assistant.lower() for token in ("allowlisted references", "web lookup", "web research")):
            return (
                "You're right. That response drifted into web lookup when you were asking a direct chat question. Ask it again and I'll answer it directly.",
                "clarification",
            )
        return (
            "You're right. I should stay with the current chat instead of jumping to web lookup for that kind of question.",
            "clarification",
        )
    return (
        truthful_limit_reply_fn(text),
        "safe_fallback",
    )


def build_fallback_context(
    *,
    text: str,
    turns,
    recent_tool_context: str,
    build_fallback_context_details_fn: Callable[..., dict],
    uses_prior_reference_fn: Callable[[str], bool],
    action_ledger_add_step: Callable[..., None],
) -> dict:
    fallback_context = build_fallback_context_details_fn(text, turns)
    retrieved_context = str(fallback_context.get("context") or "")
    action_ledger_add_step(
        "memory_context",
        "used" if str(fallback_context.get("learning_context") or "") else "empty",
        memory_used=bool(fallback_context.get("memory_used")),
        knowledge_used=bool(fallback_context.get("knowledge_used")),
        memory_chars=int(fallback_context.get("memory_chars") or 0),
        knowledge_chars=int(fallback_context.get("knowledge_chars") or 0),
    )
    chat_ctx = str(fallback_context.get("chat_context") or "")
    if chat_ctx:
        action_ledger_add_step("chat_context", "used", chars=len(chat_ctx))
    session_fact_sheet = str(fallback_context.get("session_fact_sheet") or "")
    if session_fact_sheet:
        action_ledger_add_step("session_fact_sheet", "used", chars=len(session_fact_sheet))
    if recent_tool_context and uses_prior_reference_fn(text):
        retrieved_context = (retrieved_context + "\n\nRECENT TOOL OUTPUT:\n" + recent_tool_context).strip()[:6000]
        action_ledger_add_step("recent_tool_context", "used", chars=len(recent_tool_context))
    return {
        "retrieved_context": retrieved_context,
        "fallback_context": fallback_context,
    }


def prepare_fallback_flow(
    *,
    text: str,
    turns,
    recent_tool_context: str,
    prefer_web_for_data_queries: bool,
    analyze_request_fn: Callable[..., object],
    normalize_policy_reply_fn: Callable[[str], str],
    build_fallback_context_details_fn: Callable[..., dict],
    uses_prior_reference_fn: Callable[[str], bool],
    action_ledger_add_step: Callable[..., None],
) -> dict:
    task = analyze_request_fn(
        text,
        config={"prefer_web_for_data_queries": prefer_web_for_data_queries},
    )
    policy_block_outcome = apply_policy_gate_block(
        task=task,
        action_ledger_add_step=action_ledger_add_step,
        normalize_reply_fn=normalize_policy_reply_fn,
    )
    if policy_block_outcome.get("handled"):
        return {
            "handled": True,
            "outcome": policy_block_outcome,
        }

    action_ledger_add_step("policy_gate", "allowed")
    fallback_bundle = build_fallback_context(
        text=text,
        turns=turns,
        recent_tool_context=recent_tool_context,
        build_fallback_context_details_fn=build_fallback_context_details_fn,
        uses_prior_reference_fn=uses_prior_reference_fn,
        action_ledger_add_step=action_ledger_add_step,
    )
    return {
        "handled": False,
        "retrieved_context": str(fallback_bundle.get("retrieved_context") or ""),
        "fallback_context": fallback_bundle.get("fallback_context") if isinstance(fallback_bundle.get("fallback_context"), dict) else {},
    }


def apply_policy_gate_block(
    *,
    task,
    action_ledger_add_step: Callable[..., None],
    normalize_reply_fn: Callable[[str], str],
) -> dict:
    if bool(getattr(task, "allow_llm", False)):
        return {"handled": False}

    reply = str(getattr(task, "message", "") or "")
    action_ledger_add_step("policy_gate", "blocked", detail=reply[:160])
    return {
        "handled": True,
        "reply": normalize_reply_fn(reply),
        "planner_decision": "policy_block",
        "grounded": True,
    }


def apply_low_confidence_block(
    *,
    text: str,
    retrieved_context: str,
    recent_tool_context: str,
    should_block_low_confidence_fn: Callable[..., bool],
    behavior_record_event_fn: Callable[[str], None],
    truthful_limit_outcome_fn: Callable[[str], dict],
    truthful_limit_reply_fn: Callable[[str], str],
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not should_block_low_confidence_fn(
        text,
        retrieved_context=retrieved_context,
        tool_context=recent_tool_context,
    ):
        return {"handled": False}

    behavior_record_event_fn("low_confidence_block")
    action_ledger_add_step("low_confidence_gate", "blocked")
    truthful_outcome = truthful_limit_outcome_fn(text)
    reply = str(truthful_outcome.get("reply_text") or truthful_limit_reply_fn(text))
    return {
        "handled": True,
        "reply": ensure_reply(reply),
        "planner_decision": "blocked_low_confidence",
        "grounded": False,
        "reply_contract": str(truthful_outcome.get("reply_contract") or ""),
        "reply_outcome": dict(truthful_outcome),
    }


def finalize_llm_fallback_reply(
    *,
    text: str,
    raw_user_text: str,
    input_source: str,
    retrieved_context: str,
    recent_tool_context: str,
    language_mix_spanish_pct: int,
    active_user: str,
    ollama_chat_fn: Callable[..., str],
    sanitize_llm_reply_fn: Callable[[str, str], str],
    mem_enabled_fn: Callable[[], bool],
    mem_should_store_fn: Callable[[str], bool],
    mem_add_fn: Callable[[str, str, str], None],
    strip_mem_leak_fn: Callable[[str, str], str],
    self_correct_reply_fn: Callable[[str, str], tuple[str, bool, str]],
    behavior_record_event_fn: Callable[[str], None],
    action_ledger_add_step: Callable[..., None],
    teach_store_example_fn: Callable[..., None],
    truthful_limit_outcome_fn: Callable[[str], dict],
    apply_claim_gate_fn: Callable[[str, str, str], tuple[str, bool, str]],
    preprocess_reply_fn: Callable[[str], str] | None = None,
    post_claim_reply_transform_fn: Callable[[str, str], str] | None = None,
    is_explicit_request_fn: Callable[[str], bool],
    apply_reply_overrides_fn: Callable[[str], str],
    ensure_reply_fn: Callable[[str], str],
) -> dict:
    behavior_record_event_fn("llm_fallback")
    action_ledger_add_step("llm_fallback", "invoked", retrieved_chars=len(retrieved_context))

    llm_started = time.perf_counter()
    reply = ollama_chat_fn(
        text,
        retrieved_context=retrieved_context,
        language_mix_spanish_pct=language_mix_spanish_pct,
    )
    llm_time_ms = int((time.perf_counter() - llm_started) * 1000)
    post_started = time.perf_counter()
    reply = sanitize_llm_reply_fn(reply, recent_tool_context)
    if callable(preprocess_reply_fn):
        reply = preprocess_reply_fn(reply)

    if mem_enabled_fn() and mem_should_store_fn(raw_user_text):
        mem_add_fn("chat_user", input_source, raw_user_text)

    clean_reply = strip_mem_leak_fn(reply, retrieved_context)
    corrected_reply, was_corrected, correction_reason = self_correct_reply_fn(text, clean_reply)
    planner_decision = "llm_fallback"
    grounded = None
    reply_contract = ""
    reply_outcome = {}
    if was_corrected:
        behavior_record_event_fn("correction_applied")
        behavior_record_event_fn("self_correction_applied")
        action_ledger_add_step("llm_postprocess", "self_corrected", detail=str(correction_reason or "")[:120])
        try:
            teach_store_example_fn(clean_reply, corrected_reply, user=active_user or None)
        except Exception:
            pass
        planner_decision = "llm_self_corrected"
        grounded = True
        clean_reply = corrected_reply

    claim_gated_reply, claim_gate_changed, claim_gate_reason = apply_claim_gate_fn(
        clean_reply,
        evidence_text=retrieved_context,
        tool_context=recent_tool_context,
    )
    if claim_gate_changed:
        action_ledger_add_step("claim_gate", "adjusted", claim_gate_reason)
        clean_reply = claim_gated_reply
        if claim_gate_reason == "unsupported_claim_blocked":
            truthful_outcome = truthful_limit_outcome_fn(text)
            grounded = False
            reply_contract = str(truthful_outcome.get("reply_contract") or "")
            reply_outcome = dict(truthful_outcome)

    if callable(post_claim_reply_transform_fn):
        clean_reply = post_claim_reply_transform_fn(clean_reply, reply_contract)

    try:
        if not is_explicit_request_fn(text):
            sents = re.split(r"(?<=[.!?])\s+", (clean_reply or "").strip())
            short = " ".join([sentence for sentence in sents if sentence])[:600]
            if short:
                clean_reply = short
    except Exception:
        pass

    try:
        final = apply_reply_overrides_fn(clean_reply)
    except Exception:
        final = clean_reply

    return {
        "handled": True,
        "reply": ensure_reply_fn(final),
        "planner_decision": planner_decision,
        "grounded": grounded,
        "reply_contract": reply_contract,
        "reply_outcome": reply_outcome,
        "llm_time_ms": llm_time_ms,
        "post_time_ms": int((time.perf_counter() - post_started) * 1000),
    }
