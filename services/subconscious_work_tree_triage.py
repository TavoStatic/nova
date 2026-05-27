from __future__ import annotations

from typing import Any

from subconscious_config import SUBCONSCIOUS_CHARTER

_SUPERVISOR_SEAM_HINTS = {
    "supervisor_ownership_boundary",
    "weather_continuation_route_fallthrough",
    "retrieval_followup_route_fallthrough",
    "patch_routing_fallthrough",
    "session_fact_recall_route_fallthrough",
}

_FULFILLMENT_SEAM_HINTS = {
    "fulfillment_bridge_entry_fallthrough",
}

_RETIRED_CONTENT_SEAM_HINTS = {
    "memory_capture_route_fallthrough",
}
FULFILLMENT_REVIEW_TEXT = "show me workable options without collapsing too early"


def _fallback_review_context_for_source(source_key: str) -> dict[str, Any]:
    key = str(source_key or "").strip().lower()
    if "fulfillment" in key:
        return {
            "review_text": "Show me workable options without collapsing too early.",
            "pending_action": None,
            "conversation_state": None,
            "turns": [],
        }
    if "weather" in key:
        return {
            "review_text": "yes get the weather for our location",
            "pending_action": None,
            "conversation_state": None,
            "turns": [],
        }
    if "retrieval" in key:
        return {
            "review_text": "tell me about the first one",
            "pending_action": None,
            "conversation_state": {
                "kind": "retrieval",
                "active_subject": "retrieval_followup",
                "selected_result_index": 0,
            },
            "turns": [
                ("user", "find current PEIMS reporting guidance"),
                ("assistant", "I found a few relevant results."),
            ],
        }
    if "patch" in key:
        review_text = "patch preview teach.zip" if "preview" in key else "please patch apply updates.zip"
        return {
            "review_text": review_text,
            "pending_action": None,
            "conversation_state": None,
            "turns": [],
        }
    if "session_fact" in key or "fact_recall" in key:
        return {
            "review_text": "What codeword did I just ask you to remember?",
            "pending_action": None,
            "conversation_state": None,
            "turns": [
                ("user", "For this session, remember the codeword cobalt sparrow and the topic packaging drift."),
                ("assistant", "Got it."),
            ],
        }
    if "weak" in key or "unclear" in key:
        return {
            "review_text": "what now",
            "pending_action": None,
            "conversation_state": None,
            "turns": [],
        }
    return {}


