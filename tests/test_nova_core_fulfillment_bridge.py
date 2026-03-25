import unittest
from unittest.mock import patch

import nova_core
from conversation_manager import ConversationSession
from fulfillment_contracts import ChoiceMode, ChoiceSet, CollapseStatus, FitAssessment, FrameScore, FulfillmentModel, Intent
from subconscious_live_simulator import build_default_live_scenario_families, simulate_live_family


def _intent(intent_id: str = "intent-bridge") -> Intent:
    return Intent(
        intent_id=intent_id,
        achievement_goal="reach a workable result",
        success_criteria=["result achieved"],
        constraints=["stay within current constraints"],
        preferences=["useful", "low friction"],
    )


def _models() -> list[FulfillmentModel]:
    return [
        FulfillmentModel(
            model_id="model-guided",
            intent_id="intent-bridge",
            label="Guided path",
            description="Lower-friction option.",
            path_shape="guided_decision",
            differentiators=["lower user effort"],
            strengths=["lower friction"],
            expected_friction=["slower upfront"],
        ),
        FulfillmentModel(
            model_id="model-direct",
            intent_id="intent-bridge",
            label="Direct path",
            description="Faster option.",
            path_shape="direct_resolution",
            differentiators=["faster completion"],
            strengths=["faster timing"],
            expected_friction=["more commitment earlier"],
        ),
    ]


def _assessments() -> list[FitAssessment]:
    return [
        FitAssessment(
            assessment_id="a1",
            intent_id="intent-bridge",
            model_id="model-guided",
            overall_fit_score=0.84,
            fit_band="strong_fit",
            valid=True,
            keep_reasons=["lower friction remains valuable"],
            frame_scores=[
                FrameScore(frame="explicit_constraint_fit", score=0.9),
                FrameScore(frame="achievement_goal_fit", score=0.82),
                FrameScore(frame="friction", score=0.95),
                FrameScore(frame="timing", score=0.58),
                FrameScore(frame="risk", score=0.82),
                FrameScore(frame="usefulness", score=0.86),
            ],
        ),
        FitAssessment(
            assessment_id="a2",
            intent_id="intent-bridge",
            model_id="model-direct",
            overall_fit_score=0.83,
            fit_band="strong_fit",
            valid=True,
            keep_reasons=["faster timing remains valuable"],
            frame_scores=[
                FrameScore(frame="explicit_constraint_fit", score=0.9),
                FrameScore(frame="achievement_goal_fit", score=0.82),
                FrameScore(frame="friction", score=0.6),
                FrameScore(frame="timing", score=0.96),
                FrameScore(frame="risk", score=0.78),
                FrameScore(frame="usefulness", score=0.85),
            ],
        ),
    ]


def _choice_set() -> ChoiceSet:
    presenter = __import__("choice_presenter").ChoicePresenter()
    return presenter.present(_intent(), _models(), _assessments())


