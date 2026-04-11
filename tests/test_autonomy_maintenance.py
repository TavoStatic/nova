import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import autonomy_maintenance


class TestAutonomyMaintenance(unittest.TestCase):
    def test_run_once_records_generated_queue_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            latest_path = runtime_dir / "subconscious_runs" / "latest.json"
            latest_path.parent.mkdir(parents=True, exist_ok=True)
            latest_path.write_text(
                json.dumps({"generated_at": "2026-04-04 02:00:00", "families": []}, ensure_ascii=True),
                encoding="utf-8",
            )
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"

            with mock.patch.object(autonomy_maintenance, "LATEST_SUBCONSCIOUS", latest_path), \
                 mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path), \
                 mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path), \
                 mock.patch.object(autonomy_maintenance, "_run_subconscious_pack", return_value=(True, "ok")), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_run_next_generated_work_queue_item",
                     return_value=(
                         True,
                         "generated_work_queue_next_ok:demo.json",
                         {
                             "selected": {"file": "demo.json", "latest_status": "never_run"},
                             "latest_report": {"status": "warning", "run_id": "demo_run"},
                             "work_queue": {"open_count": 3, "count": 5},
                         },
                     ),
                 ), \
                 mock.patch.object(
                     autonomy_maintenance.kidney,
                     "run_kidney",
                     return_value={
                         "ts": "2026-04-04 02:00:01",
                         "mode": "enforce",
                         "candidate_count": 2,
                         "archive_count": 1,
                         "delete_count": 1,
                         "snapshot_path": "snapshot.zip",
                     },
                 ), \
                 mock.patch.object(autonomy_maintenance, "_run_daily_regression_if_due", return_value="daily_regression_ok"):
                code = autonomy_maintenance.run_once()

            self.assertEqual(code, 0)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            queue_run = dict(state.get("last_generated_queue_run") or {})
            self.assertEqual(queue_run.get("status"), "ok")
            self.assertEqual(queue_run.get("selected_file"), "demo.json")
            self.assertEqual(queue_run.get("latest_report_status"), "warning")
            self.assertEqual(queue_run.get("latest_report_run_id"), "demo_run")
            self.assertEqual(queue_run.get("queue_open_count"), 3)
            self.assertEqual(queue_run.get("queue_count"), 5)

    def test_run_worker_loops_for_bounded_cycles_and_records_status(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"
            cycles = []
            sleeps = []

            with mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path), \
                 mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path):
                code = autonomy_maintenance.run_worker(
                    interval_sec=7,
                    max_cycles=2,
                    run_once_fn=lambda: cycles.append("cycle") or 0,
                    sleep_fn=lambda seconds: sleeps.append(seconds),
                )

            self.assertEqual(code, 0)
            self.assertEqual(len(cycles), 2)
            self.assertEqual(sleeps, [7.0])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            worker = dict(state.get("runtime_worker") or {})
            self.assertEqual(worker.get("interval_sec"), 7)
            self.assertEqual(worker.get("last_cycle"), 2)
            self.assertEqual(worker.get("cycle_count"), 2)
            self.assertEqual(worker.get("last_cycle_status"), "ok")
            self.assertEqual(worker.get("last_cycle_code"), 0)


if __name__ == "__main__":
    unittest.main()