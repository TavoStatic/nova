from __future__ import annotations

import http_chat_flow


class NovaHttpTurnEntryService:
    """Own the front-half HTTP turn-entry orchestration outside the transport shell."""

    def execute_turn_entry(
        self,
        *,
        session_id: str,
        text: str,
        session,
        ledger: dict,
        conversation_state,
        append_session_turn_fn,
        determine_turn_direction_fn,
        auto_adjust_language_mix_fn,
        action_ledger_add_step_fn,
        evaluate_supervisor_rules_fn,
        supervisor_has_route_fn,
        runtime_set_location_intent_fn,
        llm_classify_routing_intent_fn,
        is_identity_only_session_fn,
        identity_only_block_kind_fn,
        identity_only_block_reply_fn,
        build_routing_decision_fn,
        handle_supervisor_intent_fn,
        emit_supervisor_intent_trace_fn,
        ensure_reply_fn,
        should_clarify_unlabeled_numeric_turn_fn,
        unlabeled_numeric_turn_reply_fn,
        make_conversation_state_fn,
        mixed_info_request_clarify_reply_fn,
        is_saved_location_weather_query_fn,
    ) -> dict:
        prepared_turn = http_chat_flow.prepare_chat_turn(
            session_id=session_id,
            text=text,
            session=session,
            ledger=ledger,
            append_session_turn=append_session_turn_fn,
            determine_turn_direction=determine_turn_direction_fn,
            auto_adjust_language_mix=auto_adjust_language_mix_fn,
            action_ledger_add_step=action_ledger_add_step_fn,
            evaluate_supervisor_rules=evaluate_supervisor_rules_fn,
            supervisor_has_route=supervisor_has_route_fn,
            runtime_set_location_intent=runtime_set_location_intent_fn,
            llm_classify_routing_intent=llm_classify_routing_intent_fn,
            is_identity_only_session=is_identity_only_session_fn,
            identity_only_block_kind=identity_only_block_kind_fn,
        )
        turns = list(prepared_turn.get("turns") or [])
        routed_text = str(prepared_turn.get("routed_text") or text)
        turn_acts = [str(item).strip() for item in list(prepared_turn.get("turn_acts") or []) if str(item).strip()]
        intent_rule = prepared_turn.get("intent_rule") if isinstance(prepared_turn.get("intent_rule"), dict) else {}

        flow_result = http_chat_flow.apply_identity_only_mode_block(
            routed_text=routed_text,
            intent_rule=intent_rule,
            identity_only_block_kind=str(prepared_turn.get("identity_only_block_kind") or ""),
            ledger=ledger,
            build_routing_decision=build_routing_decision_fn,
            identity_only_block_reply=identity_only_block_reply_fn,
            action_ledger_add_step=action_ledger_add_step_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "turns": turns,
                "routed_text": routed_text,
                "turn_acts": turn_acts,
                "intent_rule": intent_rule,
                "routing_decision": flow_result.get("routing_decision") if isinstance(flow_result.get("routing_decision"), dict) else None,
                "conversation_state": conversation_state,
            }

        flow_result = http_chat_flow.apply_numeric_clarify_outcome(
            has_intent_route=bool(supervisor_has_route_fn(intent_rule)),
            routed_text=routed_text,
            pending_action=session.pending_action,
            current_state=conversation_state,
            session=session,
            ledger=ledger,
            should_clarify_unlabeled_numeric_turn=should_clarify_unlabeled_numeric_turn_fn,
            unlabeled_numeric_turn_reply=unlabeled_numeric_turn_reply_fn,
            make_conversation_state=make_conversation_state_fn,
            action_ledger_add_step=action_ledger_add_step_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "turns": turns,
                "routed_text": routed_text,
                "turn_acts": turn_acts,
                "intent_rule": intent_rule,
                "routing_decision": None,
                "conversation_state": session.conversation_state,
            }

        correction_pending = bool(session.pending_correction_target) or (
            isinstance(conversation_state, dict)
            and str(conversation_state.get("kind") or "") == "correction_pending"
        )
        flow_result = http_chat_flow.apply_mixed_turn_clarify(
            turn_acts=turn_acts,
            correction_pending=correction_pending,
            routed_text=routed_text,
            ledger=ledger,
            mixed_info_request_clarify_reply=mixed_info_request_clarify_reply_fn,
            action_ledger_add_step=action_ledger_add_step_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "turns": turns,
                "routed_text": routed_text,
                "turn_acts": turn_acts,
                "intent_rule": intent_rule,
                "routing_decision": None,
                "conversation_state": conversation_state,
            }

        if (
            isinstance(conversation_state, dict)
            and str(conversation_state.get("kind") or "") == "location_recall"
            and is_saved_location_weather_query_fn(routed_text)
        ):
            return {
                "handled": False,
                "turns": turns,
                "routed_text": routed_text,
                "turn_acts": turn_acts,
                "intent_rule": intent_rule,
                "routing_decision": None,
                "conversation_state": conversation_state,
            }

        routing_decision = build_routing_decision_fn(
            routed_text,
            entry_point="http",
            intent_result=intent_rule,
            handle_result=None,
            turn_acts=turn_acts,
        )
        handled_intent, intent_msg, intent_state, intent_effects = handle_supervisor_intent_fn(
            intent_rule,
            routed_text,
            turns=turns,
            input_source="typed",
            entry_point="http",
        )
        if handled_intent:
            flow_result = http_chat_flow.apply_handled_supervisor_intent(
                intent_rule=intent_rule,
                routed_text=routed_text,
                intent_msg=intent_msg,
                intent_state=intent_state,
                intent_effects=intent_effects,
                session=session,
                conversation_state=conversation_state,
                ledger=ledger,
                emit_supervisor_intent_trace=emit_supervisor_intent_trace_fn,
                action_ledger_add_step=action_ledger_add_step_fn,
                ensure_reply=ensure_reply_fn,
            )
            return {
                "handled": True,
                "flow_result": flow_result,
                "turns": turns,
                "routed_text": routed_text,
                "turn_acts": turn_acts,
                "intent_rule": intent_rule,
                "routing_decision": routing_decision,
                "conversation_state": flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state,
            }

        return {
            "handled": False,
            "turns": turns,
            "routed_text": routed_text,
            "turn_acts": turn_acts,
            "intent_rule": intent_rule,
            "routing_decision": routing_decision,
            "conversation_state": conversation_state,
        }


HTTP_TURN_ENTRY_SERVICE = NovaHttpTurnEntryService()