class TestNovaCoreFulfillmentBridge(unittest.TestCase):
    def test_snapshot_is_readable_after_supervisor_owned_route_pressure(self):
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": True,
                "preferred_tool": "weather_current_location",
            }
        )

        probe = nova_core._probe_turn_routes("go ahead", session, [], pending_action=session.pending_action)
        nova_core._update_subconscious_state(session, probe, chosen_route="supervisor_owned")

        snapshot = nova_core._get_subconscious_snapshot(session)

        self.assertFalse(snapshot.get("replan_requested"))
        self.assertEqual(snapshot.get("active_recent_signals"), [])
        self.assertEqual(snapshot.get("crack_counts"), {})
        self.assertEqual(snapshot.get("record_window"), {"count": 1, "cap": 12})
        self.assertEqual(snapshot.get("recent_pressure_records")[0].get("chosen_route"), "supervisor_owned")

    def test_snapshot_is_readable_after_fulfillment_selected_pressure(self):
        session = ConversationSession()

        with patch("intent_interpreter.IntentInterpreter.interpret", return_value=_intent()), patch(
            "fulfillment_model_generator.FulfillmentModelGenerator.generate",
            return_value=_models(),
        ), patch(
            "fit_evaluator.FitEvaluator.evaluate",
            return_value=_assessments(),
        ):
            nova_core._maybe_run_fulfillment_flow(
                "Show me the workable options without collapsing too early.",
                session,
                [("user", "Show me the workable options without collapsing too early.")],
            )

        snapshot = nova_core._get_subconscious_snapshot(session)

        self.assertFalse(snapshot.get("replan_requested"))
        self.assertEqual(snapshot.get("active_recent_signals"), [])
        self.assertEqual(snapshot.get("record_window"), {"count": 1, "cap": 12})
        self.assertEqual(snapshot.get("recent_pressure_records")[0].get("chosen_route"), "fulfillment_applicable")

    def test_snapshot_is_readable_after_fallback_pressure(self):
        session = ConversationSession()

        nova_core._maybe_run_fulfillment_flow("how are you doing today ?", session, [])

        snapshot = nova_core._get_subconscious_snapshot(session)

        self.assertFalse(snapshot.get("replan_requested"))
        self.assertIn("route_unclear", snapshot.get("active_recent_signals") or [])
        self.assertEqual(snapshot.get("crack_counts", {}).get("route_unclear"), 1)
        self.assertEqual(snapshot.get("recent_pressure_records")[0].get("chosen_route"), "generic_fallback")

    def test_update_subconscious_state_accumulates_repeated_weak_cracks(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])

        first = nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")
        self.assertIsInstance(first, nova_core.SubconsciousState)
        self.assertFalse(first.replan_requested)
        self.assertEqual(first.crack_counts.get("route_unclear"), 1)
        self.assertEqual(len(first.recent_pressure_records), 1)
        second = nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")

        self.assertIs(second, getattr(session, "subconscious_state", None))
        self.assertTrue(second.replan_requested)
        self.assertEqual(second.crack_counts.get("route_unclear"), 2)
        self.assertEqual(second.crack_counts.get("route_fit_weak"), 2)
        self.assertEqual(len(second.recent_pressure_records), 2)

        snapshot = nova_core._get_subconscious_snapshot(session)
        self.assertEqual(snapshot.get("crack_counts", {}).get("route_unclear"), 2)
        self.assertEqual(snapshot.get("crack_counts", {}).get("route_fit_weak"), 2)

    def test_update_subconscious_state_requests_replan_for_clear_fulfillment_miss(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes(
            "Show me workable options without collapsing too early.",
            session,
            [("user", "Show me workable options without collapsing too early.")],
        )

        state = nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")

        self.assertIsInstance(state, nova_core.SubconsciousState)
        self.assertTrue(state.replan_requested)
        self.assertEqual(state.crack_counts.get("fulfillment_missed"), 1)
        self.assertEqual(state.crack_counts.get("fallback_overuse"), 1)

        snapshot = nova_core._get_subconscious_snapshot(session)
        self.assertTrue(snapshot.get("replan_requested"))
        self.assertIn("fulfillment_missed", snapshot.get("active_recent_signals") or [])

    def test_snapshot_is_read_only_and_does_not_mutate_subconscious_state(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])
        nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")

        snapshot = nova_core._get_subconscious_snapshot(session)
        snapshot["replan_requested"] = True
        snapshot["active_recent_signals"].append("synthetic")
        snapshot["crack_counts"]["route_unclear"] = 99
        snapshot["recent_pressure_records"][0]["signals"].append("synthetic")

        fresh_snapshot = nova_core._get_subconscious_snapshot(session)

        self.assertFalse(fresh_snapshot.get("replan_requested"))
        self.assertNotIn("synthetic", fresh_snapshot.get("active_recent_signals") or [])
        self.assertEqual(fresh_snapshot.get("crack_counts", {}).get("route_unclear"), 1)
        self.assertNotIn("synthetic", fresh_snapshot.get("recent_pressure_records")[0].get("signals") or [])

    def test_build_turn_reflection_exposes_subconscious_snapshot_without_mutation(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])
        nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")

        with patch.object(nova_core.TURN_SUPERVISOR, "process_turn", return_value={"probe_summary": "All green", "probe_results": []}) as mocked_process:
            reflection = nova_core.build_turn_reflection(
                session,
                entry_point="cli",
                session_id="session-1",
                current_decision={"planner_decision": "llm_fallback"},
            )

        self.assertEqual(reflection.get("probe_summary"), "All green")
        session_summary = mocked_process.call_args.kwargs.get("session_summary") or {}
        snapshot = session_summary.get("subconscious_snapshot") or {}
        self.assertEqual(snapshot.get("crack_counts", {}).get("route_unclear"), 1)
        self.assertEqual(snapshot.get("record_window"), {"count": 1, "cap": 12})
        self.assertEqual(getattr(session.subconscious_state, "crack_counts", {}).get("route_unclear"), 1)

    def test_reflection_stays_quiet_when_no_training_backlog_candidates_exist(self):
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": True,
                "preferred_tool": "weather_current_location",
            }
        )
        probe = nova_core._probe_turn_routes("go ahead", session, [], pending_action=session.pending_action)
        nova_core._update_subconscious_state(session, probe, chosen_route="supervisor_owned")

        with patch.object(nova_core.TURN_SUPERVISOR, "process_turn", return_value={"probe_summary": "All green", "probe_results": []}):
            reflection = nova_core.build_turn_reflection(
                session,
                entry_point="cli",
                session_id="session-quiet",
                current_decision={"planner_decision": "deterministic"},
            )

        self.assertNotIn("subconscious_training_backlog", reflection)

    def test_reflection_exposes_training_backlog_when_candidates_exist(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])
        nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")
        nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")

        with patch.object(nova_core.TURN_SUPERVISOR, "process_turn", return_value={"probe_summary": "All green", "probe_results": []}):
            reflection = nova_core.build_turn_reflection(
                session,
                entry_point="cli",
                session_id="session-backlog",
                current_decision={"planner_decision": "llm_fallback"},
            )

        backlog = reflection.get("subconscious_training_backlog") or {}
        candidate_tests = backlog.get("candidate_tests") or []
        self.assertTrue(backlog.get("replan_requested"))
        self.assertGreaterEqual(len(candidate_tests), 1)
        first = candidate_tests[0]
        self.assertIn("signal", first)
        self.assertIn("occurrences", first)
        self.assertIn("priority", first)
        self.assertIn("suggested_test_name", first)
        self.assertIn("rationale", first)

    def test_self_reflection_report_includes_training_backlog_summary_when_present(self):
        payload = nova_core.maybe_log_self_reflection(
            records=[{"active_subject": "", "continuation_used": False, "planner_decision": "llm_fallback"}],
            total_records=1,
            every=1,
            extra_payload={
                "probe_summary": "All green",
                "probe_results": [],
                "subconscious_training_backlog": {
                    "replan_requested": True,
                    "candidate_tests": [
                        {
                            "signal": "route_unclear",
                            "occurrences": 2,
                            "priority": "medium",
                            "suggested_test_name": "test_route_probe_marks_ambiguous_turns_without_overclaiming",
                            "rationale": "Route comparison stayed unclear across recent pressure records.",
                        }
                    ],
                },
            },
        )

        backlog = payload.get("subconscious_training_backlog") or {}
        self.assertTrue(backlog.get("replan_requested"))
        self.assertEqual(backlog.get("candidate_tests")[0].get("signal"), "route_unclear")

    def test_reflection_stays_quiet_when_no_robust_weakness_summary_exists(self):
        session = ConversationSession()

        with patch.object(nova_core.TURN_SUPERVISOR, "process_turn", return_value={"probe_summary": "All green", "probe_results": []}):
            reflection = nova_core.build_turn_reflection(
                session,
                entry_point="cli",
                session_id="session-no-ranking",
                current_decision={"planner_decision": "deterministic"},
            )

        self.assertNotIn("subconscious_robust_weakness", reflection)

    def test_reflection_exposes_robust_weakness_summary_when_family_result_exists(self):
        session = ConversationSession()
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "fulfillment-fallthrough-family"
        )
        session.subconscious_live_family_summary = simulate_live_family(family)

        with patch.object(nova_core.TURN_SUPERVISOR, "process_turn", return_value={"probe_summary": "All green", "probe_results": []}):
            reflection = nova_core.build_turn_reflection(
                session,
                entry_point="cli",
                session_id="session-ranking",
                current_decision={"planner_decision": "llm_fallback"},
            )

        ranking = reflection.get("subconscious_robust_weakness") or {}
        self.assertIn("robust_signals", ranking)
        self.assertIn("script_specific_signals", ranking)
        self.assertIn("robust_backlog_candidates", ranking)
        self.assertIn("quiet_control_verdict", ranking)
        self.assertEqual(ranking.get("robust_signals")[0].get("signal"), "fallback_overuse")
        self.assertEqual(ranking.get("robust_backlog_candidates")[0].get("signal"), "fallback_overuse")
        self.assertEqual(ranking.get("quiet_control_verdict", {}).get("status"), "low_noise")

    def test_self_reflection_report_includes_robust_weakness_summary_when_present(self):
        payload = nova_core.maybe_log_self_reflection(
            records=[{"active_subject": "", "continuation_used": False, "planner_decision": "llm_fallback"}],
            total_records=1,
            every=1,
            extra_payload={
                "probe_summary": "All green",
                "probe_results": [],
                "subconscious_robust_weakness": {
                    "robust_signals": [
                        {
                            "signal": "fallback_overuse",
                            "classification": "robust",
                            "robustness_score": 1.0,
                        }
                    ],
                    "script_specific_signals": [],
                    "robust_backlog_candidates": [
                        {
                            "signal": "fallback_overuse",
                            "classification": "robust",
                            "robustness_score": 1.0,
                            "suggested_test_name": "test_generic_fallback_does_not_hide_viable_specific_route",
                        }
                    ],
                    "quiet_control_verdict": {
                        "quiet_control": False,
                        "status": "low_noise",
                        "reason": "Variations stayed readable without noisy-only outcomes.",
                    },
                },
            },
        )

        ranking = payload.get("subconscious_robust_weakness") or {}
        self.assertEqual(ranking.get("robust_signals")[0].get("signal"), "fallback_overuse")
        self.assertEqual(ranking.get("robust_backlog_candidates")[0].get("suggested_test_name"), "test_generic_fallback_does_not_hide_viable_specific_route")
        self.assertEqual(ranking.get("quiet_control_verdict", {}).get("status"), "low_noise")

    def test_probe_turn_routes_reports_supervisor_owned_without_claiming(self):
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": True,
                "preferred_tool": "weather_current_location",
            }
        )

        probe = nova_core._probe_turn_routes("go ahead", session, [], pending_action=session.pending_action)

        self.assertEqual(probe.get("comparison_strength"), "clear")
        routes = probe.get("routes") or {}
        self.assertTrue((routes.get("supervisor_owned") or {}).get("viable"))
        self.assertFalse((routes.get("fulfillment_applicable") or {}).get("viable"))
        self.assertTrue((routes.get("generic_fallback") or {}).get("viable"))

    def test_probe_turn_routes_reports_fulfillment_applicability_without_claiming(self):
        session = ConversationSession()

        probe = nova_core._probe_turn_routes(
            "Show me workable options without collapsing too early.",
            session,
            [("user", "Show me workable options without collapsing too early.")],
        )

        self.assertEqual(probe.get("comparison_strength"), "clear")
        routes = probe.get("routes") or {}
        self.assertFalse((routes.get("supervisor_owned") or {}).get("viable"))
        self.assertTrue((routes.get("fulfillment_applicable") or {}).get("viable"))
        self.assertTrue((routes.get("generic_fallback") or {}).get("viable"))

    def test_probe_turn_routes_reports_retrieval_followup_without_claiming(self):
        session = ConversationSession()
        session.set_retrieval_state(
            {
                "kind": "retrieval",
                "subject": "web_research",
                "query": "PEIMS attendance",
                "result_count": 2,
                "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
            }
        )

        probe = nova_core._probe_turn_routes("tell me about the first one", session, [("assistant", "I found several PEIMS sources.")])

        self.assertEqual(probe.get("comparison_strength"), "clear")
        routes = probe.get("routes") or {}
        self.assertTrue((routes.get("supervisor_owned") or {}).get("viable"))
        self.assertFalse((routes.get("fulfillment_applicable") or {}).get("viable"))
        self.assertIn("retrieval_followup", " ".join((routes.get("supervisor_owned") or {}).get("fit_notes") or []))

    def test_probe_turn_routes_reports_keyword_retrieval_continue_without_claiming(self):
        session = ConversationSession()
        session.set_retrieval_state(
            {
                "kind": "retrieval",
                "subject": "web_research",
                "query": "PEIMS attendance",
                "result_count": 2,
                "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
            }
        )

        probe = nova_core._probe_turn_routes("web continue", session, [("assistant", "I found more sources. Type web continue to keep going.")])

        self.assertEqual(probe.get("comparison_strength"), "clear")
        routes = probe.get("routes") or {}
        self.assertTrue((routes.get("supervisor_owned") or {}).get("viable"))
        self.assertFalse((routes.get("fulfillment_applicable") or {}).get("viable"))
        self.assertIn("planner keyword route", " ".join((routes.get("supervisor_owned") or {}).get("fit_notes") or []).lower())

    def test_probe_turn_routes_reports_patch_routing_without_claiming(self):
        session = ConversationSession()

        probe = nova_core._probe_turn_routes("please patch apply updates.zip", session, [])

        self.assertEqual(probe.get("comparison_strength"), "clear")
        routes = probe.get("routes") or {}
        self.assertTrue((routes.get("supervisor_owned") or {}).get("viable"))
        self.assertFalse((routes.get("fulfillment_applicable") or {}).get("viable"))
        self.assertIn("patch apply", " ".join((routes.get("supervisor_owned") or {}).get("fit_notes") or []).lower())

    def test_probe_turn_routes_reports_weak_comparison_for_plain_conversation(self):
        session = ConversationSession()

        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])

        self.assertEqual(probe.get("comparison_strength"), "weak")
        routes = probe.get("routes") or {}
        self.assertFalse((routes.get("supervisor_owned") or {}).get("viable"))
        self.assertFalse((routes.get("fulfillment_applicable") or {}).get("viable"))
        self.assertTrue((routes.get("generic_fallback") or {}).get("viable"))

    def test_bridge_handles_new_open_ended_turn_and_stores_state(self):
        session = ConversationSession()

        with patch("intent_interpreter.IntentInterpreter.interpret", return_value=_intent()), patch(
            "fulfillment_model_generator.FulfillmentModelGenerator.generate",
            return_value=_models(),
        ), patch(
            "fit_evaluator.FitEvaluator.evaluate",
            return_value=_assessments(),
        ):
            result = nova_core._maybe_run_fulfillment_flow(
                "Show me the workable options without collapsing too early.",
                session,
                [("user", "Show me the workable options without collapsing too early.")],
            )

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("planner_decision"), "fulfillment_choice")
        self.assertIn("multiple meaningful fulfillment paths", str(result.get("reply") or ""))
        stored_state = getattr(session, "fulfillment_state", None)
        self.assertIsInstance(stored_state, dict)
        self.assertEqual(getattr(stored_state.get("choice_set"), "mode", None), ChoiceMode.MULTI_CHOICE)
        subconscious_state = getattr(session, "subconscious_state", None)
        self.assertIsInstance(subconscious_state, nova_core.SubconsciousState)
        self.assertFalse(subconscious_state.replan_requested)
        self.assertEqual(getattr(subconscious_state.recent_pressure_records[-1], "chosen_route", None), "fulfillment_applicable")

    def test_bridge_replans_existing_fulfillment_state(self):
        session = ConversationSession()
        session.fulfillment_state = {
            "intent": _intent(),
            "models": _models(),
            "assessments": _assessments(),
            "choice_set": _choice_set(),
        }
        replanned_choice = ChoiceSet(
            choice_set_id="choice:intent-bridge",
            intent_id="intent-bridge",
            mode=ChoiceMode.SINGLE_RESULT,
            collapse_status=CollapseStatus.COLLAPSED,
            options=_choice_set().options[:1],
            selected_model_id="model-guided",
            collapse_reason="single distinct valid fulfillment shape",
            user_decision_needed=False,
        )

        with patch(
            "dynamic_replanner.DynamicReplanner.replan",
            return_value=(_intent(), [_models()[0]], [_assessments()[0]], replanned_choice),
        ):
            result = nova_core._maybe_run_fulfillment_flow(
                "New information makes the faster path less safe.",
                session,
                [("assistant", "I see multiple meaningful fulfillment paths right now:")],
            )

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("planner_decision"), "fulfillment_single_result")
        self.assertIn("one current fulfillment result", str(result.get("reply") or ""))
        self.assertEqual(session.fulfillment_state.get("choice_set").selected_model_id, "model-guided")

    def test_bridge_does_not_attempt_fulfillment_when_probe_is_weak(self):
        session = ConversationSession()

        with patch("intent_interpreter.IntentInterpreter.interpret") as mocked_interpret:
            result = nova_core._maybe_run_fulfillment_flow(
                "how are you doing today ?",
                session,
                [],
            )

        self.assertIsNone(result)
        mocked_interpret.assert_not_called()
        subconscious_state = getattr(session, "subconscious_state", None)
        self.assertIsInstance(subconscious_state, nova_core.SubconsciousState)
        self.assertFalse(subconscious_state.replan_requested)
        self.assertEqual(subconscious_state.crack_counts.get("route_unclear"), 1)
        self.assertEqual(getattr(subconscious_state.recent_pressure_records[-1], "chosen_route", None), "generic_fallback")

    def test_bridge_fails_open_when_interpreter_is_not_implemented(self):
        session = ConversationSession()

        with patch(
            "intent_interpreter.IntentInterpreter.interpret",
            side_effect=NotImplementedError("not implemented"),
        ):
            result = nova_core._maybe_run_fulfillment_flow(
                "Help me compare possible ways to solve this.",
                session,
                [],
            )

        self.assertIsNone(result)
        self.assertIsNone(getattr(session, "fulfillment_state", None))


if __name__ == "__main__":
    unittest.main()