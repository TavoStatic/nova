import unittest

from conversation_manager import ConversationSession
import nova_core
from services.subconscious_review_authority import SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE
from services.subconscious_work_tree_triage import SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE


class TestSubconsciousReviewAuthorityService(unittest.TestCase):
    def test_route_comparison_contract_approves_shared_lane(self):
        signal = {
            "payload": {
                "preferred_owner": "fulfillment_supervisor",
                "route_hint": "route_comparison",
            }
        }
        gate = {
            "approved": True,
            "review_contract": "subconscious.review.route_comparison",
        }

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(signal, gate)

        self.assertTrue(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_owner"), "fulfillment_supervisor")
        self.assertEqual(verdict.get("authority_status"), "approved")

    def test_ungated_candidate_is_not_reviewed(self):
        signal = {"payload": {"preferred_owner": "maintenance_review", "route_hint": "generic_fallback"}}
        gate = {
            "approved": False,
            "preferred_owner": "maintenance_review",
            "review_contract": "subconscious.review.maintenance",
        }

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(signal, gate)

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_status"), "not_reviewed")

    def test_probe_backed_supervisor_review_uses_real_route_snapshot(self):
        signal = {
            "payload": {
                "signal": "supervisor_overreach",
                "preferred_owner": "supervisor",
                "route_hint": "supervisor_owned",
                "review_context": {
                    "review_text": "check the weather if you can please..",
                    "pending_action": None,
                    "conversation_state": None,
                    "turns": [],
                },
            }
        }
        gate = {
            "approved": True,
            "review_contract": "subconscious.review.supervisor",
        }

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=lambda text, session, turns, pending_action=None: {
                "routes": {
                    "supervisor_owned": {"viable": True},
                    "fulfillment_applicable": {"viable": False},
                }
            },
            session_factory=lambda: object(),
        )

        self.assertTrue(verdict.get("approved"))
        self.assertIn("supervisor_viable=True", str(verdict.get("authority_reason") or ""))

    def test_live_supervisor_review_uses_runtime_supervisor_before_probe(self):
        signal = {
            "payload": {
                "signal": "supervisor_overreach",
                "urgency": "high",
                "preferred_owner": "supervisor",
                "route_hint": "supervisor_owned",
                "review_context": {
                    "review_text": "check the weather if you can please..",
                    "pending_action": None,
                    "conversation_state": None,
                    "turns": [],
                },
            }
        }
        gate = {
            "approved": True,
            "review_contract": "subconscious.review.supervisor",
        }

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            evaluate_supervisor_rules_fn=lambda *args, **kwargs: {"handled": True, "intent": "weather_lookup"},
            supervisor_has_route_fn=lambda result: bool(result.get("handled")),
            probe_turn_routes_fn=lambda *args, **kwargs: {
                "routes": {"supervisor_owned": {"viable": False}}
            },
            session_factory=ConversationSession,
        )

        self.assertTrue(verdict.get("approved"))
        self.assertIn("live supervisor route=True", str(verdict.get("authority_reason") or ""))

    def test_supervisor_reflection_can_approve_when_live_route_does_not_claim_turn(self):
        signal = {
            "payload": {
                "signal": "supervisor_overreach",
                "urgency": "high",
                "preferred_owner": "supervisor",
                "route_hint": "supervisor_owned",
                "review_contract": "subconscious.review.supervisor",
                "review_context": {
                    "review_text": "where are you right now exactly",
                    "pending_action": None,
                    "conversation_state": None,
                    "turns": [],
                },
            }
        }
        gate = {
            "approved": True,
            "review_contract": "subconscious.review.supervisor",
        }

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            evaluate_supervisor_rules_fn=lambda *args, **kwargs: {"handled": False},
            supervisor_has_route_fn=lambda result: bool(result.get("handled")),
            supervisor_process_turn_fn=lambda **kwargs: {
                "probe_findings": [{"name": "identity_location_route", "status": "red", "message": "bad route"}],
                "probe_status_counts": {"green": 6, "yellow": 0, "red": 1},
            },
            probe_turn_routes_fn=lambda *args, **kwargs: {
                "routes": {"supervisor_owned": {"viable": False}}
            },
            session_factory=ConversationSession,
        )

        self.assertTrue(verdict.get("approved"))
        self.assertIn("live supervisor reflection", str(verdict.get("authority_reason") or ""))

    def test_live_fulfillment_review_uses_runtime_fulfillment_before_probe(self):
        signal = {
            "payload": {
                "signal": "fulfillment_missed",
                "urgency": "high",
                "preferred_owner": "fulfillment",
                "route_hint": "fulfillment_applicable",
                "review_context": {
                    "review_text": "show me workable options without collapsing too early",
                    "pending_action": None,
                    "conversation_state": None,
                    "turns": [],
                },
            }
        }
        gate = {
            "approved": True,
            "review_contract": "subconscious.review.fulfillment",
        }

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            fulfillment_viability_fn=lambda *args, **kwargs: {"viable": True, "comparison_strength": "clear"},
            probe_turn_routes_fn=lambda *args, **kwargs: {
                "routes": {"fulfillment_applicable": {"viable": False}}
            },
            session_factory=ConversationSession,
        )

        self.assertTrue(verdict.get("approved"))
        self.assertIn("live fulfillment viable=True", str(verdict.get("authority_reason") or ""))

    def test_probe_backed_route_review_requires_both_routes_for_conflict(self):
        signal = {
            "payload": {
                "signal": "route_conflict",
                "preferred_owner": "fulfillment_supervisor",
                "route_hint": "route_comparison",
                "review_context": {
                    "review_text": "compare options and also use the saved route",
                    "pending_action": None,
                    "conversation_state": None,
                    "turns": [],
                },
            }
        }
        gate = {
            "approved": True,
            "review_contract": "subconscious.review.route_comparison",
        }

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=lambda text, session, turns, pending_action=None: {
                "routes": {
                    "supervisor_owned": {"viable": True},
                    "fulfillment_applicable": {"viable": False},
                }
            },
            session_factory=lambda: object(),
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_status"), "rejected")

    def test_probe_backed_weather_family_context_rejects_retired_supervisor_review(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="weather-continuation-fallthrough-family",
            target_seam="weather_continuation_route_fallthrough",
            signal_name="supervisor_overreach",
            suggested_test_name="test_weather_continuation_route",
            rationale="Weather continuation slipped out of supervisor ownership.",
            urgency="high",
            robustness=0.96,
            variation_results=[
                {
                    "scenario_id": "weather-continuation-fallthrough",
                    "active_recent_signals": ["supervisor_overreach"],
                    "candidate_tests": [{"signal": "supervisor_overreach"}],
                }
            ],
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_owner"), "supervisor")
        self.assertEqual(verdict.get("authority_status"), "rejected")
        self.assertIn("supervisor_viable=False", str(verdict.get("authority_reason") or ""))

    def test_probe_backed_patch_family_context_rejects_removed_supervisor_route(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="patch-routing-fallthrough-family",
            target_seam="patch_routing_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_patch_routing_route",
            rationale="Patch routing slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[
                {
                    "scenario_id": "patch-routing-fallthrough",
                    "active_recent_signals": [],
                    "candidate_tests": [{"signal": "", "suggested_test_name": "test_patch_routing_route"}],
                }
            ],
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_owner"), "supervisor")
        self.assertEqual(verdict.get("authority_status"), "rejected")
        self.assertIn("supervisor_viable=False", str(verdict.get("authority_reason") or ""))

    def test_probe_backed_memory_capture_family_context_rejects_retired_supervisor_review(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="memory-capture-fallthrough-family",
            target_seam="memory_capture_route_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_memory_capture_route",
            rationale="Memory capture slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[
                {
                    "scenario_id": "memory-capture-fallthrough",
                    "active_recent_signals": [],
                    "candidate_tests": [{"signal": "", "suggested_test_name": "test_memory_capture_route"}],
                }
            ],
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_owner"), "maintenance_review")
        self.assertEqual(verdict.get("authority_status"), "not_reviewed")
        self.assertIn("did not clear triage gate", str(verdict.get("authority_reason") or ""))

    def test_probe_backed_low_priority_review_can_defer_under_runtime_pressure(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="weather-continuation-fallthrough-family",
            target_seam="weather_continuation_route_fallthrough",
            signal_name="supervisor_overreach",
            suggested_test_name="test_weather_continuation_route",
            rationale="Weather continuation slipped out of supervisor ownership.",
            urgency="medium",
            robustness=0.82,
            variation_results=[
                {
                    "scenario_id": "weather-continuation-fallthrough",
                    "active_recent_signals": ["supervisor_overreach"],
                    "candidate_tests": [{"signal": "supervisor_overreach"}],
                }
            ],
            runtime_context={
                "last_regression_status": "FAILED",
                "generated_queue_status": "failed",
                "queue_open_count": 3,
                "work_tree_status": "waiting",
                "work_tree_executed_count": 0,
                "work_tree_tree_count": 2,
                "kidney_mode": "enforce",
                "kidney_candidate_count": 41,
            },
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_status"), "rejected")
        self.assertIn("supervisor_viable=False", str(verdict.get("authority_reason") or ""))

    def test_runtime_pressure_ignores_stale_regression_failure(self):
        signal = {
            "payload": {
                "review_context": {
                    "runtime_context": {
                        "last_regression_status": "FAILED",
                        "last_regression_stale": True,
                        "generated_queue_status": "ok",
                        "queue_open_count": 0,
                        "work_tree_status": "ok",
                    }
                }
            }
        }

        pressure = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE._runtime_pressure(signal)

        self.assertFalse(pressure.get("active"))
        self.assertEqual(pressure.get("reason"), "")

    def test_low_priority_review_can_be_skipped_when_candidate_is_already_staged(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="patch-routing-fallthrough-family",
            target_seam="patch_routing_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_patch_routing_route",
            rationale="Patch routing slipped to fallback.",
            urgency="medium",
            robustness=0.82,
            variation_results=[],
            runtime_context={
                "last_regression_status": "FAILED",
                "generated_queue_status": "failed",
                "queue_open_count": 3,
                "work_tree_status": "waiting",
                "work_tree_executed_count": 0,
                "work_tree_tree_count": 2,
                "kidney_mode": "enforce",
                "kidney_candidate_count": 41,
                "candidate_backlog": {
                    "prior_action": "updated",
                    "prior_branch_id": "branch_patch1",
                    "prior_authority_status": "approved",
                    "prior_triage_status": "approved_priority_review",
                    "already_waiting": True,
                    "waiting_tool": "patch_rollback",
                    "waiting_action": "awaiting_operator",
                    "waiting_branch_title": "Step 2: apply patch rollback",
                },
            },
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_status"), "already_staged")
        self.assertIn("branch_patch1", str(verdict.get("authority_reason") or ""))

    def test_low_priority_review_can_be_skipped_when_prior_branch_is_staged_under_waiting_work_tree(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="patch-routing-fallthrough-family",
            target_seam="patch_routing_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_patch_routing_route",
            rationale="Patch routing slipped to fallback.",
            urgency="low",
            robustness=0.74,
            variation_results=[],
            runtime_context={
                "last_regression_status": "FAILED",
                "generated_queue_status": "failed",
                "queue_open_count": 3,
                "work_tree_status": "waiting",
                "work_tree_executed_count": 0,
                "work_tree_tree_count": 2,
                "kidney_mode": "enforce",
                "kidney_candidate_count": 41,
                "candidate_backlog": {
                    "prior_action": "updated",
                    "prior_branch_id": "branch_patch2",
                    "prior_authority_status": "approved",
                    "prior_triage_status": "approved_review",
                    "already_waiting": False,
                    "waiting_tool": "",
                    "waiting_action": "",
                    "waiting_branch_title": "",
                },
            },
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_status"), "already_staged")
        self.assertIn("branch_patch2", str(verdict.get("authority_reason") or ""))

    def test_medium_priority_review_can_be_skipped_when_live_branch_has_open_work(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="patch-routing-fallthrough-family",
            target_seam="patch_routing_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_patch_routing_route",
            rationale="Patch routing slipped to fallback.",
            urgency="medium",
            robustness=0.82,
            variation_results=[],
            runtime_context={
                "last_regression_status": "",
                "generated_queue_status": "ok",
                "queue_open_count": 0,
                "work_tree_status": "ok",
                "work_tree_executed_count": 1,
                "work_tree_tree_count": 2,
                "kidney_mode": "enforce",
                "kidney_candidate_count": 41,
                "candidate_backlog": {
                    "prior_action": "updated",
                    "prior_branch_id": "branch_patch3",
                    "prior_authority_status": "approved",
                    "prior_triage_status": "approved_review",
                    "already_waiting": False,
                    "waiting_tool": "",
                    "waiting_action": "",
                    "waiting_branch_title": "",
                    "live_branch_status": "ready",
                    "live_resolution_state": "open",
                    "live_preferred_tool": "patch_rollback",
                    "open_task_count": 1,
                    "active_task_count": 0,
                    "next_open_task_title": "Apply patch rollback",
                    "next_open_task_status": "open",
                },
            },
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_status"), "already_staged")
        self.assertIn("Apply patch rollback", str(verdict.get("authority_reason") or ""))

    def test_probe_backed_high_priority_review_notes_runtime_pressure_but_still_approves(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="weather-continuation-fallthrough-family",
            target_seam="weather_continuation_route_fallthrough",
            signal_name="supervisor_overreach",
            suggested_test_name="test_weather_continuation_route",
            rationale="Weather continuation slipped out of supervisor ownership.",
            urgency="high",
            robustness=0.96,
            variation_results=[
                {
                    "scenario_id": "weather-continuation-fallthrough",
                    "active_recent_signals": ["supervisor_overreach"],
                    "candidate_tests": [{"signal": "supervisor_overreach"}],
                }
            ],
            runtime_context={
                "last_regression_status": "FAILED",
                "generated_queue_status": "failed",
                "queue_open_count": 3,
                "work_tree_status": "waiting",
                "work_tree_executed_count": 0,
                "work_tree_tree_count": 2,
                "kidney_mode": "enforce",
                "kidney_candidate_count": 41,
            },
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_owner"), "supervisor")
        self.assertEqual(verdict.get("authority_status"), "rejected")
        self.assertIn("supervisor_viable=False", str(verdict.get("authority_reason") or ""))

    def test_probe_backed_session_fact_family_context_rejects_removed_supervisor_route(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="session-fact-recall-fallthrough-family",
            target_seam="session_fact_recall_route_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_session_fact_recall_route",
            rationale="Session fact recall slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[
                {
                    "scenario_id": "session-fact-recall-fallthrough",
                    "active_recent_signals": [],
                    "candidate_tests": [{"signal": "", "suggested_test_name": "test_session_fact_recall_route"}],
                }
            ],
        )
        gate = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(signal)

        verdict = SUBCONSCIOUS_REVIEW_AUTHORITY_SERVICE.review_candidate(
            signal,
            gate,
            probe_turn_routes_fn=nova_core._probe_turn_routes,
            session_factory=ConversationSession,
        )

        self.assertFalse(verdict.get("approved"))
        self.assertEqual(verdict.get("authority_owner"), "supervisor")
        self.assertIn("supervisor_viable=False", str(verdict.get("authority_reason") or ""))
