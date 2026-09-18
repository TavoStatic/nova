import tempfile
import unittest
from pathlib import Path

from services.regression_status_projection import project_canonical_status
from services.regression_truth_registry import LANE_ORDER, record_lane_result

FP_A = "a" * 64
FP_B = "b" * 64


def lane_record(lane: str, fingerprint: str = FP_A, status: str = "PASS", failures: int = 0) -> dict:
    return {
        "lane": lane,
        "source_fingerprint": fingerprint,
        "status": status,
        "started_at": "2026-09-08 09:00:00",
        "finished_at": "2026-09-08 09:40:00",
        "duration_sec": 2400,
        "tests": 83,
        "failures": failures,
        "artifact_log_ref": "",
    }


class TestRegressionStatusProjection(unittest.TestCase):
    def _records(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name) / "records.jsonl"

    def test_full_projects_ok_with_canonical_lanes(self):
        path = self._records()
        payload = project_canonical_status(path, FP_A, generated_at="2026-09-08 12:00:00")
        for lane in LANE_ORDER:
            record_lane_result(lane_record(lane), path)
        payload = project_canonical_status(path, FP_A, generated_at="2026-09-08 12:00:00")
        self.assertEqual(payload["status"], "OK")
        self.assertEqual(payload["returncode"], 0)
        self.assertEqual(payload["lanes"], list(LANE_ORDER))
        self.assertEqual(payload["failed_lane"], "")
        self.assertEqual(payload["detail"], "")
        self.assertEqual(payload["certification"], "FULL")
        self.assertEqual(payload["source"], "scheduler:regression_truth_registry")

    def test_failed_lane_projects_failed_with_failed_lane(self):
        path = self._records()
        record_lane_result(lane_record("unit", status="FAILED", failures=2), path)
        for lane in ("behavior", "integration"):
            record_lane_result(lane_record(lane), path)
        payload = project_canonical_status(path, FP_A, generated_at="2026-09-08 12:00:00")
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["returncode"], 1)
        self.assertEqual(payload["failed_lane"], "unit")
        self.assertIn("unit_failed_on_current", payload["detail"])

    def test_timed_out_lane_projects_partial_not_failed(self):
        path = self._records()
        record_lane_result(lane_record("unit"), path)
        record_lane_result(lane_record("behavior", status="TIMED_OUT"), path)
        payload = project_canonical_status(path, FP_A)
        self.assertEqual(payload["status"], "PARTIAL")
        self.assertEqual(payload["returncode"], 1)
        self.assertEqual(payload["failed_lane"], "")
        self.assertIn("behavior_timed_out_on_current", payload["detail"])

    def test_partial_projects_partial_with_reasons(self):
        path = self._records()
        record_lane_result(lane_record("unit"), path)
        payload = project_canonical_status(path, FP_A)
        self.assertEqual(payload["status"], "PARTIAL")
        self.assertIn("behavior_not_observed_on_current", payload["detail"])
        self.assertEqual(payload["certification"], "PARTIAL")

    def test_empty_projects_not_current(self):
        path = self._records()
        payload = project_canonical_status(path, FP_A)
        self.assertEqual(payload["status"], "NOT_CURRENT")
        self.assertEqual(payload["returncode"], 1)
        self.assertEqual(payload["certification"], "NOT_CURRENT")

    def test_stale_fingerprint_projects_not_current(self):
        path = self._records()
        for lane in LANE_ORDER:
            record_lane_result(lane_record(lane, fingerprint=FP_B), path)
        payload = project_canonical_status(path, FP_A)
        self.assertEqual(payload["status"], "NOT_CURRENT")
        self.assertEqual(payload["registry_fingerprint"], FP_A)

    def test_projection_keeps_reason_and_fingerprint_keys(self):
        path = self._records()
        record_lane_result(lane_record("unit"), path)
        payload = project_canonical_status(path, FP_A)
        self.assertEqual(payload["registry_fingerprint"], FP_A)
        self.assertEqual(payload["reason"], ["behavior_not_observed_on_current", "integration_not_observed_on_current"])


if __name__ == "__main__":
    unittest.main()