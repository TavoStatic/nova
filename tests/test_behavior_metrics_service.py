import json
import tempfile
import unittest
from pathlib import Path

from services.behavior_metrics import BehaviorMetricsStore


class TestBehaviorMetricsStore(unittest.TestCase):
    def test_record_event_increments_counter_and_persists(self):
        with tempfile.TemporaryDirectory() as td:
            metrics_file = Path(td) / "behavior_metrics.json"
            store = BehaviorMetricsStore(metrics_file)

            store.record_event("deterministic_hit")
            store.record_event("deterministic_hit")

            snap = store.snapshot()
            self.assertEqual(snap.get("deterministic_hit"), 2)
            self.assertEqual(snap.get("last_event"), "deterministic_hit")
            self.assertTrue(metrics_file.exists())

            on_disk = json.loads(metrics_file.read_text(encoding="utf-8"))
            self.assertEqual(on_disk.get("deterministic_hit"), 2)

    def test_update_from_reflection_updates_expected_fields(self):
        with tempfile.TemporaryDirectory() as td:
            metrics_file = Path(td) / "behavior_metrics.json"
            store = BehaviorMetricsStore(metrics_file)

            payload = {
                "top_repeated_failure_class": "routing_miss",
                "top_repeated_correction_class": "self_fix",
                "routing_stable": False,
                "unsupported_claims_blocked": True,
                "ts": "2026-03-27 12:00:00",
            }
            store.update_from_reflection(payload, 30)

            snap = store.snapshot()
            self.assertEqual(snap.get("top_repeated_failure_class"), "routing_miss")
            self.assertEqual(snap.get("top_repeated_correction_class"), "self_fix")
            self.assertFalse(snap.get("routing_stable"))
            self.assertTrue(snap.get("unsupported_claims_blocked"))
            self.assertEqual(snap.get("last_reflection_turn"), 30)
            self.assertEqual(snap.get("last_reflection_at"), "2026-03-27 12:00:00")


if __name__ == "__main__":
    unittest.main()
