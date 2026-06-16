"""Tests for orchestrator codegen support and capability gap branch routing."""

import json
import unittest
from unittest.mock import MagicMock, patch

from services.autonomy_orchestrator import AutonomyOrchestratorService
from services.nova_control_action_dispatcher import (
    autonomy_advisory_action_catalog,
    is_autonomy_advisory_action,
)


class TestCodegenActionCatalog(unittest.TestCase):
    """Test codegen_run in action catalog."""

    def test_codegen_run_in_catalog(self):
        """codegen_run action is registered in catalog."""
        catalog = autonomy_advisory_action_catalog()
        self.assertIn("codegen_run", catalog)

    def test_codegen_run_metadata(self):
        """codegen_run has required metadata."""
        catalog = autonomy_advisory_action_catalog()
        codegen = catalog.get("codegen_run", {})

        self.assertEqual(codegen.get("target_kind"), "lane")
        self.assertEqual(codegen.get("target_id"), "capability_gap")
        self.assertEqual(codegen.get("execution_group"), "generated_code")
        self.assertFalse(codegen.get("requires_ack", False))
        self.assertIn("capability_gap_detected", codegen.get("preconditions", []))

    def test_codegen_run_is_advisory_action(self):
        """codegen_run is recognized as advisory action."""
        self.assertTrue(is_autonomy_advisory_action("codegen_run"))

    def test_codegen_run_has_impact_and_risk(self):
        """codegen_run has impact and safety_risk scores."""
        catalog = autonomy_advisory_action_catalog()
        codegen = catalog.get("codegen_run", {})

        impact = codegen.get("impact")
        safety_risk = codegen.get("safety_risk")

        self.assertIsNotNone(impact)
        self.assertIsNotNone(safety_risk)
        self.assertGreater(impact, 0.5)
        self.assertGreater(safety_risk, 0.1)
        self.assertLess(safety_risk, 0.3)

    def test_leah_build_run_next_in_catalog(self):
        """leah_build_run_next action is registered in catalog."""
        catalog = autonomy_advisory_action_catalog()
        self.assertIn("leah_build_run_next", catalog)

    def test_leah_build_run_next_metadata(self):
        """leah_build_run_next has the Leah build metadata."""
        catalog = autonomy_advisory_action_catalog()
        leah = catalog.get("leah_build_run_next", {})

        self.assertEqual(leah.get("target_kind"), "lane")
        self.assertEqual(leah.get("target_id"), "leah_build")
        self.assertEqual(leah.get("execution_group"), "leah_build")
        self.assertTrue(leah.get("requires_ack", False))
        self.assertIn("policy_allows_leah_build_run_next", leah.get("preconditions", []))


class TestOrchestratorCodegenDetection(unittest.TestCase):
    """Test orchestrator detection of capability_gap branches."""

    def test_orchestrator_detects_capability_gap_branches(self):
        """Orchestrator identifies capability_gap branches as candidates."""
        orchestrator = AutonomyOrchestratorService()

        evidence = {
            "work_tree_snapshot": {
                "branches": [
                    {
                        "branch_id": "cap-gap-001",
                        "kind": "capability_gap",
                        "status": "ready",
                        "title": "Implement autonomous_code_generation",
                        "metadata": {
                            "capability_name": "autonomous_code_generation",
                        },
                    }
                ],
            },
            "queue_pressure": {},
            "runtime_guard_status": {"guard_running": True},
            "triage_hints": {},
            "autonomy_maintenance": {},
        }

        candidates = orchestrator._contract_candidate_actions(evidence)

        codegen_candidates = [
            c for c in candidates
            if c.get("action", {}).get("action_type") == "codegen_run"
        ]
        self.assertEqual(len(codegen_candidates), 1)

    def test_orchestrator_codegen_action_includes_branch_id(self):
        """Orchestrator codegen action targets the capability gap branch."""
        orchestrator = AutonomyOrchestratorService()

        evidence = {
            "work_tree_snapshot": {
                "branches": [
                    {
                        "branch_id": "cap-gap-xyz",
                        "kind": "capability_gap",
                        "status": "ready",
                        "title": "Add type_checking capability",
                        "metadata": {"capability_name": "type_checking"},
                    }
                ],
            },
            "queue_pressure": {},
            "runtime_guard_status": {"guard_running": True},
            "triage_hints": {},
            "autonomy_maintenance": {},
        }

        candidates = orchestrator._contract_candidate_actions(evidence)
        codegen_action = None
        for c in candidates:
            if c.get("action", {}).get("action_type") == "codegen_run":
                codegen_action = c.get("action", {})
                break

        self.assertIsNotNone(codegen_action)
        self.assertEqual(codegen_action.get("target_id"), "cap-gap-xyz")
        self.assertIn("type_checking", codegen_action.get("expected_effect", ""))

    def test_orchestrator_skips_non_ready_capability_gaps(self):
        """Orchestrator ignores non-ready capability gap branches."""
        orchestrator = AutonomyOrchestratorService()

        evidence = {
            "work_tree_snapshot": {
                "branches": [
                    {
                        "branch_id": "cap-gap-002",
                        "kind": "capability_gap",
                        "status": "blocked",  # Not ready
                        "title": "Blocked gap",
                        "metadata": {},
                    }
                ],
            },
            "queue_pressure": {},
            "runtime_guard_status": {"guard_running": True},
            "triage_hints": {},
            "autonomy_maintenance": {},
        }

        candidates = orchestrator._contract_candidate_actions(evidence)
        codegen_candidates = [
            c for c in candidates
            if c.get("action", {}).get("action_type") == "codegen_run"
        ]
        self.assertEqual(len(codegen_candidates), 0)

    def test_orchestrator_handles_multiple_capability_gaps(self):
        """Orchestrator selects first ready capability gap branch."""
        orchestrator = AutonomyOrchestratorService()

        evidence = {
            "work_tree_snapshot": {
                "branches": [
                    {
                        "branch_id": "cap-gap-first",
                        "kind": "capability_gap",
                        "status": "ready",
                        "title": "First gap",
                        "metadata": {"capability_name": "first_gap"},
                    },
                    {
                        "branch_id": "cap-gap-second",
                        "kind": "capability_gap",
                        "status": "ready",
                        "title": "Second gap",
                        "metadata": {"capability_name": "second_gap"},
                    },
                ],
            },
            "queue_pressure": {},
            "runtime_guard_status": {"guard_running": True},
            "triage_hints": {},
            "autonomy_maintenance": {},
        }

        candidates = orchestrator._contract_candidate_actions(evidence)
        codegen_action = None
        for c in candidates:
            if c.get("action", {}).get("action_type") == "codegen_run":
                codegen_action = c.get("action", {})
                break

        self.assertIsNotNone(codegen_action)
        self.assertEqual(codegen_action.get("target_id"), "cap-gap-first")

    def test_orchestrator_codegen_excluded_from_general_work_count(self):
        """Capability gap branches excluded from general active work count."""
        orchestrator = AutonomyOrchestratorService()

        work_tree = {
            "branches": [
                {
                    "branch_id": "cap-gap-001",
                    "kind": "capability_gap",
                    "status": "ready",
                    "owner": "capability_gap",
                    "title": "Gap",
                    "metadata": {},
                },
                {
                    "branch_id": "other-work-001",
                    "kind": "signal_ingestion",
                    "status": "open",
                    "owner": "signal_ingestion",
                    "title": "Signal work",
                    "metadata": {},
                },
            ],
        }

        count = AutonomyOrchestratorService._contract_active_work_tree_count(work_tree)
        self.assertEqual(count, 0)  # Both are managed owners, so not counted as "active"

    def test_orchestrator_codegen_action_contract(self):
        """Codegen action has valid contract structure."""
        orchestrator = AutonomyOrchestratorService()
        action = orchestrator._contract_action(
            "codegen_run",
            reason_code="capability_gap_ready",
            target_id="cap-gap-001",
            expected_effect="Close autonomy capability gap",
        )

        self.assertEqual(action["action_type"], "codegen_run")
        self.assertEqual(action["target_kind"], "lane")
        self.assertEqual(action["target_id"], "cap-gap-001")
        self.assertEqual(action["reason_code"], "capability_gap_ready")
        self.assertIn("autonomy", action["expected_effect"].lower())
        self.assertFalse(action["requires_ack"])
        self.assertGreater(action["cooldown_sec"], 0)
        self.assertIn("capability_gap_detected", action["preconditions"])


