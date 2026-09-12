"""End-to-end integration tests for the detached regression lane worker.

These exercise the real process boundaries: autonomy_maintenance spawning the
real worker via subprocess.Popen, the worker spawning its lane runner via
subprocess.run, the truth registry write, and the derived projection publish.
Only the lane runner itself is swapped for a fast stub (NOVA_REGRESSION_RUNNER)
so the suite stays CI-able; every other link is real.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

import autonomy_maintenance
from services.regression_truth_registry import read_lane_records

warnings.filterwarnings(
    "ignore",
    message=r"subprocess \d+ is still running",
    category=ResourceWarning,
)

PY = sys.executable
STUB_PASS = textwrap.dedent(
    """\
    import sys
    print("unit lane OK")
    sys.exit(0)
    """
)
STUB_FAIL = textwrap.dedent(
    """\
    import sys
    print("[FAIL] unit lane (exit=1)")
    sys.exit(1)
    """
)
STUB_SLOW = textwrap.dedent(
    """\
    import time
    time.sleep(8)
    print("finished late")
    """
)
STUB_LOCKED = textwrap.dedent(
    """\
    import sys
    print("[FAIL] regression already running (pid=999, lanes=unit, started_at=now)")
    sys.exit(2)
    """
)


def _write_stub(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def _env_for(td: str, runner: str, *, max_seconds: str = "20") -> dict[str, str]:
    return {
        "NOVA_REGRESSION_TRUTHS_PATH": str(Path(td) / "regression" / "regression_truth.jsonl"),
        "NOVA_REGRESSION_STATUS_FILE": str(Path(td) / "regression_status.json"),
        "NOVA_REGRESSION_LOCK_FILE": str(Path(td) / "regression.lock"),
        "NOVA_REGRESSION_MAX_LANE_SECONDS": max_seconds,
        "NOVA_REGRESSION_WORKER_LOG": str(Path(td) / "lane_unit_worker.log"),
        "NOVA_REGRESSION_RUNNER": runner,
    }


class RegressionLaneWorkerIntegrationTest(unittest.TestCase):
    def test_spawned_worker_runs_stub_run_and_publishes_partial(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            stub = _write_stub(Path(td), "stub_pass.py", STUB_PASS)
            env = dict(os.environ)
            env.update(_env_for(td, str(stub)))
            result = subprocess.run(
                [PY, str(autonomy_maintenance.REGRESSION_LANE_WORKER), "unit", "fp1"],
                cwd=str(autonomy_maintenance.ROOT),
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            records = read_lane_records(Path(td) / "regression" / "regression_truth.jsonl")
            payload = json.loads((Path(td) / "regression_status.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "PASS")
        self.assertEqual(records[0]["lane"], "unit")
        self.assertEqual(records[0]["source_fingerprint"], "fp1")
        self.assertEqual(payload["status"], "PARTIAL")
        self.assertEqual(payload["certification"], "PARTIAL")

    def test_spawned_worker_records_failure_and_publishes_failed_lane(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            stub = _write_stub(Path(td), "stub_fail.py", STUB_FAIL)
            env = dict(os.environ)
            env.update(_env_for(td, str(stub)))
            result = subprocess.run(
                [PY, str(autonomy_maintenance.REGRESSION_LANE_WORKER), "unit", "fp1"],
                cwd=str(autonomy_maintenance.ROOT),
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            records = read_lane_records(Path(td) / "regression" / "regression_truth.jsonl")
            payload = json.loads((Path(td) / "regression_status.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(records[0]["status"], "FAILED")
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["certification"], "FAILED")
        self.assertEqual(payload["failed_lane"], "unit")

    def test_spawned_worker_records_timeout_when_lane_exceeds_budget(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            stub = _write_stub(Path(td), "stub_slow.py", STUB_SLOW)
            env = dict(os.environ)
            env.update(_env_for(td, str(stub), max_seconds="1"))
            result = subprocess.run(
                [PY, str(autonomy_maintenance.REGRESSION_LANE_WORKER), "unit", "fp1"],
                cwd=str(autonomy_maintenance.ROOT),
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            records = read_lane_records(Path(td) / "regression" / "regression_truth.jsonl")
            payload = json.loads((Path(td) / "regression_status.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(records[0]["status"], "TIMED_OUT")
        self.assertEqual(payload["status"], "PARTIAL")
        self.assertIn("unit_timed_out_on_current", payload["reason"])

    def test_spawned_worker_is_noop_when_lane_already_running(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            stub = _write_stub(Path(td), "stub_locked.py", STUB_LOCKED)
            env = dict(os.environ)
            env.update(_env_for(td, str(stub)))
            result = subprocess.run(
                [PY, str(autonomy_maintenance.REGRESSION_LANE_WORKER), "unit", "fp1"],
                cwd=str(autonomy_maintenance.ROOT),
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            records = read_lane_records(Path(td) / "regression" / "regression_truth.jsonl")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(records, [])

    def test_maintenance_spawn_chain_completes_end_to_end(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            stub = _write_stub(Path(td), "stub_pass.py", STUB_PASS)
            truths_path = Path(td) / "regression" / "regression_truth.jsonl"
            status_path = Path(td) / "regression_status.json"
            state: dict = {}
            with mock.patch.dict(
                os.environ,
                {"NOVA_REGRESSION_RUNNER": str(stub)},
            ), mock.patch.object(
                autonomy_maintenance, "REGRESSION_TRUTHS_PATH", truths_path
            ), mock.patch.object(
                autonomy_maintenance, "REGRESSION_STATUS_FILE", status_path
            ), mock.patch.object(
                autonomy_maintenance, "RUNTIME_DIR", Path(td)
            ), mock.patch.object(
                autonomy_maintenance, "_host_regression_status_file_fresh", return_value=False
            ):
                result = autonomy_maintenance._run_daily_regression_if_due(state)
                worker_pid = int(state.get("last_regression_worker_pid") or 0)
                try:
                    deadline = time.time() + 90
                    while time.time() < deadline:
                        if truths_path.exists() and read_lane_records(truths_path):
                            break
                        time.sleep(0.5)
                    else:
                        self.fail("worker never wrote registry evidence")
                finally:
                    if worker_pid:
                        try:
                            os.kill(worker_pid, 9)
                        except OSError:
                            pass
            records = read_lane_records(truths_path)
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(result, "daily_regression_lane_started")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "PASS")
        self.assertEqual(payload["status"], "PARTIAL")
        self.assertEqual(state["last_regression_status"], "NOT_CURRENT")
        self.assertEqual(autonomy_maintenance._active_regression_worker_count(), 0)


if __name__ == "__main__":
    unittest.main()
