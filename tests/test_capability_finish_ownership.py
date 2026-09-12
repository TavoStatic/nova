import unittest

from services.capability_finish_ownership import (
    classify_capability,
    nova_code_gap_names,
    partition_capability_gaps,
)
from services.layer_maturity_policy import filter_actionable_capability_gaps
from services.nova_shell.external_finish import external_finish_status
from services.supervisor_finish import supervisor_ownership_finish_status


class TestCapabilityFinishOwnership(unittest.TestCase):
    def test_partition_splits_nova_code_from_external(self):
        gaps = [
            "autonomous_code_generation",
            "api_gateway",
            "deployment_automation",
            "security_scanning",
        ]
        part = partition_capability_gaps(gaps)
        self.assertIn("autonomous_code_generation", part["nova_code_gap_names"])
        self.assertIn("api_gateway", part["external_gap_names"])
        self.assertIn("deployment_automation", part["external_gap_names"])
        self.assertIn("security_scanning", part["external_gap_names"])
        self.assertNotIn("api_gateway", part["nova_code_gap_names"])

    def test_classify_nova_code(self):
        row = classify_capability("generated_code_tests")
        self.assertTrue(row["nova_can_finish_alone"])
        self.assertEqual(row["finisher"], "nova_code")
        self.assertTrue(row["missing"])

    def test_classify_operator_product(self):
        row = classify_capability("security_scanning")
        self.assertFalse(row["nova_can_finish_alone"])
        self.assertEqual(row["finisher"], "operator_product")

    def test_filter_actionable_excludes_external_finishers(self):
        gaps = ["autonomous_code_generation", "api_gateway", "deployment_automation"]
        # Active policy so layer gate does not strip everything
        policy = {
            "layers": {
                "codegen": {"mode": "active", "promoted_capabilities": ["*"]},
                "leah": {"mode": "observe", "promoted_capabilities": []},
            }
        }
        # Without promote list, active mode still may block - use empty promote means none
        # capability_action_allowed for codegen in active with empty promote may block all.
        # Use observe-mode pass-through path: filter still drops external before layer check.
        status = {"capabilities_roadmap": {}}
        actionable = filter_actionable_capability_gaps(gaps, policy=policy, status_payload=status)
        self.assertNotIn("api_gateway", actionable)
        self.assertNotIn("deployment_automation", actionable)

    def test_nova_code_gap_names_helper(self):
        names = nova_code_gap_names(["api_gateway", "type_checking"])
        self.assertEqual(names, ["type_checking"])


class TestExternalFinishSurfaces(unittest.TestCase):
    def test_shell_external_finish_lists_llc_missing(self):
        status = external_finish_status()
        self.assertEqual(status.get("finisher"), "llc_external")
        self.assertFalse(status.get("ok"))
        self.assertFalse(status.get("llc_systems_built"))
        self.assertGreaterEqual(int(status.get("incomplete_count") or 0), 1)
        areas = {row.get("area") for row in list(status.get("areas") or [])}
        self.assertIn("llc_public_key", areas)
        self.assertIn("telemetry_central", areas)
        by_area = {row.get("area"): row for row in list(status.get("areas") or [])}
        self.assertTrue(by_area["llc_public_key"].get("temporary_bake_in"))
        self.assertTrue(by_area["telemetry_central"].get("temporary_bake_in"))

    def test_supervisor_finish_lists_empty_rules(self):
        status = supervisor_ownership_finish_status()
        self.assertEqual(status.get("finisher"), "operator_policy")
        self.assertFalse(status.get("ok"))
        self.assertGreaterEqual(int(status.get("incomplete_count") or 0), 1)
        names = {row.get("area") for row in list(status.get("incomplete_areas") or [])}
        all_names = {row.get("area") for row in list(status.get("areas") or [])}
        self.assertIn("explicit_intent_ownership_rules", names)
        self.assertIn("default_supervisor_rule_specs", all_names)

    def test_finish_areas_inventory_aggregates(self):
        from services.finish_areas_inventory import build_finish_areas_inventory

        inv = build_finish_areas_inventory()
        self.assertIn("external_finish", inv)
        self.assertIn("nova_code_finish", inv)
        self.assertGreaterEqual(int(inv.get("external_finish_count") or 0), 1)
        self.assertNotIn("capability_gap_detection", inv.get("nova_code_finish") or [])


if __name__ == "__main__":
    unittest.main()
