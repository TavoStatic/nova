import json
import tempfile
import unittest
from pathlib import Path

from services.regression_truth_registry import (
    LANE_ORDER,
    lanes_needing_observation,
    read_lane_records,
    record_lane_result,
    truth,
    validate_lane_result,
    write_truth_snapshot,
)

FP_A = "a" * 64
FP_B = "b" * 64

SIX_MONTHS_AGO = "2026-03-01 00:00:00"


def lane_record(lane: str, fingerprint: str = FP_A, status: str = "PASS", **extra) -> dict:
    record = {
        "lane": lane,
        "source_fingerprint": fingerprint,
        "status": status,
        "started_at": "2026-09-08 09:00:00",
        "finished_at": "2026-09-08 09:40:00",
        "duration_sec": 2400,
        "tests": 83,
        "failures": 0,
        "artifact_log_ref": f"runtime/logs/{lane}.log",
    }
    record.update(extra)
    return record


class TestRegressionTruthRegistry(unittest.TestCase):
    def test_validate_and_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            self.assertEqual(validate_lane_result(lane_record("unit")), [])
            self.assertEqual(record_lane_result(lane_record("unit"), path), [])
            records = read_lane_records(path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["lane"], "unit")
        self.assertEqual(records[0]["status"], "PASS")
        self.assertEqual(records[0]["source_fingerprint"], FP_A)

    def test_validate_rejects_unknown_lane_and_missing_fingerprint(self):
        errors = validate_lane_result(lane_record("sock"))
        self.assertIn("lane_not_required:sock", errors)
        errors = validate_lane_result(lane_record("unit", fingerprint=""))
        self.assertIn("source_fingerprint_required", errors)
        errors = validate_lane_result(lane_record("unit", status="GREEN"))
        self.assertIn("status_unknown:GREEN", errors)

    def test_current_requires_matching_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            record_lane_result(lane_record("unit", fingerprint=FP_A), path)
            result_a = truth(path, FP_A)
            result_b = truth(path, FP_B)
        self.assertEqual(result_a["lanes"]["unit"]["status"], "PASS")
        self.assertTrue(result_a["lanes"]["unit"]["current"])
        self.assertEqual(result_b["lanes"]["unit"]["status"], "UNKNOWN")
        self.assertFalse(result_b["lanes"]["unit"]["current"])
        self.assertEqual(result_b["certification"], "NOT_CURRENT")

    def test_fingerprint_is_freshness_record_is_current_even_after_six_months(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            record_lane_result(
                lane_record("unit", fingerprint=FP_A, finished_at=SIX_MONTHS_AGO, duration_sec=1),
                path,
            )
            current = truth(path, FP_A)
            changed = truth(path, FP_B)
        self.assertEqual(current["lanes"]["unit"]["status"], "PASS")
        self.assertTrue(current["lanes"]["unit"]["current"])
        self.assertEqual(current["certification"], "PARTIAL")
        self.assertEqual(changed["lanes"]["unit"]["status"], "UNKNOWN")
        self.assertEqual(changed["certification"], "NOT_CURRENT")

    def test_full_certification_requires_all_lanes_current_pass(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            for lane in LANE_ORDER:
                record_lane_result(lane_record(lane), path)
            result = truth(path, FP_A)
        self.assertEqual(result["certification"], "FULL")
        self.assertEqual(result["reason"], [])
        self.assertEqual(result["lanes_needing_observation"], [])

    def test_partial_reports_lanes_not_verified_against_current_source(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            record_lane_result(lane_record("unit"), path)
            result = truth(path, FP_A)
        self.assertEqual(result["certification"], "PARTIAL")
        self.assertEqual(result["reason"], ["behavior_not_observed_on_current", "integration_not_observed_on_current"])
        self.assertEqual(result["lanes_needing_observation"], ["behavior", "integration"])

    def test_resume_at_gap_keeps_passed_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            for lane in ("unit", "behavior"):
                record_lane_result(lane_record(lane), path)
            result = truth(path, FP_A)
        self.assertEqual(result["certification"], "PARTIAL")
        self.assertEqual(result["lanes_needing_observation"], ["integration"])
        self.assertEqual(result["lanes"]["unit"]["status"], "PASS")
        self.assertEqual(result["lanes"]["behavior"]["status"], "PASS")

    def test_old_fingerprint_evidence_is_not_current_but_certifies_partial_with_other_lanes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            record_lane_result(lane_record("unit"), path)
            record_lane_result(lane_record("behavior"), path)
            record_lane_result(
                lane_record("integration", fingerprint=FP_B),
                path,
            )
            result = truth(path, FP_A)
        self.assertEqual(result["certification"], "PARTIAL")
        self.assertEqual(result["reason"], ["integration_not_current"])
        self.assertEqual(result["lanes"]["integration"]["status"], "UNKNOWN")

    def test_failed_lane_dominates_certification(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            record_lane_result(lane_record("unit", status="FAILED", failures=2), path)
            record_lane_result(lane_record("behavior"), path)
            record_lane_result(lane_record("integration"), path)
            result = truth(path, FP_A)
        self.assertEqual(result["certification"], "FAILED")
        self.assertEqual(result["reason"], ["unit_failed_on_current"])
        self.assertEqual(result["lanes_needing_observation"], ["unit"])

    def test_timed_out_lane_is_not_failed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            record_lane_result(lane_record("unit"), path)
            record_lane_result(lane_record("behavior", status="TIMED_OUT"), path)
            result = truth(path, FP_A)
        self.assertEqual(result["certification"], "PARTIAL")
        self.assertEqual(
            result["reason"],
            ["behavior_timed_out_on_current", "integration_not_observed_on_current"],
        )
        self.assertEqual(result["lanes_needing_observation"], ["behavior", "integration"])

    def test_needs_observation_returns_all_missing_lanes_without_gating(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            self.assertEqual(lanes_needing_observation(path, FP_A), ["unit", "behavior", "integration"])
            record_lane_result(lane_record("unit"), path)
            self.assertEqual(lanes_needing_observation(path, FP_A), ["behavior", "integration"])
            self.assertEqual(
                truth(path, FP_A)["lanes_needing_observation"],
                ["behavior", "integration"],
            )

    def test_not_current_when_no_lane_has_current_observation(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            empty = truth(path, FP_A)
            record_lane_result(lane_record("behavior", fingerprint=FP_A), path)
            stale_only = truth(path, FP_B)
        self.assertEqual(empty["certification"], "NOT_CURRENT")
        self.assertEqual(
            empty["reason"],
            ["unit_not_observed_on_current", "behavior_not_observed_on_current", "integration_not_observed_on_current"],
        )
        self.assertEqual(stale_only["certification"], "NOT_CURRENT")
        self.assertEqual(
            stale_only["reason"],
            ["unit_not_observed_on_current", "behavior_not_current", "integration_not_observed_on_current"],
        )

    def test_corrupted_line_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            record_lane_result(lane_record("unit"), path)
            with open(str(path), "a", encoding="utf-8") as handle:
                handle.write("{this is not json}\n")
            records = read_lane_records(path)
            result = truth(path, FP_A)
        self.assertEqual(len(records), 1)
        self.assertEqual(result["certification"], "PARTIAL")

    def test_truth_snapshot_written_derived_only(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            records_path = td / "records.jsonl"
            snapshot_path = td / "truth.json"
            for lane in LANE_ORDER:
                record_lane_result(lane_record(lane), records_path)
            write_truth_snapshot(records_path, FP_A, snapshot_path)
            self.assertTrue(snapshot_path.exists())
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["certification"], "FULL")
        self.assertEqual(payload["lanes"]["unit"]["status"], "PASS")
        self.assertEqual(payload["lanes_needing_observation"], [])

    def test_needs_observation_empty_when_no_work_needed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "records.jsonl"
            for lane in LANE_ORDER:
                record_lane_result(lane_record(lane), path)
            self.assertEqual(lanes_needing_observation(path, FP_A), [])
            self.assertEqual(lanes_needing_observation(path, FP_B), ["unit", "behavior", "integration"])


if __name__ == "__main__":
    unittest.main()