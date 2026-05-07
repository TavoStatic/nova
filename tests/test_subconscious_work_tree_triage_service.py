import unittest

from services.subconscious_work_tree_triage import SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE


class TestSubconsciousWorkTreeTriageService(unittest.TestCase):
    def test_build_signal_marks_fulfillment_supervisor_route_review(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="fulfillment-fallthrough-family",
            target_seam="fulfillment_route",
            signal_name="fallback_overuse",
            suggested_test_name="test_fulfillment_fallback_route",
            rationale="Robust family pressure kept surfacing fallback_overuse.",
            urgency="high",
            robustness=0.97,
            variation_results=[
                {
                    "scenario_id": "fulfillment-fallthrough",
                    "active_recent_signals": ["fulfillment_missed", "fallback_overuse"],
                    "candidate_tests": [{"signal": "fallback_overuse"}],
                }
            ],
        )

        payload = dict(signal.get("payload") or {})
        self.assertIn("fulfillment", str(signal.get("title") or "").lower())
        self.assertEqual(payload.get("preferred_owner"), "fulfillment_supervisor")
        self.assertEqual(payload.get("route_hint"), "route_comparison")
        self.assertEqual(payload.get("review_contract"), "subconscious.review.route_comparison")
        self.assertEqual(((payload.get("review_context") or {}).get("review_text")), "Show me workable options without collapsing too early.")
        self.assertEqual(((payload.get("review_context") or {}).get("scenario_id")), "fulfillment-fallthrough")

    def test_build_signal_uses_weather_family_context_when_available(self):
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

        review_context = dict((signal.get("payload") or {}).get("review_context") or {})
        self.assertEqual(review_context.get("scenario_id"), "weather-continuation-fallthrough")
        self.assertEqual(((review_context.get("pending_action") or {}).get("kind")), "weather_lookup")

    def test_build_signal_can_match_family_context_by_suggested_test_name(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="retrieval-followup-fallthrough-family",
            target_seam="retrieval_followup_route_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_retrieval_followup_route",
            rationale="Retrieval followup slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[
                {
                    "scenario_id": "retrieval-followup-fallthrough",
                    "active_recent_signals": [],
                    "candidate_tests": [
                        {
                            "signal": "",
                            "suggested_test_name": "test_retrieval_followup_route",
                        }
                    ],
                }
            ],
        )

        review_context = dict((signal.get("payload") or {}).get("review_context") or {})
        self.assertEqual((signal.get("payload") or {}).get("preferred_owner"), "supervisor")
        self.assertEqual((signal.get("payload") or {}).get("route_hint"), "supervisor_owned")
        self.assertEqual((signal.get("payload") or {}).get("review_contract"), "subconscious.review.supervisor")
        self.assertEqual(review_context.get("scenario_id"), "retrieval-followup-fallthrough")

    def test_build_signal_treats_session_fact_recall_family_as_supervisor_owned(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="session-fact-recall-fallthrough-family",
            target_seam="session_fact_recall_route_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_session_fact_recall_route",
            rationale="Session fact recall slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[],
        )

        payload = dict(signal.get("payload") or {})
        self.assertEqual(payload.get("preferred_owner"), "supervisor")
        self.assertEqual(payload.get("route_hint"), "supervisor_owned")
        self.assertEqual(payload.get("review_contract"), "subconscious.review.supervisor")

    def test_build_signal_uses_patch_family_context_when_available(self):
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

        payload = dict(signal.get("payload") or {})
        review_context = dict(payload.get("review_context") or {})
        self.assertEqual(payload.get("preferred_owner"), "supervisor")
        self.assertEqual(review_context.get("scenario_id"), "patch-routing-fallthrough")
        self.assertEqual(review_context.get("review_text"), "please patch apply updates.zip")

    def test_build_signal_adds_family_specific_patch_guidance(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="patch-routing-fallthrough-family",
            target_seam="patch_routing_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_patch_routing_route",
            rationale="Patch routing slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[],
        )

        payload = dict(signal.get("payload") or {})
        self.assertIn("patch routing still falls through", str(signal.get("next_task") or "").lower())
        self.assertIn("patch_apply or patch_rollback", str(signal.get("next_task") or ""))
        self.assertIn("Patch-routing review", str(payload.get("branch_note") or ""))

    def test_fallback_overuse_without_scenario_uses_family_review_context(self):
        cases = [
            (
                "weather-continuation-fallthrough-family",
                "weather_continuation_route_fallthrough",
                "test_weather_continuation_route",
                "yes get the weather for our location",
            ),
            (
                "memory-capture-fallthrough-family",
                "memory_capture_route_fallthrough",
                "test_memory_capture_route",
                "Remember this: my favorite color is teal. Don't forget.",
            ),
            (
                "retrieval-followup-fallthrough-family",
                "retrieval_followup_route_fallthrough",
                "test_retrieval_followup_route",
                "tell me about the first one",
            ),
            (
                "patch-routing-fallthrough-family",
                "patch_routing_fallthrough",
                "test_patch_routing_route",
                "please patch apply updates.zip",
            ),
            (
                "session-fact-recall-fallthrough-family",
                "session_fact_recall_route_fallthrough",
                "test_session_fact_recall_route",
                "What codeword did I just ask you to remember?",
            ),
        ]

        for family_id, target_seam, test_name, expected_text in cases:
            with self.subTest(family_id=family_id):
                signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
                    family_id=family_id,
                    target_seam=target_seam,
                    signal_name="fallback_overuse",
                    suggested_test_name=test_name,
                    rationale="Specific route slipped to fallback.",
                    urgency="high",
                    robustness=0.95,
                    variation_results=[],
                )

                review_context = dict((signal.get("payload") or {}).get("review_context") or {})
                self.assertEqual(review_context.get("review_text"), expected_text)

    def test_build_signal_uses_memory_capture_family_context_when_available(self):
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

        payload = dict(signal.get("payload") or {})
        review_context = dict(payload.get("review_context") or {})
        self.assertEqual(payload.get("preferred_owner"), "supervisor")
        self.assertEqual(review_context.get("scenario_id"), "memory-capture-fallthrough")
        self.assertEqual(review_context.get("review_text"), "Remember this: my favorite color is teal. Don't forget.")

    def test_build_signal_adds_family_specific_retrieval_guidance(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="retrieval-followup-fallthrough-family",
            target_seam="retrieval_followup_route_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_retrieval_followup_route",
            rationale="Retrieval followup slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[],
        )

        payload = dict(signal.get("payload") or {})
        self.assertIn("retrieval followup state is preserved", str(signal.get("next_task") or "").lower())
        self.assertIn("selected result or provider context", str(signal.get("next_task") or "").lower())
        self.assertIn("Retrieval-followup review", str(payload.get("branch_note") or ""))

    def test_build_signal_adds_family_specific_memory_guidance(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="memory-capture-fallthrough-family",
            target_seam="memory_capture_route_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_memory_capture_route",
            rationale="Memory capture slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[],
        )

        payload = dict(signal.get("payload") or {})
        self.assertIn("memory capture still falls through", str(signal.get("next_task") or "").lower())
        self.assertIn("store memory, ask for confirmation, or defer learning", str(signal.get("next_task") or "").lower())
        self.assertIn("Memory-capture review", str(payload.get("branch_note") or ""))

    def test_build_signal_adds_family_specific_weather_guidance(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="weather-continuation-fallthrough-family",
            target_seam="weather_continuation_route_fallthrough",
            signal_name="supervisor_overreach",
            suggested_test_name="test_weather_continuation_route",
            rationale="Weather continuation slipped out of supervisor ownership.",
            urgency="high",
            robustness=0.96,
            variation_results=[],
        )

        payload = dict(signal.get("payload") or {})
        self.assertIn("weather continuation still falls through", str(signal.get("next_task") or "").lower())
        self.assertIn("saved-location handling", str(signal.get("next_task") or "").lower())
        self.assertIn("Weather-continuation review", str(payload.get("branch_note") or ""))

    def test_build_signal_adds_family_specific_session_fact_guidance(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="session-fact-recall-fallthrough-family",
            target_seam="session_fact_recall_route_fallthrough",
            signal_name="fallback_overuse",
            suggested_test_name="test_session_fact_recall_route",
            rationale="Session fact recall slipped to fallback.",
            urgency="high",
            robustness=0.95,
            variation_results=[],
        )

        payload = dict(signal.get("payload") or {})
        self.assertIn("session fact recall still falls through", str(signal.get("next_task") or "").lower())
        self.assertIn("recap or fact-followup state is missing", str(signal.get("next_task") or "").lower())
        self.assertIn("Session-fact review", str(payload.get("branch_note") or ""))

    def test_build_signal_prefers_report_review_context_when_present(self):
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
                    "review_context": {
                        "review_text": "report-backed weather context",
                        "pending_action": {"kind": "weather_lookup"},
                        "conversation_state": None,
                        "turns": [],
                        "scenario_id": "weather-continuation-fallthrough",
                        "family_id": "weather-continuation-fallthrough-family",
                    },
                }
            ],
        )

        review_context = dict((signal.get("payload") or {}).get("review_context") or {})
        self.assertEqual(review_context.get("review_text"), "report-backed weather context")
        self.assertEqual((review_context.get("pending_action") or {}).get("kind"), "weather_lookup")

    def test_build_signal_attaches_runtime_review_context_when_present(self):
        signal = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.build_signal(
            family_id="weather-continuation-fallthrough-family",
            target_seam="weather_continuation_route_fallthrough",
            signal_name="supervisor_overreach",
            suggested_test_name="test_weather_continuation_route",
            rationale="Weather continuation slipped out of supervisor ownership.",
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
                    "prior_branch_id": "branch_123",
                    "already_waiting": True,
                    "waiting_tool": "patch_rollback",
                    "waiting_action": "awaiting_operator",
                    "waiting_branch_title": "Step 2: apply patch rollback",
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

        review_context = dict((signal.get("payload") or {}).get("review_context") or {})
        runtime_context = dict(review_context.get("runtime_context") or {})
        candidate_backlog = dict(review_context.get("candidate_backlog") or {})
        self.assertEqual(runtime_context.get("last_regression_status"), "FAILED")
        self.assertEqual(runtime_context.get("generated_queue_status"), "failed")
        self.assertEqual(runtime_context.get("queue_open_count"), 3)
        self.assertEqual(candidate_backlog.get("prior_branch_id"), "branch_123")
        self.assertTrue(candidate_backlog.get("already_waiting"))
        self.assertEqual(candidate_backlog.get("live_branch_status"), "ready")
        self.assertEqual(candidate_backlog.get("open_task_count"), 1)

    def test_review_gate_requires_owner_and_robustness(self):
        approved = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(
            {
                "payload": {
                    "signal": "fallback_overuse",
                    "preferred_owner": "fulfillment_supervisor",
                    "urgency": "high",
                    "robustness": 0.97,
                }
            }
        )
        self.assertTrue(approved.get("approved"))
        self.assertEqual(approved.get("status"), "approved_priority_review")
        self.assertEqual(approved.get("review_contract"), "subconscious.review.route_comparison")

        skipped = SUBCONSCIOUS_WORK_TREE_TRIAGE_SERVICE.review_gate(
            {
                "payload": {
                    "signal": "route_fit_weak",
                    "preferred_owner": "maintenance_review",
                    "urgency": "medium",
                    "robustness": 0.91,
                }
            }
        )
        self.assertFalse(skipped.get("approved"))
        self.assertEqual(skipped.get("status"), "ungrounded_owner")
        self.assertEqual(skipped.get("review_contract"), "subconscious.review.maintenance")