class TestOrchestratorCodegenPriority(unittest.TestCase):
    """Test how codegen_run prioritizes against other actions."""

    def test_codegen_prioritizes_capability_gaps(self):
        """Orchestrator includes codegen when capability gaps present."""
        orchestrator = AutonomyOrchestratorService()

        evidence = {
            "work_tree_snapshot": {
                "branches": [
                    {
                        "branch_id": "cap-gap-priority",
                        "kind": "capability_gap",
                        "status": "ready",
                        "title": "High-priority capability",
                        "metadata": {"capability_name": "critical_feature"},
                    }
                ],
                "active_executable_count": 0,
                "open_count": 0,
            },
            "queue_pressure": {
                "generated_pending_count": 0,
                "generated_actionable_count": 0,
                "patch_ready_count": 0,
                "approved_eligible_previews": 0,
            },
            "runtime_guard_status": {"guard_running": True},
            "triage_hints": {"max_seam_pressure": 0.0},
            "autonomy_maintenance": {"worker_status": "running"},
        }

        candidates = orchestrator._contract_candidate_actions(evidence)

        # Should have at least the codegen candidate
        self.assertGreater(len(candidates), 0)

        action_types = [c.get("action", {}).get("action_type") for c in candidates]
        self.assertIn("codegen_run", action_types)


class TestOrchestratorLeahBuildRouting(unittest.TestCase):
    """Test Leah build routing from capability gap branches."""

    def test_orchestrator_routes_leah_capabilities_to_leah_build(self):
        orchestrator = AutonomyOrchestratorService()

        evidence = {
            "work_tree_snapshot": {
                "branches": [
                    {
                        "branch_id": "leah-gap-001",
                        "kind": "capability_gap",
                        "status": "ready",
                        "title": "Implement leah_voice_persona_engine",
                        "source_payload": {
                            "primary_capability": "leah_voice_persona_engine",
                            "execution_group": "leah_build",
                        },
                        "metadata": {"capability_name": "leah_voice_persona_engine"},
                    }
                ],
            },
            "queue_pressure": {},
            "runtime_guard_status": {"guard_running": True},
            "triage_hints": {},
            "autonomy_maintenance": {},
        }

        candidates = orchestrator._contract_candidate_actions(evidence)
        leah_candidates = [
            c for c in candidates
            if c.get("action", {}).get("action_type") == "leah_build_run_next"
        ]
        self.assertEqual(len(leah_candidates), 1)
        action = leah_candidates[0]["action"]
        self.assertEqual(action.get("target_id"), "leah-gap-001")
        self.assertIn("leah_voice_persona_engine", action.get("expected_effect", ""))


if __name__ == "__main__":
    unittest.main()
