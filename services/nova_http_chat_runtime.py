from __future__ import annotations


class NovaHttpChatRuntimeService:
    """Own the top-level HTTP chat session coordinator outside the transport shell."""

    def process_chat(
        self,
        session_id: str,
        user_text: str,
        *,
        user_id: str = "",
        core_module,
        session_state_manager,
        turn_entry_service,
        chat_orchestration_service,
        turn_finalization_service,
        http_chat_flow_module,
        append_session_turn_fn,
        generate_chat_reply_fn,
        invalidate_control_status_cache_fn,
        fast_smalltalk_reply_fn,
        is_developer_profile_request_fn,
        developer_profile_reply_fn,
        learn_contextual_developer_facts_fn,
        extract_memory_teach_text_fn,
    ) -> str:
        previous_user = core_module.get_active_user()
        core_module.set_active_user(user_id or previous_user)
        try:
            text = core_module._strip_invocation_prefix((user_text or "").strip())
            if not text:
                invalidate_control_status_cache_fn()
                return "Okay."

            session = session_state_manager.get(session_id)
            session.reset_turn_flags()
            conversation_state = session.conversation_state

            ledger = core_module.start_action_ledger_record(
                text,
                channel="http",
                session_id=session_id,
                input_source="typed",
                active_subject=session.active_subject(),
            )
            routing_decision: dict | None = None

            def _finalize_flow_reply(flow_result: dict) -> str:
                return turn_finalization_service.finalize_flow_reply(
                    flow_result,
                    session=session,
                    session_id=session_id,
                    user_input=text,
                    ledger=ledger,
                    routing_decision=routing_decision if isinstance(routing_decision, dict) else {},
                    append_session_turn_fn=append_session_turn_fn,
                    build_turn_reflection_fn=core_module.build_turn_reflection,
                    finalize_action_ledger_record_fn=core_module.finalize_action_ledger_record,
                    finalize_routing_decision_fn=core_module._finalize_routing_decision,
                    action_ledger_route_summary_fn=core_module.action_ledger_route_summary,
                )

            turn_entry_result = turn_entry_service.execute_turn_entry(
                session_id=session_id,
                text=text,
                session=session,
                ledger=ledger,
                conversation_state=conversation_state,
                append_session_turn_fn=append_session_turn_fn,
                determine_turn_direction_fn=core_module._determine_turn_direction,
                auto_adjust_language_mix_fn=core_module._auto_adjust_language_mix,
                action_ledger_add_step_fn=core_module.action_ledger_add_step,
                evaluate_supervisor_rules_fn=lambda routed_text, **kwargs: core_module.TURN_SUPERVISOR.evaluate_rules(routed_text, **kwargs),
                supervisor_has_route_fn=core_module._supervisor_result_has_route,
                runtime_set_location_intent_fn=core_module._runtime_set_location_intent,
                llm_classify_routing_intent_fn=core_module._llm_classify_routing_intent,
                is_identity_only_session_fn=core_module._session_identity_only_mode,
                identity_only_block_kind_fn=core_module._identity_only_block_kind,
                identity_only_block_reply_fn=core_module._identity_only_block_reply,
                build_routing_decision_fn=core_module._build_routing_decision,
                handle_supervisor_intent_fn=core_module._handle_supervisor_intent,
                emit_supervisor_intent_trace_fn=core_module._emit_supervisor_intent_trace,
                ensure_reply_fn=core_module._ensure_reply,
                should_clarify_unlabeled_numeric_turn_fn=core_module._should_clarify_unlabeled_numeric_turn,
                unlabeled_numeric_turn_reply_fn=core_module._unlabeled_numeric_turn_reply,
                make_conversation_state_fn=core_module._make_conversation_state,
                mixed_info_request_clarify_reply_fn=core_module._mixed_info_request_clarify_reply,
                is_saved_location_weather_query_fn=core_module._is_saved_location_weather_query,
            )
            turns = list(turn_entry_result.get("turns") or [])
            routed_text = str(turn_entry_result.get("routed_text") or text)
            intent_rule = turn_entry_result.get("intent_rule") if isinstance(turn_entry_result.get("intent_rule"), dict) else {}
            conversation_state = turn_entry_result.get("conversation_state") if isinstance(turn_entry_result.get("conversation_state"), dict) else conversation_state
            routing_decision = turn_entry_result.get("routing_decision") if isinstance(turn_entry_result.get("routing_decision"), dict) else routing_decision
            if turn_entry_result.get("handled"):
                flow_result = turn_entry_result.get("flow_result") if isinstance(turn_entry_result.get("flow_result"), dict) else {}
                return _finalize_flow_reply(flow_result)

            post_intent_result = chat_orchestration_service.execute_post_intent_sequence(
                text=text,
                routed_text=routed_text,
                turns=turns,
                session=session,
                ledger=ledger,
                conversation_state=conversation_state,
                intent_rule=intent_rule,
                routing_decision=routing_decision,
                supervisor_has_route_fn=core_module._supervisor_result_has_route,
                should_warn_supervisor_bypass_fn=core_module._should_warn_supervisor_bypass,
                is_web_research_override_request_fn=core_module._is_web_research_override_request,
                action_ledger_add_step_fn=core_module.action_ledger_add_step,
                learn_self_identity_binding_fn=core_module._learn_self_identity_binding,
                ensure_reply_fn=core_module._ensure_reply,
                evaluate_supervisor_handle_rules_fn=lambda routed, **kwargs: core_module.TURN_SUPERVISOR.evaluate_rules(routed, **kwargs),
                execute_registered_supervisor_rule_fn=core_module._execute_registered_supervisor_rule,
                build_routing_decision_fn=core_module._build_routing_decision,
                fulfillment_flow_service=core_module._fulfillment_flow_service(),
                fast_smalltalk_reply_fn=fast_smalltalk_reply_fn,
                is_developer_profile_request_fn=is_developer_profile_request_fn,
                developer_profile_reply_fn=developer_profile_reply_fn,
                learn_contextual_developer_facts_fn=learn_contextual_developer_facts_fn,
                infer_profile_conversation_state_fn=core_module._infer_profile_conversation_state,
                make_conversation_state_fn=core_module._make_conversation_state,
                learn_contextual_self_facts_fn=core_module._learn_contextual_self_facts,
                extract_memory_teach_text_fn=extract_memory_teach_text_fn,
                mem_enabled_fn=core_module.mem_enabled,
                store_location_fact_reply_fn=core_module._store_location_fact_reply,
                weather_for_saved_location_fn=core_module._weather_for_saved_location,
                is_saved_location_weather_query_fn=core_module._is_saved_location_weather_query,
                store_declarative_fact_outcome_fn=core_module._store_declarative_fact_outcome,
                render_reply_fn=core_module.render_reply,
                consume_conversation_followup_fn=core_module._consume_conversation_followup,
                conversation_active_subject_fn=core_module._conversation_active_subject,
                developer_work_guess_turn_fn=core_module._developer_work_guess_turn,
                developer_location_turn_fn=core_module._developer_location_turn,
                handle_location_conversation_turn_fn=core_module._handle_location_conversation_turn,
            )
            conversation_state = post_intent_result.get("conversation_state") if isinstance(post_intent_result.get("conversation_state"), dict) else conversation_state
            routing_decision = post_intent_result.get("routing_decision") if isinstance(post_intent_result.get("routing_decision"), dict) else routing_decision
            warn_supervisor_bypass = bool(post_intent_result.get("warn_supervisor_bypass"))
            if post_intent_result.get("handled"):
                flow_result = post_intent_result.get("flow_result") if isinstance(post_intent_result.get("flow_result"), dict) else {}
                return _finalize_flow_reply(flow_result)

            reply, meta = generate_chat_reply_fn(
                turns,
                routed_text,
                ledger_record=ledger,
                pending_action=session.pending_action,
                prefer_web_for_data_queries=session.prefer_web_for_data_queries,
                language_mix_spanish_pct=int(session.language_mix_spanish_pct or 0),
                session=session,
            )
            reply_contract = str(meta.get("reply_contract") or "") if isinstance(meta, dict) else ""
            planner_decision = str(meta.get("planner_decision") or "deterministic")
            flow_result = http_chat_flow_module.apply_supervisor_bypass_safe_fallback(
                warn_supervisor_bypass=warn_supervisor_bypass,
                reply_contract=reply_contract,
                routed_text=routed_text,
                turns=turns,
                routing_decision=routing_decision,
                ledger=ledger,
                open_probe_reply=core_module._open_probe_reply,
                action_ledger_add_step=core_module.action_ledger_add_step,
            )
            if flow_result.get("handled"):
                reply = str(flow_result.get("reply") or reply)
                reply_contract = str(flow_result.get("reply_contract") or reply_contract)
                planner_decision = str(flow_result.get("planner_decision") or planner_decision)
                meta = flow_result.get("meta") if isinstance(flow_result.get("meta"), dict) else meta
                routing_decision = flow_result.get("routing_decision") if isinstance(flow_result.get("routing_decision"), dict) else routing_decision
            reply_text = turn_finalization_service.finalize_reply_sequence_result(
                reply,
                session=session,
                session_id=session_id,
                user_input=text,
                ledger=ledger,
                routing_decision=routing_decision if isinstance(routing_decision, dict) else {},
                meta=meta if isinstance(meta, dict) else {},
                routed_text=routed_text,
                turns=turns,
                fallback_state=conversation_state,
                append_session_turn_fn=append_session_turn_fn,
                behavior_record_event_fn=core_module.behavior_record_event,
                infer_post_reply_conversation_state_fn=core_module._infer_post_reply_conversation_state,
                build_turn_reflection_fn=core_module.build_turn_reflection,
                finalize_action_ledger_record_fn=core_module.finalize_action_ledger_record,
                finalize_routing_decision_fn=core_module._finalize_routing_decision,
                action_ledger_route_summary_fn=core_module.action_ledger_route_summary,
            )
            invalidate_control_status_cache_fn()
            return reply_text
        finally:
            core_module.set_active_user(previous_user)


HTTP_CHAT_RUNTIME_SERVICE = NovaHttpChatRuntimeService()