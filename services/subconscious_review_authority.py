from __future__ import annotations

from typing import Any, Callable, Optional


def _default_supervisor_review(signal: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
    preferred_owner = str(payload.get("preferred_owner") or "").strip().lower()
    route_hint = str(payload.get("route_hint") or "").strip().lower()
    approved = preferred_owner == "supervisor" and route_hint == "supervisor_owned"
    return {
        "approved": approved,
        "authority_owner": "supervisor",
        "authority_status": "approved" if approved else "rejected",
        "authority_reason": (
            "supervisor contract matched owner and route hint"
            if approved
            else "supervisor contract did not match owner/route hint"
        ),
    }


def _default_fulfillment_review(signal: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
    preferred_owner = str(payload.get("preferred_owner") or "").strip().lower()
    route_hint = str(payload.get("route_hint") or "").strip().lower()
    approved = preferred_owner == "fulfillment" and route_hint == "fulfillment_applicable"
    return {
        "approved": approved,
        "authority_owner": "fulfillment",
        "authority_status": "approved" if approved else "rejected",
        "authority_reason": (
            "fulfillment contract matched owner and route hint"
            if approved
            else "fulfillment contract did not match owner/route hint"
        ),
    }


def _default_route_comparison_review(signal: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
    preferred_owner = str(payload.get("preferred_owner") or "").strip().lower()
    route_hint = str(payload.get("route_hint") or "").strip().lower()
    approved = preferred_owner == "fulfillment_supervisor" and route_hint == "route_comparison"
    return {
        "approved": approved,
        "authority_owner": "fulfillment_supervisor",
        "authority_status": "approved" if approved else "rejected",
        "authority_reason": (
            "route comparison contract matched shared review lane"
            if approved
            else "route comparison contract did not match shared review lane"
        ),
    }


class SubconsciousReviewAuthorityService:
    """Consume subconscious review contracts and return promotion verdicts."""

    @staticmethod
    def _runtime_pressure(signal: dict[str, Any]) -> dict[str, Any]:
        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        review_context = payload.get("review_context") if isinstance(payload.get("review_context"), dict) else {}
        runtime_context = review_context.get("runtime_context") if isinstance(review_context.get("runtime_context"), dict) else {}
        if not runtime_context:
            return {
                "active": False,
                "reason": "",
            }
        regression_status = str(runtime_context.get("last_regression_status") or "").strip()
        regression_stale = bool(runtime_context.get("last_regression_stale", False))
        regression_failed = (
            not regression_stale
            and bool(regression_status)
            and "pass" not in regression_status.lower()
            and regression_status.lower() != "ok"
        )
        queue_failed = str(runtime_context.get("generated_queue_status") or "").strip().lower() == "failed"
        queue_open_count = int(runtime_context.get("queue_open_count", 0) or 0)
        work_tree_waiting = str(runtime_context.get("work_tree_status") or "").strip().lower() == "waiting"
        active = regression_failed or queue_failed or (work_tree_waiting and queue_open_count > 0)
        reasons: list[str] = []
        if regression_failed:
            reasons.append("regression_failed")
        if queue_failed:
            reasons.append("generated_queue_failed")
        if work_tree_waiting and queue_open_count > 0:
            reasons.append(f"work_tree_waiting_with_open_queue={queue_open_count}")
        return {
            "active": active,
            "reason": ", ".join(reasons),
        }

    @staticmethod
    def _candidate_backlog(signal: dict[str, Any]) -> dict[str, Any]:
        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        review_context = payload.get("review_context") if isinstance(payload.get("review_context"), dict) else {}
        candidate_backlog = review_context.get("candidate_backlog") if isinstance(review_context.get("candidate_backlog"), dict) else {}
        return {
            "prior_action": str(candidate_backlog.get("prior_action") or "").strip(),
            "prior_branch_id": str(candidate_backlog.get("prior_branch_id") or "").strip(),
            "prior_tree_id": str(candidate_backlog.get("prior_tree_id") or "").strip(),
            "prior_authority_status": str(candidate_backlog.get("prior_authority_status") or "").strip(),
            "prior_triage_status": str(candidate_backlog.get("prior_triage_status") or "").strip(),
            "already_waiting": bool(candidate_backlog.get("already_waiting")),
            "waiting_tool": str(candidate_backlog.get("waiting_tool") or "").strip(),
            "waiting_action": str(candidate_backlog.get("waiting_action") or "").strip(),
            "waiting_branch_title": str(candidate_backlog.get("waiting_branch_title") or "").strip(),
            "live_branch_status": str(candidate_backlog.get("live_branch_status") or "").strip(),
            "live_resolution_state": str(candidate_backlog.get("live_resolution_state") or "").strip(),
            "live_preferred_tool": str(candidate_backlog.get("live_preferred_tool") or "").strip(),
            "open_task_count": int(candidate_backlog.get("open_task_count", 0) or 0),
            "active_task_count": int(candidate_backlog.get("active_task_count", 0) or 0),
            "next_open_task_title": str(candidate_backlog.get("next_open_task_title") or "").strip(),
            "next_open_task_status": str(candidate_backlog.get("next_open_task_status") or "").strip(),
        }

    @staticmethod
    def _probe_snapshot(
        signal: dict[str, Any],
        *,
        probe_turn_routes_fn: Optional[Callable[..., dict[str, Any]]] = None,
        session_factory: Optional[Callable[[], object]] = None,
    ) -> dict[str, Any]:
        if probe_turn_routes_fn is None or session_factory is None:
            return {}
        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        review_context = payload.get("review_context") if isinstance(payload.get("review_context"), dict) else {}
        user_text = str(review_context.get("review_text") or "").strip()
        pending_action = review_context.get("pending_action") if isinstance(review_context.get("pending_action"), dict) else None
        conversation_state = review_context.get("conversation_state") if isinstance(review_context.get("conversation_state"), dict) else None
        turns = list(review_context.get("turns") or []) if isinstance(review_context.get("turns"), list) else []
        if not user_text:
            return {}
        try:
            session = session_factory()
            if conversation_state is not None and hasattr(session, "set_conversation_state"):
                session.set_conversation_state(conversation_state)
            if pending_action is not None and hasattr(session, "set_pending_action"):
                session.set_pending_action(pending_action)
            probe = probe_turn_routes_fn(user_text, session, turns, pending_action=pending_action)
        except Exception as exc:
            return {"probe_error": str(exc)}
        return probe if isinstance(probe, dict) else {}

    @staticmethod
    def _supervisor_reflection_snapshot(
        signal: dict[str, Any],
        *,
        session_factory: Optional[Callable[[], object]] = None,
        supervisor_process_turn_fn: Optional[Callable[..., dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        if session_factory is None or supervisor_process_turn_fn is None:
            return {}
        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        review_context = payload.get("review_context") if isinstance(payload.get("review_context"), dict) else {}
        user_text = str(review_context.get("review_text") or "").strip()
        pending_action = review_context.get("pending_action") if isinstance(review_context.get("pending_action"), dict) else None
        conversation_state = review_context.get("conversation_state") if isinstance(review_context.get("conversation_state"), dict) else None
        if not user_text:
            return {}
        try:
            session = session_factory()
            if conversation_state is not None and hasattr(session, "set_conversation_state"):
                session.set_conversation_state(conversation_state)
            if pending_action is not None and hasattr(session, "set_pending_action"):
                session.set_pending_action(pending_action)
            session_summary = session.reflection_summary() if hasattr(session, "reflection_summary") else {}
            current_decision = {
                "user_input": user_text,
                "pending_action": pending_action,
                "active_subject": session.active_subject() if hasattr(session, "active_subject") else "",
                "planner_decision": "subconscious_review",
                "reply_contract": str(payload.get("review_contract") or ""),
            }
            reflection = supervisor_process_turn_fn(
                entry_point="subconscious_review",
                session_id="subconscious_review",
                session_summary=session_summary if isinstance(session_summary, dict) else {},
                current_decision=current_decision,
                recent_records=[],
                recent_reflections=[],
            )
        except Exception as exc:
            return {"reflection_error": str(exc)}
        return reflection if isinstance(reflection, dict) else {}

    def review_candidate(
        self,
        signal: dict[str, Any],
        gate: dict[str, Any],
        *,
        fulfillment_review_fn: Optional[Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = None,
        supervisor_review_fn: Optional[Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = None,
        route_review_fn: Optional[Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = None,
        probe_turn_routes_fn: Optional[Callable[..., dict[str, Any]]] = None,
        session_factory: Optional[Callable[[], object]] = None,
        evaluate_supervisor_rules_fn: Optional[Callable[..., dict[str, Any]]] = None,
        supervisor_has_route_fn: Optional[Callable[[dict[str, Any]], bool]] = None,
        fulfillment_viability_fn: Optional[Callable[..., dict[str, Any]]] = None,
        supervisor_process_turn_fn: Optional[Callable[..., dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        contract = str(gate.get("review_contract") or "").strip().lower()
        if not bool(gate.get("approved")):
            return {
                "approved": False,
                "authority_owner": str(gate.get("preferred_owner") or "").strip(),
                "authority_status": "not_reviewed",
                "authority_reason": "candidate did not clear triage gate",
            }

        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        urgency = str(payload.get("urgency") or "").strip().lower()
        runtime_pressure = self._runtime_pressure(signal)
        candidate_backlog = self._candidate_backlog(signal)
        review_context = payload.get("review_context") if isinstance(payload.get("review_context"), dict) else {}
        runtime_context = review_context.get("runtime_context") if isinstance(review_context.get("runtime_context"), dict) else {}
        prior_staged = bool(candidate_backlog.get("prior_branch_id")) and str(candidate_backlog.get("prior_authority_status") or "").strip().lower() == "approved"
        sampled_waiting = bool(candidate_backlog.get("already_waiting"))
        broad_waiting = str(runtime_context.get("work_tree_status") or "").strip().lower() == "waiting"
        live_open = int(candidate_backlog.get("open_task_count", 0) or 0) > 0
        live_branch_status = str(candidate_backlog.get("live_branch_status") or "").strip().lower()
        active_or_ready = live_branch_status in {"ready", "active", "blocked"}
        if (
            (sampled_waiting and urgency in {"low", "medium"})
            or (prior_staged and broad_waiting and urgency == "low")
            or (prior_staged and live_open and active_or_ready and urgency == "medium")
        ):
            return {
                "approved": False,
                "authority_owner": str(gate.get("preferred_owner") or payload.get("preferred_owner") or "").strip(),
                "authority_status": "already_staged",
                "authority_reason": (
                    f"candidate already staged on branch {candidate_backlog.get('prior_branch_id') or '?'} "
                    f"waiting_action={candidate_backlog.get('waiting_action') or candidate_backlog.get('live_branch_status') or '?'} "
                    f"tool={candidate_backlog.get('waiting_tool') or candidate_backlog.get('live_preferred_tool') or '?'} "
                    f"next_task={candidate_backlog.get('next_open_task_title') or '?'}"
                ),
            }
        review_context = payload.get("review_context") if isinstance(payload.get("review_context"), dict) else {}
        user_text = str(review_context.get("review_text") or "").strip()
        pending_action = review_context.get("pending_action") if isinstance(review_context.get("pending_action"), dict) else None
        conversation_state = review_context.get("conversation_state") if isinstance(review_context.get("conversation_state"), dict) else None
        turns = list(review_context.get("turns") or []) if isinstance(review_context.get("turns"), list) else []

        if user_text and session_factory is not None:
            try:
                live_session = session_factory()
                if conversation_state is not None and hasattr(live_session, "set_conversation_state"):
                    live_session.set_conversation_state(conversation_state)
                if pending_action is not None and hasattr(live_session, "set_pending_action"):
                    live_session.set_pending_action(pending_action)
            except Exception:
                live_session = None
        else:
            live_session = None

        if contract == "subconscious.review.supervisor" and live_session is not None and evaluate_supervisor_rules_fn is not None and supervisor_has_route_fn is not None:
            try:
                supervisor_result = evaluate_supervisor_rules_fn(
                    user_text,
                    manager=live_session,
                    turns=turns,
                    phase="handle",
                    entry_point="subconscious_review",
                )
            except Exception as exc:
                supervisor_result = {"handled": False, "rule_error": str(exc)}
            supervisor_viable = bool(supervisor_has_route_fn(supervisor_result if isinstance(supervisor_result, dict) else {}))
            if supervisor_viable and runtime_pressure.get("active") and urgency in {"low", "medium"}:
                return {
                    "approved": False,
                    "authority_owner": "supervisor",
                    "authority_status": "deferred_runtime_pressure",
                    "authority_reason": f"runtime pressure blocked low-priority supervisor review: {runtime_pressure.get('reason')}",
                }
            if supervisor_viable:
                return {
                    "approved": True,
                    "authority_owner": "supervisor",
                    "authority_status": "approved",
                    "authority_reason": (
                        f"live supervisor route=True; runtime_pressure={runtime_pressure.get('reason')}"
                        if runtime_pressure.get("active")
                        else "live supervisor route=True"
                    ),
                }

        if contract == "subconscious.review.supervisor":
            reflection = self._supervisor_reflection_snapshot(
                signal,
                session_factory=session_factory,
                supervisor_process_turn_fn=supervisor_process_turn_fn,
            )
            if reflection:
                status_counts = reflection.get("probe_status_counts") if isinstance(reflection.get("probe_status_counts"), dict) else {}
                red_count = int(status_counts.get("red", 0) or 0)
                yellow_count = int(status_counts.get("yellow", 0) or 0)
                findings = list(reflection.get("probe_findings") or []) if isinstance(reflection.get("probe_findings"), list) else []
                flagged = [str(item.get("name") or "").strip() for item in findings if isinstance(item, dict) and str(item.get("name") or "").strip()]
                if red_count > 0 or (yellow_count > 0 and urgency == "high"):
                    if runtime_pressure.get("active") and urgency in {"low", "medium"}:
                        return {
                            "approved": False,
                            "authority_owner": "supervisor",
                            "authority_status": "deferred_runtime_pressure",
                            "authority_reason": f"runtime pressure blocked low-priority supervisor review: {runtime_pressure.get('reason')}",
                        }
                    return {
                        "approved": True,
                        "authority_owner": "supervisor",
                        "authority_status": "approved",
                        "authority_reason": (
                            f"live supervisor reflection red={red_count} yellow={yellow_count} findings={', '.join(flagged[:3])}"
                        ),
                    }

        if contract == "subconscious.review.fulfillment" and live_session is not None and fulfillment_viability_fn is not None:
            try:
                fulfillment_result = fulfillment_viability_fn(
                    user_text,
                    live_session,
                    turns,
                    pending_action=pending_action,
                )
            except Exception as exc:
                fulfillment_result = {"viable": False, "error": str(exc)}
            fulfillment_viable = bool((fulfillment_result or {}).get("viable"))
            if fulfillment_viable and runtime_pressure.get("active") and urgency in {"low", "medium"}:
                return {
                    "approved": False,
                    "authority_owner": "fulfillment",
                    "authority_status": "deferred_runtime_pressure",
                    "authority_reason": f"runtime pressure blocked low-priority fulfillment review: {runtime_pressure.get('reason')}",
                }
            if fulfillment_viable:
                return {
                    "approved": True,
                    "authority_owner": "fulfillment",
                    "authority_status": "approved",
                    "authority_reason": (
                        f"live fulfillment viable=True; runtime_pressure={runtime_pressure.get('reason')}"
                        if runtime_pressure.get("active")
                        else "live fulfillment viable=True"
                    ),
                }

        probe = self._probe_snapshot(
            signal,
            probe_turn_routes_fn=probe_turn_routes_fn,
            session_factory=session_factory,
        )
        if probe:
            routes = probe.get("routes") if isinstance(probe.get("routes"), dict) else {}
            supervisor_viable = bool((routes.get("supervisor_owned") or {}).get("viable"))
            fulfillment_viable = bool((routes.get("fulfillment_applicable") or {}).get("viable"))
            signal_name = str(payload.get("signal") or "").strip().lower()
            if contract == "subconscious.review.supervisor":
                approved = supervisor_viable
                if approved and runtime_pressure.get("active") and urgency in {"low", "medium"}:
                    return {
                        "approved": False,
                        "authority_owner": "supervisor",
                        "authority_status": "deferred_runtime_pressure",
                        "authority_reason": f"runtime pressure blocked low-priority supervisor review: {runtime_pressure.get('reason')}",
                    }
                return {
                    "approved": approved,
                    "authority_owner": "supervisor",
                    "authority_status": "approved" if approved else "rejected",
                    "authority_reason": (
                        f"probe supervisor_viable={supervisor_viable}; runtime_pressure={runtime_pressure.get('reason')}"
                        if approved and runtime_pressure.get("active")
                        else f"probe supervisor_viable={supervisor_viable}"
                    ),
                }
            if contract == "subconscious.review.fulfillment":
                approved = fulfillment_viable
                if approved and runtime_pressure.get("active") and urgency in {"low", "medium"}:
                    return {
                        "approved": False,
                        "authority_owner": "fulfillment",
                        "authority_status": "deferred_runtime_pressure",
                        "authority_reason": f"runtime pressure blocked low-priority fulfillment review: {runtime_pressure.get('reason')}",
                    }
                return {
                    "approved": approved,
                    "authority_owner": "fulfillment",
                    "authority_status": "approved" if approved else "rejected",
                    "authority_reason": (
                        f"probe fulfillment_viable={fulfillment_viable}; runtime_pressure={runtime_pressure.get('reason')}"
                        if approved and runtime_pressure.get("active")
                        else f"probe fulfillment_viable={fulfillment_viable}"
                    ),
                }
            if contract == "subconscious.review.route_comparison":
                if signal_name == "route_conflict":
                    approved = supervisor_viable and fulfillment_viable
                else:
                    approved = supervisor_viable or fulfillment_viable
                if approved and runtime_pressure.get("active") and urgency in {"low", "medium"}:
                    return {
                        "approved": False,
                        "authority_owner": "fulfillment_supervisor",
                        "authority_status": "deferred_runtime_pressure",
                        "authority_reason": f"runtime pressure blocked low-priority route review: {runtime_pressure.get('reason')}",
                    }
                return {
                    "approved": approved,
                    "authority_owner": "fulfillment_supervisor",
                    "authority_status": "approved" if approved else "rejected",
                    "authority_reason": (
                        (
                            f"probe supervisor_viable={supervisor_viable} "
                            f"fulfillment_viable={fulfillment_viable}; "
                            f"runtime_pressure={runtime_pressure.get('reason')}"
                        )
                        if approved and runtime_pressure.get("active")
                        else (
                            f"probe supervisor_viable={supervisor_viable} "
                            f"fulfillment_viable={fulfillment_viable}"
                        )
                    ),
                }

        if contract == "subconscious.review.supervisor":
            reviewer = supervisor_review_fn or _default_supervisor_review
            return reviewer(signal, gate)
        if contract == "subconscious.review.fulfillment":
            reviewer = fulfillment_review_fn or _default_fulfillment_review
            return reviewer(signal, gate)
        if contract == "subconscious.review.route_comparison":
            reviewer = route_review_fn or _default_route_comparison_review
            return reviewer(signal, gate)
        return {
            "approved": False,
            "authority_owner": "maintenance_review",
            "authority_status": "unsupported_contract",
            "authority_reason": f"unsupported review contract: {contract or 'missing'}",
        }


SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE = SubconsciousReviewAuthorityService()
