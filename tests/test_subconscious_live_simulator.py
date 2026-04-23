import unittest

from subconscious_live_simulator import (
    LiveSimulationFamily,
    LiveSimulationFamilyResult,
    LiveSimulationScenario,
    LiveSimulationTurn,
    TrainingPriorityItem,
    build_training_priorities,
    build_default_live_scenario_families,
    build_default_live_scenarios,
    simulate_live_families,
    simulate_live_family,
    simulate_live_scenario,
    simulate_live_use,
)


class TestSubconsciousLiveSimulator(unittest.TestCase):
    def test_supervisor_boundary_scenario_stays_quiet_without_cracks(self):
        scenario = LiveSimulationScenario(
            scenario_id="supervisor-boundary",
            target_seam="supervisor_ownership_boundary",
            turns=[
                LiveSimulationTurn(
                    user_text="go ahead",
                    chosen_route="supervisor_owned",
                    pending_action={
                        "kind": "weather_lookup",
                        "status": "awaiting_location",
                        "saved_location_available": True,
                        "preferred_tool": "weather_current_location",
                    },
                )
            ],
        )

        result = simulate_live_scenario(scenario)

        self.assertEqual(result.target_seam, "supervisor_ownership_boundary")
        self.assertEqual(len(result.pressure_records), 1)
        self.assertEqual(getattr(result.pressure_records[0], "chosen_route", None), "supervisor_owned")
        self.assertFalse(result.subconscious_snapshot.get("replan_requested"))
        self.assertIsNone(result.training_backlog)

    def test_fulfillment_fallthrough_scenario_surfaces_backlog_candidate(self):
        scenario = LiveSimulationScenario(
            scenario_id="fulfillment-fallthrough",
            target_seam="fulfillment_bridge_entry_fallthrough",
            turns=[
                LiveSimulationTurn(
                    user_text="Show me workable options without collapsing too early.",
                    chosen_route="generic_fallback",
                )
            ],
        )

        result = simulate_live_scenario(scenario)

        self.assertTrue(result.subconscious_snapshot.get("replan_requested"))
        signals = result.subconscious_snapshot.get("active_recent_signals") or []
        self.assertIn("fulfillment_missed", signals)
        self.assertIsInstance(result.training_backlog, dict)
        candidate_tests = result.training_backlog.get("candidate_tests") or []
        self.assertGreaterEqual(len(candidate_tests), 1)
        self.assertEqual(candidate_tests[0].get("signal"), "fallback_overuse")

    def test_multi_turn_weak_pressure_scenario_accumulates_cracks_and_backlog(self):
        scenario = LiveSimulationScenario(
            scenario_id="weak-pressure",
            target_seam="subconscious_pressure_backlog_generation",
            turns=[
                LiveSimulationTurn(user_text="how are you doing today ?", chosen_route="generic_fallback"),
                LiveSimulationTurn(user_text="what now", chosen_route="generic_fallback"),
            ],
        )

        result = simulate_live_scenario(scenario)

        self.assertEqual(len(result.pressure_records), 2)
        self.assertTrue(result.subconscious_snapshot.get("replan_requested"))
        self.assertGreaterEqual(result.subconscious_snapshot.get("crack_counts", {}).get("route_unclear", 0), 1)
        self.assertIsInstance(result.training_backlog, dict)
        backlog_signals = [item.get("signal") for item in list(result.training_backlog.get("candidate_tests") or [])]
        self.assertIn("route_unclear", backlog_signals)
        self.assertIn("route_fit_weak", backlog_signals)

    def test_simulate_live_use_runs_default_scenarios(self):
        results = simulate_live_use(build_default_live_scenarios())

        self.assertEqual(len(results), 3)
        scenario_ids = [item.scenario_id for item in results]
        self.assertIn("supervisor-boundary", scenario_ids)
        self.assertIn("fulfillment-fallthrough", scenario_ids)
        self.assertIn("repeated-weak-pressure", scenario_ids)

    def test_default_live_scenario_families_create_variations_per_current_seam(self):
        families = build_default_live_scenario_families()

        self.assertEqual(len(families), 8)
        family_ids = [item.family_id for item in families]
        self.assertIn("supervisor-boundary-family", family_ids)
        self.assertIn("fulfillment-fallthrough-family", family_ids)
        self.assertIn("repeated-weak-pressure-family", family_ids)
        self.assertIn("memory-capture-fallthrough-family", family_ids)
        self.assertIn("weather-continuation-fallthrough-family", family_ids)
        self.assertIn("retrieval-followup-fallthrough-family", family_ids)
        self.assertIn("patch-routing-fallthrough-family", family_ids)
        self.assertIn("session-fact-recall-fallthrough-family", family_ids)
        for family in families:
            self.assertGreaterEqual(len(family.scenarios), 3)
            self.assertLessEqual(len(family.scenarios), 5)

    def test_seed_turns_support_session_fact_recall_fallthrough_probe(self):
        scenario = LiveSimulationScenario(
            scenario_id="session-fact-recall-fallthrough",
            target_seam="session_fact_recall_route_fallthrough",
            seed_turns=[
                ("user", "For this session, remember the codeword cobalt sparrow and the topic packaging drift."),
                ("assistant", "Got it."),
            ],
            turns=[
                LiveSimulationTurn(
                    user_text="What codeword did I just ask you to remember?",
                    chosen_route="generic_fallback",
                )
            ],
        )

        result = simulate_live_scenario(scenario)

        self.assertEqual(result.target_seam, "session_fact_recall_route_fallthrough")
        self.assertEqual(len(result.pressure_records), 1)
        self.assertTrue(result.subconscious_snapshot.get("replan_requested"))
        signals = result.subconscious_snapshot.get("active_recent_signals") or []
        self.assertIn("fallback_overuse", signals)

    def test_quiet_control_family_stays_quiet_across_variations(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "supervisor-boundary-family"
        )

        result = simulate_live_family(family)

        self.assertIsInstance(result, LiveSimulationFamilyResult)
        self.assertEqual(result.noise_summary.get("quiet_variations"), len(family.scenarios))
        self.assertEqual(result.noise_summary.get("useful_variations"), 0)
        self.assertEqual(result.noise_summary.get("noisy_variations"), 0)
        self.assertTrue(result.noise_summary.get("quiet_control"))
        self.assertEqual(result.repeated_signals, [])
        self.assertEqual(result.top_backlog_candidates, [])
        self.assertEqual(result.robust_signals, [])
        self.assertEqual(result.script_specific_signals, [])
        self.assertTrue(result.quiet_control_verdict.get("quiet_control"))
        self.assertEqual(result.quiet_control_verdict.get("status"), "quiet_control")

    def test_fulfillment_family_marks_core_cracks_as_robust_across_variations(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "fulfillment-fallthrough-family"
        )

        result = simulate_live_family(family)

        by_signal = {item.get("signal"): item for item in result.repeated_signals}
        robust_by_signal = {item.get("signal"): item for item in result.robust_signals}
        script_specific_signals = {item.get("signal") for item in result.script_specific_signals}
        self.assertEqual(result.noise_summary.get("useful_variations"), len(family.scenarios))
        self.assertEqual(by_signal["fallback_overuse"].get("classification"), "robust")
        self.assertEqual(by_signal["fulfillment_missed"].get("classification"), "robust")
        self.assertEqual(robust_by_signal["fallback_overuse"].get("classification"), "robust")
        self.assertGreater(robust_by_signal["fallback_overuse"].get("robustness_score"), 0.9)
        self.assertLess(robust_by_signal["fallback_overuse"].get("robustness_score"), 1.0)
        self.assertNotIn("fallback_overuse", script_specific_signals)
        self.assertNotIn("fulfillment_missed", script_specific_signals)

    def test_variation_aggregation_marks_script_specific_crack_when_only_one_variant_hits(self):
        family = LiveSimulationFamily(
            family_id="script-specific-family",
            target_seam="fulfillment_bridge_entry_fallthrough",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="hit",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="Show me workable options without collapsing too early.", chosen_route="generic_fallback")],
                ),
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="quiet-one",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="go ahead", chosen_route="supervisor_owned", pending_action={
                        "kind": "weather_lookup",
                        "status": "awaiting_location",
                        "saved_location_available": True,
                        "preferred_tool": "weather_current_location",
                    })],
                ),
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="quiet-two",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="okay do that", chosen_route="supervisor_owned", pending_action={
                        "kind": "weather_lookup",
                        "status": "awaiting_location",
                        "saved_location_available": True,
                        "preferred_tool": "weather_current_location",
                    })],
                ),
            ],
        )

        result = simulate_live_family(family)

        by_signal = {item.get("signal"): item for item in result.repeated_signals}
        script_specific_by_signal = {item.get("signal"): item for item in result.script_specific_signals}
        self.assertEqual(by_signal["fallback_overuse"].get("classification"), "script_specific")
        self.assertEqual(by_signal["fulfillment_missed"].get("classification"), "script_specific")
        self.assertEqual(script_specific_by_signal["fallback_overuse"].get("classification"), "script_specific")
        self.assertLess(script_specific_by_signal["fallback_overuse"].get("robustness_score"), 0.7)

    def test_robust_backlog_candidate_ranking_matches_repeated_family_pressure(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "repeated-weak-pressure-family"
        )

        result = simulate_live_family(family)

        self.assertGreaterEqual(len(result.robust_backlog_candidates), 2)
        signals = [item.get("signal") for item in result.robust_backlog_candidates]
        self.assertIn("route_unclear", signals)
        self.assertIn("route_fit_weak", signals)
        first = result.robust_backlog_candidates[0]
        self.assertEqual(first.get("classification"), "robust")
        self.assertGreater(first.get("robustness_score"), 0.9)

    def test_simulate_live_families_runs_family_aggregation(self):
        results = simulate_live_families(build_default_live_scenario_families())

        self.assertEqual(len(results), 8)
        family_ids = [item.family_id for item in results]
        self.assertIn("supervisor-boundary-family", family_ids)
        self.assertIn("fulfillment-fallthrough-family", family_ids)
        self.assertIn("repeated-weak-pressure-family", family_ids)
        self.assertIn("memory-capture-fallthrough-family", family_ids)
        self.assertIn("weather-continuation-fallthrough-family", family_ids)
        self.assertIn("retrieval-followup-fallthrough-family", family_ids)
        self.assertIn("patch-routing-fallthrough-family", family_ids)
        self.assertIn("session-fact-recall-fallthrough-family", family_ids)

    def test_memory_capture_family_marks_fallback_overuse_as_robust(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "memory-capture-fallthrough-family"
        )

        result = simulate_live_family(family)

        robust_by_signal = {item.get("signal"): item for item in result.robust_signals}
        priorities = build_training_priorities(result)

        self.assertEqual(result.noise_summary.get("useful_variations"), len(family.scenarios))
        self.assertIn("fallback_overuse", robust_by_signal)
        self.assertGreater(robust_by_signal["fallback_overuse"].get("robustness_score"), 0.9)
        self.assertEqual(priorities[0].signal, "fallback_overuse")

    def test_weather_continuation_family_marks_supervisor_fallthrough_as_robust(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "weather-continuation-fallthrough-family"
        )

        result = simulate_live_family(family)

        robust_by_signal = {item.get("signal"): item for item in result.robust_signals}
        candidate_by_signal = {item.get("signal"): item for item in result.robust_backlog_candidates}

        self.assertEqual(result.noise_summary.get("useful_variations"), len(family.scenarios))
        self.assertIn("fallback_overuse", robust_by_signal)
        self.assertIn("fallback_overuse", candidate_by_signal)
        self.assertGreater(robust_by_signal["fallback_overuse"].get("robustness_score"), 0.9)

    def test_retrieval_followup_family_marks_fallback_overuse_as_robust(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "retrieval-followup-fallthrough-family"
        )

        result = simulate_live_family(family)

        robust_by_signal = {item.get("signal"): item for item in result.robust_signals}
        self.assertEqual(result.noise_summary.get("useful_variations"), len(family.scenarios))
        self.assertIn("fallback_overuse", robust_by_signal)
        self.assertGreater(robust_by_signal["fallback_overuse"].get("robustness_score"), 0.9)

    def test_patch_routing_family_marks_fallback_overuse_as_robust(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "patch-routing-fallthrough-family"
        )

        result = simulate_live_family(family)

        robust_by_signal = {item.get("signal"): item for item in result.robust_signals}
        self.assertEqual(result.noise_summary.get("useful_variations"), len(family.scenarios))
        self.assertIn("fallback_overuse", robust_by_signal)
        self.assertGreater(robust_by_signal["fallback_overuse"].get("robustness_score"), 0.9)

    def test_session_fact_recall_family_marks_fallback_overuse_as_robust(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "session-fact-recall-fallthrough-family"
        )

        result = simulate_live_family(family)

        robust_by_signal = {item.get("signal"): item for item in result.robust_signals}
        self.assertEqual(result.target_seam, "session_fact_recall_route_fallthrough")
        self.assertEqual(result.noise_summary.get("useful_variations"), len(family.scenarios))
        self.assertIn("fallback_overuse", robust_by_signal)
        self.assertGreater(robust_by_signal["fallback_overuse"].get("robustness_score"), 0.9)

    def test_robust_weakness_creates_higher_priority_training_item(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "fulfillment-fallthrough-family"
        )

        result = simulate_live_family(family)
        priorities = build_training_priorities(result)

        self.assertGreaterEqual(len(priorities), 1)
        self.assertIsInstance(priorities[0], TrainingPriorityItem)
        self.assertEqual(priorities[0].seam, "fulfillment_bridge_entry_fallthrough")
        self.assertEqual(priorities[0].signal, "fallback_overuse")
        self.assertEqual(priorities[0].urgency, "high")
        self.assertGreater(priorities[0].robustness, 0.9)

    def test_script_specific_weakness_stays_lower_or_deferred(self):
        family = LiveSimulationFamily(
            family_id="script-specific-family",
            target_seam="fulfillment_bridge_entry_fallthrough",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="hit",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="Show me workable options without collapsing too early.", chosen_route="generic_fallback")],
                ),
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="quiet-one",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="go ahead", chosen_route="supervisor_owned", pending_action={
                        "kind": "weather_lookup",
                        "status": "awaiting_location",
                        "saved_location_available": True,
                        "preferred_tool": "weather_current_location",
                    })],
                ),
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="quiet-two",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="okay do that", chosen_route="supervisor_owned", pending_action={
                        "kind": "weather_lookup",
                        "status": "awaiting_location",
                        "saved_location_available": True,
                        "preferred_tool": "weather_current_location",
                    })],
                ),
            ],
        )

        result = simulate_live_family(family)
        priorities = build_training_priorities(result)
        by_signal = {item.signal: item for item in priorities}

        self.assertNotIn("fallback_overuse", by_signal)

    def test_robustness_scores_do_not_saturate_at_perfect_one(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "repeated-weak-pressure-family"
        )

        result = simulate_live_family(family)

        self.assertGreater(result.robust_signals[0].get("robustness_score"), 0.9)
        self.assertLess(result.robust_signals[0].get("robustness_score"), 1.0)

    def test_script_specific_low_robustness_signals_do_not_enter_training_priority_queue(self):
        family = LiveSimulationFamily(
            family_id="low-robustness-script-specific-family",
            target_seam="fulfillment_bridge_entry_fallthrough",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="hit",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="Show me workable options without collapsing too early.", chosen_route="generic_fallback")],
                ),
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="quiet-one",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="go ahead", chosen_route="supervisor_owned", pending_action={
                        "kind": "weather_lookup",
                        "status": "awaiting_location",
                        "saved_location_available": True,
                        "preferred_tool": "weather_current_location",
                    })],
                ),
                LiveSimulationScenario(
                    scenario_id="custom",
                    variation_id="quiet-two",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[LiveSimulationTurn(user_text="okay do that", chosen_route="supervisor_owned", pending_action={
                        "kind": "weather_lookup",
                        "status": "awaiting_location",
                        "saved_location_available": True,
                        "preferred_tool": "weather_current_location",
                    })],
                ),
            ],
        )

        result = simulate_live_family(family)
        priorities = build_training_priorities(result)

        self.assertTrue(result.script_specific_signals)
        self.assertLess(result.script_specific_signals[0].get("robustness_score"), 0.40)
        self.assertEqual(priorities, [])

    def test_quiet_control_creates_no_training_priority_noise(self):
        family = next(
            item for item in build_default_live_scenario_families()
            if item.family_id == "supervisor-boundary-family"
        )

        result = simulate_live_family(family)
        priorities = build_training_priorities(result)

        self.assertEqual(priorities, [])


if __name__ == "__main__":
    unittest.main()