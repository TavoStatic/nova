from __future__ import annotations

from typing import Any, Callable

import http_chat_flow
from services.decision_pipeline import StageRegistry
from services.decision_pipeline import run_registered_stages


HTTP_REGISTERED_SUPERVISOR_ACTIONS = {
    "name_origin_store",
    "self_location",
    "location_recall",
    "location_name",
    "weather_current_location",
    "apply_correction",
    "retrieval_followup",
    "identity_history_family",
    "open_probe_family",
    "session_fact_recall",
    "last_question_recall",
    "rules_list",
    "developer_identity_followup",
    "identity_profile_followup",
    "developer_location",
}


def execute_http_routing_sequence(
    *,
    text: str,
    routed_text: str,
    identity_only_block_kind: str,
    turns: list[tuple[str, str]],
    turn_acts: list[str],
    intent_rule: dict,
    session,
    conversation_state,
    ledger: dict,
    identity_only_block_reply: Callable[[str], str],
    should_clarify_unlabeled_numeric_turn: Callable[..., bool],
    unlabeled_numeric_turn_reply: Callable[..., str],
    mixed_info_request_clarify_reply: Callable[[str], str],
    build_routing_decision: Callable[..., dict],
    handle_supervisor_intent: Callable[..., tuple[bool, str, Any, Any]],
    supervisor_has_route: Callable[[dict], bool],
    should_warn_supervisor_bypass: Callable[[str], bool],
    emit_supervisor_intent_trace: Callable[..., None],
    is_web_research_override_request: Callable[[str], bool],
    learn_self_identity_binding: Callable[[str], tuple[bool, str]],
    evaluate_supervisor_rules: Callable[..., dict],
    execute_registered_supervisor_rule: Callable[..., tuple[bool, str, Any]],
    fulfillment_flow_service,
    fast_smalltalk_reply: Callable[[str], str],
    learn_contextual_developer_facts: Callable[[list[tuple[str, str]], str], tuple[bool, str]],
    infer_profile_conversation_state: Callable[..., dict],
    make_conversation_state: Callable[..., dict],
    learn_contextual_self_facts: Callable[..., tuple[bool, str]],
    extract_memory_teach_text: Callable[[str], str],
    mem_enabled: Callable[[], bool],
    store_location_fact_reply: Callable[..., str],
    weather_for_saved_location: Callable[..., str],
    is_saved_location_weather_query: Callable[[str], bool],
    store_declarative_fact_outcome: Callable[..., dict],
    render_reply: Callable[[Any], str],
    consume_conversation_followup: Callable[..., tuple[bool, str, Any]],
    conversation_active_subject: Callable[[dict], str],
    developer_work_guess_turn: Callable[[str], tuple[bool, Any]],
    developer_location_turn: Callable[..., tuple[str, Any]],
    handle_location_conversation_turn: Callable[..., tuple[bool, str, Any, str]],
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "conversation_state": conversation_state,
        "routing_decision": None,
        "warn_supervisor_bypass": False,
    }

    def _handled_result(flow_result: dict, *, state: Any = None, detail: str = "", **data: Any) -> dict[str, Any]:
        next_state = state if isinstance(state, dict) else context.get("conversation_state")
        return {
            "handled": True,
            "reply": "",
            "meta": {
                "flow_result": flow_result,
                "conversation_state": next_state,
                "routing_decision": context.get("routing_decision"),
                "warn_supervisor_bypass": bool(context.get("warn_supervisor_bypass")),
            },
            "result": "handled",
            "detail": detail,
            "data": data,
        }

    def _identity_only_mode_stage(_context: dict[str, Any]) -> dict[str, Any]:
        flow_result = http_chat_flow.apply_identity_only_mode_block(
            routed_text=routed_text,
            intent_rule=intent_rule,
            identity_only_block_kind=identity_only_block_kind,
            ledger=ledger,
            build_routing_decision=build_routing_decision,
            identity_only_block_reply=identity_only_block_reply,
            action_ledger_add_step=action_ledger_add_step,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        context["routing_decision"] = flow_result.get("routing_decision") if isinstance(flow_result.get("routing_decision"), dict) else None
        return _handled_result(flow_result, detail="identity_only_mode", owner="policy_block")

    def _numeric_clarify_stage(_context: dict[str, Any]) -> dict[str, Any]:
        flow_result = http_chat_flow.apply_numeric_clarify_outcome(
            has_intent_route=bool(supervisor_has_route(intent_rule)),
            routed_text=routed_text,
            pending_action=session.pending_action,
            current_state=context.get("conversation_state"),
            session=session,
            ledger=ledger,
            should_clarify_unlabeled_numeric_turn=should_clarify_unlabeled_numeric_turn,
            unlabeled_numeric_turn_reply=unlabeled_numeric_turn_reply,
            make_conversation_state=make_conversation_state,
            action_ledger_add_step=action_ledger_add_step,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else context.get("conversation_state")
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="numeric_clarify", owner="ask_clarify")

    def _mixed_turn_clarify_stage(_context: dict[str, Any]) -> dict[str, Any]:
        correction_pending = bool(session.pending_correction_target) or (
            isinstance(context.get("conversation_state"), dict)
            and str((context.get("conversation_state") or {}).get("kind") or "") == "correction_pending"
        )
        flow_result = http_chat_flow.apply_mixed_turn_clarify(
            turn_acts=turn_acts,
            correction_pending=correction_pending,
            routed_text=routed_text,
            ledger=ledger,
            mixed_info_request_clarify_reply=mixed_info_request_clarify_reply,
            action_ledger_add_step=action_ledger_add_step,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        return _handled_result(flow_result, detail="mixed_turn_clarify", owner="ask_clarify")

    def _saved_location_weather_stage(_context: dict[str, Any]) -> dict[str, Any]:
        try:
            flow_result = http_chat_flow.apply_saved_location_weather_outcome(
                conversation_state=context.get("conversation_state"),
                routed_text=routed_text,
                weather_for_saved_location=weather_for_saved_location,
                is_saved_location_weather_query=is_saved_location_weather_query,
                session=session,
                ledger=ledger,
                make_conversation_state=make_conversation_state,
                action_ledger_add_step=action_ledger_add_step,
                ensure_reply=ensure_reply,
            )
        except Exception:
            return {"handled": False, "result": "pass"}
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="saved_location_weather", tool="weather")

    def _supervisor_intent_stage(_context: dict[str, Any]) -> dict[str, Any]:
        context["routing_decision"] = build_routing_decision(
            routed_text,
            entry_point="http",
            intent_result=intent_rule,
            handle_result=None,
            turn_acts=turn_acts,
        )
        handled_intent, intent_msg, intent_state, intent_effects = handle_supervisor_intent(
            intent_rule,
            routed_text,
            turns=turns,
            input_source="typed",
            entry_point="http",
        )
        if not handled_intent:
            context["warn_supervisor_bypass"] = not supervisor_has_route(intent_rule) and should_warn_supervisor_bypass(routed_text)
            return {"handled": False, "result": "pass", "data": {"warn_supervisor_bypass": bool(context.get("warn_supervisor_bypass"))}}
        flow_result = http_chat_flow.apply_handled_supervisor_intent(
            intent_rule=intent_rule,
            routed_text=routed_text,
            intent_msg=intent_msg,
            intent_state=intent_state,
            intent_effects=intent_effects,
            session=session,
            conversation_state=context.get("conversation_state"),
            ledger=ledger,
            emit_supervisor_intent_trace=emit_supervisor_intent_trace,
            action_ledger_add_step=action_ledger_add_step,
            ensure_reply=ensure_reply,
        )
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="supervisor_intent", owner="supervisor_intent")

    def _web_research_override_stage(_context: dict[str, Any]) -> dict[str, Any]:
        flow_result = http_chat_flow.apply_web_research_override(
            text=text,
            session=session,
            ledger=ledger,
            is_web_research_override_request=is_web_research_override_request,
            action_ledger_add_step=action_ledger_add_step,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        return _handled_result(flow_result, detail="web_research_override", owner="web_research_override")

    def _identity_binding_stage(_context: dict[str, Any]) -> dict[str, Any]:
        try:
            identity_learned, identity_msg = learn_self_identity_binding(text)
        except Exception:
            return {"handled": False, "result": "pass"}
        flow_result = http_chat_flow.apply_identity_binding_learning(
            identity_learned=identity_learned,
            identity_msg=identity_msg,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step,
            ensure_reply=ensure_reply,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        return _handled_result(flow_result, detail="identity_binding_learning", owner="identity_binding")

    def _registered_supervisor_rule_stage(_context: dict[str, Any]) -> dict[str, Any]:
        general_rule = evaluate_supervisor_rules(
            text,
            manager=session,
            turns=turns,
            phase="handle",
            entry_point="http",
        )
        handled_rule, rule_reply, rule_state = execute_registered_supervisor_rule(
            general_rule,
            text,
            context.get("conversation_state"),
            turns=turns,
            input_source="typed",
            allowed_actions=HTTP_REGISTERED_SUPERVISOR_ACTIONS,
        )
        context["routing_decision"] = build_routing_decision(
            routed_text,
            entry_point="http",
            intent_result=intent_rule,
            handle_result=general_rule,
            reply_contract=str(general_rule.get("reply_contract") or "") if isinstance(general_rule, dict) else "",
            reply_outcome=general_rule.get("reply_outcome") if isinstance(general_rule.get("reply_outcome"), dict) else {},
        )
        flow_result = http_chat_flow.apply_registered_supervisor_rule(
            handled_rule=handled_rule,
            general_rule=general_rule,
            rule_reply=rule_reply,
            rule_state=rule_state,
            session=session,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step,
            ensure_reply=ensure_reply,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        context["conversation_state"] = session.conversation_state
        rule_name = str(general_rule.get("rule_name") or "registered_rule") if isinstance(general_rule, dict) else "registered_rule"
        return _handled_result(flow_result, state=session.conversation_state, detail=rule_name, owner="supervisor_handle")

    def _fulfillment_stage(_context: dict[str, Any]) -> dict[str, Any]:
        fulfillment_result = fulfillment_flow_service.maybe_run_fulfillment_flow(
            routed_text,
            session,
            turns,
            pending_action=session.pending_action,
        )
        flow_result = http_chat_flow.apply_fulfillment_flow(
            fulfillment_result=fulfillment_result,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step,
            ensure_reply=ensure_reply,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        return _handled_result(flow_result, detail="fulfillment_flow", owner="fulfillment")

    def _fast_smalltalk_stage(_context: dict[str, Any]) -> dict[str, Any]:
        flow_result = http_chat_flow.apply_fast_smalltalk(
            quick_reply=fast_smalltalk_reply(text),
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        return _handled_result(flow_result, detail="fast_smalltalk", owner="smalltalk")

    def _developer_profile_learning_stage(_context: dict[str, Any]) -> dict[str, Any]:
        learned_profile, learned_profile_msg = learn_contextual_developer_facts(turns, text)
        flow_result = http_chat_flow.apply_developer_profile_learning(
            learned_profile=learned_profile,
            learned_profile_msg=learned_profile_msg,
            text=text,
            session=session,
            ledger=ledger,
            infer_profile_conversation_state=infer_profile_conversation_state,
            make_conversation_state=make_conversation_state,
            action_ledger_add_step=action_ledger_add_step,
            ensure_reply=ensure_reply,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="developer_profile_learning", owner="developer_profile")

    def _self_profile_learning_stage(_context: dict[str, Any]) -> dict[str, Any]:
        try:
            learned_self, learned_self_msg = learn_contextual_self_facts(text, input_source="typed")
        except Exception:
            return {"handled": False, "result": "pass"}
        flow_result = http_chat_flow.apply_self_profile_learning(
            learned_self=learned_self,
            learned_self_msg=learned_self_msg,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step,
            ensure_reply=ensure_reply,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        return _handled_result(flow_result, detail="self_profile_learning", owner="self_profile")

    def _location_store_stage(_context: dict[str, Any]) -> dict[str, Any]:
        memory_teach = extract_memory_teach_text(text)
        if memory_teach and mem_enabled():
            pass
        try:
            location_ack = store_location_fact_reply(
                text,
                input_source="typed",
                pending_action=session.pending_action,
            )
        except Exception:
            return {"handled": False, "result": "pass"}
        flow_result = http_chat_flow.apply_location_store_outcome(
            location_ack=location_ack,
            conversation_state=context.get("conversation_state"),
            session=session,
            ledger=ledger,
            make_conversation_state=make_conversation_state,
            action_ledger_add_step=action_ledger_add_step,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="location_store", owner="location_store")

    def _declarative_store_stage(_context: dict[str, Any]) -> dict[str, Any]:
        declarative_outcome = store_declarative_fact_outcome(text, input_source="typed")
        flow_result = http_chat_flow.apply_declarative_store_outcome(
            declarative_outcome=declarative_outcome,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step,
            render_reply=render_reply,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        return _handled_result(flow_result, detail="declarative_store", owner="declarative_store")

    def _conversation_followup_stage(_context: dict[str, Any]) -> dict[str, Any]:
        try:
            handled_followup, followup_msg, next_state = consume_conversation_followup(
                context.get("conversation_state"),
                routed_text,
                input_source="typed",
                turns=turns,
            )
        except Exception:
            return {"handled": False, "result": "pass"}
        flow_result = http_chat_flow.apply_conversation_followup_outcome(
            handled_followup=handled_followup,
            followup_msg=followup_msg,
            next_state=next_state,
            conversation_state=context.get("conversation_state"),
            session=session,
            ledger=ledger,
            conversation_active_subject=conversation_active_subject,
            action_ledger_add_step=action_ledger_add_step,
            ensure_reply=ensure_reply,
        )
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else context.get("conversation_state")
        context["conversation_state"] = next_state
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        return _handled_result(flow_result, state=next_state, detail="conversation_followup", owner="conversation_followup")

    def _developer_guess_stage(_context: dict[str, Any]) -> dict[str, Any]:
        try:
            developer_guess, next_state = developer_work_guess_turn(routed_text)
        except Exception:
            return {"handled": False, "result": "pass"}
        flow_result = http_chat_flow.apply_developer_guess_outcome(
            developer_guess=developer_guess,
            next_state=next_state,
            session=session,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step,
            ensure_reply=ensure_reply,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="developer_guess", owner="developer_guess")

    def _developer_location_stage(_context: dict[str, Any]) -> dict[str, Any]:
        reply, next_state = developer_location_turn(
            routed_text,
            state=context.get("conversation_state"),
            turns=turns,
        )
        flow_result = http_chat_flow.apply_developer_location_outcome(
            reply_text=reply,
            next_state=next_state,
            session=session,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="developer_location", owner="developer_location")

    def _location_conversation_stage(_context: dict[str, Any]) -> dict[str, Any]:
        try:
            handled_location, location_reply, next_location_state, location_intent = handle_location_conversation_turn(
                context.get("conversation_state"),
                routed_text,
                turns=turns,
            )
        except Exception:
            return {"handled": False, "result": "pass"}
        flow_result = http_chat_flow.apply_location_conversation_outcome(
            handled_location=handled_location,
            location_reply=location_reply,
            next_location_state=next_location_state,
            location_intent=location_intent,
            conversation_state=context.get("conversation_state"),
            session=session,
            ensure_reply=ensure_reply,
        )
        if not flow_result.get("handled"):
            return {"handled": False, "result": "pass"}
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="location_conversation", owner="location_conversation")

    registry = StageRegistry()
    registry.register("identity_only_mode", priority=10, handler=_identity_only_mode_stage)
    registry.register("numeric_clarify", priority=20, handler=_numeric_clarify_stage)
    registry.register("mixed_turn_clarify", priority=30, handler=_mixed_turn_clarify_stage)
    registry.register("saved_location_weather", priority=40, handler=_saved_location_weather_stage)
    registry.register("supervisor_intent", priority=50, handler=_supervisor_intent_stage)
    registry.register("web_research_override", priority=60, handler=_web_research_override_stage)
    registry.register("identity_binding_learning", priority=70, handler=_identity_binding_stage)
    registry.register("registered_supervisor_rule", priority=80, handler=_registered_supervisor_rule_stage)
    registry.register("fulfillment_flow", priority=90, handler=_fulfillment_stage)
    registry.register("fast_smalltalk", priority=100, handler=_fast_smalltalk_stage)
    registry.register("developer_profile_learning", priority=110, handler=_developer_profile_learning_stage)
    registry.register("self_profile_learning", priority=120, handler=_self_profile_learning_stage)
    registry.register("location_store", priority=130, handler=_location_store_stage)
    registry.register("declarative_store", priority=140, handler=_declarative_store_stage)
    registry.register("conversation_followup", priority=150, handler=_conversation_followup_stage)
    registry.register("developer_guess", priority=160, handler=_developer_guess_stage)
    registry.register("developer_location", priority=170, handler=_developer_location_stage)
    registry.register("location_conversation", priority=180, handler=_location_conversation_stage)

    outcome = run_registered_stages(registry, context=context)
    if outcome.get("handled"):
        meta = outcome.get("meta") if isinstance(outcome.get("meta"), dict) else {}
        flow_result = dict(meta.get("flow_result") or {})
        flow_result["decision_trace"] = list(outcome.get("decision_trace") or [])
        flow_result["decision_stage"] = str(outcome.get("decision_stage") or "")
        return {
            "handled": True,
            "flow_result": flow_result,
            "conversation_state": meta.get("conversation_state") if isinstance(meta.get("conversation_state"), dict) else context.get("conversation_state"),
            "routing_decision": meta.get("routing_decision") if isinstance(meta.get("routing_decision"), dict) else context.get("routing_decision"),
            "warn_supervisor_bypass": bool(meta.get("warn_supervisor_bypass")) if isinstance(meta, dict) else bool(context.get("warn_supervisor_bypass")),
            "decision_trace": list(outcome.get("decision_trace") or []),
            "decision_stage": str(outcome.get("decision_stage") or ""),
        }

    return {
        "handled": False,
        "conversation_state": context.get("conversation_state"),
        "routing_decision": context.get("routing_decision"),
        "warn_supervisor_bypass": bool(context.get("warn_supervisor_bypass")),
        "decision_trace": list(outcome.get("decision_trace") or []),
        "decision_stage": str(outcome.get("decision_stage") or ""),
    }