from __future__ import annotations

from services.nova_http_routing import execute_http_routing_sequence


class NovaHttpChatRuntimeService:
    """Own the top-level HTTP chat session coordinator outside the transport shell."""

    @staticmethod
    def _runtime_fn(runtime_scope: dict[str, object], name: str):
        return runtime_scope[name]

    def process_chat(
        self,
        session_id: str,
        user_text: str,
        *,
        user_id: str = "",
        core_module,
        session_state_manager,
        turn_finalization_service,
        http_chat_flow_module,
        append_session_turn_fn,
        generate_chat_reply_fn,
        invalidate_control_status_cache_fn,
        fast_smalltalk_reply_fn,
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

            prepared_turn = http_chat_flow_module.prepare_chat_turn(
                session_id=session_id,
                text=text,
                session=session,
                ledger=ledger,
                append_session_turn=append_session_turn_fn,
                determine_turn_direction=core_module._determine_turn_direction,
                auto_adjust_language_mix=core_module._auto_adjust_language_mix,
                action_ledger_add_step=core_module.action_ledger_add_step,
                evaluate_supervisor_rules=lambda routed_text, **kwargs: core_module.TURN_SUPERVISOR.evaluate_rules(routed_text, **kwargs),
                supervisor_has_route=core_module._supervisor_result_has_route,
                runtime_set_location_intent=core_module._runtime_set_location_intent,
                llm_classify_routing_intent=core_module._llm_classify_routing_intent,
                is_identity_only_session=core_module._session_identity_only_mode,
                identity_only_block_kind=core_module._identity_only_block_kind,
            )
            turns = list(prepared_turn.get("turns") or [])
            routed_text = str(prepared_turn.get("routed_text") or text)
            turn_acts = [str(item).strip() for item in list(prepared_turn.get("turn_acts") or []) if str(item).strip()]
            intent_rule = prepared_turn.get("intent_rule") if isinstance(prepared_turn.get("intent_rule"), dict) else {}

            routing_result = execute_http_routing_sequence(
                text=text,
                routed_text=routed_text,
                identity_only_block_kind=str(prepared_turn.get("identity_only_block_kind") or ""),
                turns=turns,
                turn_acts=turn_acts,
                intent_rule=intent_rule,
                session=session,
                ledger=ledger,
                conversation_state=conversation_state,
                identity_only_block_reply=core_module._identity_only_block_reply,
                should_clarify_unlabeled_numeric_turn=core_module._should_clarify_unlabeled_numeric_turn,
                unlabeled_numeric_turn_reply=core_module._unlabeled_numeric_turn_reply,
                mixed_info_request_clarify_reply=core_module._mixed_info_request_clarify_reply,
                build_routing_decision=core_module._build_routing_decision,
                handle_supervisor_intent=core_module._handle_supervisor_intent,
                supervisor_has_route=core_module._supervisor_result_has_route,
                should_warn_supervisor_bypass=core_module._should_warn_supervisor_bypass,
                emit_supervisor_intent_trace=core_module._emit_supervisor_intent_trace,
                is_web_research_override_request=core_module._is_web_research_override_request,
                learn_self_identity_binding=core_module._learn_self_identity_binding,
                evaluate_supervisor_rules=lambda routed, **kwargs: core_module.TURN_SUPERVISOR.evaluate_rules(routed, **kwargs),
                execute_registered_supervisor_rule=core_module._execute_registered_supervisor_rule,
                fulfillment_flow_service=core_module._fulfillment_flow_service(),
                fast_smalltalk_reply=fast_smalltalk_reply_fn,
                learn_contextual_developer_facts=learn_contextual_developer_facts_fn,
                infer_profile_conversation_state=core_module._infer_profile_conversation_state,
                make_conversation_state=core_module._make_conversation_state,
                learn_contextual_self_facts=core_module._learn_contextual_self_facts,
                extract_memory_teach_text=extract_memory_teach_text_fn,
                mem_enabled=core_module.mem_enabled,
                store_location_fact_reply=core_module._store_location_fact_reply,
                weather_for_saved_location=core_module._weather_for_saved_location,
                is_saved_location_weather_query=core_module._is_saved_location_weather_query,
                get_saved_location_text=core_module.get_saved_location_text,
                store_declarative_fact_outcome=core_module._store_declarative_fact_outcome,
                render_reply=core_module.render_reply,
                consume_conversation_followup=core_module._consume_conversation_followup,
                conversation_active_subject=core_module._conversation_active_subject,
                developer_work_guess_turn=core_module._developer_work_guess_turn,
                developer_location_turn=core_module._developer_location_turn,
                action_ledger_add_step=core_module.action_ledger_add_step,
                ensure_reply=core_module._ensure_reply,
            )
            conversation_state = routing_result.get("conversation_state") if isinstance(routing_result.get("conversation_state"), dict) else conversation_state
            routing_decision = routing_result.get("routing_decision") if isinstance(routing_result.get("routing_decision"), dict) else routing_decision
            warn_supervisor_bypass = bool(routing_result.get("warn_supervisor_bypass"))
            if routing_result.get("handled"):
                flow_result = routing_result.get("flow_result") if isinstance(routing_result.get("flow_result"), dict) else {}
                return _finalize_flow_reply(flow_result)

            normalized_routed_text = str(routed_text or "").strip().lower()
            patch_command_like = bool(
                normalized_routed_text == "patch rollback"
                or normalized_routed_text.startswith("patch ")
                or " patch apply " in f" {normalized_routed_text} "
                or " patch preview " in f" {normalized_routed_text} "
                or " patch show " in f" {normalized_routed_text} "
                or " patch approve " in f" {normalized_routed_text} "
                or " patch reject " in f" {normalized_routed_text} "
            )
            if warn_supervisor_bypass and patch_command_like:
                flow_result = http_chat_flow_module.apply_supervisor_bypass_safe_fallback(
                    warn_supervisor_bypass=True,
                    reply_contract="",
                    routed_text=routed_text,
                    turns=turns,
                    routing_decision=routing_decision,
                    ledger=ledger,
                    open_probe_reply=core_module._open_probe_reply,
                    action_ledger_add_step=core_module.action_ledger_add_step,
                )
                reply = str(flow_result.get("reply") or "")
                meta = flow_result.get("meta") if isinstance(flow_result.get("meta"), dict) else {}
                routing_decision = flow_result.get("routing_decision") if isinstance(flow_result.get("routing_decision"), dict) else routing_decision
            else:
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

    def process_chat_from_runtime(
        self,
        session_id: str,
        user_text: str,
        *,
        user_id: str = "",
        core_module,
        runtime_scope: dict[str, object],
    ) -> str:
        return self.process_chat(
            session_id,
            user_text,
            user_id=user_id,
            core_module=core_module,
            session_state_manager=runtime_scope["SESSION_STATE_MANAGER"],
            turn_finalization_service=runtime_scope["HTTP_TURN_FINALIZATION_SERVICE"],
            http_chat_flow_module=runtime_scope["http_chat_flow"],
            append_session_turn_fn=self._runtime_fn(runtime_scope, "_append_session_turn"),
            generate_chat_reply_fn=self._runtime_fn(runtime_scope, "_generate_chat_reply"),
            invalidate_control_status_cache_fn=self._runtime_fn(runtime_scope, "_invalidate_control_status_cache"),
            fast_smalltalk_reply_fn=self._runtime_fn(runtime_scope, "_fast_smalltalk_reply"),
            learn_contextual_developer_facts_fn=self._runtime_fn(runtime_scope, "_learn_contextual_developer_facts"),
            extract_memory_teach_text_fn=core_module._extract_memory_teach_text,
        )


HTTP_CHAT_RUNTIME_SERVICE = NovaHttpChatRuntimeService()
