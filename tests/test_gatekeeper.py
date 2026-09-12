import json
import tempfile
import unittest
from pathlib import Path

from services.gatekeeper import append_record, compact_records, summarize_records, validate_record


class TestGatekeeper(unittest.TestCase):
    def _record(self) -> dict:
        return {
            "gate_id": "mission_hold",
            "record_type": "gate_observation",
            "status": "WATCH",
            "purpose": "Observe an existing mission gate.",
            "decision_context": {
                "decision": "block",
                "controlling_reason": "regression_failed",
                "observed_at": "2026-09-07T20:00:00-0500",
            },
            "evidence_before": [{"source": "runtime/regression_status.json"}],
            "expected_effect": {"claim": "prevent unsafe advancement"},
            "outcome": {"classification": "stale_controlling_evidence", "evidence_freshness_fault": True},
            "utility_verdict": {"value": "unknown"},
            "verification_contract": {"model_assessment_is_evidence": False},
            "automatic_policy_change": False,
            "automatic_gate_retirement": False,
        }

    def test_record_round_trip_and_summary(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gatekeeper_records.jsonl"
            self.assertEqual(validate_record(self._record()), [])
            self.assertEqual(append_record(self._record(), path), [])
            summary = summarize_records(path)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["record_count"], 1)
        self.assertEqual(summary["gate_count"], 1)
        self.assertEqual(summary["stale_evidence_count"], 1)
        self.assertEqual(summary["unknown_utility_count"], 1)
        self.assertEqual(summary["records"][0]["gate_id"], "mission_hold")

    def test_rejects_model_as_evidence_and_policy_mutation(self):
        record = self._record()
        record["verification_contract"]["model_assessment_is_evidence"] = True
        record["automatic_policy_change"] = True
        errors = validate_record(record)
        self.assertIn("model_cannot_be_evidence", errors)
        self.assertIn("automatic_policy_change_forbidden", errors)

    def test_coalesces_identical_consecutive_observations(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gatekeeper_records.jsonl"
            first = self._record()
            first["decision_context"]["controlling_reason"] = "same_failed_fingerprint"
            first["evidence_before"] = [{"source": "runtime", "fingerprint": "abc"}]
            self.assertEqual(append_record(first, path), [])
            self.assertEqual(append_record(dict(first), path), [])
            changed = dict(first)
            changed["evidence_before"] = [{"source": "runtime", "fingerprint": "def"}]
            self.assertEqual(append_record(changed, path), [])
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["seen_count"], 2)
        self.assertEqual(rows[1]["seen_count"], 1)
        self.assertEqual(rows[1]["evidence_before"][0]["fingerprint"], "def")
        self.assertEqual(rows[0]["first_observed_at"], rows[0]["decision_context"]["observed_at"])
        self.assertEqual(rows[0]["last_observed_at"], rows[0]["decision_context"]["observed_at"])

    def test_compact_records_preserves_repetition_count(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gatekeeper_records.jsonl"
            record = self._record()
            record["decision_context"]["controlling_reason"] = "same_failed_fingerprint"
            record["evidence_before"] = [{"fingerprint": "abc"}]
            for _ in range(4):
                append_record(record, path)
            result = compact_records(path)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result["merged"], 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["seen_count"], 4)
        self.assertEqual(rows[0]["first_observed_at"], rows[0]["last_observed_at"])


if __name__ == "__main__":
    unittest.main()
