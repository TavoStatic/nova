"""Tests for the detached per-lane regression worker (slice 2 decoupling)."""

from __future__ import annotations

import json
import os
import subprocess as _subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.regression_lane_worker as worker
from services.regression_truth_registry import read_lane_records


def _env_for(td: str) -> dict[str, str]:
    return {
        "NOVA_REGRESSION_TRUTHS_PATH": str(Path(td) / "regression" / "regression_truth.jsonl"),
        "NOVA_REGRESSION_STATUS_FILE": str(Path(td) / "regression_status.json"),
        "NOVA_REGRESSION_LOCK_FILE": str(Path(td) / "regression.lock"),
        "NOVA_REGRESSION_MAX_LANE_SECONDS": "720",
        "NOVA_REGRESSION_WORKER_LOG": str(Path(td) / "lane_unit_worker.log"),
    }


class RegressionLaneWorkerTest(unittest.TestCase):
    def test_worker_records_pass_and_publishes_partial_projection(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, _env_for(td)), mock.patch.object(
                worker.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="unit lane OK", stderr=""),
            ):
                code = worker.main(["unit", "fp1"])
            truth_path = Path(td) / "regression" / "regression_truth.jsonl"
            status_path = Path(td) / "regression_status.json"
            records = read_lane_records(truth_path)
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["lane"], "unit")
        self.assertEqual(records[0]["status"], "PASS")
        self.assertEqual(records[0]["source_fingerprint"], "fp1")
        self.assertEqual(payload.get("status"), "PARTIAL")
        self.assertEqual(payload.get("source"), "scheduler:regression_truth_registry")
        self.assertEqual(payload.get("registry_fingerprint"), "fp1")

    def test_worker_records_failed_and_publishes_failed_projection(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, _env_for(td)), mock.patch.object(
                worker.subprocess,
                "run",
                return_value=mock.Mock(returncode=1, stdout="unit lane still failing", stderr=""),
            ):
                code = worker.main(["unit", "fp1"])
            truth_path = Path(td) / "regression" / "regression_truth.jsonl"
            status_path = Path(td) / "regression_status.json"
            records = read_lane_records(truth_path)
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["lane"], "unit")
        self.assertEqual(records[0]["status"], "FAILED")
        self.assertEqual(payload.get("status"), "FAILED")
        self.assertEqual(payload.get("failed_lane"), "unit")
        self.assertEqual(payload.get("certification"), "FAILED")

    def test_worker_records_timeout_as_incomplete_observation(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, _env_for(td)), mock.patch.object(
                worker.subprocess,
                "run",
                side_effect=_subprocess.TimeoutExpired(cmd=["python"], timeout=720),
            ):
                code = worker.main(["unit", "fp1"])
            truth_path = Path(td) / "regression" / "regression_truth.jsonl"
            status_path = Path(td) / "regression_status.json"
            records = read_lane_records(truth_path)
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "TIMED_OUT")
        self.assertEqual(payload.get("status"), "PARTIAL")
        self.assertIn("unit_timed_out_on_current", list(payload.get("reason") or []))

    def test_worker_noops_when_lane_already_running(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, _env_for(td)), mock.patch.object(
                worker.subprocess,
                "run",
                return_value=mock.Mock(
                    returncode=2,
                    stdout="[FAIL] regression already running (pid=999, lanes=unit, started_at=2026-09-08 00:00:00)",
                    stderr="",
                ),
            ):
                code = worker.main(["unit", "fp1"])
            truth_path = Path(td) / "regression" / "regression_truth.jsonl"
            records = read_lane_records(truth_path)
        self.assertEqual(code, 0)
        self.assertEqual(len(records), 0)

    def test_worker_requires_fingerprint(self):
        self.assertEqual(worker.main(["unit"]), 2)


if __name__ == "__main__":
    unittest.main()