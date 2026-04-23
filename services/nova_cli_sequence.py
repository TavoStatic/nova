from __future__ import annotations

from typing import Callable, Optional


def execute_cli_sequence(
    *,
    execute_reply_sequence_fn: Callable[..., tuple[str, dict]],
    **kwargs,
) -> tuple[str, dict]:
    options = dict(kwargs or {})
    options["planner_before_deterministic_content"] = True
    options["stop_before_llm_fallback"] = True
    return execute_reply_sequence_fn(**options)


def normalize_sequence_reply(
    reply: str,
    *,
    ensure_reply_fn: Callable[[str], str],
    apply_reply_overrides_fn: Callable[[str], str],
) -> str:
    try:
        return ensure_reply_fn(apply_reply_overrides_fn(reply))
    except Exception:
        return ensure_reply_fn(reply)


def apply_sequence_result(
    *,
    final: str,
    meta: dict,
    pending_action_ledger: Optional[dict],
    merge_route_evidence_fn: Callable[[dict | None, dict | None], dict | None],
    set_pending_action_fn: Callable[[Optional[dict]], None],
    session_state,
    routed_text: str,
    turns: list[tuple[str, str]],
    fallback_state: Optional[dict],
    infer_post_reply_conversation_state_fn: Callable[..., Optional[dict]],
    apply_reply_runtime_effects_fn: Callable[..., dict],
    apply_reply_session_updates_fn: Callable[..., None],
    sync_pending_conversation_tracking_fn: Callable[[], None],
    trace_fn: Callable[..., None],
    emit_cli_reply_outcome_fn: Callable[..., dict],
    behavior_record_event_fn: Callable[..., None],
    extract_urls_fn: Callable[[str], list[str]],
    detect_identity_conflict_fn: Callable[..., bool],
    recent_tool_context: str,
    recent_web_urls: list[str],
) -> dict:
    planner_decision = str(meta.get("planner_decision") or "deterministic")
    tool = str(meta.get("tool") or "")
    tool_args = meta.get("tool_args") if isinstance(meta.get("tool_args"), dict) else {}
    tool_result = str(meta.get("tool_result") or "")
    grounded = meta.get("grounded") if isinstance(meta.get("grounded"), bool) else None
    reply_contract = str(meta.get("reply_contract") or "")
    reply_outcome = meta.get("reply_outcome") if isinstance(meta.get("reply_outcome"), dict) else {}
    route_evidence = meta.get("route_evidence") if isinstance(meta.get("route_evidence"), dict) else {}

    if pending_action_ledger is not None:
        pending_action_ledger["planner_decision"] = planner_decision
        pending_action_ledger["tool"] = tool
        pending_action_ledger["tool_args"] = tool_args
        pending_action_ledger["tool_result"] = tool_result
        pending_action_ledger["grounded"] = grounded
        pending_action_ledger["reply_contract"] = reply_contract
        pending_action_ledger["reply_outcome"] = dict(reply_outcome)
        if route_evidence:
            pending_action_ledger["route_evidence"] = dict(route_evidence)
            pending_action_ledger["routing_decision"] = merge_route_evidence_fn(
                pending_action_ledger.get("routing_decision") if isinstance(pending_action_ledger.get("routing_decision"), dict) else {},
                {"route_evidence": route_evidence},
            )

    pending_next = meta.get("pending_action")
    if isinstance(pending_next, dict) and pending_next:
        set_pending_action_fn(pending_next)
    elif planner_decision == "run_tool" and tool in {"weather_current_location", "weather_location"}:
        set_pending_action_fn(None)

    runtime_effects = apply_reply_runtime_effects_fn(
        planner_decision=planner_decision,
        tool=tool,
        tool_result=tool_result,
        behavior_record_event_fn=behavior_record_event_fn,
        extract_urls_fn=extract_urls_fn,
        detect_identity_conflict_fn=detect_identity_conflict_fn,
    )
    if runtime_effects.get("identity_conflict"):
        trace_fn("identity_conflict", "detected")

    apply_reply_session_updates_fn(
        session_state,
        meta={
            "planner_decision": planner_decision,
            "tool": tool,
            "tool_args": tool_args,
            "tool_result": tool_result,
            "pending_action": session_state.pending_action,
        },
        routed_text=routed_text,
        turns=turns,
        fallback_state=fallback_state,
        infer_post_reply_conversation_state=infer_post_reply_conversation_state_fn,
    )
    sync_pending_conversation_tracking_fn()

    updated_recent_tool_context = recent_tool_context
    updated_recent_web_urls = list(recent_web_urls)
    if runtime_effects.get("context_updated"):
        updated_recent_tool_context = str(runtime_effects.get("recent_tool_context") or "")
        updated_recent_web_urls = list(runtime_effects.get("recent_web_urls") or [])

    emit_cli_reply_outcome_fn(
        reply_text=final,
        planner_decision=planner_decision,
        session_turns=turns,
    )

    return {
        "recent_tool_context": updated_recent_tool_context,
        "recent_web_urls": updated_recent_web_urls,
        "conversation_state": session_state.conversation_state,
        "pending_action": session_state.pending_action,
    }
