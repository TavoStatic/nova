from __future__ import annotations

from typing import Callable, Any

from services.nova_turn_outcomes import apply_numeric_clarify_outcome


CHAT_SUPERVISOR_INTENTS_RETIRED_FOR_HTTP = frozenset({
    "grounded_self_report",
    "capability_inventory",
    "runtime_identity",
    "retrieval_followup",
    "web_research_family",
    "weather_lookup",
})


def apply_handled_supervisor_intent(
    *,
    intent_rule: dict,
    routed_text: str,
    intent_msg: str,
    intent_state,
    intent_effects,
    session,
    conversation_state,
    ledger: dict,
    emit_supervisor_intent_trace: Callable[..., None],
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    intent_name = str(intent_rule.get("intent") or "")
    if intent_name in CHAT_SUPERVISOR_INTENTS_RETIRED_FOR_HTTP:
        return {
            "handled": False,
            "reply": "",
            "planner_decision": "unhandled",
            "grounded": False,
            "intent": intent_name,
            "conversation_state": conversation_state,
        }
    emit_supervisor_intent_trace(intent_rule, user_text=routed_text)
    reply_contract = ""
    reply_outcome = {}
    if isinstance(intent_effects, dict) and "pending_action" in intent_effects:
        session.set_pending_action(intent_effects.get("pending_action"))
    if isinstance(intent_effects, dict):
        reply_contract = str(intent_effects.get("reply_contract") or "")
        reply_outcome = (
            dict(intent_effects.get("reply_outcome") or {})
            if isinstance(intent_effects.get("reply_outcome"), dict)
            else {}
        )

    planner_decision = "deterministic"
    tool = ""
    tool_args = {}
    tool_result = ""
    grounded = True
    if intent_name == "apply_correction" and intent_state is None:
        session.apply_state_update(None)
    else:
        session.apply_state_update(intent_state, fallback_state=conversation_state)
    action_ledger_add_step(
        ledger,
        "supervisor_intent",
        "handled",
        str(intent_rule.get("intent") or "intent"),
        rule=str(intent_rule.get("rule_name") or ""),
    )
    reply = ensure_reply(intent_msg)
    return {
        "reply": reply,
        "planner_decision": planner_decision,
        "tool": tool,
        "tool_args": tool_args,
        "tool_result": tool_result,
        "grounded": grounded,
        "intent": str(intent_rule.get("intent") or "deterministic"),
        "reply_contract": reply_contract,
        "reply_outcome": reply_outcome,
        "conversation_state": session.conversation_state,
    }


def apply_fulfillment_flow(
    *,
    fulfillment_result,
    ledger: dict,
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not isinstance(fulfillment_result, dict):
        return {"handled": False}

    reply = ensure_reply(str(fulfillment_result.get("reply") or ""))
    if not reply:
        return {"handled": False}

    action_ledger_add_step(
        ledger,
        "fulfillment_flow",
        "handled",
        str(fulfillment_result.get("planner_decision") or "fulfillment"),
    )
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": str(fulfillment_result.get("planner_decision") or "fulfillment"),
        "grounded": bool(fulfillment_result.get("grounded", True)),
        "intent": "fulfillment_flow",
    }


def apply_registered_supervisor_rule(
    *,
    handled_rule: bool,
    general_rule: dict,
    rule_reply: str,
    rule_state,
    session,
    ledger: dict,
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not handled_rule:
        return {"handled": False}

    session.apply_state_update(rule_state)
    if bool(general_rule.get("continuation")):
        session.mark_continuation_used()
    action_ledger_add_step(
        ledger,
        str(general_rule.get("ledger_stage") or "registered_rule"),
        "matched",
        rule=str(general_rule.get("rule_name") or "registered_rule"),
    )
    reply = ensure_reply(rule_reply)
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": bool(general_rule.get("grounded", True)),
        "intent": str(general_rule.get("intent") or "deterministic"),
        "reply_contract": str(general_rule.get("reply_contract") or ""),
        "reply_outcome": general_rule.get("reply_outcome") if isinstance(general_rule.get("reply_outcome"), dict) else {},
    }


def apply_conversation_followup_outcome(
    *,
    handled_followup: bool,
    followup_msg: str,
    next_state,
    conversation_state,
    session,
    ledger: dict,
    conversation_active_subject: Callable[[dict], str],
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not handled_followup:
        updated_state = next_state if isinstance(next_state, dict) else conversation_state
        session.apply_state_update(updated_state)
        return {
            "handled": False,
            "conversation_state": updated_state,
        }

    session.mark_continuation_used()
    if isinstance(next_state, dict) and str(next_state.get("kind") or "").strip() == "retrieval":
        session.set_retrieval_state(next_state)
    else:
        session.apply_state_update(next_state)

    action_ledger_add_step(
        ledger,
        "conversation_followup",
        "used",
        active_subject=conversation_active_subject(conversation_state),
    )
    reply = ensure_reply(followup_msg)
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "conversation_followup",
        "grounded": True,
        "intent": "conversation_followup",
        "conversation_state": session.conversation_state,
    }


def prepare_chat_turn(
    *,
    session_id: str,
    text: str,
    session,
    ledger: dict,
    append_session_turn: Callable[[str, str, str], list[tuple[str, str]]],
    determine_turn_direction: Callable[..., dict],
    auto_adjust_language_mix: Callable[[int, str], int],
    action_ledger_add_step: Callable[..., None],
    evaluate_supervisor_rules: Callable[..., dict],
    supervisor_has_route: Callable[[dict], bool],
    runtime_set_location_intent: Callable[..., dict | None],
) -> dict:
    turns = append_session_turn(session_id, "user", text)
    routed_text = text
    turn_acts: list[str] = []
    try:
        turn_direction = determine_turn_direction(
            turns,
            text,
            active_subject=session.active_subject(),
            pending_action=session.pending_action,
        )
        routed_text = str(turn_direction.get("effective_query") or text)
        session.set_language_mix_spanish_pct(
            auto_adjust_language_mix(
                int(session.language_mix_spanish_pct or 0),
                routed_text,
            )
        )
        turn_acts = [str(item).strip() for item in list(turn_direction.get("turn_acts") or []) if str(item).strip()]
        ledger["turn_acts"] = list(turn_acts)
        action_ledger_add_step(
            ledger,
            "direction_analysis",
            str(turn_direction.get("primary") or "general_chat"),
            str(turn_direction.get("analysis_reason") or "")[:120],
            effective_query=routed_text[:180],
            turn_acts=",".join(turn_acts),
            identity_focused=bool(turn_direction.get("identity_focused")),
            bypass_pattern_routes=bool(turn_direction.get("bypass_pattern_routes")),
        )
    except Exception:
        routed_text = text
        turn_acts = []

    intent_rule = evaluate_supervisor_rules(
        routed_text,
        manager=session,
        turns=turns,
        phase="intent",
        entry_point="http",
    )
    intent_has_route = supervisor_has_route(intent_rule)
    if not intent_has_route:
        runtime_intent = runtime_set_location_intent(routed_text, pending_action=session.pending_action)
        if isinstance(runtime_intent, dict):
            intent_rule = runtime_intent
            intent_has_route = supervisor_has_route(intent_rule)
    return {
        "turns": turns,
        "routed_text": routed_text,
        "turn_acts": turn_acts,
        "intent_rule": intent_rule,
    }


def resume_last_pending_turn(
    session_id: str,
    user_id: str = "",
    *,
    get_active_user: Callable[[], str | None],
    set_active_user: Callable[[str | None], None],
    get_last_session_turn: Callable[[str], tuple[str, str] | None],
    get_session_turns: Callable[[str], list[tuple[str, str]]],
    generate_chat_reply: Callable[[list[tuple[str, str]], str], tuple[str, dict[str, Any]]],
    append_session_turn: Callable[[str, str, str], list[tuple[str, str]]],
    invalidate_control_status_cache: Callable[[], None] | None = None,
) -> dict:
    previous_user = get_active_user()
    set_active_user(user_id or previous_user)
    try:
        sid = (session_id or "").strip()
        if not sid:
            return {"ok": False, "error": "session_id_required"}

        last = get_last_session_turn(sid)
        if not last:
            return {"ok": True, "resumed": False, "reason": "no_turns"}

        role, text = last
        if role != "user":
            return {"ok": True, "resumed": False, "reason": "no_pending_user_turn"}

        turns = get_session_turns(sid)
        reply, _meta = generate_chat_reply(turns, text)
        append_session_turn(sid, "assistant", reply)
        if callable(invalidate_control_status_cache):
            invalidate_control_status_cache()
        return {"ok": True, "resumed": True, "session_id": sid, "reply": reply}
    finally:
        set_active_user(previous_user)


def resume_last_pending_turn_from_runtime(
    session_id: str,
    user_id: str = "",
    *,
    runtime_scope: dict[str, object],
) -> dict:
    return resume_last_pending_turn(
        session_id,
        user_id,
        get_active_user=runtime_scope["nova_core"].get_active_user,
        set_active_user=runtime_scope["nova_core"].set_active_user,
        get_last_session_turn=runtime_scope["_get_last_session_turn"],
        get_session_turns=runtime_scope["_get_session_turns"],
        generate_chat_reply=runtime_scope["_generate_chat_reply"],
        append_session_turn=runtime_scope["_append_session_turn"],
        invalidate_control_status_cache=runtime_scope.get("_invalidate_control_status_cache"),
    )