class SubconsciousWorkTreeTriageService:
    """Translate subconscious pressure into governed Work Tree review candidates."""

    @staticmethod
    def _scenario_review_context(
        family_id: str,
        signal_name: str,
        suggested_test_name: str,
        variation_results: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if not family_id:
            return {}
        matched_scenario_ids: list[str] = []
        for item in list(variation_results or []):
            if not isinstance(item, dict):
                continue
            scenario_id = str(item.get("scenario_id") or "").strip()
            if not scenario_id:
                continue
            report_review_context = item.get("review_context") if isinstance(item.get("review_context"), dict) else {}
            active_signals = {str(value or "").strip() for value in list(item.get("active_recent_signals") or []) if str(value or "").strip()}
            candidate_pairs = {
                (
                    str(candidate.get("signal") or "").strip(),
                    str(candidate.get("suggested_test_name") or "").strip(),
                )
                for candidate in list(item.get("candidate_tests") or [])
                if isinstance(candidate, dict)
            }
            if (
                signal_name in active_signals
                or any(sig == signal_name for sig, _name in candidate_pairs)
                or any(name == suggested_test_name for _sig, name in candidate_pairs if suggested_test_name)
            ):
                if report_review_context:
                    return {
                        "review_text": str(report_review_context.get("review_text") or "").strip(),
                        "pending_action": report_review_context.get("pending_action") if isinstance(report_review_context.get("pending_action"), dict) else None,
                        "conversation_state": report_review_context.get("conversation_state") if isinstance(report_review_context.get("conversation_state"), dict) else None,
                        "turns": list(report_review_context.get("turns") or []) if isinstance(report_review_context.get("turns"), list) else [],
                        "scenario_id": str(report_review_context.get("scenario_id") or scenario_id).strip(),
                        "family_id": str(report_review_context.get("family_id") or family_id).strip(),
                    }
                matched_scenario_ids.append(scenario_id)
        if not matched_scenario_ids:
            return {}
        try:
            from subconscious_live_simulator import build_default_live_scenario_families
        except Exception:
            return {}
        for family in list(build_default_live_scenario_families() or []):
            if str(getattr(family, "family_id", "") or "").strip() != family_id:
                continue
            for scenario in list(getattr(family, "scenarios", []) or []):
                scenario_id = str(getattr(scenario, "scenario_id", "") or "").strip()
                if scenario_id not in matched_scenario_ids:
                    continue
                turns = list(getattr(scenario, "turns", []) or [])
                first_turn = turns[0] if turns else None
                return {
                    "review_text": str(getattr(first_turn, "user_text", "") or "").strip(),
                    "pending_action": getattr(first_turn, "pending_action", None) if first_turn is not None else None,
                    "conversation_state": getattr(first_turn, "conversation_state", None) if first_turn is not None else None,
                    "turns": list(getattr(scenario, "seed_turns", []) or []),
                    "scenario_id": scenario_id,
                    "family_id": family_id,
                }
        return {}

    @classmethod
    def _review_context(
        cls,
        signal_name: str,
        target_seam: str,
        *,
        family_id: str = "",
        suggested_test_name: str = "",
        variation_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        scenario_context = cls._scenario_review_context(family_id, signal_name, suggested_test_name, variation_results)
        if scenario_context:
            return scenario_context
        signal_key = str(signal_name or "").strip().lower()
        seam_key = str(target_seam or "").strip().lower()

        if signal_key == "supervisor_overreach":
            return {
                "review_text": "check the weather if you can please..",
                "pending_action": None,
                "conversation_state": None,
                "turns": [],
            }
        if signal_key == "fulfillment_missed":
            return {
                "review_text": FULFILLMENT_REVIEW_TEXT,
                "pending_action": None,
                "conversation_state": None,
                "turns": [],
            }
        if signal_key == "fallback_overuse":
            review_context = _fallback_review_context_for_source(
                " ".join(
                    value
                    for value in (
                        family_id,
                        target_seam,
                        suggested_test_name,
                    )
                    if value
                )
            )
            if review_context:
                return review_context
        if signal_key == "route_conflict":
            return {
                "review_text": "compare options and also use the saved route",
                "pending_action": None,
                "conversation_state": None,
                "turns": [],
            }
        if signal_key in {"route_unclear", "route_fit_weak"}:
            return {
                "review_text": "what now",
                "pending_action": None,
                "conversation_state": None,
                "turns": [],
            }
        if "fulfillment" in seam_key:
            return {
                "review_text": FULFILLMENT_REVIEW_TEXT,
                "pending_action": None,
                "conversation_state": None,
                "turns": [],
            }
        if "supervisor" in seam_key:
            return {
                "review_text": "check the weather if you can please..",
                "pending_action": None,
                "conversation_state": None,
                "turns": [],
            }
        return {
            "review_text": "",
            "pending_action": None,
            "conversation_state": None,
            "turns": [],
        }

    def classify_owner(self, signal_name: str, target_seam: str) -> dict[str, str]:
        signal_key = str(signal_name or "").strip().lower()
        seam_key = str(target_seam or "").strip().lower()

        if seam_key in _RETIRED_CONTENT_SEAM_HINTS:
            return {
                "preferred_owner": "maintenance_review",
                "route_hint": "retired_content_route",
                "triage_reason": "target seam belongs to retired content-owned chat routing",
            }
        if seam_key in _SUPERVISOR_SEAM_HINTS:
            return {
                "preferred_owner": "supervisor",
                "route_hint": "supervisor_owned",
                "triage_reason": "target seam is a supervisor-owned route family",
            }
        if seam_key in _FULFILLMENT_SEAM_HINTS:
            return {
                "preferred_owner": "fulfillment",
                "route_hint": "fulfillment_applicable",
                "triage_reason": "target seam is a fulfillment-owned route family",
            }

        if signal_key == "supervisor_overreach":
            return {
                "preferred_owner": "supervisor",
                "route_hint": "supervisor_owned",
                "triage_reason": "subconscious pressure says supervisor ownership may be drifting",
            }
        if signal_key == "fulfillment_missed":
            return {
                "preferred_owner": "fulfillment",
                "route_hint": "fulfillment_applicable",
                "triage_reason": "subconscious pressure says a viable fulfillment path was missed",
            }
        if signal_key in {"route_conflict", "fallback_overuse", "route_unclear", "route_fit_weak"}:
            return {
                "preferred_owner": "fulfillment_supervisor",
                "route_hint": "route_comparison",
                "triage_reason": "subconscious pressure says route comparison needs fulfillment/supervisor review",
            }
        if "fulfillment" in seam_key:
            return {
                "preferred_owner": "fulfillment",
                "route_hint": "fulfillment_applicable",
                "triage_reason": "target seam sits in the fulfillment lane",
            }
        if "supervisor" in seam_key:
            return {
                "preferred_owner": "supervisor",
                "route_hint": "supervisor_owned",
                "triage_reason": "target seam sits in the supervisor lane",
            }
        return {
            "preferred_owner": "maintenance_review",
            "route_hint": "generic_fallback",
            "triage_reason": "no stronger fulfillment/supervisor owner was inferred from subconscious pressure",
        }

    @staticmethod
    def _review_contract(preferred_owner: str, route_hint: str) -> str:
        owner_key = str(preferred_owner or "").strip().lower()
        route_key = str(route_hint or "").strip().lower()
        if owner_key == "supervisor":
            return "subconscious.review.supervisor"
        if owner_key == "fulfillment":
            return "subconscious.review.fulfillment"
        if owner_key == "fulfillment_supervisor" or route_key == "route_comparison":
            return "subconscious.review.route_comparison"
        return "subconscious.review.maintenance"

    @staticmethod
    def _family_review_guidance(
        *,
        family_id: str,
        target_seam: str,
        signal_name: str,
        suggested_test_name: str,
        preferred_owner: str,
    ) -> dict[str, str]:
        family_key = str(family_id or "").strip().lower()
        seam_key = str(target_seam or "").strip().lower()
        signal_key = str(signal_name or "").strip().lower()
        owner_key = str(preferred_owner or "").strip().lower()
        test_name = str(suggested_test_name or "").strip() or "the suggested review session"

        if "memory-capture" in family_key or "memory_capture" in seam_key:
            return {
                "next_task": (
                    f"Trace evidence from {test_name}, confirm this is retired content-owned memory capture pressure, "
                    "and do not reopen supervisor ownership for normal chat phrases."
                ),
                "branch_note": (
                    "Retired memory-capture review: normal chat phrases should not create a supervisor-owned memory lane."
                ),
            }
        if "patch" in family_key or "patch" in seam_key:
            return {
                "next_task": (
                    f"Trace evidence from {test_name}, confirm whether patch routing still falls through, "
                    "and capture whether patch_apply or patch_rollback is the governed next step."
                ),
                "branch_note": (
                    "Patch-routing review: verify the exact patch lane, preserve rollback/apply governance, "
                    "and leave the branch with the right patch tool hint instead of a generic fallback."
                ),
            }
        if "retrieval" in family_key or "retrieval" in seam_key:
            return {
                "next_task": (
                    f"Trace evidence from {test_name}, confirm whether retrieval followup state is preserved, "
                    "and record which selected result or provider context is being lost."
                ),
                "branch_note": (
                    "Retrieval-followup review: check selected-result continuity, retrieval conversation state, "
                    "and whether supervisor routing is dropping the active result context."
                ),
            }
        if "weather" in family_key or "weather" in seam_key:
            return {
                "next_task": (
                    f"Trace evidence from {test_name}, confirm whether weather continuation still falls through, "
                    "and verify pending weather action plus saved-location handling."
                ),
                "branch_note": (
                    "Weather-continuation review: inspect pending weather state, saved-location continuation, "
                    "and whether supervisor routing preserves the weather followup contract."
                ),
            }
        if "session_fact" in family_key or "session_fact" in seam_key or "fact_recall" in seam_key:
            return {
                "next_task": (
                    f"Trace evidence from {test_name}, confirm whether session fact recall still falls through, "
                    "and record what recap or fact-followup state is missing."
                ),
                "branch_note": (
                    "Session-fact review: verify recap and fact recall continuity so the branch captures the missing "
                    "session memory cue instead of only reporting a generic route miss."
                ),
            }
        if "fulfillment" in family_key or "fulfillment" in seam_key or signal_key == "fulfillment_missed":
            return {
                "next_task": (
                    f"Trace evidence from {test_name}, compare fulfillment against the competing route, "
                    "and confirm which viable option was collapsed too early."
                ),
                "branch_note": (
                    "Fulfillment review: compare viable routes, preserve option breadth, and note the exact place "
                    "Nova collapses into fallback before the better fulfillment path is exhausted."
                ),
            }
        if owner_key == "supervisor":
            return {
                "next_task": (
                    f"Trace evidence from {test_name}, confirm whether supervisor-owned handling still drifts, "
                    "and capture the exact route or ownership boundary that fails."
                ),
                "branch_note": (
                    "Supervisor review: inspect route ownership, handoff boundaries, and the concrete condition that "
                    "should keep this family in the supervisor lane."
                ),
            }
        if owner_key == "fulfillment_supervisor" or signal_key in {"route_conflict", "fallback_overuse", "route_unclear", "route_fit_weak"}:
            return {
                "next_task": (
                    f"Trace evidence from {test_name}, compare fulfillment and supervisor outcomes, "
                    "and record why this family still degrades into fallback or route conflict."
                ),
                "branch_note": (
                    "Route-comparison review: compare fulfillment vs supervisor behavior, note the fresher authority "
                    "result, and keep the branch focused on the exact route conflict rather than generic backlog churn."
                ),
            }
        return {
            "next_task": f"Trace evidence from {test_name} and confirm whether {signal_name} is still active in {target_seam}",
            "branch_note": (
                "Subconscious review: inspect the suggested family, confirm whether the pressure is still active, "
                "and leave behind the exact owner, route, and missing behavior."
            ),
        }

    @staticmethod
    def _evidence_sequence(*, target_seam: str, signal_name: str) -> list[dict[str, object]]:
        seam = str(target_seam or "").strip() or "subconscious_pressure"
        signal = str(signal_name or "").strip() or "route_pressure"
        pressure_source = "services" if signal == "fallback_overuse" else "tests"
        return [
            {
                "title": f"Find route evidence for {seam} without running generated tests",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": [seam, "subconscious_live_simulator.py"],
            },
            {
                "title": f"Find pressure evidence for {signal} in {seam}",
                "allowed_tools": ["find"],
                "preferred_tool": "find",
                "tool_args": [signal, pressure_source],
            },
            {
                "title": "Read runtime/subconscious_runs/latest.json subconscious priority report",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
                "tool_args": ["runtime/subconscious_runs/latest.json"],
            },
            {
                "title": "Queue status after subconscious pressure ingestion",
                "allowed_tools": ["queue_status"],
                "preferred_tool": "queue_status",
            },
            {
                "title": f"Synthesize subconscious review judgment for {seam} / {signal}",
                "allowed_tools": ["subconscious_review_judgment"],
                "preferred_tool": "subconscious_review_judgment",
            },
        ]

    def build_signal(
        self,
        *,
        family_id: str,
        target_seam: str,
        signal_name: str,
        suggested_test_name: str,
        rationale: str,
        urgency: str,
        robustness: float,
        variation_results: list[dict[str, Any]] | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        triage = self.classify_owner(signal_name, target_seam)
        preferred_owner = str(triage.get("preferred_owner") or "maintenance_review").strip()
        route_hint = str(triage.get("route_hint") or "generic_fallback").strip()
        triage_reason = str(triage.get("triage_reason") or "").strip()
        review_context = self._review_context(
            signal_name,
            target_seam,
            family_id=family_id,
            suggested_test_name=suggested_test_name,
            variation_results=variation_results,
        )
        if isinstance(runtime_context, dict) and runtime_context:
            review_context = dict(review_context)
            review_context["runtime_context"] = {
                "last_regression_status": str(runtime_context.get("last_regression_status") or "").strip(),
                "generated_queue_status": str(runtime_context.get("generated_queue_status") or "").strip(),
                "queue_open_count": int(runtime_context.get("queue_open_count", 0) or 0),
                "work_tree_status": str(runtime_context.get("work_tree_status") or "").strip(),
                "work_tree_executed_count": int(runtime_context.get("work_tree_executed_count", 0) or 0),
                "work_tree_tree_count": int(runtime_context.get("work_tree_tree_count", 0) or 0),
                "kidney_mode": str(runtime_context.get("kidney_mode") or "").strip(),
                "kidney_candidate_count": int(runtime_context.get("kidney_candidate_count", 0) or 0),
            }
            candidate_backlog = runtime_context.get("candidate_backlog") if isinstance(runtime_context.get("candidate_backlog"), dict) else {}
            if candidate_backlog:
                review_context["candidate_backlog"] = {
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
        severity = {
            "high": "high",
            "medium": "medium",
            "low": "low",
            "deferred": "low",
        }.get(str(urgency or "").strip().lower(), "medium")
        actionability = "blocked" if str(urgency or "").strip().lower() == "deferred" else "safe_now"
        title_prefix = {
            "fulfillment": "Review subconscious priority with fulfillment",
            "supervisor": "Review subconscious priority with supervisor",
            "fulfillment_supervisor": "Review subconscious priority with fulfillment/supervisor",
        }.get(preferred_owner, "Review subconscious priority")
        guidance = self._family_review_guidance(
            family_id=family_id,
            target_seam=target_seam,
            signal_name=signal_name,
            suggested_test_name=suggested_test_name,
            preferred_owner=preferred_owner,
        )
        sequence = self._evidence_sequence(target_seam=target_seam, signal_name=signal_name)
        evidence_first_task = str(sequence[0].get("title") or "").strip()
        family_task = str(guidance.get("next_task") or "").strip()
        next_task = f"{evidence_first_task}; {family_task}" if evidence_first_task and family_task else (family_task or evidence_first_task)
        return {
            "source": "subconscious",
            "signal_class": "subconscious_candidate",
            "title": f"{title_prefix}: {target_seam} / {signal_name}",
            "fingerprint": {
                "class": "subconscious_candidate",
                "surface": target_seam,
                "error": signal_name,
                "symbol": suggested_test_name,
            },
            "payload": {
                "family_id": family_id,
                "target_seam": target_seam,
                "signal": signal_name,
                "suggested_test_name": suggested_test_name,
                "rationale": rationale,
                "urgency": urgency,
                "robustness": robustness,
                "preferred_owner": preferred_owner,
                "route_hint": route_hint,
                "triage_reason": triage_reason,
                "review_contract": self._review_contract(preferred_owner, route_hint),
                "review_context": review_context,
                "branch_note": str(guidance.get("branch_note") or "").strip(),
            },
            "severity": severity,
            "actionability": actionability,
            "allowed_tools": ["find", "read", "queue_status", "subconscious_review_judgment"],
            "preferred_tool": "find",
            "next_task": next_task,
            "task_sequence": sequence,
            "blocked_task": (
                f"Hold owner-root repair lane for {target_seam} / {signal_name} "
                "using synthesized judgment instead of running generated tests as progress"
            ),
            "blocked_reason": "subconscious_pressure_owner_repair_required",
        }

    def review_gate(self, signal: dict[str, Any]) -> dict[str, Any]:
        payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
        signal_name = str(payload.get("signal") or "").strip().lower()
        preferred_owner = str(payload.get("preferred_owner") or "").strip().lower()
        urgency = str(payload.get("urgency") or "").strip().lower()
        robustness = float(payload.get("robustness", 0.0) or 0.0)
        route_hint = str(payload.get("route_hint") or "").strip().lower()
        review_contract = self._review_contract(preferred_owner, route_hint)

        def _decision(approved: bool, status: str, reason: str) -> dict[str, Any]:
            return {
                "approved": approved,
                "status": status,
                "reason": reason,
                "preferred_owner": preferred_owner,
                "route_hint": route_hint,
                "review_contract": review_contract,
            }

        training_rules = dict(SUBCONSCIOUS_CHARTER.get("training_backlog_generation_rules") or {})
        noise_rules = dict(SUBCONSCIOUS_CHARTER.get("noise_suppression_rules") or {})
        immediate_signals = {str(item or "").strip().lower() for item in list(training_rules.get("immediate_priority_signals") or [])}
        high_min = float(noise_rules.get("training_priority_high_urgency_min_robustness") or 0.85)
        low_min = float(noise_rules.get("training_priority_low_urgency_min_robustness") or 0.50)
        script_min = float(noise_rules.get("training_priority_script_specific_min_robustness") or 0.40)

        if urgency == "deferred":
            return _decision(False, "deferred", "subconscious marked this priority deferred")
        if preferred_owner == "maintenance_review":
            return _decision(False, "ungrounded_owner", "candidate does not yet point to fulfillment or supervisor review")

        if urgency == "high":
            approved = robustness >= high_min
            reason = f"high urgency robustness {robustness:.2f} {'meets' if approved else 'misses'} threshold {high_min:.2f}"
        elif urgency == "low":
            approved = robustness >= low_min
            reason = f"low urgency robustness {robustness:.2f} {'meets' if approved else 'misses'} threshold {low_min:.2f}"
        else:
            approved = robustness >= script_min
            reason = f"medium urgency robustness {robustness:.2f} {'meets' if approved else 'misses'} threshold {script_min:.2f}"

        if approved and signal_name in immediate_signals:
            return _decision(True, "approved_priority_review", f"{reason}; subconscious marked this signal as immediate-priority")
        if approved:
            return _decision(True, "approved_review", reason)
        return _decision(False, "needs_more_robustness", reason)


SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE = SubconsciousWorkTreeTriageService()
