from __future__ import annotations

import unittest
from pathlib import Path

from services.nova_live_closure import build_live_closure_inventory_payload
from tests.test_nova_wiring_inventory_service import _status_contract


class TestNovaLiveClosureService(unittest.TestCase):
    def test_live_closure_accepts_thinning_when_owner_verdict_reports_executable_work(self) -> None:
        status = {
            **_status_contract(),
            "nova_mission_owner_verdicts": [
                {
                    "owner": "core_thinning",
                    "evidence": {"order_count": 8, "executable_count": 8},
                }
            ],
        }
        payload = build_live_closure_inventory_payload(status)
        row = next(item for item in payload["roots"] if item["root_id"] == "core_steward_reflection")

        self.assertEqual(row["live_gaps"], [])

    def test_live_closure_reads_executable_count_from_sync_owner_verdict(self) -> None:
        status = {
            **_status_contract(),
            "core_thinning_sync": {
                "order_count": 8,
                "owner_verdict": {
                    "owner": "core_thinning",
                    "evidence": {"order_count": 8, "executable_count": 8},
                },
            },
        }
        payload = build_live_closure_inventory_payload(status)
        row = next(item for item in payload["roots"] if item["root_id"] == "core_steward_reflection")

        self.assertEqual(row["live_gaps"], [])

    def test_live_closure_flags_thinning_pressure_without_executable_work(self) -> None:
        status = {
            **_status_contract(),
            "nova_mission_owner_verdicts": [
                {
                    "owner": "core_thinning",
                    "evidence": {"order_count": 8, "executable_count": 0},
                }
            ],
        }
        payload = build_live_closure_inventory_payload(status)

        self.assertFalse(payload["ok"])
        self.assertIn("core_steward_reflection", payload["gap_roots"])
        row = next(item for item in payload["roots"] if item["root_id"] == "core_steward_reflection")
        self.assertIn("feedback_loop_gap:thinning_pressure_without_executable_work", row["live_gaps"])

    def test_live_closure_verifies_memory_identity_production_wiring(self) -> None:
        payload = build_live_closure_inventory_payload(_status_contract())
        row = next(item for item in payload["roots"] if item["root_id"] == "memory_identity")

        self.assertTrue(row["semantic_check_available"])
        self.assertEqual(row["live_gaps"], [])
        self.assertEqual(row["live_closure_depth"], "live_verified")

    def test_live_closure_verifies_conversation_routing_spine_parity(self) -> None:
        payload = build_live_closure_inventory_payload(_status_contract())
        row = next(item for item in payload["roots"] if item["root_id"] == "conversation_routing")

        self.assertEqual(row["live_gaps"], [])
        self.assertEqual(row["live_closure_depth"], "live_verified")

    def test_live_closure_flags_active_regression_failure(self) -> None:
        status = {
            **_status_contract(),
            "regression_status": {
                "status": "FAILED",
                "date": "2099-01-01",
                "detail": "behavior lane failed",
            },
        }
        payload = build_live_closure_inventory_payload(status)
        row = next(item for item in payload["roots"] if item["root_id"] == "release")

        self.assertIn("feedback_loop_gap:active_regression_failure", row["live_gaps"])

    def test_live_closure_does_not_publish_uninstalled_edfi_core_root(self) -> None:
        payload = build_live_closure_inventory_payload(_status_contract())
        self.assertNotIn("edfi_core", [item["root_id"] for item in payload["roots"]])


if __name__ == "__main__":
    unittest.main()