import json
import os
import tempfile
import unittest
from pathlib import Path

from services.testing_ecology import TESTING_ECOLOGY_SERVICE


class TestTestingEcologyService(unittest.TestCase):
    def test_green_contract_becomes_mutation_due_when_evidence_ages(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "result.json"
            report_path.write_text("{}", encoding="utf-8")
            now_ts = 2_000_000.0
            old_ts = now_ts - (25 * 3600)
            os.utime(report_path, (old_ts, old_ts))

            payload = TESTING_ECOLOGY_SERVICE.build_report(
                [
                    {
                        "file": "demo_contract.json",
                        "name": "Demo contract",
                        "origin": "generated",
                        "training_priorities": [{"signal": "fallback_overuse", "urgency": "high", "robustness": 0.91}],
                        "fingerprint": "contract",
                    }
                ],
                [
                    {
                        "run_id": "demo_run",
                        "session_path": "c:/Nova/runtime/test_sessions/generated_definitions/demo_contract.json",
                        "status": "green",
                        "report_path": str(report_path),
                    }
                ],
                runtime_dir=root / "runtime",
                now_ts=now_ts,
                contract_revalidate_hours=24,
            )

        item = (payload.get("items") or [])[0]
        self.assertEqual(item.get("lifecycle_state"), "stable_contract")
        self.assertTrue(item.get("mutation_due"))
        self.assertEqual(item.get("growth_action"), "mutate_or_revalidate_contract")
        self.assertEqual(payload.get("growth_pressure_count"), 1)
        self.assertEqual(payload.get("mutation_due_count"), 1)
        self.assertEqual(payload.get("ecology_status"), "mutation_due")
        self.assertEqual(payload.get("origin_counts"), {"generated": 1})
        self.assertEqual((payload.get("next_growth_item") or {}).get("file"), "demo_contract.json")

    def test_reviewed_drift_becomes_historical_not_growth_pressure(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            audit_path = runtime_dir / "test_sessions" / "promotion_audit.jsonl"
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(
                json.dumps({"file": "reviewed_drift.json", "fingerprint": "same"}) + "\n",
                encoding="utf-8",
            )

            payload = TESTING_ECOLOGY_SERVICE.build_report(
                [
                    {
                        "file": "reviewed_drift.json",
                        "name": "Reviewed drift",
                        "origin": "generated",
                        "training_priorities": [{"signal": "fallback_overuse", "urgency": "high", "robustness": 0.95}],
                        "fingerprint": "same",
                    }
                ],
                [
                    {
                        "run_id": "drift_run",
                        "session_path": "c:/Nova/runtime/test_sessions/generated_definitions/reviewed_drift.json",
                        "status": "drift",
                    }
                ],
                runtime_dir=runtime_dir,
                now_ts=2_000_000.0,
            )

        item = (payload.get("items") or [])[0]
        self.assertEqual(item.get("lifecycle_state"), "reviewed_drift")
        self.assertEqual(item.get("ecology_role"), "historical")
        self.assertFalse(item.get("growth_ready"))
        self.assertEqual(payload.get("growth_pressure_count"), 0)
        self.assertEqual(payload.get("ecology_status"), "historical_watch")

    def test_never_run_priority_is_seed_growth_candidate(self):
        payload = TESTING_ECOLOGY_SERVICE.build_report(
            [
                {
                    "file": "new_probe.json",
                    "name": "New probe",
                    "origin": "generated",
                    "training_priorities": [{"signal": "route_unclear", "urgency": "medium", "robustness": 0.7}],
                    "fingerprint": "seed",
                }
            ],
            [],
            runtime_dir=None,
            now_ts=2_000_000.0,
        )

        item = (payload.get("items") or [])[0]
        self.assertEqual(item.get("lifecycle_state"), "seed")
        self.assertEqual(item.get("ecology_role"), "growth_candidate")
        self.assertEqual(item.get("owner_hint"), "route_comparison")
        self.assertTrue(item.get("growth_ready"))
        self.assertEqual(payload.get("growth_pressure_count"), 1)
        self.assertEqual(payload.get("ecology_status"), "growth_ready")

    def test_bad_priority_values_do_not_break_the_ecology_report(self):
        payload = TESTING_ECOLOGY_SERVICE.build_report(
            [
                {
                    "file": "odd_probe.json",
                    "name": "Odd probe",
                    "origin": "saved",
                    "training_priorities": [{"signal": "route_conflict", "urgency": "bogus", "robustness": "not-a-number"}],
                    "fingerprint": "seed",
                }
            ],
            [],
            runtime_dir=None,
            now_ts=2_000_000.0,
        )

        item = (payload.get("items") or [])[0]
        self.assertEqual(item.get("owner_hint"), "route_comparison")
        self.assertEqual(item.get("top_robustness"), 0.0)
        self.assertEqual(payload.get("origin_counts"), {"saved": 1})

    def test_saved_reference_without_priorities_does_not_create_growth_pressure(self):
        payload = TESTING_ECOLOGY_SERVICE.build_report(
            [
                {
                    "file": "run_tools_http_parity.json",
                    "name": "HTTP parity",
                    "origin": "saved",
                    "training_priorities": [],
                    "fingerprint": "saved",
                }
            ],
            [],
            runtime_dir=None,
            now_ts=2_000_000.0,
        )

        item = (payload.get("items") or [])[0]
        self.assertEqual(item.get("lifecycle_state"), "saved_reference")
        self.assertEqual(item.get("ecology_role"), "reference")
        self.assertFalse(item.get("growth_ready"))
        self.assertEqual(payload.get("growth_pressure_count"), 0)
        self.assertEqual(payload.get("ecology_status"), "needs_observation")

    def test_template_definition_does_not_create_growth_pressure(self):
        payload = TESTING_ECOLOGY_SERVICE.build_report(
            [
                {
                    "file": "real_world/TEMPLATE_real_world_task.json",
                    "name": "Template",
                    "origin": "saved",
                    "training_priorities": [{"signal": "route_unclear", "urgency": "high", "robustness": 0.9}],
                    "fingerprint": "template",
                }
            ],
            [],
            runtime_dir=None,
            now_ts=2_000_000.0,
        )

        item = (payload.get("items") or [])[0]
        self.assertEqual(item.get("lifecycle_state"), "template")
        self.assertEqual(item.get("ecology_role"), "template")
        self.assertFalse(item.get("growth_ready"))
        self.assertEqual(payload.get("growth_pressure_count"), 0)


if __name__ == "__main__":
    unittest.main()
