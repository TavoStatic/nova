from __future__ import annotations

from services.nova_session_state import apply_reply_session_updates


class NovaHttpTurnFinalizationService:
    """Own HTTP reply finalization and post-reply session updates outside the shell."""

    @staticmethod
    def finalize_http_reply(
        reply_text: str,
        *,
        session,
        session_id: str,
        user_input: str,
        ledger: dict,
        routing_decision: dict | None,
        build_turn_reflection_fn,
        finalize_action_ledger_record_fn,
        finalize_routing_decision_fn,
        action_ledger_route_summary_fn,
        planner_decision: str = "deterministic",
        tool: str = "",
        tool_args: dict | None = None,
        tool_result: str = "",
        grounded: bool | None = None,
        intent: str = "",
        reply_contract: str = "",
        reply_outcome: dict | None = None,
    ) -> str:
        tool_args_payload = tool_args if isinstance(tool_args, dict) else {}
        reply_outcome_payload = reply_outcome if isinstance(reply_outcome, dict) else {}
        routing_payload = routing_decision if isinstance(routing_decision, dict) else {}
        finalized_routing = finalize_routing_decision_fn(
            routing_payload,
            planner_decision=planner_decision,
            reply_contract=str(reply_contract or ""),
            reply_outcome=reply_outcome_payload,
            turn_acts=list(ledger.get("turn_acts") or []),
        )
        reflection_payload = build_turn_reflection_fn(
            session,
            entry_point="http",
            session_id=session_id,
            current_decision={
                "user_input": user_input,
                "planner_decision": planner_decision,
                "tool": tool,
                "tool_args": tool_args_payload,
                "tool_result": tool_result,
                "final_answer": reply_text,
                "reply_contract": str(reply_contract or ""),
                "reply_outcome": reply_outcome_payload,
                "turn_acts": list(ledger.get("turn_acts") or []),
                "grounded": grounded,
                "active_subject": session.active_subject(),
                "continuation_used": session.continuation_used_last_turn,
                "pending_action": session.pending_action,
                "routing_decision": finalized_routing,
                "route_summary": action_ledger_route_summary_fn(ledger),
                "overrides_active": session.reflection_summary().get("overrides_active", []),
            },
        )
        finalize_action_ledger_record_fn(
            ledger,
            final_answer=reply_text,
            planner_decision=planner_decision,
            tool=tool,
            tool_args=tool_args_payload,
            tool_result=tool_result,
            grounded=grounded,
            intent=intent,
            active_subject=session.active_subject(),
            continuation_used=session.continuation_used_last_turn,
            reply_contract=str(reply_contract or ""),
            reply_outcome=reply_outcome_payload,
            routing_decision=routing_payload,
            reflection_payload=reflection_payload,
        )
        return reply_text

    def finalize_flow_reply(
        self,
        flow_result: dict,
        *,
        session,
        session_id: str,
        user_input: str,
        ledger: dict,
        routing_decision: dict | None,
        append_session_turn_fn,
        build_turn_reflection_fn,
        finalize_action_ledger_record_fn,
        finalize_routing_decision_fn,
        action_ledger_route_summary_fn,
    ) -> str:
        reply = str(flow_result.get("reply") or "")
        append_session_turn_fn(session_id, "assistant", reply)
        return self.finalize_http_reply(
            reply,
            session=session,
            session_id=session_id,
            user_input=user_input,
            ledger=ledger,
            routing_decision=routing_decision,
            build_turn_reflection_fn=build_turn_reflection_fn,
            finalize_action_ledger_record_fn=finalize_action_ledger_record_fn,
            finalize_routing_decision_fn=finalize_routing_decision_fn,
            action_ledger_route_summary_fn=action_ledger_route_summary_fn,
            planner_decision=str(flow_result.get("planner_decision") or "deterministic"),
            tool=str(flow_result.get("tool") or ""),
            tool_args=flow_result.get("tool_args") if isinstance(flow_result.get("tool_args"), dict) else {},
            tool_result=str(flow_result.get("tool_result") or ""),
            grounded=flow_result.get("grounded") if isinstance(flow_result.get("grounded"), bool) else None,
            intent=str(flow_result.get("intent") or ""),
            reply_contract=str(flow_result.get("reply_contract") or ""),
            reply_outcome=flow_result.get("reply_outcome") if isinstance(flow_result.get("reply_outcome"), dict) else {},
        )

    def finalize_reply_sequence_result(
        self,
        reply_text: str,
        *,
        session,
        session_id: str,
        user_input: str,
        ledger: dict,
        routing_decision: dict | None,
        meta: dict | None,
        routed_text: str,
        turns: list[tuple[str, str]],
        fallback_state,
        append_session_turn_fn,
        behavior_record_event_fn,
        infer_post_reply_conversation_state_fn,
        build_turn_reflection_fn,
        finalize_action_ledger_record_fn,
        finalize_routing_decision_fn,
        action_ledger_route_summary_fn,
    ) -> str:
        reply_outcome_payload = self.apply_reply_outcome(
            session=session,
            meta=meta,
            routed_text=routed_text,
            turns=turns,
            fallback_state=fallback_state,
            behavior_record_event_fn=behavior_record_event_fn,
            infer_post_reply_conversation_state_fn=infer_post_reply_conversation_state_fn,
        )
        append_session_turn_fn(session_id, "assistant", reply_text)
        return self.finalize_http_reply(
            reply_text,
            session=session,
            session_id=session_id,
            user_input=user_input,
            ledger=ledger,
            routing_decision=routing_decision,
            build_turn_reflection_fn=build_turn_reflection_fn,
            finalize_action_ledger_record_fn=finalize_action_ledger_record_fn,
            finalize_routing_decision_fn=finalize_routing_decision_fn,
            action_ledger_route_summary_fn=action_ledger_route_summary_fn,
            planner_decision=str(reply_outcome_payload.get("planner_decision") or "deterministic"),
            tool=str(reply_outcome_payload.get("tool") or ""),
            tool_args=reply_outcome_payload.get("tool_args") if isinstance(reply_outcome_payload.get("tool_args"), dict) else {},
            tool_result=str(reply_outcome_payload.get("tool_result") or ""),
            grounded=reply_outcome_payload.get("grounded") if isinstance(reply_outcome_payload.get("grounded"), bool) else None,
            reply_contract=str(reply_outcome_payload.get("reply_contract") or ""),
            reply_outcome=reply_outcome_payload.get("reply_outcome") if isinstance(reply_outcome_payload.get("reply_outcome"), dict) else {},
        )

    @staticmethod
    def apply_reply_outcome(
        *,
        session,
        meta: dict | None,
        routed_text: str,
        turns: list[tuple[str, str]],
        fallback_state,
        behavior_record_event_fn,
        infer_post_reply_conversation_state_fn,
    ) -> dict:
        payload = meta if isinstance(meta, dict) else {}
        planner_decision = str(payload.get("planner_decision") or "deterministic")
        tool = str(payload.get("tool") or "")
        tool_args = payload.get("tool_args") if isinstance(payload.get("tool_args"), dict) else {}
        tool_result = str(payload.get("tool_result") or "")
        grounded = payload.get("grounded") if isinstance(payload.get("grounded"), bool) else None
        reply_contract = str(payload.get("reply_contract") or "")
        reply_outcome = payload.get("reply_outcome") if isinstance(payload.get("reply_outcome"), dict) else {}

        if planner_decision in {"command", "run_tool", "grounded_lookup"}:
            behavior_record_event_fn("tool_route")
        elif planner_decision == "llm_fallback":
            behavior_record_event_fn("llm_fallback")

        next_state = apply_reply_session_updates(
            session,
            meta={
                "planner_decision": planner_decision,
                "tool": tool,
                "tool_args": tool_args,
                "tool_result": tool_result,
                "pending_action": payload.get("pending_action"),
            },
            routed_text=routed_text,
            turns=turns,
            fallback_state=fallback_state,
            infer_post_reply_conversation_state=infer_post_reply_conversation_state_fn,
        )
        return {
            "planner_decision": planner_decision,
            "tool": tool,
            "tool_args": tool_args,
            "tool_result": tool_result,
            "grounded": grounded,
            "reply_contract": reply_contract,
            "reply_outcome": reply_outcome,
            "next_state": next_state,
        }


HTTP_TURN_FINALIZATION_SERVICE = NovaHttpTurnFinalizationService()