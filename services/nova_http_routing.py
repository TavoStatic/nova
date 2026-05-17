from __future__ import annotations

from typing import Any, Callable

import http_chat_flow
from services.decision_pipeline import StageRegistry
from services.decision_pipeline import run_registered_stages


HTTP_REGISTERED_SUPERVISOR_ACTIONS = frozenset()


def execute_http_routing_sequence(
    *,
    text: str,
    routed_text: str,
    turns: list[tuple[str, str]],
    turn_acts: list[str],
    intent_rule: dict,
    session,
    conversation_state,
    ledger: dict,
    should_clarify_unlabeled_numeric_turn: Callable[..., bool],
    unlabeled_numeric_turn_reply: Callable[..., str],
    build_routing_decision: Callable[..., dict],
    handle_supervisor_intent: Callable[..., tuple[bool, str, Any, Any]],
    supervisor_has_route: Callable[[dict], bool],
    should_warn_supervisor_bypass: Callable[[str], bool],
    emit_supervisor_intent_trace: Callable[..., None],
    evaluate_supervisor_rules: Callable[..., dict],
    execute_registered_supervisor_rule: Callable[..., tuple[bool, str, Any]],
    make_conversation_state: Callable[..., dict],
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
        if flow_result.get("handled") is False:
            context["warn_supervisor_bypass"] = False
            return {"handled": False, "result": "pass", "detail": "supervisor_intent_unhandled"}
        next_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state
        context["conversation_state"] = next_state
        return _handled_result(flow_result, state=next_state, detail="supervisor_intent", owner="supervisor_intent")

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

    registry = StageRegistry()
    registry.register("numeric_clarify", priority=20, handler=_numeric_clarify_stage)
    registry.register("supervisor_intent", priority=50, handler=_supervisor_intent_stage)
    registry.register("registered_supervisor_rule", priority=80, handler=_registered_supervisor_rule_stage)

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
