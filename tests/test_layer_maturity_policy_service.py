import unittest

from services.layer_maturity_policy import (
    LEAH_BUILD_SEQUENCE,
    build_layer_maturity_summary,
    capability_action_allowed,
    capability_gap_signal_suppressed,
    enrich_status_with_layer_maturity,
    evaluate_core_gate,
    filter_actionable_capability_gaps,
    next_leah_capability_in_sequence,
    normalize_layer_policy,
    orchestrator_codegen_action_allowed,
)
from services.work_tree_signal_ingestion import _capability_gap_signal_from_status


class TestLayerMaturityPolicyService(unittest.TestCase):
    def test_normalize_layer_policy_defaults_to_observe(self):
        layers = normalize_layer_policy({})

        self.assertEqual(layers["leah"]["mode"], "observe")
        self.assertEqual(layers["codegen"]["mode"], "observe")
        self.assertEqual(layers["leah"]["promoted_capabilities"], [])

    def test_observe_mode_suppresses_capability_gap_signals(self):
        status = enrich_status_with_layer_maturity(
            {
                "capability_gap_count": 4,
                "capability_gaps": [
                    "leah_voice_persona_engine",
                    "leah_memory_recall",
                    "autonomous_code_generation",
                ],
            },
            policy={"layers": {"leah": {"mode": "observe"}, "codegen": {"mode": "observe"}}},
        )

        self.assertTrue(capability_gap_signal_suppressed(status))
        self.assertEqual(status.get("capability_gap_actionable_count"), 0)
        self.assertGreaterEqual(status.get("capability_gap_observed_count"), 1)
        self.assertIsNone(_capability_gap_signal_from_status(status))

    def test_active_mode_requires_explicit_promotion(self):
        status = enrich_status_with_layer_maturity(
            {
                "capability_gap_count": 2,
                "capability_gaps": ["autonomous_code_generation", "type_checking"],
                "root_closure_inventory": {
                    "roots": [
                        {"root_id": root_id, "ok": True}
                        for root_id in (
                            "model_runtime",
                            "conversation_routing",
                            "frontdoor_cli",
                            "operator_control",
                            "http_api_control",
                        )
                    ]
                },
            },
            policy={
                "layers": {
                    "codegen": {
                        "mode": "active",
                        "promoted_capabilities": ["autonomous_code_generation"],
                    },
                    "leah": {"mode": "observe", "promoted_capabilities": []},
                }
            },
        )

        actionable = list(status.get("capability_gaps_actionable") or [])
        self.assertEqual(actionable, ["autonomous_code_generation"])
        signal = _capability_gap_signal_from_status(status)
        self.assertIsNotNone(signal)
        self.assertEqual(signal["payload"]["primary_capability"], "autonomous_code_generation")

    def test_leah_sequence_requires_ordered_promotion(self):
        gaps = [
            "leah_voice_persona_engine",
            "leah_memory_recall",
            "leah_conversation_continuity",
        ]
        promoted = ["leah_conversation_continuity", "leah_memory_recall", "leah_voice_persona_engine"]

        self.assertEqual(
            next_leah_capability_in_sequence(gaps, promoted_capabilities=promoted),
            "leah_conversation_continuity",
        )
        self.assertEqual(LEAH_BUILD_SEQUENCE[0], "leah_conversation_continuity")

    def test_core_gate_passes_when_required_roots_close_and_drift_clear(self):
        status = {
            "release_runtime_truth": {"suppress_closure_inventory_signals": False},
            "root_closure_inventory": {
                "roots": [
                    {"root_id": root_id, "ok": True}
                    for root_id in (
                        "model_runtime",
                        "conversation_routing",
                        "frontdoor_cli",
                        "operator_control",
                        "http_api_control",
                    )
                ]
            },
            "live_closure_inventory": {"ok": True, "gap_roots": []},
        }

        core_gate = evaluate_core_gate(status)

        self.assertTrue(core_gate.get("ok"))
        self.assertFalse(core_gate.get("drift_blocked"))
        self.assertEqual(core_gate.get("missing_roots"), [])
        self.assertEqual(core_gate.get("live_closure_gap_roots"), [])

    def test_core_gate_fails_when_live_closure_reports_semantic_gaps(self):
        status = {
            "release_runtime_truth": {"suppress_closure_inventory_signals": False},
            "root_closure_inventory": {
                "roots": [{"root_id": "conversation_routing", "ok": True}]
            },
            "live_closure_inventory": {
                "ok": False,
                "gap_roots": ["conversation_routing"],
            },
        }

        core_gate = evaluate_core_gate(status)

        self.assertFalse(core_gate.get("ok"))
        self.assertEqual(core_gate.get("live_closure_gap_roots"), ["conversation_routing"])

    def test_leah_capability_blocked_until_core_gate_passes(self):
        policy = {
            "layers": {
                "leah": {
                    "mode": "active",
                    "promoted_capabilities": ["leah_conversation_continuity"],
                },
                "codegen": {"mode": "observe", "promoted_capabilities": []},
            }
        }
        status = {
            "capability_gaps": ["leah_conversation_continuity"],
            "root_closure_inventory": {"roots": [{"root_id": "model_runtime", "ok": False}]},
            "release_runtime_truth": {"suppress_closure_inventory_signals": True},
        }

        self.assertFalse(
            capability_action_allowed(
                "leah_conversation_continuity",
                policy=policy,
                status_payload=status,
            )
        )
        actionable = filter_actionable_capability_gaps(
            ["leah_conversation_continuity"],
            policy=policy,
            status_payload=status,
        )
        self.assertEqual(actionable, [])

    def test_orchestrator_blocks_codegen_actions_in_observe_mode(self):
        policy = {"layers": {"leah": {"mode": "observe"}, "codegen": {"mode": "observe"}}}

        self.assertFalse(
            orchestrator_codegen_action_allowed(
                "codegen_run",
                policy=policy,
                capability_name="autonomous_code_generation",
            )
        )
        self.assertFalse(
            orchestrator_codegen_action_allowed(
                "leah_build_run_next",
                policy=policy,
                capability_name="leah_conversation_continuity",
            )
        )

    def test_build_layer_maturity_summary_exposes_next_leah_capability(self):
        summary = build_layer_maturity_summary(
            {
                "capability_gaps": [
                    "leah_voice_persona_engine",
                    "leah_conversation_continuity",
                ],
            },
            policy={
                "layers": {
                    "leah": {
                        "mode": "active",
                        "promoted_capabilities": ["leah_conversation_continuity"],
                    },
                    "codegen": {"mode": "observe", "promoted_capabilities": []},
                }
            },
        )

        self.assertEqual(summary.get("next_leah_capability"), "leah_conversation_continuity")
        self.assertFalse(summary.get("leah_observe_mode"))


if __name__ == "__main__":
    unittest.main()