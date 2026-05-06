import json
import tempfile
import unittest
from pathlib import Path

from services.autonomy_orchestrator_ledger import AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE


class TestAutonomyOrchestratorLedgerService(unittest.TestCase):
    def test_summary_tracks_churn_and_weak_posture_refusals(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "autonomy_orchestrator_ledger.jsonl"
            rows = [
                {
                    "ts": "2026-05-06 12:00:00",
                    "decision": "block_with_reason",
                    "action": {},
                    "reason": "Core posture is repair.",
                    "rejection_reasons": ["posture_below_threshold"],
                    "evidence": {"posture": {"score": 70, "threshold": 85, "level": "repair"}},
                },
                {
                    "ts": "2026-05-06 12:01:00",
                    "decision": "recommend_action",
                    "action": {"act": "generated_queue_run_next"},
                    "reason": "Generated Work Queue has 1 actionable item.",
                    "rejection_reasons": [],
                    "evidence": {"posture": {"score": 95, "threshold": 85, "level": "strong"}},
                },
                {
                    "ts": "2026-05-06 12:02:00",
                    "decision": "recommend_action",
                    "action": {"act": "generated_queue_run_next"},
                    "reason": "Generated Work Queue has 1 actionable item.",
                    "rejection_reasons": [],
                    "evidence": {"posture": {"score": 96, "threshold": 85, "level": "strong"}},
                },
            ]
            path.write_text("\n".join(json.dumps(row, ensure_ascii=True) for row in rows), encoding="utf-8")

            summary = AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE.summary(path, limit=10)

        self.assertTrue(summary.get("ok"))
        self.assertEqual(summary.get("count"), 3)
        self.assertEqual(summary.get("decision_counts"), {"block_with_reason": 1, "recommend_action": 2})
        self.assertEqual(summary.get("action_counts"), {"none": 1, "generated_queue_run_next": 2})
        self.assertEqual(summary.get("recommendation_changes"), 1)
        self.assertEqual(summary.get("recommendation_change_rate"), 0.5)
        self.assertFalse(summary.get("stable_recommendation"))
        self.assertEqual(summary.get("weak_posture_count"), 1)
        self.assertEqual(summary.get("weak_posture_refusal_count"), 1)
        self.assertEqual(summary.get("weak_posture_refusal_rate"), 1.0)
        self.assertEqual(summary.get("last_action"), "generated_queue_run_next")
        self.assertEqual(summary.get("last_recommendation_key"), "recommend_action:generated_queue_run_next")

    def test_summary_returns_empty_shape_when_ledger_missing(self):
        summary = AUTONOMY_ORCHESTRATOR_LEDGER_SERVICE.summary(Path("C:/Nova/runtime/_missing_advisor_ledger.jsonl"))

        self.assertTrue(summary.get("ok"))
        self.assertEqual(summary.get("count"), 0)
        self.assertTrue(summary.get("stable_recommendation"))
        self.assertEqual(summary.get("last_decision"), "")


if __name__ == "__main__":
    unittest.main()
