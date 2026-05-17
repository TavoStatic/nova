from __future__ import annotations

from services.nova_http_routing import execute_http_routing_sequence
from services.work_tree_decision_adapter import WORK_TREE_DECISION_ADAPTER
from services.work_tree_seeding import WORK_TREE_SEEDING_SERVICE


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

            def _ensure_active_work_tree(seed_text: str) -> str:
                existing = str(getattr(session, "active_work_tree_id", "") or "").strip()
                existing_identity = str(getattr(session, "active_work_identity", "") or "").strip()
                try:
                    import work_tree

                    if existing and work_tree.get_tree(existing) is not None:
                        return existing
                    resolution = WORK_TREE_SEEDING_SERVICE.resolve_seeded_tree(
                        work_tree_module=work_tree,
                        title_seed=str(seed_text or "").strip(),
                        source="http",
                        user_id=user_id or previous_user or "",
                        nova_core_module=core_module,
                        active_tree_id=existing,
                        active_work_identity=existing_identity,
                    )
                except Exception:
                    return ""
                tree_id = str((resolution or {}).get("tree_id") or "").strip()
                work_identity_key = str((resolution or {}).get("work_identity_key") or "").strip()
                continuity = str((resolution or {}).get("continuity") or "").strip()
                branch_decision = str((resolution or {}).get("branch_decision") or "").strip()
                decision_type = str((resolution or {}).get("decision_type") or "").strip()
                branch_id = str((resolution or {}).get("branch_id") or "").strip()
                if work_identity_key and (decision_type or continuity) and hasattr(session, "record_decision"):
                    try:
                        session.record_decision(
                            decision_type=decision_type or continuity,
                            work_identity_key=work_identity_key,
                            branch_id=branch_id,
                        )
                    except Exception:
                        pass
                if work_identity_key and hasattr(session, "set_decision_adapter_bias"):
                    try:
                        bias = WORK_TREE_DECISION_ADAPTER.get_bias_for_identity(work_identity_key=work_identity_key)
                        if bias:
                            session.set_decision_adapter_bias(bias)
                    except Exception:
                        pass
                if hasattr(session, "set_active_work_tree_id"):
                    try:
                        session.set_active_work_tree_id(tree_id)
                    except Exception:
                        pass
                if hasattr(session, "set_active_work_identity"):
                    try:
                        session.set_active_work_identity(work_identity_key)
                    except Exception:
                        pass
                if hasattr(session, "set_last_work_continuity"):
                    try:
                        session.set_last_work_continuity(continuity)
                    except Exception:
                        pass
                if hasattr(session, "set_last_branch_decision"):
                    try:
                        session.set_last_branch_decision(branch_decision or continuity)
                    except Exception:
                        pass
                return tree_id

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
            )
            turns = list(prepared_turn.get("turns") or [])
            routed_text = str(prepared_turn.get("routed_text") or text)
            turn_acts = [str(item).strip() for item in list(prepared_turn.get("turn_acts") or []) if str(item).strip()]
            intent_rule = prepared_turn.get("intent_rule") if isinstance(prepared_turn.get("intent_rule"), dict) else {}

            routing_result = execute_http_routing_sequence(
                text=text,
                routed_text=routed_text,
                turns=turns,
                turn_acts=turn_acts,
                intent_rule=intent_rule,
                session=session,
                ledger=ledger,
                conversation_state=conversation_state,
                should_clarify_unlabeled_numeric_turn=core_module._should_clarify_unlabeled_numeric_turn,
                unlabeled_numeric_turn_reply=core_module._unlabeled_numeric_turn_reply,
                build_routing_decision=core_module._build_routing_decision,
                handle_supervisor_intent=core_module._handle_supervisor_intent,
                supervisor_has_route=core_module._supervisor_result_has_route,
                should_warn_supervisor_bypass=core_module._should_warn_supervisor_bypass,
                emit_supervisor_intent_trace=core_module._emit_supervisor_intent_trace,
                evaluate_supervisor_rules=lambda routed, **kwargs: core_module.TURN_SUPERVISOR.evaluate_rules(routed, **kwargs),
                execute_registered_supervisor_rule=core_module._execute_registered_supervisor_rule,
                make_conversation_state=core_module._make_conversation_state,
                action_ledger_add_step=core_module.action_ledger_add_step,
                ensure_reply=core_module._ensure_reply,
            )
            if "conversation_state" in routing_result:
                next_conversation_state = routing_result.get("conversation_state")
                conversation_state = next_conversation_state if isinstance(next_conversation_state, dict) else None
            routing_decision = routing_result.get("routing_decision") if isinstance(routing_result.get("routing_decision"), dict) else routing_decision
            if routing_result.get("handled"):
                flow_result = routing_result.get("flow_result") if isinstance(routing_result.get("flow_result"), dict) else {}
                if hasattr(session, "set_conversation_state"):
                    session.set_conversation_state(conversation_state if isinstance(conversation_state, dict) else None)
                return _finalize_flow_reply(flow_result)

            reply, meta = generate_chat_reply_fn(
                turns,
                routed_text,
                ledger_record=ledger,
                pending_action=session.pending_action,
                prefer_web_for_data_queries=session.prefer_web_for_data_queries,
                language_mix_spanish_pct=int(session.language_mix_spanish_pct or 0),
                session=session,
                ensure_active_work_tree_fn=_ensure_active_work_tree,
            )
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
        )


HTTP_CHAT_RUNTIME_SERVICE = NovaHttpChatRuntimeService()
