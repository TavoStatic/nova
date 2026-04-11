from __future__ import annotations

import http_chat_flow


class NovaHttpChatOrchestrationService:
    """Own the post-intent HTTP chat branch orchestration outside the transport shell."""

    def execute_post_intent_sequence(
        self,
        *,
        text: str,
        routed_text: str,
        turns: list[tuple[str, str]],
        session,
        ledger: dict,
        conversation_state,
        intent_rule: dict,
        routing_decision: dict | None,
        supervisor_has_route_fn,
        should_warn_supervisor_bypass_fn,
        is_web_research_override_request_fn,
        action_ledger_add_step_fn,
        learn_self_identity_binding_fn,
        ensure_reply_fn,
        evaluate_supervisor_handle_rules_fn,
        execute_registered_supervisor_rule_fn,
        build_routing_decision_fn,
        fulfillment_flow_service,
        fast_smalltalk_reply_fn,
        is_developer_profile_request_fn,
        developer_profile_reply_fn,
        learn_contextual_developer_facts_fn,
        infer_profile_conversation_state_fn,
        make_conversation_state_fn,
        learn_contextual_self_facts_fn,
        extract_memory_teach_text_fn,
        mem_enabled_fn,
        store_location_fact_reply_fn,
        weather_for_saved_location_fn,
        is_saved_location_weather_query_fn,
        store_declarative_fact_outcome_fn,
        render_reply_fn,
        consume_conversation_followup_fn,
        conversation_active_subject_fn,
        developer_work_guess_turn_fn,
        developer_location_turn_fn,
        handle_location_conversation_turn_fn,
    ) -> dict:
        warn_supervisor_bypass = not supervisor_has_route_fn(intent_rule) and should_warn_supervisor_bypass_fn(routed_text)

        flow_result = http_chat_flow.apply_web_research_override(
            text=text,
            session=session,
            ledger=ledger,
            is_web_research_override_request=is_web_research_override_request_fn,
            action_ledger_add_step=action_ledger_add_step_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "conversation_state": conversation_state,
                "routing_decision": routing_decision,
                "warn_supervisor_bypass": warn_supervisor_bypass,
            }

        try:
            identity_learned, identity_msg = learn_self_identity_binding_fn(text)
            flow_result = http_chat_flow.apply_identity_binding_learning(
                identity_learned=identity_learned,
                identity_msg=identity_msg,
                ledger=ledger,
                action_ledger_add_step=action_ledger_add_step_fn,
                ensure_reply=ensure_reply_fn,
            )
            if flow_result.get("handled"):
                return {
                    "handled": True,
                    "flow_result": flow_result,
                    "conversation_state": conversation_state,
                    "routing_decision": routing_decision,
                    "warn_supervisor_bypass": warn_supervisor_bypass,
                }
        except Exception:
            pass

        general_rule = evaluate_supervisor_handle_rules_fn(
            text,
            manager=session,
            turns=turns,
            phase="handle",
            entry_point="http",
        )
        handled_rule, rule_reply, rule_state = execute_registered_supervisor_rule_fn(
            general_rule,
            text,
            conversation_state,
            turns=turns,
            input_source="typed",
            allowed_actions={
                "name_origin_store",
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
            },
        )
        routing_decision = build_routing_decision_fn(
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
            action_ledger_add_step=action_ledger_add_step_fn,
            ensure_reply=ensure_reply_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "conversation_state": session.conversation_state,
                "routing_decision": routing_decision,
                "warn_supervisor_bypass": warn_supervisor_bypass,
            }

        flow_result = http_chat_flow.apply_fast_smalltalk(
            quick_reply=fast_smalltalk_reply_fn(text),
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "conversation_state": conversation_state,
                "routing_decision": routing_decision,
                "warn_supervisor_bypass": warn_supervisor_bypass,
            }

        if is_developer_profile_request_fn(text):
            session.apply_state_update(
                infer_profile_conversation_state_fn(text)
                or make_conversation_state_fn("identity_profile", subject="developer")
            )
            action_ledger_add_step_fn(ledger, "developer_profile", "matched")
            return {
                "handled": True,
                "flow_result": {
                    "reply": ensure_reply_fn(developer_profile_reply_fn(turns, text)),
                    "planner_decision": "deterministic",
                    "grounded": True,
                    "intent": "developer_profile",
                },
                "conversation_state": session.conversation_state,
                "routing_decision": routing_decision,
                "warn_supervisor_bypass": warn_supervisor_bypass,
            }

        fulfillment_result = fulfillment_flow_service.maybe_run_fulfillment_flow(
            routed_text,
            session,
            turns,
            pending_action=session.pending_action,
        )
        flow_result = http_chat_flow.apply_fulfillment_flow(
            fulfillment_result=fulfillment_result,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step_fn,
            ensure_reply=ensure_reply_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "conversation_state": conversation_state,
                "routing_decision": routing_decision,
                "warn_supervisor_bypass": warn_supervisor_bypass,
            }

        learned_profile, learned_profile_msg = learn_contextual_developer_facts_fn(turns, text)
        flow_result = http_chat_flow.apply_developer_profile_learning(
            learned_profile=learned_profile,
            learned_profile_msg=learned_profile_msg,
            text=text,
            session=session,
            ledger=ledger,
            infer_profile_conversation_state=infer_profile_conversation_state_fn,
            make_conversation_state=make_conversation_state_fn,
            action_ledger_add_step=action_ledger_add_step_fn,
            ensure_reply=ensure_reply_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "conversation_state": session.conversation_state,
                "routing_decision": routing_decision,
                "warn_supervisor_bypass": warn_supervisor_bypass,
            }

        try:
            learned_self, learned_self_msg = learn_contextual_self_facts_fn(text, input_source="typed")
            flow_result = http_chat_flow.apply_self_profile_learning(
                learned_self=learned_self,
                learned_self_msg=learned_self_msg,
                ledger=ledger,
                action_ledger_add_step=action_ledger_add_step_fn,
                ensure_reply=ensure_reply_fn,
            )
            if flow_result.get("handled"):
                return {
                    "handled": True,
                    "flow_result": flow_result,
                    "conversation_state": conversation_state,
                    "routing_decision": routing_decision,
                    "warn_supervisor_bypass": warn_supervisor_bypass,
                }
        except Exception:
            pass

        memory_teach = extract_memory_teach_text_fn(text)
        if memory_teach and mem_enabled_fn():
            pass

        try:
            location_ack = store_location_fact_reply_fn(
                text,
                input_source="typed",
                pending_action=session.pending_action,
            )
            flow_result = http_chat_flow.apply_location_store_outcome(
                location_ack=location_ack,
                conversation_state=conversation_state,
                session=session,
                ledger=ledger,
                make_conversation_state=make_conversation_state_fn,
                action_ledger_add_step=action_ledger_add_step_fn,
            )
            if flow_result.get("handled"):
                return {
                    "handled": True,
                    "flow_result": flow_result,
                    "conversation_state": flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state,
                    "routing_decision": routing_decision,
                    "warn_supervisor_bypass": warn_supervisor_bypass,
                }
        except Exception:
            pass

        try:
            flow_result = http_chat_flow.apply_saved_location_weather_outcome(
                conversation_state=conversation_state,
                routed_text=routed_text,
                weather_for_saved_location=weather_for_saved_location_fn,
                is_saved_location_weather_query=is_saved_location_weather_query_fn,
                session=session,
                ledger=ledger,
                make_conversation_state=make_conversation_state_fn,
                action_ledger_add_step=action_ledger_add_step_fn,
                ensure_reply=ensure_reply_fn,
            )
            if flow_result.get("handled"):
                return {
                    "handled": True,
                    "flow_result": flow_result,
                    "conversation_state": flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state,
                    "routing_decision": routing_decision,
                    "warn_supervisor_bypass": warn_supervisor_bypass,
                }
        except Exception:
            pass

        flow_result = http_chat_flow.apply_declarative_store_outcome(
            declarative_outcome=store_declarative_fact_outcome_fn(text, input_source="typed"),
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step_fn,
            render_reply=render_reply_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "conversation_state": conversation_state,
                "routing_decision": routing_decision,
                "warn_supervisor_bypass": warn_supervisor_bypass,
            }

        try:
            handled_followup, followup_msg, next_state = consume_conversation_followup_fn(
                conversation_state,
                routed_text,
                input_source="typed",
                turns=turns,
            )
            flow_result = http_chat_flow.apply_conversation_followup_outcome(
                handled_followup=handled_followup,
                followup_msg=followup_msg,
                next_state=next_state,
                conversation_state=conversation_state,
                session=session,
                ledger=ledger,
                conversation_active_subject=conversation_active_subject_fn,
                action_ledger_add_step=action_ledger_add_step_fn,
                ensure_reply=ensure_reply_fn,
            )
            updated_state = flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else conversation_state
            if flow_result.get("handled"):
                return {
                    "handled": True,
                    "flow_result": flow_result,
                    "conversation_state": updated_state,
                    "routing_decision": routing_decision,
                    "warn_supervisor_bypass": warn_supervisor_bypass,
                }
            conversation_state = updated_state
        except Exception:
            pass

        try:
            developer_guess, next_state = developer_work_guess_turn_fn(routed_text)
            flow_result = http_chat_flow.apply_developer_guess_outcome(
                developer_guess=developer_guess,
                next_state=next_state,
                session=session,
                ledger=ledger,
                action_ledger_add_step=action_ledger_add_step_fn,
                ensure_reply=ensure_reply_fn,
            )
            if flow_result.get("handled"):
                return {
                    "handled": True,
                    "flow_result": flow_result,
                    "conversation_state": flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state,
                    "routing_decision": routing_decision,
                    "warn_supervisor_bypass": warn_supervisor_bypass,
                }
        except Exception:
            pass

        reply, next_state = developer_location_turn_fn(
            routed_text,
            state=conversation_state,
            turns=turns,
        )
        flow_result = http_chat_flow.apply_developer_location_outcome(
            reply_text=reply,
            next_state=next_state,
            session=session,
            ledger=ledger,
            action_ledger_add_step=action_ledger_add_step_fn,
        )
        if flow_result.get("handled"):
            return {
                "handled": True,
                "flow_result": flow_result,
                "conversation_state": flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state,
                "routing_decision": routing_decision,
                "warn_supervisor_bypass": warn_supervisor_bypass,
            }

        try:
            handled_location, location_reply, next_location_state, location_intent = handle_location_conversation_turn_fn(
                conversation_state,
                routed_text,
                turns=turns,
            )
            flow_result = http_chat_flow.apply_location_conversation_outcome(
                handled_location=handled_location,
                location_reply=location_reply,
                next_location_state=next_location_state,
                location_intent=location_intent,
                conversation_state=conversation_state,
                session=session,
                ensure_reply=ensure_reply_fn,
            )
            if flow_result.get("handled"):
                return {
                    "handled": True,
                    "flow_result": flow_result,
                    "conversation_state": flow_result.get("conversation_state") if isinstance(flow_result.get("conversation_state"), dict) else session.conversation_state,
                    "routing_decision": routing_decision,
                    "warn_supervisor_bypass": warn_supervisor_bypass,
                }
        except Exception:
            pass

        return {
            "handled": False,
            "conversation_state": conversation_state,
            "routing_decision": routing_decision,
            "warn_supervisor_bypass": warn_supervisor_bypass,
        }


HTTP_CHAT_ORCHESTRATION_SERVICE = NovaHttpChatOrchestrationService()