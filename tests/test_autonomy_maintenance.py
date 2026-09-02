import json
import os
import tempfile
import time
import unittest
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from unittest import mock
import uuid

import autonomy_maintenance
import work_tree
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE


def _validation_tmp_root() -> Path:
    return Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "_test_tmp"


class TestAutonomyMaintenance(unittest.TestCase):
    def _isolated_work_tree_db(self):
        original_path = Path(work_tree._DB_REQUESTED_PATH)
        original_connect_target = work_tree._DB_CONNECT_TARGET
        original_connect_use_uri = work_tree._DB_CONNECT_USE_URI
        original_guard_log = work_tree._DB_GUARD_LOG
        original_access_log = work_tree._DB_ACCESS_LOG
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        db_path = base_tmp / f"autonomy_maintenance_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(db_path)

        def _cleanup() -> None:
            try:
                # Restore path globals directly -- avoids opening the production DB
                # (which may be inaccessible when Nova is running on the host OS).
                work_tree._DB_REQUESTED_PATH = original_path
                work_tree._DB_PATH = original_path
                work_tree._DB_CONNECT_TARGET = original_connect_target
                work_tree._DB_CONNECT_USE_URI = original_connect_use_uri
                work_tree._DB_GUARD_LOG = original_guard_log
                work_tree._DB_ACCESS_LOG = original_access_log
                work_tree._TREES.clear()
                work_tree._BRANCHES.clear()
                work_tree._TASKS.clear()
            finally:
                for candidate in (
                    db_path,
                    db_path.with_name(f"{db_path.name}-journal"),
                    db_path.with_suffix(f"{db_path.suffix}-wal"),
                    db_path.with_suffix(f"{db_path.suffix}-shm"),
                ):
                    try:
                        if candidate.exists():
                            candidate.unlink()
                    except Exception:
                        pass

        self.addCleanup(_cleanup)
        return db_path

    def _patch_signal_intake_external_signals(self):
        """Keep signal-intake unit tests from ingesting live release/maturity side signals."""
        return (
            mock.patch.object(
                autonomy_maintenance,
                "_apply_release_runtime_truth_to_status_payload",
                side_effect=lambda payload, state=None: dict(payload or {}),
            ),
            mock.patch.object(
                autonomy_maintenance,
                "_apply_layer_maturity_to_status_payload",
                side_effect=lambda payload: dict(payload or {}),
            ),
        )

    def test_apply_storage_watch_stamps_ingest_surface_keys(self):
        payload = autonomy_maintenance._apply_storage_watch_to_status_payload(
            {},
            {
                "status": "ok",
                "note": "watched storage is within normal limits",
                "total_bytes": 12,
                "runtime_total_bytes": 12,
                "runtime_file_count": 3,
                "release_validation_extract_bytes": 0,
            },
        )
        self.assertEqual(payload.get("storage_watch_status"), "ok")
        self.assertEqual(payload.get("storage_watch_note"), "watched storage is within normal limits")
        self.assertEqual(int(payload.get("storage_watch_total_bytes") or 0), 12)

    def test_queue_pressure_uses_open_count_zero_as_clear_truth(self):
        payload = autonomy_maintenance._queue_pressure_for_orchestrator(
            {
                "status": "clear",
                "count": 2,
                "open_count": 0,
                "actionable_count": 0,
                "blocked_count": 0,
            },
            {},
        )

        self.assertEqual(payload.get("generated_pending_count"), 0)
        self.assertEqual(payload.get("pending_count"), 0)
        self.assertEqual(payload.get("high_priority_count"), 0)
        self.assertEqual(payload.get("pressure_band"), "low")

    def test_queue_pressure_falls_back_to_count_only_when_open_count_missing(self):
        payload = autonomy_maintenance._queue_pressure_for_orchestrator(
            {
                "status": "ready",
                "count": 2,
                "actionable_count": 0,
                "blocked_count": 0,
            },
            {},
        )

        self.assertEqual(payload.get("generated_pending_count"), 2)
        self.assertEqual(payload.get("pending_count"), 2)
        self.assertEqual(payload.get("pressure_band"), "medium")

    def test_queue_pressure_clear_status_without_open_count_does_not_invent_pending_work(self):
        payload = autonomy_maintenance._queue_pressure_for_orchestrator(
            {
                "status": "clear",
                "count": 2,
                "actionable_count": 0,
                "blocked_count": 0,
            },
            {},
        )

        self.assertEqual(payload.get("generated_pending_count"), 0)
        self.assertEqual(payload.get("pending_count"), 0)
        self.assertEqual(payload.get("pressure_band"), "low")

    def test_sync_regression_status_from_file_uses_newer_canonical_status(self):
        with tempfile.TemporaryDirectory() as td:
            status_path = Path(td) / "regression_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-05-13 16:30:56",
                        "date": "2026-05-13",
                        "status": "OK",
                        "lanes": ["integration"],
                        "returncode": 0,
                        "source": "scripts/run_regression.py",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            state = {
                "last_regression_at": "2026-05-13 13:46:51",
                "last_regression_status": "FAILED",
                "last_regression_stale": True,
            }

            synced = autonomy_maintenance._sync_regression_status_from_file(state, status_path=status_path)

        self.assertTrue(synced)
        self.assertEqual(state.get("last_regression_status"), "OK")
        self.assertFalse(state.get("last_regression_stale"))
        self.assertEqual(state.get("last_regression_lanes"), ["integration"])
        self.assertEqual(state.get("last_regression_source"), "scripts/run_regression.py")

    def test_sync_regression_status_from_file_supersedes_same_day_unit_failure_with_all_pass(self):
        today = time.strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as td:
            status_path = Path(td) / "regression_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "generated_at": f"{today} 10:32:42",
                        "date": today,
                        "status": "OK",
                        "lanes": ["unit", "behavior", "integration"],
                        "returncode": 0,
                        "source": "scripts/run_regression.py",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            state = {
                "last_regression_date": today,
                "last_regression_at": f"{today} 00:03:32",
                "last_regression_status": "FAILED",
                "last_regression_stale": False,
                "last_regression_failed_lane": "unit",
                "last_regression_failed_tests": ["tests.test_example.TestCase.test_interrupted"],
            }

            synced = autonomy_maintenance._sync_regression_status_from_file(state, status_path=status_path)

        self.assertTrue(synced)
        self.assertEqual(state.get("last_regression_status"), "OK")
        self.assertFalse(state.get("last_regression_stale"))
        self.assertEqual(state.get("last_regression_lanes"), ["unit", "behavior", "integration"])
        self.assertEqual(state.get("last_regression_failed_lane"), "")
        self.assertEqual(state.get("last_regression_failed_tests"), [])

    def test_solution_ladder_learning_runs_when_due_and_skips_cadence(self):
        """Gap 1: learn_families_from_history must have a live maintenance owner."""
        state: dict = {}
        with mock.patch(
            "services.work_tree_task_progress.learn_families_from_history",
            return_value={
                "ok": True,
                "family_count": 2,
                "path": "runtime/work_tree/solution_ladders_learned.json",
                "seeded_count": 8,
                "families": {},
            },
        ) as learn_mock:
            first = autonomy_maintenance._run_solution_ladder_learning_if_due(state)
            second = autonomy_maintenance._run_solution_ladder_learning_if_due(state)

        self.assertEqual(learn_mock.call_count, 1)
        self.assertEqual(first.get("status"), "ok")
        self.assertEqual(first.get("family_count"), 2)
        self.assertTrue(str(first.get("path") or "").endswith("solution_ladders_learned.json"))
        self.assertEqual(second.get("status"), "skipped_cadence")
        self.assertEqual((state.get("last_solution_ladder_learning") or {}).get("status"), "skipped_cadence")

    def test_daily_regression_uses_canonical_regression_runner(self):
        with tempfile.TemporaryDirectory() as td:
            status_path = Path(td) / "regression_status.json"
            state = {
                "last_regression_date": "2026-05-13",
                "last_regression_at": "2026-05-13 13:46:51",
                "last_regression_status": "FAILED",
                "last_regression_stale": True,
            }

            def _run_regression(cmd, **_kwargs):
                status_path.write_text(
                    json.dumps(
                        {
                            "generated_at": "2026-05-14 10:00:00",
                            "date": "2026-05-14",
                            "status": "OK",
                            "lanes": ["unit", "behavior", "integration"],
                            "returncode": 0,
                            "source": "scripts/run_regression.py",
                        },
                        ensure_ascii=True,
                    ),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="All selected regression checks passed.", stderr="")

            with mock.patch.object(autonomy_maintenance, "REGRESSION_STATUS_FILE", status_path), \
                 mock.patch.object(autonomy_maintenance.subprocess, "run", side_effect=_run_regression) as run_mock:
                result = autonomy_maintenance._run_daily_regression_if_due(state)

        command = list(run_mock.call_args.args[0])
        self.assertEqual(result, "daily_regression_ok")
        self.assertIn(str(autonomy_maintenance.REGRESSION_RUNNER), command)
        self.assertEqual(command[-1], "all")
        self.assertNotIn("unittest", command)
        self.assertEqual(state.get("last_regression_status"), "OK")
        self.assertFalse(state.get("last_regression_stale"))
        self.assertEqual(state.get("last_regression_lanes"), ["unit", "behavior", "integration"])
        self.assertEqual(state.get("last_regression_source"), "scripts/run_regression.py")

    def test_daily_regression_reruns_when_status_file_stale_even_if_date_is_today(self):
        import time as _time

        with tempfile.TemporaryDirectory() as td:
            status_path = Path(td) / "regression_status.json"
            # OK but older than release max age (6h) — must not skip forever.
            stale_generated = _time.strftime(
                "%Y-%m-%d %H:%M:%S",
                _time.localtime(_time.time() - 40000),
            )
            status_path.write_text(
                json.dumps(
                    {
                        "generated_at": stale_generated,
                        "status": "OK",
                        "lanes": ["unit", "behavior", "integration"],
                        "returncode": 0,
                        "source": "scripts/run_regression.py",
                    }
                ),
                encoding="utf-8",
            )
            today = _time.strftime("%Y-%m-%d")
            state = {
                "last_regression_date": today,
                "last_regression_at": stale_generated,
                "last_regression_status": "OK",
                "last_regression_stale": False,
            }

            def _run_regression(cmd, **_kwargs):
                status_path.write_text(
                    json.dumps(
                        {
                            "generated_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
                            "date": today,
                            "status": "OK",
                            "lanes": ["unit", "behavior", "integration"],
                            "returncode": 0,
                            "source": "scripts/run_regression.py",
                        }
                    ),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="ok", stderr="")

            with mock.patch.object(autonomy_maintenance, "REGRESSION_STATUS_FILE", status_path), \
                 mock.patch.object(autonomy_maintenance.subprocess, "run", side_effect=_run_regression) as run_mock, \
                 mock.patch.object(autonomy_maintenance, "_regression_lock_owner_alive", return_value=(False, "")):
                result = autonomy_maintenance._run_daily_regression_if_due(state)

        self.assertEqual(result, "daily_regression_ok")
        self.assertEqual(run_mock.call_count, 1)
        self.assertEqual(state.get("last_regression_status"), "OK")
        self.assertLessEqual(int(run_mock.call_args.kwargs.get("timeout") or 0), 15 * 60)

    def test_daily_regression_skips_retry_after_failed_attempt_today(self):
        import time as _time

        today = _time.strftime("%Y-%m-%d")
        state = {
            "last_regression_date": today,
            "last_regression_status": "FAILED",
            "last_regression_stale": True,
        }
        with mock.patch.object(autonomy_maintenance, "_host_regression_status_file_fresh", return_value=False), \
             mock.patch.object(autonomy_maintenance.subprocess, "run") as run_mock:
            result = autonomy_maintenance._run_daily_regression_if_due(state)
        self.assertEqual(result, "daily_regression_skipped_already_attempted")
        run_mock.assert_not_called()

    def test_daily_regression_records_timeout_without_hanging_the_cycle(self):
        import subprocess as _subprocess
        import time as _time

        today = _time.strftime("%Y-%m-%d")
        state = {"last_regression_date": "2026-05-13", "last_regression_status": "FAILED"}
        with tempfile.TemporaryDirectory() as td:
            status_path = Path(td) / "regression_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-08-01 00:09:41",
                        "status": "OK",
                        "lanes": ["unit", "behavior", "integration"],
                        "returncode": 0,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                autonomy_maintenance.subprocess,
                "run",
                side_effect=_subprocess.TimeoutExpired(cmd=["python"], timeout=720),
            ), mock.patch.object(autonomy_maintenance, "_append_log"), mock.patch.object(
                autonomy_maintenance, "REGRESSION_STATUS_FILE", status_path
            ), mock.patch.object(
                autonomy_maintenance, "_regression_lock_owner_alive", return_value=(False, "")
            ):
                result = autonomy_maintenance._run_daily_regression_if_due(state)
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(result, "daily_regression_timed_out")
        self.assertEqual(state.get("last_regression_status"), "TIMED_OUT")
        self.assertEqual(state.get("last_regression_date"), today)
        self.assertEqual(payload.get("status"), "TIMED_OUT")
        self.assertEqual(payload.get("generated_at"), state.get("last_regression_at"))

    def test_regression_lock_owner_alive_uses_pid_exists_not_signal_zero(self):
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "regression.lock"
            lock_path.write_text(
                json.dumps({"pid": 4242, "lanes": ["unit"], "started_at": "2026-08-16 01:00:00"}),
                encoding="utf-8",
            )
            with mock.patch.object(autonomy_maintenance, "RUNTIME_DIR", Path(td)), \
                 mock.patch("os.kill", side_effect=OSError(87, "The parameter is incorrect")) as kill_mock, \
                 mock.patch("psutil.pid_exists", return_value=False) as exists_mock:
                alive, detail = autonomy_maintenance._regression_lock_owner_alive()
            self.assertFalse(lock_path.exists())

        self.assertFalse(alive)
        self.assertEqual(detail, "")
        exists_mock.assert_called_once_with(4242)
        kill_mock.assert_not_called()

    def test_run_temporal_feed_pass_reads_ics_and_surfaces_pressure(self):
        state: dict = {}
        with tempfile.TemporaryDirectory() as td:
            ics_path = Path(td) / "calendar.ics"
            ics_path.write_text(
                "\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "SUMMARY:state education data deadline",
                        "DTSTART:20260610T090000Z",
                        "STATUS:CONFIRMED",
                        "END:VEVENT",
                        "END:VCALENDAR",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                autonomy_maintenance,
                "_temporal_policy_settings",
                return_value={
                    "enabled": True,
                    "ics_paths": [str(ics_path)],
                    "poll_interval_sec": 900,
                    "surface_min_score": 0.0,
                    "max_surface_events": 8,
                },
            ):
                payload = autonomy_maintenance._run_temporal_feed_pass(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(int(payload.get("event_count", 0) or 0), 1)
        self.assertGreaterEqual(int(payload.get("surfaced_count", 0) or 0), 1)
        self.assertTrue(isinstance(state.get("last_temporal_feed"), dict))

    def test_sync_signal_intake_work_tree_includes_temporal_feed_payload(self):
        captured: dict = {}

        def _capture_status_payload(status_payload, **kwargs):
            captured.update(dict(status_payload or {}))
            return []

        state = {
            "last_regression_status": "OK",
            "last_regression_stale": False,
        }
        temporal_feed = {
            "enabled": True,
            "status": "ok",
            "ran_at": "2026-06-06 12:00:00",
            "source_count": 1,
            "event_count": 1,
            "surfaced_count": 1,
            "error_count": 0,
            "surfaced_pressures": [
                {
                    "event": {
                        "title": "state education data deadline",
                        "start": "2026-06-10T09:00:00+00:00",
                    },
                    "final_score": 88.0,
                    "output_path": "work_tree",
                }
            ],
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value={}), \
             mock.patch.object(autonomy_maintenance.nova_core, "mem_enabled", return_value=True), \
             mock.patch.object(autonomy_maintenance, "_validation_artifact_truth_payload_for_signal_ingestion", return_value={}), \
             mock.patch.object(autonomy_maintenance, "_live_control_status_payload_for_signal_ingestion", side_effect=lambda payload: payload), \
             mock.patch.object(autonomy_maintenance, "_generated_work_queue", return_value={}), \
             mock.patch.object(autonomy_maintenance, "_latest_subconscious_report_for_triage", return_value={}), \
             mock.patch.object(autonomy_maintenance, "_subconscious_triage_signals_for_work_tree", return_value=[]), \
             mock.patch.object(autonomy_maintenance.WORK_TREE_SIGNAL_INGESTION_SERVICE, "sync_status_snapshot", side_effect=_capture_status_payload):
            autonomy_maintenance._sync_signal_intake_work_tree(state, temporal_feed=temporal_feed)

        self.assertTrue(bool(captured.get("temporal_enabled")))
        self.assertEqual(int(captured.get("temporal_feed_surfaced_count", 0) or 0), 1)
        self.assertEqual(len(list(captured.get("temporal_pressure") or [])), 1)

    def test_subconscious_pack_timeout_uses_positive_timeout_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "maintenance.log"

            def _timeout(*_args, **_kwargs):
                raise autonomy_maintenance.subprocess.TimeoutExpired(
                    cmd=["subconscious_runner.py"],
                    timeout=-19,
                    output="partial stdout",
                    stderr="partial stderr",
                )

            with mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path), \
                 mock.patch.object(autonomy_maintenance.subprocess, "run", side_effect=_timeout), \
                 mock.patch.object(autonomy_maintenance.time, "monotonic", side_effect=[100.0, 105.25]):
                ok, output = autonomy_maintenance._run_subconscious_pack()

            self.assertFalse(ok)
            self.assertIn("timed out after 900 seconds", output)
            self.assertIn("elapsed_sec=5.25", output)
            self.assertNotIn("-19", output)
            self.assertIn("partial stdout", output)
            self.assertIn("partial stderr", output)
            self.assertIn("subconscious_pack_duration_sec=5.25 status=timeout timeout_sec=900", log_path.read_text(encoding="utf-8"))

    def test_sync_pipeline_workers_skipped_in_validation_scope(self):
        state: dict = {}
        classified = {"enabled": ["data_connector"], "paused": [], "discovered": ["data_connector"]}
        with mock.patch.object(autonomy_maintenance, "classify_pipeline_ids_for_workers", return_value=classified), \
             mock.patch.object(autonomy_maintenance, "runtime_pipeline_worker_ids", return_value=[]), \
             mock.patch.object(autonomy_maintenance, "reconcile_pipeline_workers_for_ids") as reconcile_mock, \
             mock.patch.object(autonomy_maintenance, "stop_pipeline_workers_for_ids") as stop_mock, \
             mock.patch.object(autonomy_maintenance, "ensure_pipeline_workers_for_ids") as ensure_mock, \
             mock.patch.object(autonomy_maintenance, "runtime_scope_name", return_value="validation"):
            autonomy_maintenance._sync_pipeline_workers_for_maintenance(state)

        reconcile_mock.assert_not_called()
        stop_mock.assert_not_called()
        ensure_mock.assert_not_called()
        skipped = dict(state.get("last_pipeline_worker_ensure") or {})
        self.assertEqual(skipped.get("status"), "skipped_validation_scope")
        self.assertEqual(skipped.get("reason"), "pipeline_workers_disabled_in_validation_scope")
        self.assertEqual(skipped.get("runtime_scope"), "validation")
        self.assertEqual(int(skipped.get("pipeline_count", 0) or 0), 1)
        self.assertEqual((state.get("last_pipeline_worker_reconcile") or {}).get("status"), "skipped_validation_scope")
        self.assertEqual((state.get("last_pipeline_worker_stop") or {}).get("status"), "skipped_validation_scope")

    def test_sync_pipeline_workers_runs_reconcile_and_ensure_in_live_scope(self):
        state: dict = {}
        classified = {"enabled": ["data_connector"], "paused": [], "discovered": ["data_connector"]}
        reconcile_payload = {"status": "ok", "reclaimed_count": 0, "cleared_count": 0}
        ensure_payload = {"status": "ok", "running_count": 1, "started_count": 0, "failed_count": 0}
        with mock.patch.object(autonomy_maintenance, "classify_pipeline_ids_for_workers", return_value=classified), \
             mock.patch.object(autonomy_maintenance, "runtime_pipeline_worker_ids", return_value=[]), \
             mock.patch.object(autonomy_maintenance, "runtime_scope_name", return_value="live"), \
             mock.patch.object(autonomy_maintenance, "reconcile_pipeline_workers_for_ids", return_value=reconcile_payload) as reconcile_mock, \
             mock.patch.object(autonomy_maintenance, "stop_pipeline_workers_for_ids", return_value={"status": "absent"}) as stop_mock, \
             mock.patch.object(autonomy_maintenance, "ensure_pipeline_workers_for_ids", return_value=ensure_payload) as ensure_mock:
            autonomy_maintenance._sync_pipeline_workers_for_maintenance(state)

        reconcile_mock.assert_called_once()
        stop_mock.assert_called_once_with([], runtime_root=autonomy_maintenance.RUNTIME_DIR, os_name=mock.ANY)
        ensure_mock.assert_called_once()
        self.assertEqual(ensure_mock.call_args.args[0], ["data_connector"])
        self.assertEqual((state.get("last_pipeline_worker_reconcile") or {}).get("status"), "ok")
        self.assertEqual((state.get("last_pipeline_worker_ensure") or {}).get("running_count"), 1)

    def test_sync_pipeline_workers_stops_paused_and_leftover_without_ensuring_them(self):
        state: dict = {}
        classified = {
            "enabled": ["live_lane"],
            "paused": ["paused_lane"],
            "discovered": ["live_lane", "paused_lane"],
        }
        with mock.patch.object(autonomy_maintenance, "classify_pipeline_ids_for_workers", return_value=classified), \
             mock.patch.object(autonomy_maintenance, "runtime_pipeline_worker_ids", return_value=["paused_lane", "ghost"]), \
             mock.patch.object(autonomy_maintenance, "runtime_scope_name", return_value="live"), \
             mock.patch.object(autonomy_maintenance, "reconcile_pipeline_workers_for_ids", return_value={"status": "ok"}) as reconcile_mock, \
             mock.patch.object(autonomy_maintenance, "stop_pipeline_workers_for_ids", return_value={"status": "stopped", "stopped_count": 2}) as stop_mock, \
             mock.patch.object(autonomy_maintenance, "ensure_pipeline_workers_for_ids", return_value={"status": "ok"}) as ensure_mock:
            autonomy_maintenance._sync_pipeline_workers_for_maintenance(state)

        self.assertEqual(sorted(reconcile_mock.call_args.args[0]), ["ghost", "live_lane", "paused_lane"])
        self.assertEqual(sorted(stop_mock.call_args.args[0]), ["ghost", "paused_lane"])
        self.assertEqual(ensure_mock.call_args.args[0], ["live_lane"])
        self.assertEqual((state.get("last_pipeline_worker_stop") or {}).get("status"), "stopped")

    def test_sanitize_uninstalled_backpack_residue_skipped_in_validation_scope(self):
        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "runtime_scope_name", return_value="validation"):
            payload = autonomy_maintenance._sanitize_uninstalled_backpack_residue(state)
        self.assertEqual(payload.get("status"), "skipped_validation_scope")
        self.assertEqual(int(payload.get("sanitized_count") or 0), 0)
        self.assertEqual((state.get("last_backpack_residue_sanitize") or {}).get("status"), "skipped_validation_scope")

    def test_sanitize_uninstalled_backpack_residue_runs_when_not_installed(self):
        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "runtime_scope_name", return_value="live"), \
             mock.patch.object(autonomy_maintenance, "_discover_backpack_ids", return_value=["edfi"]), \
             mock.patch(
                 "services.backpack_host.install_state.backpack_runtime_installed",
                 return_value=False,
             ), \
             mock.patch(
                 "services.backpack_host.sanitize.scan_backpack_residue",
                 return_value={"residue": True, "found": ["runtime/edfi"]},
             ), \
             mock.patch(
                 "services.backpack_host.sanitize.sanitize_uninstalled_backpack",
                 return_value={"ok": True, "backpack_id": "edfi"},
             ) as sanitize_mock:
            payload = autonomy_maintenance._sanitize_uninstalled_backpack_residue(state)
        sanitize_mock.assert_called_once()
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(int(payload.get("sanitized_count", 0) or 0), 1)
        self.assertEqual(payload.get("backpack_ids"), ["edfi"])

    def test_backpack_residue_sanitize_step_records_failure(self):
        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "_append_log") as log_mock, \
             mock.patch.object(autonomy_maintenance, "_patch_queue_timestamp", return_value="ts"), \
             mock.patch.object(
                 autonomy_maintenance,
                 "_sanitize_uninstalled_backpack_residue",
                 side_effect=RuntimeError("disk gone"),
             ):
            payload = autonomy_maintenance._run_backpack_residue_sanitize_step(state)
        self.assertEqual(payload.get("status"), "failed")
        self.assertFalse(payload.get("ok"))
        self.assertIn("disk gone", str(payload.get("error") or ""))
        self.assertEqual((state.get("last_backpack_residue_sanitize") or {}).get("status"), "failed")
        log_mock.assert_called()

    def test_run_once_logs_cycle_duration_on_subconscious_failure(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            log_path = Path(td) / "maintenance.log"

            with mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path), \
                 mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path), \
                 mock.patch.object(autonomy_maintenance, "_run_subconscious_pack", return_value=(False, "subconscious boom")), \
                 mock.patch.object(autonomy_maintenance.time, "monotonic", side_effect=[10.0, 12.5]):
                code = autonomy_maintenance.run_once()

            self.assertEqual(code, 1)
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("subconscious boom", log_text)
            self.assertIn("cycle_complete cycle_elapsed_sec=2.5 code=1 reason=subconscious_pack_failed", log_text)

    def test_archive_stale_complete_trees_keeps_recent_history_visible(self):
        self._isolated_work_tree_db()
        now = work_tree._now()
        created_ids = []
        for idx in range(4):
            tree = work_tree.initialize_tree(
                f"Cli: stale {idx}",
                meta={"kind": "system", "source": "cli"},
            )
            work_tree._refresh_tree_state(tree.tree_id, persist=True)
            tree.updated_at = now - timedelta(hours=idx + 1)
            work_tree.save_tree(tree)
            work_tree._persist_tree_state(tree.tree_id)
            created_ids.append(tree.tree_id)

        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "COMPLETE_TREE_VISIBLE_KEEP", 2), \
             mock.patch.object(autonomy_maintenance, "COMPLETE_TREE_ARCHIVE_MIN_AGE_SEC", 0):
            payload = autonomy_maintenance._archive_stale_complete_trees(state)

        self.assertEqual(payload.get("archived_count"), 2)
        self.assertEqual(payload.get("retained_count"), 2)
        retained_ids = set(created_ids[:2])
        archived_ids = set(created_ids[2:])
        visible_ids = {item.get("tree_id") for item in work_tree.list_visual_trees(limit=None)}
        self.assertTrue(retained_ids.issubset(visible_ids))
        self.assertTrue(archived_ids.isdisjoint(visible_ids))
        for tree_id in archived_ids:
            self.assertEqual(work_tree.get_tree(tree_id).status, work_tree.TreeStatus.ARCHIVED)

    def test_archive_empty_active_trees_archives_only_old_root_shells(self):
        self._isolated_work_tree_db()
        now = work_tree._now()
        old_empty = work_tree.initialize_tree("Cli: empty old")
        old_empty.updated_at = now - timedelta(hours=2)
        work_tree.save_tree(old_empty)
        work_tree._persist_tree_state(old_empty.tree_id)

        old_with_task = work_tree.initialize_tree("Cli: task old")
        old_with_task.updated_at = now - timedelta(hours=2)
        work_tree.add_task_to_branch(old_with_task.root_branch_id, "Keep this task")
        work_tree.save_tree(old_with_task)
        work_tree._persist_tree_state(old_with_task.tree_id)

        recent_empty = work_tree.initialize_tree("Cli: empty recent")
        recent_empty.updated_at = now
        work_tree.save_tree(recent_empty)
        work_tree._persist_tree_state(recent_empty.tree_id)

        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "EMPTY_ACTIVE_TREE_ARCHIVE_MIN_AGE_SEC", 3600):
            payload = autonomy_maintenance._archive_empty_active_trees(state)

        self.assertEqual(payload.get("archived_count"), 1)
        self.assertEqual(payload.get("skipped_recent_count"), 1)
        self.assertEqual(work_tree.get_tree(old_empty.tree_id).status, work_tree.TreeStatus.ARCHIVED)
        self.assertEqual(work_tree.get_tree(old_with_task.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertEqual(work_tree.get_tree(recent_empty.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertEqual((state.get("last_empty_active_tree_archive") or {}).get("archived_count"), 1)

    def test_archive_stale_cli_active_trees_archives_only_simple_prompt_shells(self):
        self._isolated_work_tree_db()
        now = work_tree._now()

        stale_cli = work_tree.initialize_tree(
            "Cli: stale prompt",
            meta={"kind": "system", "source": "cli", "work_identity_key": "work:stale-prompt"},
        )
        work_tree.add_task_to_branch(stale_cli.root_branch_id, "stale followup")
        stale_cli.created_at = now - timedelta(hours=13)
        stale_cli.updated_at = now - timedelta(hours=13)
        work_tree.save_tree(stale_cli)
        work_tree._persist_tree_state(stale_cli.tree_id)

        recent_cli = work_tree.initialize_tree(
            "Cli: recent prompt",
            meta={"kind": "system", "source": "cli", "work_identity_key": "work:recent-prompt"},
        )
        work_tree.add_task_to_branch(recent_cli.root_branch_id, "recent followup")
        recent_cli.created_at = now - timedelta(minutes=10)
        recent_cli.updated_at = now - timedelta(minutes=10)
        work_tree.save_tree(recent_cli)
        work_tree._persist_tree_state(recent_cli.tree_id)

        core_thinning = work_tree.initialize_tree(
            "Core Thinning",
            meta={"source": "core_thinning", "work_identity_key": "system:core-thinning"},
        )
        work_tree.add_task_to_branch(core_thinning.root_branch_id, "keep thinning")
        core_thinning.created_at = now - timedelta(hours=48)
        core_thinning.updated_at = now - timedelta(hours=48)
        work_tree.save_tree(core_thinning)
        work_tree._persist_tree_state(core_thinning.tree_id)

        complex_cli = work_tree.initialize_tree(
            "Cli: complex prompt",
            meta={"kind": "system", "source": "cli", "work_identity_key": "work:complex-prompt"},
        )
        for idx in range(5):
            work_tree.add_branch_to_tree(complex_cli.tree_id, f"complex branch {idx}", "work", complex_cli.root_branch_id)
        complex_cli.created_at = now - timedelta(hours=13)
        complex_cli.updated_at = now - timedelta(hours=13)
        work_tree.save_tree(complex_cli)
        work_tree._persist_tree_state(complex_cli.tree_id)

        state: dict = {}
        with mock.patch.object(autonomy_maintenance, "STALE_CLI_ACTIVE_TREE_ARCHIVE_MIN_AGE_SEC", 3600), \
             mock.patch.object(autonomy_maintenance, "STALE_CLI_ACTIVE_TREE_MAX_BRANCHES", 5), \
             mock.patch.object(autonomy_maintenance, "STALE_CLI_ACTIVE_TREE_MAX_OPEN_TASKS", 2):
            payload = autonomy_maintenance._archive_stale_cli_active_trees(state)

        self.assertEqual(payload.get("archived_count"), 1)
        self.assertEqual(payload.get("skipped_recent_count"), 1)
        self.assertEqual(payload.get("skipped_complex_count"), 1)
        self.assertEqual(work_tree.get_tree(stale_cli.tree_id).status, work_tree.TreeStatus.ARCHIVED)
        self.assertEqual(work_tree.get_tree(recent_cli.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertEqual(work_tree.get_tree(core_thinning.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertEqual(work_tree.get_tree(complex_cli.tree_id).status, work_tree.TreeStatus.ACTIVE)
        self.assertTrue(
            all(task.status == work_tree.TaskStatus.DROPPED for task in work_tree.list_tree_tasks(stale_cli.tree_id))
        )
        self.assertEqual((state.get("last_stale_cli_tree_archive") or {}).get("archived_count"), 1)

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
            state_path.write_text(
                json.dumps({"last_error": "old subconscious timeout"}, ensure_ascii=True),
                encoding="utf-8",
            )

            def _generated_queue_cycle(state):
                autonomy_maintenance._record_generated_queue_run(
                    state,
                    True,
                    "generated_work_queue_cycle_executed",
                    {
                        "selected": {"file": "demo.json", "latest_status": "warning"},
                        "latest_report": {"status": "warning", "run_id": "demo_run"},
                        "work_queue": {
                            "status": "actionable",
                            "open_count": 3,
                            "actionable_count": 2,
                            "blocked_count": 1,
                            "blocked_reason_counts": {"parity_drift_locked": 1},
                            "blocked_files": ["stuck.json"],
                            "count": 5,
                        },
                    },
                )
                payload = {
                    "ts": "2026-04-04 02:00:01",
                    "status": "ok",
                    "tree_id": "tree_generated_demo",
                    "tree_title": autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE,
                    "tree_count": 1,
                    "executed_count": 1,
                    "history_count": 1,
                    "last_action": "executed",
                    "actionable_count": 2,
                    "queue_status": "actionable",
                    "selected_file": "demo.json",
                }
                state["last_generated_queue_tree_cycle"] = payload
                return payload

            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(autonomy_maintenance, "LATEST_SUBCONSCIOUS", latest_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_subconscious_pack", return_value=(True, "ok")))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_sync_generated_queue_work_tree",
                    return_value={
                        "ts": "2026-04-04 02:00:01",
                        "status": "ok",
                        "tree_id": "tree_generated_demo",
                        "tree_title": autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE,
                        "queue_status": "actionable",
                        "queue_count": 5,
                        "open_count": 3,
                        "actionable_count": 2,
                        "blocked_count": 1,
                        "created_count": 1,
                        "updated_count": 0,
                        "reopened_count": 0,
                        "retired_count": 0,
                        "next_file": "demo.json",
                    },
                ))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_run_generated_queue_work_tree_cycle",
                    side_effect=_generated_queue_cycle,
                ))
                stack.enter_context(mock.patch.object(
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
                ))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_run_patch_queue_cleanup",
                    return_value={
                        "ts": "2026-04-04 02:00:01",
                        "status": "ok",
                        "orphan_rejected_count": 0,
                        "orphan_failed_count": 0,
                        "superseded_archived_count": 0,
                        "superseded_failed_count": 0,
                        "review_total_before": 0,
                        "review_total_after": 0,
                    },
                ))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_sync_patch_queue_work_tree",
                    return_value={
                        "ts": "2026-04-04 02:00:01",
                        "status": "ok",
                        "tree_id": "tree_demo",
                        "tree_title": "Patch Queue",
                        "apply_ready_count": 0,
                        "created_count": 0,
                        "updated_count": 0,
                    },
                ))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_run_patch_queue_work_tree_cycle",
                    return_value={
                        "ts": "2026-04-04 02:00:01",
                        "status": "idle",
                        "tree_count": 1,
                        "executed_count": 0,
                    },
                ))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_run_active_work_tree_cycle",
                    return_value={
                        "ts": "2026-04-04 02:00:01",
                        "status": "idle",
                        "tree_count": 0,
                        "executed_count": 0,
                    },
                ))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_legacy_maintenance_execution_enabled", return_value=True))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_retire_legacy_patch_update_trees",
                    return_value={
                        "ts": "2026-04-04 02:00:01",
                        "status": "idle",
                        "retired_count": 0,
                    },
                ))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_daily_regression_if_due", return_value="daily_regression_ok"))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_reevaluate_pending_review_queue", return_value={"status": "ok", "reevaluated_count": 0, "moved_promoted_count": 0, "moved_quarantined_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_signal_intake_work_tree", return_value={"status": "ok", "result_count": 0, "resolved_count": 0, "subconscious_signal_count": 0, "active_regression_failure": False}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_stale_complete_trees", return_value={"status": "idle", "archived_count": 0, "retained_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_empty_active_trees", return_value={"status": "idle", "archived_count": 0, "skipped_recent_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_stale_cli_active_trees", return_value={"status": "idle", "archived_count": 0, "skipped_recent_count": 0, "skipped_complex_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_regression_status_from_file", return_value=False))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_run_autonomy_orchestrator_advisory",
                    side_effect=lambda state, _kidney: state.setdefault(
                        "last_autonomy_orchestrator",
                        {
                            "decision": "defer_with_reason",
                            "action": {},
                            "reason": "test advisory",
                            "ledger_status": "recorded",
                        },
                    ),
                ))
                code = autonomy_maintenance.run_once()

            self.assertEqual(code, 0)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            queue_run = dict(state.get("last_generated_queue_run") or {})
            self.assertEqual(queue_run.get("status"), "actionable")
            self.assertEqual(queue_run.get("selected_file"), "demo.json")
            self.assertEqual(queue_run.get("selected_status"), "warning")
            self.assertEqual(queue_run.get("latest_report_status"), "warning")
            self.assertEqual(queue_run.get("latest_report_run_id"), "demo_run")
            self.assertEqual(queue_run.get("queue_open_count"), 3)
            self.assertEqual(queue_run.get("queue_actionable_count"), 2)
            self.assertEqual(queue_run.get("queue_blocked_count"), 1)
            self.assertEqual(queue_run.get("queue_blocked_reason_counts"), {"parity_drift_locked": 1})
            self.assertEqual(queue_run.get("queue_blocked_files"), ["stuck.json"])
            self.assertEqual(queue_run.get("queue_count"), 5)
            self.assertEqual((state.get("last_generated_queue_tree_cycle") or {}).get("executed_count"), 1)
            self.assertEqual(state.get("last_error"), "")
            subconscious_run = dict(state.get("last_subconscious_run") or {})
            self.assertEqual(subconscious_run.get("status"), "ok")
            self.assertEqual(subconscious_run.get("generated_at"), "2026-04-04 02:00:00")
            self.assertEqual(subconscious_run.get("training_priority_count"), 0)

    def test_run_once_syncs_signal_intake_before_orchestrator_execution(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            latest_path = runtime_dir / "subconscious_runs" / "latest.json"
            latest_path.parent.mkdir(parents=True, exist_ok=True)
            latest_path.write_text("{}", encoding="utf-8")
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"
            order: list[str] = []

            sync_calls: list[dict[str, object]] = []

            def _sync_signal(state, kidney_summary=None, temporal_feed=None, *, archive_superseded=True):
                sync_calls.append({"archive_superseded": archive_superseded})
                order.append("signal")
                payload = {
                    "ts": "2026-05-14 18:00:00",
                    "status": "ok",
                    "result_count": 1,
                    "resolved_count": 1,
                    "subconscious_signal_count": 0,
                    "active_regression_failure": False,
                }
                if len(sync_calls) == 1:
                    state["last_pre_execution_signal_ingestion"] = payload
                else:
                    state["last_signal_ingestion"] = payload
                return payload

            def _orchestrator(state, kidney_summary):
                order.append("orchestrator")
                payload = {
                    "decision": "defer_with_reason",
                    "action": {},
                    "reason": "test advisory",
                    "ledger_status": "recorded",
                    "execution": {"result": "blocked"},
                }
                state["last_autonomy_orchestrator"] = payload
                return payload

            def _active_cycle(state):
                order.append("active")
                return {
                    "ts": "2026-05-14 18:00:01",
                    "status": "idle",
                    "tree_count": 0,
                    "executed_count": 0,
                }

            idle_tree = {
                "ts": "2026-05-14 18:00:01",
                "status": "idle",
                "tree_count": 0,
                "executed_count": 0,
            }
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(autonomy_maintenance, "LATEST_SUBCONSCIOUS", latest_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_subconscious_pack", return_value=(True, "ok")))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_reevaluate_pending_review_queue", return_value={"status": "ok"}))
                stack.enter_context(mock.patch.object(autonomy_maintenance.kidney, "run_kidney", return_value={"mode": "enforce"}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_patch_queue_cleanup", return_value={"status": "ok"}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_patch_queue_work_tree", return_value={"status": "ok", "apply_ready_count": 0, "created_count": 0, "updated_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_patch_queue_work_tree_cycle", return_value=idle_tree))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_generated_queue_work_tree", return_value={"status": "ok", "actionable_count": 0, "created_count": 0, "updated_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_signal_intake_work_tree", side_effect=_sync_signal))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_autonomy_orchestrator_advisory", side_effect=_orchestrator))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_generated_queue_work_tree_cycle", return_value=idle_tree))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_active_work_tree_cycle", side_effect=_active_cycle))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_stale_complete_trees", return_value={"status": "idle", "archived_count": 0, "retained_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_empty_active_trees", return_value={"status": "idle", "archived_count": 0, "skipped_recent_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_stale_cli_active_trees", return_value={"status": "idle", "archived_count": 0, "skipped_recent_count": 0, "skipped_complex_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_retire_legacy_patch_update_trees", return_value={"status": "idle", "retired_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_daily_regression_if_due", return_value="daily_regression_skipped_already_ran"))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_regression_status_from_file", return_value=False))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_legacy_maintenance_execution_enabled", return_value=True))
                self.assertEqual(autonomy_maintenance.run_once(), 0)

            self.assertLess(order.index("signal"), order.index("orchestrator"))
            self.assertLess(order.index("orchestrator"), order.index("active"))
            self.assertEqual(len(sync_calls), 2)
            self.assertFalse(sync_calls[0]["archive_superseded"])
            self.assertTrue(sync_calls[1]["archive_superseded"])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual((state.get("last_pre_execution_signal_ingestion") or {}).get("status"), "ok")

    def test_execute_autonomy_recommendation_uses_dispatcher_for_canary_action(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "generated_queue_run_next",
                "target_kind": "queue",
                "target_id": "generated_work_queue",
                "reason_code": "queue_pressure_actionable",
                "requires_ack": False,
                "cooldown_sec": 180,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": ["generated_queue_run_next"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_next_generated_work_queue_item",
            return_value=(
                True,
                "generated_work_queue_run_ok",
                {
                    "selected": {"file": "demo.json", "latest_status": "pass"},
                    "latest_report": {"status": "pass", "run_id": "run-demo", "report_path": "runtime/report.json"},
                    "reports": [
                        {"status": "pass", "run_id": "run-demo", "report_path": "runtime/report.json"},
                        {"status": "drift", "run_id": "run-old", "report_path": "runtime/old.json"},
                    ],
                    "definitions": [
                        {"file": "demo.json", "path": "C:/Nova/runtime/test_sessions/generated_definitions/demo.json", "messages": ["one"]},
                        {"file": "next.json", "path": "C:/Nova/runtime/test_sessions/generated_definitions/next.json", "messages": ["two"]},
                    ],
                    "work_queue": {
                        "status": "actionable",
                        "open_count": 1,
                        "actionable_count": 1,
                        "blocked_count": 0,
                        "count": 1,
                        "next_item": {"file": "next.json"},
                        "items": [{"file": "next.json", "latest_status": "drift", "actionable": True}],
                    },
                },
            ),
        ):
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        self.assertEqual(result.get("result"), "success")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("action_type"), "generated_queue_run_next")
        self.assertEqual((state.get("last_generated_queue_run") or {}).get("selected_file"), "demo.json")
        events = list(result.get("events") or [])
        self.assertEqual(events[0].get("act"), "generated_queue_run_next")
        self.assertEqual(events[0].get("status"), "ok")
        self.assertNotIn("definitions", result.get("extra") or {})
        self.assertEqual((result.get("extra") or {}).get("definition_count"), 2)
        self.assertEqual((result.get("extra") or {}).get("definition_files"), ["demo.json", "next.json"])
        self.assertEqual(((result.get("extra") or {}).get("work_queue") or {}).get("next_file"), "next.json")

    def test_autonomy_execution_owner_defaults_to_orchestrator_in_canary(self):
        owner = autonomy_maintenance._autonomy_execution_owner(
            {
                "mode": "canary",
                "execute_enabled": True,
            }
        )
        self.assertEqual(owner, "orchestrator")
        self.assertFalse(autonomy_maintenance._legacy_maintenance_execution_enabled({"mode": "canary", "execute_enabled": True}))

    def test_autonomy_execution_owner_honors_explicit_legacy_opt_in(self):
        settings = {
            "mode": "canary",
            "execute_enabled": True,
            "orchestrator_owns_execution": False,
            "legacy_maintenance_execution_enabled": True,
        }
        self.assertEqual(autonomy_maintenance._autonomy_execution_owner(settings), "legacy")
        self.assertTrue(autonomy_maintenance._legacy_maintenance_execution_enabled(settings))

    def test_orchestrator_owner_skips_dispatcher_when_legacy_opted_in(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "generated_queue_run_next",
                "target_kind": "queue",
                "target_id": "generated_work_queue",
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "mode": "canary",
            "execute_enabled": True,
            "orchestrator_owns_execution": False,
            "legacy_maintenance_execution_enabled": True,
        }

        with mock.patch.object(autonomy_maintenance, "_autonomy_policy_settings", return_value=policy), \
             mock.patch.object(autonomy_maintenance, "_execute_autonomy_recommendation") as execute_mock, \
             mock.patch.object(autonomy_maintenance.AUTONOMY_ORCHESTRATOR_SERVICE, "evaluate_next_action", return_value=packet), \
             mock.patch.object(autonomy_maintenance.AUTONOMY_ORCHESTRATOR_SERVICE, "set_mode"), \
             mock.patch.object(autonomy_maintenance, "_autonomy_orchestrator_input_envelope", return_value={"mission_snapshot": {}}), \
             mock.patch.object(autonomy_maintenance, "_append_autonomy_orchestrator_ledger"), \
             mock.patch.object(autonomy_maintenance, "_publish_operator_notice_from_autonomy", return_value={}), \
             mock.patch.object(autonomy_maintenance, "_publish_operator_notices_from_work_tree", return_value=[]):
            result = autonomy_maintenance._run_autonomy_orchestrator_advisory(state, {"mode": "enforce"})

        execute_mock.assert_not_called()
        self.assertEqual((result.get("execution") or {}).get("result"), "skipped")
        self.assertEqual((result.get("execution") or {}).get("gate_reason"), "legacy_owns_execution")

    def test_orchestrator_owner_records_generated_queue_cycle_from_execution(self):
        state = {
            "last_generated_queue_sync": {
                "tree_id": "tree_generated_demo",
                "tree_title": "Generated Queue",
                "actionable_count": 2,
            }
        }
        packet = {
            "execution": {
                "action_type": "generated_queue_run_next",
                "result": "success",
                "message": "generated_work_queue_run_ok",
                "extra": {
                    "selected": {"file": "demo.json"},
                    "work_queue": {"status": "actionable", "actionable_count": 2},
                },
            }
        }
        cycle = autonomy_maintenance._orchestrator_executed_generated_queue_cycle(packet, state=state)

        self.assertTrue(cycle.get("orchestrator_owned"))
        self.assertEqual(cycle.get("executed_count"), 1)
        self.assertEqual(cycle.get("tree_id"), "tree_generated_demo")
        self.assertEqual(cycle.get("actionable_count"), 2)

    def test_execute_autonomy_recommendation_dispatches_guard_start_runtime_control_action(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "guard_start",
                "target_kind": "runtime",
                "target_id": "guard",
                "reason_code": "guard_not_running",
                "requires_ack": False,
                "cooldown_sec": 300,
            },
            "confidence": 0.82,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["runtime_control"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(autonomy_maintenance, "_maintenance_start_guard", return_value=(True, "guard_start_requested")), \
             mock.patch.object(autonomy_maintenance, "_maintenance_guard_status_payload", return_value={"running": True, "status": "running"}):
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        self.assertEqual(result.get("result"), "success")
        self.assertEqual(result.get("action_type"), "guard_start")
        self.assertEqual((result.get("events") or [])[0].get("act"), "guard_start")
        self.assertEqual((result.get("extra") or {}).get("guard"), {"running": True, "status": "running"})

    def test_execute_autonomy_recommendation_records_decision_judge_observation_only(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-judge",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "guard_start",
                "target_kind": "runtime",
                "target_id": "guard",
                "reason_code": "runtime_guard_stopped",
                "expected_effect": "Restore the runtime guard so maintenance ticks can resume.",
                "requires_ack": False,
                "cooldown_sec": 300,
            },
            "confidence": 0.82,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["runtime_control"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
            # enforce off: judge must not block
        }

        with mock.patch.object(
            autonomy_maintenance, "_maintenance_start_guard", return_value=(True, "guard_start_requested")
        ), mock.patch.object(
            autonomy_maintenance,
            "_maintenance_guard_status_payload",
            return_value={"running": True, "status": "running"},
        ):
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        self.assertEqual(result.get("result"), "success")
        proposal = result.get("decision_proposal") or state.get("last_decision_proposal") or {}
        judge = result.get("decision_judge") or state.get("last_decision_judge") or {}
        self.assertEqual(proposal.get("action_id"), "guard_start")
        self.assertTrue(proposal.get("intended_effect"))
        self.assertTrue(proposal.get("expected_evidence"))
        self.assertTrue(judge.get("observation_only"))
        self.assertIn(judge.get("disposition"), {"proceed", "proceed_annotate"})
        self.assertIsNotNone((judge.get("outcome") or {}).get("execution_result"))
        self.assertTrue(state.get("decision_judge_history"))

    def test_execute_autonomy_recommendation_dispatches_maintenance_start_runtime_control_action(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "autonomy_maintenance_start",
                "target_kind": "runtime",
                "target_id": "autonomy_maintenance",
                "reason_code": "maintenance_worker_not_running",
                "requires_ack": False,
                "cooldown_sec": 300,
            },
            "confidence": 0.82,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["runtime_control"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_maintenance_start_autonomy_maintenance_worker",
            return_value=(True, "autonomy_maintenance_start_requested"),
        ), mock.patch.object(
            autonomy_maintenance,
            "_maintenance_autonomy_maintenance_summary",
            return_value={"runtime_worker": {"last_cycle_status": "running"}},
        ):
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        self.assertEqual(result.get("result"), "success")
        self.assertEqual(result.get("action_type"), "autonomy_maintenance_start")
        self.assertEqual((result.get("events") or [])[0].get("act"), "autonomy_maintenance_start")
        self.assertEqual(
            ((result.get("extra") or {}).get("autonomy_maintenance") or {}).get("runtime_worker"),
            {"last_cycle_status": "running"},
        )

    def test_execute_autonomy_recommendation_dispatches_patch_queue_conduit_action(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "patch_queue_run_next",
                "target_kind": "lane",
                "target_id": "patch_queue",
                "reason_code": "patch_queue_ready",
                "requires_ack": False,
                "cooldown_sec": 240,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["patch_queue"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_patch_queue_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 1, "tree_count": 1},
        ) as cycle_mock:
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        cycle_mock.assert_called_once_with(state, max_steps=1)
        self.assertEqual(result.get("result"), "success")
        self.assertEqual(result.get("action_type"), "patch_queue_run_next")
        self.assertEqual(((result.get("extra") or {}).get("cycle") or {}).get("executed_count"), 1)
        self.assertEqual((result.get("events") or [])[0].get("act"), "patch_queue_run_next")

    def test_execute_autonomy_recommendation_dispatches_generated_queue_investigate_in_maintenance_scope(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "generated_queue_investigate",
                "target_kind": "queue",
                "target_id": "generated_work_queue",
                "reason_code": "work_tree_or_queue_blocked",
                "requires_ack": False,
                "cooldown_sec": 180,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": ["generated_queue_investigate"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_active_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 1, "tree_count": 1},
        ) as cycle_mock:
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        cycle_mock.assert_called_once_with(state, max_steps=1, max_trees=1)
        self.assertEqual(result.get("result"), "success")
        self.assertEqual(result.get("action_type"), "generated_queue_investigate")
        self.assertEqual(((result.get("extra") or {}).get("cycle") or {}).get("executed_count"), 1)
        self.assertEqual((result.get("events") or [])[0].get("act"), "generated_queue_investigate")

    def test_execute_autonomy_recommendation_dispatches_active_work_tree_conduit_action(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "active_work_tree_run_next",
                "target_kind": "lane",
                "target_id": "active_work_tree",
                "reason_code": "active_work_tree_ready",
                "requires_ack": False,
                "cooldown_sec": 120,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["active_work_tree"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_active_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 3, "tree_count": 3},
        ) as cycle_mock:
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        cycle_mock.assert_called_once_with(state, max_steps=3, max_trees=8)
        self.assertEqual(result.get("result"), "success")
        self.assertEqual(result.get("action_type"), "active_work_tree_run_next")
        self.assertEqual(((result.get("extra") or {}).get("cycle") or {}).get("executed_count"), 3)
        self.assertEqual((result.get("events") or [])[0].get("act"), "active_work_tree_run_next")

    def test_execute_autonomy_recommendation_treats_active_work_tree_tool_failed_as_failed(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "active_work_tree_run_next",
                "target_kind": "lane",
                "target_id": "active_work_tree",
                "reason_code": "active_work_tree_ready",
                "requires_ack": False,
                "cooldown_sec": 120,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["active_work_tree"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_active_work_tree_cycle",
            return_value={
                "status": "tool_failed",
                "attempted_count": 1,
                "executed_count": 0,
                "history": [
                    {
                        "action": "tool_failed",
                        "tool": "release_rebuild_verify",
                        "failure_evidence_id": "evidence_failure",
                        "error": "repo_hygiene_failed",
                    }
                ],
            },
        ) as cycle_mock:
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        cycle_mock.assert_called_once_with(state, max_steps=3, max_trees=8)
        self.assertEqual(result.get("result"), "failed")
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("message"), "active_work_tree_run_next_tool_failed")
        self.assertEqual((result.get("events") or [])[0].get("status"), "fail")
        self.assertEqual(
            (((result.get("extra") or {}).get("cycle") or {}).get("history") or [])[0].get("evidence_id"),
            "evidence_failure",
        )

    def test_execute_autonomy_recommendation_honors_active_work_tree_step_budget(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "active_work_tree_run_next",
                "target_kind": "lane",
                "target_id": "active_work_tree",
                "reason_code": "active_work_tree_ready",
                "requires_ack": False,
                "cooldown_sec": 120,
                "max_steps": 5,
                "max_trees": 6,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["active_work_tree"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_active_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 5, "tree_count": 6},
        ) as cycle_mock:
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        cycle_mock.assert_called_once_with(state, max_steps=5, max_trees=6)
        self.assertEqual(result.get("result"), "success")
        event_payload = (result.get("events") or [{}])[0].get("payload") or {}
        self.assertEqual(event_payload.get("max_steps"), 5)
        self.assertEqual(event_payload.get("max_trees"), 6)

    def test_execute_autonomy_recommendation_honors_active_work_tree_target(self):
        state: dict = {}
        packet = {
            "cycle_id": "cycle-test",
            "decision_type": "RecommendAction",
            "recommended_action": {
                "action_type": "active_work_tree_run_next",
                "target_kind": "lane",
                "target_id": "branch_release",
                "target_step_id": "task_release",
                "reason_code": "active_work_tree_ready",
                "requires_ack": False,
                "cooldown_sec": 120,
                "max_steps": 1,
                "max_trees": 1,
            },
            "confidence": 0.72,
            "refusal_reasons": [],
        }
        policy = {
            "enabled": True,
            "mode": "canary",
            "execute_enabled": True,
            "execute_allowed_actions": [],
            "execute_allowed_action_groups": ["active_work_tree"],
            "execute_blocked_actions": [],
            "requires_operator_ack_for": [],
            "execute_min_confidence": 0.55,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_run_active_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 1, "tree_count": 1},
        ) as cycle_mock:
            result = autonomy_maintenance._execute_autonomy_recommendation(state, packet, policy)

        cycle_mock.assert_called_once_with(
            state,
            max_steps=1,
            max_trees=1,
            target_branch_id="branch_release",
            target_task_id="task_release",
        )
        self.assertEqual(result.get("result"), "success")

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
            self.assertGreater(int(worker.get("pid") or 0), 0)
            self.assertEqual(worker.get("script_path"), str(Path(autonomy_maintenance.__file__).resolve()))
            self.assertTrue(worker.get("active"))
            self.assertFalse(worker.get("stale_identity"))

    def test_non_loop_cycle_clears_dead_runtime_worker_identity(self):
        state = {
            "runtime_worker": {
                "interval_sec": 300,
                "last_cycle": 8,
                "cycle_count": 8,
                "pid": 987654,
                "create_time": 12.5,
                "active": True,
                "stale_identity": False,
                "last_cycle_status": "ok",
            }
        }

        with mock.patch.object(autonomy_maintenance, "_runtime_worker_loop_identity_live", return_value=False):
            changed = autonomy_maintenance._clear_non_loop_runtime_worker_state(
                state,
                timestamp_fn=lambda: "2026-05-15 22:30:00",
            )

        worker = dict(state.get("runtime_worker") or {})
        self.assertTrue(changed)
        self.assertFalse(worker.get("active"))
        self.assertFalse(worker.get("stale_identity"))
        self.assertTrue(worker.get("cleared_stale_identity"))
        self.assertIsNone(worker.get("pid"))
        self.assertIsNone(worker.get("create_time"))
        self.assertEqual(worker.get("last_cycle_status"), "stopped")
        self.assertEqual(worker.get("stopped_reason"), "one_shot_cycle_not_worker_loop")
        self.assertEqual(worker.get("stopped_at"), "2026-05-15 22:30:00")
        self.assertEqual(worker.get("stale_identity_cleared_at"), "2026-05-15 22:30:00")

    def test_non_loop_cycle_preserves_live_loop_worker_identity(self):
        state = {
            "runtime_worker": {
                "pid": 1234,
                "create_time": 45.0,
                "active": True,
                "stale_identity": False,
                "last_cycle_status": "ok",
            }
        }

        with mock.patch.object(autonomy_maintenance, "_runtime_worker_loop_identity_live", return_value=True):
            changed = autonomy_maintenance._clear_non_loop_runtime_worker_state(state)

        worker = dict(state.get("runtime_worker") or {})
        self.assertFalse(changed)
        self.assertTrue(worker.get("active"))
        self.assertEqual(worker.get("pid"), 1234)
        self.assertEqual(worker.get("last_cycle_status"), "ok")

    def test_one_shot_cycle_preserves_live_runtime_worker_identity(self):
        worker_state = {
            "pid": 4321,
            "create_time": 99.0,
            "active": True,
            "stale_identity": False,
            "last_cycle_status": "running",
        }
        with mock.patch("psutil.Process") as process_mock:
            process_mock.return_value.create_time.return_value = 99.0
            process_mock.return_value.cmdline.return_value = [
                "C:/NOVA/.venv/Scripts/python.exe",
                "C:/NOVA/autonomy_maintenance.py",
                "--once",
            ]
            self.assertTrue(autonomy_maintenance._runtime_worker_loop_identity_live(worker_state))

        state = {"runtime_worker": worker_state}
        with mock.patch.object(autonomy_maintenance, "_runtime_worker_loop_identity_live", return_value=True):
            changed = autonomy_maintenance._clear_non_loop_runtime_worker_state(state)

        worker = dict(state.get("runtime_worker") or {})
        self.assertFalse(changed)
        self.assertTrue(worker.get("active"))
        self.assertEqual(worker.get("pid"), 4321)
        self.assertEqual(worker.get("last_cycle_status"), "running")

    def test_non_loop_cycle_clears_stale_flag_after_identity_was_removed(self):
        state = {
            "runtime_worker": {
                "pid": None,
                "create_time": None,
                "active": False,
                "stale_identity": True,
                "last_cycle_status": "stopped",
            }
        }

        with mock.patch.object(autonomy_maintenance, "_runtime_worker_loop_identity_live", return_value=False):
            changed = autonomy_maintenance._clear_non_loop_runtime_worker_state(
                state,
                timestamp_fn=lambda: "2026-05-15 22:35:00",
            )

        worker = dict(state.get("runtime_worker") or {})
        self.assertTrue(changed)
        self.assertFalse(worker.get("active"))
        self.assertFalse(worker.get("stale_identity"))
        self.assertTrue(worker.get("cleared_stale_identity"))
        self.assertEqual(worker.get("stale_identity_cleared_at"), "2026-05-15 22:35:00")

    def test_run_worker_uses_worker_loop_context_for_default_cycle(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"
            worker_loop_values = []

            def _run_once(*, worker_loop=False):
                worker_loop_values.append(bool(worker_loop))
                return 0

            with mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path), \
                 mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path), \
                 mock.patch.object(autonomy_maintenance, "run_once", side_effect=_run_once):
                code = autonomy_maintenance.run_worker(
                    interval_sec=7,
                    max_cycles=1,
                    sleep_fn=lambda _seconds: None,
                )

        self.assertEqual(code, 0)
        self.assertEqual(worker_loop_values, [True])

    def test_autonomy_orchestrator_advisory_records_state_and_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "runtime" / "autonomy_orchestrator_ledger.jsonl"
            state: dict = {}
            core_steward = {
                "score": 100,
                "level": "strong",
                "summary": "core surfaces look stable",
                "runtime": {
                    "heartbeat": {"ok": True, "info": "heartbeat ok"},
                    "core_state": {"ok": True, "info": "core ok"},
                    "ollama": {"ok": True, "info": "ollama ok"},
                },
                "autonomy_maintenance": {"worker_status": "running"},
                "pulse": {"fallback_overuse_score": 0.0, "approved_eligible_previews": 0},
            }

            with mock.patch.object(autonomy_maintenance, "AUTONOMY_ORCHESTRATOR_LEDGER", ledger_path), \
                 mock.patch.object(autonomy_maintenance, "_core_steward_for_orchestrator", return_value=core_steward), \
                 mock.patch.object(
                     autonomy_maintenance.CONTROL_WORK_TREES_SERVICE,
                     "payload",
                     return_value={
                         "ok": True,
                         "counts": {"total": 0, "active": 0, "branches": 0, "open_tasks": 0, "working": 0},
                         "trees": [],
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_generated_work_queue",
                     return_value={
                         "status": "ready",
                         "count": 1,
                         "open_count": 1,
                         "actionable_count": 1,
                         "blocked_count": 0,
                         "next_item": {"file": "generated_demo.json"},
                     },
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_guard_health_for_orchestrator",
                     return_value={"running": True, "status": "running"},
                 ), \
                 mock.patch.object(
                     autonomy_maintenance,
                     "_webui_health_for_orchestrator",
                     return_value={"running": False, "status": "stopped", "http_ok": False, "port_open": False},
                 ), \
                 mock.patch.object(autonomy_maintenance, "_active_work_tree_candidates", return_value=[]), \
                 mock.patch.object(autonomy_maintenance, "_autonomy_policy_settings", return_value={"enabled": True, "mode": "advisory"}):
                packet = autonomy_maintenance._run_autonomy_orchestrator_advisory(state, {"mode": "enforce"})

            self.assertEqual(packet.get("decision"), "recommend_action")
            self.assertEqual((packet.get("action") or {}).get("act"), "generated_queue_run_next")
            self.assertEqual((state.get("last_autonomy_orchestrator") or {}).get("ledger_status"), "recorded")
            rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("decision"), "recommend_action")
            self.assertIn("candidate_actions", rows[0])
            self.assertEqual(rows[0].get("execution_result"), "skipped")
            self.assertEqual((rows[0].get("execution") or {}).get("result"), "skipped")
            self.assertEqual((rows[0].get("execution") or {}).get("gate_reason"), "execution_disabled")

    def test_orchestrator_input_envelope_carries_maintenance_worker_surface(self):
        envelope = autonomy_maintenance._autonomy_orchestrator_input_envelope(
            state={},
            core_steward={
                "score": 100,
                "level": "strong",
                "runtime": {
                    "heartbeat": {"ok": True},
                    "core_state": {"ok": True},
                },
                "autonomy_maintenance": {
                    "worker_status": "stopped",
                    "worker_active": False,
                    "worker_stale_identity": True,
                    "scheduler_active": False,
                    "scheduler_mode": "inactive",
                    "scheduler_status": "inactive",
                },
            },
            work_tree_state={"ok": True, "counts": {}, "trees": []},
            generated_queue={"status": "clear", "open_count": 0, "actionable_count": 0},
            guard_health={"running": True, "status": "running"},
        )

        maintenance = envelope.get("autonomy_maintenance") or {}
        self.assertEqual(maintenance.get("worker_status"), "stopped")
        self.assertTrue(maintenance.get("worker_stale_identity"))
        self.assertFalse(maintenance.get("scheduler_active"))

    def test_orchestrator_input_envelope_green_cycle_includes_mission_snapshot(self):
        from services.layer_maturity_policy import CORE_GATE_ROOT_IDS

        truth_evidence = {
            "validation_artifact_truth": {"ok": True, "status": "ok", "hidden_by_green_regression": False},
            "last_regression_status": "OK",
            "last_regression_stale": False,
            "release_runtime_truth": {
                "running_build_identity": "nova:rc:work-tree",
                "latest_source_changed_after_build": False,
                "runtime_drift_tolerated": False,
            },
            "release_status": {
                "latest_artifact_name": "nova:rc:work-tree",
                "latest_source_changed_after_build": False,
            },
            "root_closure_inventory": {
                "ok": True,
                "gap_count": 0,
                "roots": [
                    {"root_id": root_id, "ok": True, "gaps": []}
                    for root_id in CORE_GATE_ROOT_IDS
                ],
            },
        }
        clean_work_tree_pressure = {
            "open_task_count": 0,
            "working_count": 0,
            "blocked_branch_count": 0,
            "blocked_observing_count": 0,
            "observing_branch_count": 0,
            "latent_root_signal_count": 0,
            "operator_hold_branch_count": 0,
            "release_stale_ready_count": 0,
            "stale_count": 0,
            "oldest_open_age_min": 0,
        }
        with mock.patch.object(
            autonomy_maintenance,
            "_truth_evidence_for_mission",
            return_value=truth_evidence,
        ), mock.patch.object(
            autonomy_maintenance,
            "_work_tree_pressure_truth",
            return_value=clean_work_tree_pressure,
        ), mock.patch.object(
            autonomy_maintenance,
            "_webui_health_for_orchestrator",
            return_value={"running": True, "http_ok": True, "port_open": True},
        ), mock.patch.object(
            autonomy_maintenance,
            "_triage_hints_for_orchestrator",
            return_value={
                "approved_review_count": 0,
                "source": "core_steward_pulse",
                "source_freshness_sec": 0,
            },
        ):
            envelope = autonomy_maintenance._autonomy_orchestrator_input_envelope(
                state={},
                core_steward={
                    "score": 100,
                    "level": "strong",
                    "runtime": {
                        "heartbeat": {"ok": True},
                        "core_state": {"ok": True},
                    },
                    "autonomy_maintenance": {
                        "worker_status": "running",
                        "worker_active": True,
                    },
                    "pulse": {"fallback_overuse_score": 0.0},
                },
                work_tree_state={"ok": True, "counts": {}, "trees": []},
                generated_queue={
                    "status": "clear",
                    "open_count": 0,
                    "actionable_count": 0,
                    "blocked_count": 0,
                    "drift_count": 0,
                },
                guard_health={"running": True, "status": "running"},
                policy_snapshot={
                    "autonomy_enabled": True,
                    "execute_enabled": True,
                    "mission": {
                        "enabled": True,
                        "mode": "steady_state_guard",
                        "objective": "hold_steady_and_surface_fresh_gaps",
                        "release_stale_ready_is_pressure": False,
                    },
                },
            )

        mission = envelope.get("mission_snapshot") or {}
        self.assertTrue(bool(mission))
        self.assertEqual(mission.get("status"), "green")
        self.assertTrue(bool(mission.get("green_cycle")))
        self.assertEqual((envelope.get("triage_hints") or {}).get("mission_snapshot"), mission)

    def test_mission_hold_blocks_legacy_generated_queue_execution(self):
        self.assertTrue(
            autonomy_maintenance._mission_hold_blocks_generated_queue(
                {
                    "enabled": True,
                    "mode": "steady_state_guard",
                    "green_cycle": True,
                    "action": "hold",
                }
            )
        )
        self.assertTrue(
            autonomy_maintenance._mission_hold_blocks_generated_queue(
                {
                    "enabled": True,
                    "mode": "steady_state_guard",
                    "green_cycle": False,
                    "status": "validation_required",
                    "action": "hold",
                }
            )
        )
        self.assertFalse(
            autonomy_maintenance._mission_hold_blocks_generated_queue(
                {
                    "enabled": True,
                    "mode": "steady_state_guard",
                    "green_cycle": False,
                    "status": "validation_required",
                    "action": "hold",
                    "truth_ready": False,
                    "truth_blockers": ["generated_queue_untested"],
                    "green_blockers": [
                        {
                            "owner": "generated_queue",
                            "code": "generated_queue_untested",
                            "source": "generated_work_queue",
                            "remediation": {"action": "generated_queue_run_next"},
                        }
                    ],
                    "validation_fresh": True,
                    "regression_current": True,
                    "release_truth_current": True,
                    "generated_queue_untested_count": 2,
                }
            )
        )
        self.assertTrue(
            autonomy_maintenance._mission_hold_blocks_generated_queue(
                {
                    "enabled": True,
                    "mode": "steady_state_guard",
                    "green_cycle": False,
                    "status": "validation_required",
                    "action": "hold",
                    "truth_ready": False,
                    "truth_blockers": ["validation_truth_missing", "generated_queue_untested"],
                    "green_blockers": [
                        {"owner": "validation", "code": "validation_truth_missing"},
                        {"owner": "generated_queue", "code": "generated_queue_untested"},
                    ],
                    "validation_fresh": False,
                    "regression_current": True,
                    "release_truth_current": True,
                    "generated_queue_untested_count": 2,
                }
            )
        )
        self.assertFalse(
            autonomy_maintenance._mission_hold_blocks_generated_queue(
                {
                    "enabled": True,
                    "mode": "steady_state_guard",
                    "green_cycle": False,
                    "action": "investigate",
                }
            )
        )

    def test_mission_hold_blocks_legacy_active_work_tree_execution(self):
        state = {}
        mission = {
            "enabled": True,
            "mode": "steady_state_guard",
            "green_cycle": False,
            "status": "validation_required",
            "action": "hold",
        }

        with mock.patch.object(autonomy_maintenance, "_run_active_work_tree_cycle") as mocked_run:
            payload = autonomy_maintenance._active_work_tree_cycle_for_execution_mode(
                state,
                mission_snapshot=mission,
                policy_snapshot=autonomy_maintenance._policy_snapshot_for_orchestrator(),
                autonomy_orchestrator={},
                legacy_execution_enabled=True,
            )

        mocked_run.assert_not_called()
        self.assertEqual(payload.get("status"), "skipped")
        self.assertEqual(payload.get("reason"), "mission_steady_state_hold")
        self.assertEqual(state.get("last_active_work_tree_cycle"), payload)

    def test_orchestrator_owner_records_core_thinning_active_work_tree_execution(self):
        state = {}
        mission = {
            "enabled": True,
            "mode": "steady_state_guard",
            "green_cycle": True,
            "truth_ready": True,
            "status": "green",
            "action": "hold",
        }
        orchestrator_packet = {
            "execution": {
                "action_type": "active_work_tree_run_next",
                "result": "success",
                "extra": {
                    "cycle": {
                        "status": "ok",
                        "executed_count": 1,
                        "tree_count": 1,
                        "history": [{"tool": "core_thinning", "action": "executed"}],
                    }
                },
            }
        }

        with mock.patch.object(autonomy_maintenance, "_run_active_work_tree_cycle") as mocked_run:
            payload = autonomy_maintenance._active_work_tree_cycle_for_execution_mode(
                state,
                mission_snapshot=mission,
                policy_snapshot=autonomy_maintenance._policy_snapshot_for_orchestrator(),
                autonomy_orchestrator=orchestrator_packet,
                legacy_execution_enabled=False,
            )

        mocked_run.assert_not_called()
        self.assertEqual(payload.get("status"), "ok")
        self.assertTrue(payload.get("orchestrator_owned"))
        self.assertEqual(payload.get("orchestrator_action_type"), "active_work_tree_run_next")

    def test_release_drift_hold_allows_targeted_core_thinning_execution(self):
        state = {}
        mission = {
            "enabled": True,
            "mode": "steady_state_guard",
            "green_cycle": False,
            "truth_ready": False,
            "status": "validation_required",
            "action": "hold",
            "truth_blockers": ["core_gate_release_drift"],
            "green_blockers": [{"owner": "layer_maturity", "code": "core_gate_release_drift"}],
            "owner_verdicts": [
                {
                    "owner": "release",
                    "ready": True,
                    "evidence": {
                        "runtime_drift_expected": True,
                        "runtime_drift_tolerated": True,
                    },
                }
            ],
            "validation_fresh": True,
            "regression_current": True,
            "release_truth_current": True,
            "core_gate": {"ok": False, "drift_blocked": True, "missing_roots": []},
            "generated_queue_untested_count": 0,
        }
        orchestrator_packet = {
            "execution": {
                "action_type": "active_work_tree_run_next",
                "result": "success",
                "extra": {
                    "cycle": {
                        "status": "ok",
                        "executed_count": 1,
                        "tree_count": 1,
                        "history": [{"tool": "core_thinning", "action": "executed"}],
                    }
                },
            }
        }

        with mock.patch.object(autonomy_maintenance, "_run_active_work_tree_cycle") as mocked_run:
            payload = autonomy_maintenance._active_work_tree_cycle_for_execution_mode(
                state,
                mission_snapshot=mission,
                policy_snapshot=autonomy_maintenance._policy_snapshot_for_orchestrator(),
                autonomy_orchestrator=orchestrator_packet,
                legacy_execution_enabled=False,
            )

        mocked_run.assert_not_called()
        self.assertEqual(payload.get("status"), "ok")
        self.assertTrue(payload.get("orchestrator_owned"))

    def test_autonomy_orchestrator_status_for_signal_ingestion_includes_execution_failure(self):
        payload = autonomy_maintenance._autonomy_orchestrator_status_for_signal_ingestion(
            {
                "last_autonomy_orchestrator": {
                    "decision": "recommend_action",
                    "decision_type": "RecommendAction",
                    "recommended_action": {
                        "action_type": "active_work_tree_run_next",
                        "target_id": "branch-core",
                        "target_step_id": "task-core",
                        "target_tree_id": "tree-core",
                        "recommended_tool": "core_thinning",
                    },
                    "ledger_status": "recorded",
                },
                "last_autonomy_execution": {
                    "action_type": "active_work_tree_run_next",
                    "target_id": "branch-core",
                    "target_step_id": "task-core",
                    "result": "failed",
                    "message": "active_work_tree_run_next_invalid_decision",
                    "extra": {"cycle": {"status": "invalid_decision"}},
                },
            }
        )

        self.assertEqual(payload.get("autonomy_orchestrator_action_type"), "active_work_tree_run_next")
        self.assertEqual(payload.get("autonomy_orchestrator_execution_result"), "failed")
        self.assertEqual(payload.get("autonomy_orchestrator_execution_cycle_status"), "invalid_decision")
        self.assertEqual(payload.get("autonomy_orchestrator_target_tree_id"), "tree-core")
        self.assertEqual(payload.get("autonomy_orchestrator_recommended_tool"), "core_thinning")

    def test_run_autonomy_orchestrator_persists_mission_snapshot(self):
        state = {}
        defer_packet = {
            "created_at_utc": "2026-07-08T12:00:00Z",
            "mode": "advisory",
            "decision_type": "Defer",
            "decision": "defer_with_reason",
            "confidence": 0.0,
            "action": {},
            "reason": "Mission steady-state guard: green cycle hold.",
            "explain_text": "Mission steady-state guard: green cycle hold.",
            "rejection_reasons": ["mission_green_cycle_hold"],
            "ledger": {"status": "not_requested", "row": {}},
        }
        green_mission = {
            "enabled": True,
            "mode": "steady_state_guard",
            "objective": "hold_steady_and_surface_fresh_gaps",
            "status": "green",
            "action": "hold",
            "green_cycle": True,
            "headline": "steady governance cycle; no fresh gap pressure",
            "fresh_gap_signal_count": 0,
            "source": "services.nova_mission",
        }
        with mock.patch.object(
            autonomy_maintenance,
            "_autonomy_orchestrator_input_envelope",
            return_value={
                "cycle_id": "autonomy-maintenance-test",
                "mission_snapshot": green_mission,
                "triage_hints": {"mission_snapshot": green_mission},
            },
        ), mock.patch.object(
            autonomy_maintenance.AUTONOMY_ORCHESTRATOR_SERVICE,
            "evaluate_next_action",
            return_value=defer_packet,
        ), mock.patch.object(
            autonomy_maintenance,
            "_execute_autonomy_recommendation",
            return_value={"result": "skipped"},
        ), mock.patch.object(
            autonomy_maintenance,
            "_publish_operator_notice_from_autonomy",
            return_value={},
        ), mock.patch.object(
            autonomy_maintenance,
            "_publish_operator_notices_from_work_tree",
            return_value=[],
        ):
            autonomy_maintenance._run_autonomy_orchestrator_advisory(state, {"mode": "enforce"})

        self.assertEqual(state.get("last_nova_mission"), green_mission)
        self.assertEqual((state.get("last_autonomy_orchestrator") or {}).get("mission_snapshot"), green_mission)

    def test_triage_hints_for_orchestrator_use_live_subconscious_triage(self):
        report = {
            "_source_freshness_sec": 9,
            "families": [
                {
                    "family_id": "patch-routing-fallthrough-family",
                    "target_seam": "patch_routing_fallthrough",
                    "training_priorities": [
                        {
                            "seam": "patch_routing_fallthrough",
                            "signal": "fallback_overuse",
                            "robustness": 0.97,
                            "suggested_test_name": "test_patch_routing_route",
                            "rationale": "Patch routing slipped to fallback.",
                            "urgency": "high",
                        }
                    ],
                    "variation_results": [],
                }
            ],
        }
        generated_queue = {
            "status": "actionable",
            "drift_count": 2,
            "next_item": {
                "file": "subconscious_patch-routing-fallthrough-family_patch-apply-direct-tool.json",
                "highest_priority": {
                    "seam": "patch_routing_fallthrough",
                    "signal": "fallback_overuse",
                    "robustness": 0.97,
                },
            },
        }

        hints = autonomy_maintenance._triage_hints_for_orchestrator(
            {"pulse": {"fallback_overuse_score": 0.1}},
            generated_queue,
            latest_report=report,
            state={"last_regression_status": "OK"},
            kidney_summary={"mode": "enforce", "candidate_count": 3},
        )

        self.assertEqual(hints.get("source"), "subconscious_work_tree_triage")
        self.assertEqual(hints.get("source_freshness_sec"), 9)
        self.assertEqual(hints.get("approved_review_count"), 1)
        self.assertAlmostEqual((hints.get("lane_pressure_scores") or {}).get("patch_queue"), 0.97)
        self.assertAlmostEqual((hints.get("lane_pressure_scores") or {}).get("generated_queue"), 0.97)
        self.assertAlmostEqual((hints.get("owner_pressure_scores") or {}).get("supervisor"), 0.97)
        self.assertIn("generated:subconscious_patch-routing-fallthrough-family_patch-apply-direct-tool.json", hints.get("likely_owner_by_branch") or {})
        top = (hints.get("top_triage_candidates") or [])[0]
        self.assertEqual(top.get("preferred_owner"), "supervisor")
        self.assertEqual(top.get("review_contract"), "subconscious.review.supervisor")

    def test_subconscious_triage_signals_use_evidence_first_work_tree_tasks(self):
        report = {
            "_source_freshness_sec": 4,
            "families": [
                {
                    "family_id": "patch-routing-fallthrough-family",
                    "target_seam": "patch_routing_fallthrough",
                    "training_priorities": [
                        {
                            "seam": "patch_routing_fallthrough",
                            "signal": "fallback_overuse",
                            "robustness": 0.97,
                            "suggested_test_name": "test_patch_routing_route",
                            "rationale": "Patch routing slipped to fallback.",
                            "urgency": "high",
                        }
                    ],
                    "variation_results": [],
                }
            ],
        }

        signals = autonomy_maintenance._subconscious_triage_signals_for_work_tree(
            state={"last_regression_status": "OK"},
            generated_queue={"status": "clear", "open_count": 0},
            latest_report=report,
            kidney_summary={"mode": "enforce", "candidate_count": 0},
        )

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.get("signal_class"), "subconscious_candidate")
        self.assertNotIn("Run or inspect", signal.get("next_task") or "")
        self.assertIn("Find route evidence", signal.get("next_task") or "")
        self.assertEqual(signal.get("preferred_tool"), "find")
        sequence = list(signal.get("task_sequence") or [])
        self.assertEqual(sequence[0].get("tool_args"), ["patch_routing_fallthrough", "subconscious_live_simulator.py"])
        self.assertEqual(sequence[1].get("tool_args"), ["fallback_overuse", "services"])
        self.assertEqual(sequence[2].get("tool_args"), ["runtime/subconscious_runs/latest.json"])
        self.assertEqual(signal.get("blocked_reason"), "subconscious_pressure_owner_repair_required")
        self.assertTrue((signal.get("payload") or {}).get("review_gate", {}).get("approved"))

    def test_subconscious_triage_skips_candidate_with_no_owner_root_judgment(self):
        self._isolated_work_tree_db()
        report = {
            "_source_freshness_sec": 4,
            "families": [
                {
                    "family_id": "repeated-weak-pressure-family",
                    "target_seam": "subconscious_pressure_backlog_generation",
                    "training_priorities": [
                        {
                            "seam": "subconscious_pressure_backlog_generation",
                            "signal": "route_fit_weak",
                            "robustness": 0.97,
                            "suggested_test_name": "test_route_probe_exposes_weak_fit_without_forcing_routing",
                            "rationale": "Robust family pressure kept surfacing route_fit_weak.",
                            "urgency": "high",
                        }
                    ],
                    "variation_results": [],
                }
            ],
        }
        family = dict((report.get("families") or [])[0])
        priority = dict((family.get("training_priorities") or [])[0])
        seed_signal = autonomy_maintenance._triage_signal_from_priority(family, priority, {})
        source_key = autonomy_maintenance.WORK_TREE_SIGNAL_INGESTION_SERVICE.source_key_for_signal(seed_signal)
        tree = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            str(seed_signal.get("title") or "Review subconscious pressure"),
            "subconscious",
            tree.root_branch_id,
        )
        branch.source_type = "subconscious"
        branch.source_key = source_key
        branch.source_payload = dict(seed_signal.get("payload") or {})
        task = work_tree.add_task_to_branch(
            branch.branch_id,
            "Synthesize subconscious review judgment for subconscious_pressure_backlog_generation / route_fit_weak",
        )
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=task.task_id,
            tool_name="subconscious_review_judgment",
            tool_args=[branch.branch_id],
            result=(
                "Subconscious Review Judgment\n"
                "- verdict: no_owner_root_repair\n"
                "- classification: authority_rejected\n"
                "- root cause: probe supervisor_viable=False fulfillment_viable=False\n"
            ),
        )
        work_tree.mark_task_complete(task.task_id)

        signals = autonomy_maintenance._subconscious_triage_signals_for_work_tree(
            state={"last_regression_status": "OK"},
            generated_queue={"status": "clear", "open_count": 0},
            latest_report=report,
            kidney_summary={"mode": "enforce", "candidate_count": 0},
        )

        self.assertEqual(signals, [])

    def test_run_once_keeps_same_day_failed_regression_current_when_regression_is_skipped(self):
        today = time.strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            latest_path = runtime_dir / "subconscious_runs" / "latest.json"
            latest_path.parent.mkdir(parents=True, exist_ok=True)
            latest_path.write_text(json.dumps({"generated_at": f"{today} 08:00:00", "families": []}, ensure_ascii=True), encoding="utf-8")
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"
            state_path.write_text(
                json.dumps(
                    {
                        "last_regression_date": today,
                        "last_regression_status": "FAILED",
                        "last_regression_stale": False,
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )

            def _generated_queue_cycle(state):
                autonomy_maintenance._record_generated_queue_run(
                    state,
                    True,
                    "generated_work_queue_clear",
                    {
                        "work_queue": {
                            "status": "clear",
                            "open_count": 0,
                            "actionable_count": 0,
                            "blocked_count": 0,
                            "count": 7,
                        }
                    },
                )
                payload = {
                    "ts": "2026-04-23 08:00:01",
                    "status": "idle",
                    "tree_id": "tree_generated_demo",
                    "tree_title": autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE,
                    "tree_count": 1,
                    "executed_count": 0,
                    "reason": "no_actionable_generated_queue_item",
                    "actionable_count": 0,
                    "queue_status": "clear",
                }
                state["last_generated_queue_tree_cycle"] = payload
                return payload

            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(autonomy_maintenance, "LATEST_SUBCONSCIOUS", latest_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "STATE_FILE", state_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "MAINT_LOG", log_path))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_subconscious_pack", return_value=(True, "ok")))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_generated_queue_work_tree", return_value={"ts": "2026-04-23 08:00:01", "status": "ok", "tree_id": "tree_generated_demo", "tree_title": autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE, "queue_status": "clear", "queue_count": 7, "open_count": 0, "actionable_count": 0, "blocked_count": 0, "created_count": 0, "updated_count": 0, "reopened_count": 0, "retired_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_generated_queue_work_tree_cycle", side_effect=_generated_queue_cycle))
                stack.enter_context(mock.patch.object(autonomy_maintenance.kidney, "run_kidney", return_value={"ts": "2026-04-23 08:00:01", "mode": "enforce", "candidate_count": 0, "archive_count": 0, "delete_count": 0, "snapshot_path": ""}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_patch_queue_cleanup", return_value={"ts": "2026-04-23 08:00:01", "status": "ok"}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_patch_queue_work_tree", return_value={"ts": "2026-04-23 08:00:01", "status": "ok", "tree_id": "tree_demo", "tree_title": "Patch Queue", "apply_ready_count": 0, "created_count": 0, "updated_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_patch_queue_work_tree_cycle", return_value={"ts": "2026-04-23 08:00:01", "status": "idle", "tree_count": 1, "executed_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_active_work_tree_cycle", return_value={"ts": "2026-04-23 08:00:01", "status": "idle", "tree_count": 0, "executed_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_legacy_maintenance_execution_enabled", return_value=True))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_retire_legacy_patch_update_trees", return_value={"ts": "2026-04-23 08:00:01", "status": "idle", "retired_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_run_daily_regression_if_due", return_value="daily_regression_skipped_already_ran"))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_reevaluate_pending_review_queue", return_value={"status": "ok", "reevaluated_count": 0, "moved_promoted_count": 0, "moved_quarantined_count": 0}))
                def _mock_sync_signal(state, kidney_summary=None, temporal_feed=None, **kwargs):
                    payload = {
                        "status": "ok", "result_count": 0, "resolved_count": 0,
                        "subconscious_signal_count": 0, "active_regression_failure": False,
                        "last_regression_stale": bool(state.get("last_regression_stale")),
                        "last_regression_status": str(state.get("last_regression_status") or ""),
                    }
                    state["last_signal_ingestion"] = payload
                    return payload
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_signal_intake_work_tree", side_effect=_mock_sync_signal))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_stale_complete_trees", return_value={"status": "idle", "archived_count": 0, "retained_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_empty_active_trees", return_value={"status": "idle", "archived_count": 0, "skipped_recent_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_archive_stale_cli_active_trees", return_value={"status": "idle", "archived_count": 0, "skipped_recent_count": 0, "skipped_complex_count": 0}))
                stack.enter_context(mock.patch.object(autonomy_maintenance, "_sync_regression_status_from_file", return_value=False))
                stack.enter_context(mock.patch.object(
                    autonomy_maintenance,
                    "_run_autonomy_orchestrator_advisory",
                    side_effect=lambda state, _kidney: state.setdefault(
                        "last_autonomy_orchestrator",
                        {
                            "decision": "defer_with_reason",
                            "action": {},
                            "reason": "test advisory",
                            "ledger_status": "recorded",
                        },
                    ),
                ))
                code = autonomy_maintenance.run_once()

            self.assertEqual(code, 0)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertFalse(state.get("last_regression_stale"))
            self.assertEqual(state.get("last_regression_status"), "FAILED")
            self.assertEqual((state.get("last_generated_queue_run") or {}).get("status"), "clear")
            self.assertFalse(bool((state.get("last_signal_ingestion") or {}).get("last_regression_stale")))

    def test_sync_signal_intake_work_tree_creates_regression_branch_for_live_failure(self):
        self._isolated_work_tree_db()
        state = {
            "last_regression_status": "FAILED",
            "last_regression_stale": False,
        }

        release_patch, maturity_patch = self._patch_signal_intake_external_signals()
        with release_patch, maturity_patch, mock.patch.object(
            autonomy_maintenance.nova_core,
            "build_pulse_payload",
            return_value={"memory_health_status": "ok", "memory_health_issue_count": 0, "memory_health_issues": [], "memory_health": {"status": "ok", "issue_count": 0}},
        ), mock.patch.object(autonomy_maintenance.nova_core, "mem_enabled", return_value=True), \
             mock.patch.object(autonomy_maintenance.VALIDATION_ARTIFACT_TRUTH_SERVICE, "payload", return_value={"ok": True, "status": "ok"}), \
             mock.patch.object(autonomy_maintenance, "_live_control_status_payload_for_signal_ingestion", side_effect=lambda payload: payload):
            payload = autonomy_maintenance._sync_signal_intake_work_tree(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertTrue(payload.get("active_regression_failure"))
        self.assertEqual(payload.get("created_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(str(branch.work_class or ""), "regression_failure")
        self.assertEqual(str(branch.source_type or ""), "test_ecosystem")
        self.assertEqual((branch.source_payload or {}).get("test_ecosystem_signal"), "daily_regression")
        self.assertEqual(str(branch.resolution_state or ""), "open")
        self.assertEqual(branch.status, work_tree.BranchStatus.READY)

    def test_live_control_status_fetch_uses_release_safe_timeout(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'{"release_status":{"latest_readiness_state":"source-changed-after-build"}}'

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "http_full"), \
             mock.patch.object(autonomy_maintenance, "CONTROL_STATUS_TIMEOUT_SEC", 10.0), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", return_value=_Response()) as mocked:
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("signal_ingestion_status_source"), "control_status_http")
        self.assertEqual((payload.get("release_status") or {}).get("latest_readiness_state"), "source-changed-after-build")
        self.assertEqual(mocked.call_args_list[0].kwargs.get("timeout"), 10.0)

    def test_live_control_status_enriches_missing_model_runtime_keys_from_local_probe(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}
        slim_http = {
            "ok": True,
            "ollama_api_up": True,
            "last_intent": "ping",
            "last_planner_decision": "llm_fallback",
            "last_route_summary": "input:received",
        }
        ollama_health = {
            "ok": True,
            "server_ok": True,
            "status": "ready",
            "info": "",
            "tags_ok": True,
            "chat_route_ok": True,
            "version": "0.12.3",
            "version_ok": True,
            "version_status": 200,
            "api_contract_status": "ok",
            "chat_model": "llama3.2:3b",
            "model_available": True,
            "model_status": "available",
            "available_models": ["llama3.2:3b"],
        }
        port_payload = {"ok": True, "status": "ok", "issue_count": 0, "ports": []}

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(slim_http).encode("utf-8")

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "http_full"), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", return_value=_Response()), \
             mock.patch.object(autonomy_maintenance.nova_core, "ollama_health_payload", return_value=ollama_health), \
             mock.patch.object(autonomy_maintenance, "_probe_local_port_ownership", return_value=port_payload):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("signal_ingestion_status_source"), "control_status_http")
        self.assertTrue(payload.get("ollama_api_up"))
        self.assertEqual(payload.get("ollama_version"), "0.12.3")
        self.assertEqual(payload.get("ollama_api_contract_status"), "ok")
        self.assertTrue(payload.get("ollama_chat_route_ok"))
        self.assertEqual((payload.get("ollama_health") or {}).get("version"), "0.12.3")
        self.assertEqual((payload.get("port_ownership") or {}).get("status"), "ok")
        model_runtime = next(
            row for row in list((payload.get("root_closure_inventory") or {}).get("roots") or [])
            if (row or {}).get("root_id") == "model_runtime"
        )
        self.assertTrue(model_runtime.get("ok"))

    def test_local_first_status_uses_surfaces_timeout_and_merges_supplement_keys(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}
        slim_http = {
            "status_kind": "signal_ingestion_surfaces",
            "operator_outbox_open_count": 2,
            "release_status": {"latest_readiness_state": "ready"},
            "alerts": ["operator_outbox_open"],
        }

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(slim_http).encode("utf-8")

        observe_policy = {
            "layers": {
                "leah": {"mode": "observe", "promoted_capabilities": []},
                "codegen": {"mode": "observe", "promoted_capabilities": []},
            }
        }
        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_first"), \
             mock.patch.object(autonomy_maintenance, "CONTROL_STATUS_SURFACES_TIMEOUT_SEC", 3.0), \
             mock.patch.object(autonomy_maintenance, "CONTROL_STATUS_TIMEOUT_SEC", 3.0), \
             mock.patch.object(autonomy_maintenance.nova_core, "load_policy", return_value=observe_policy), \
             mock.patch.object(autonomy_maintenance, "_probe_local_ollama_health", return_value={"ok": True, "server_ok": True}), \
             mock.patch.object(autonomy_maintenance, "_probe_local_port_ownership", return_value={"status": "ok"}), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", return_value=_Response(), create=True) as mocked:
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("signal_ingestion_status_source"), "local_first_with_http_surfaces")
        self.assertEqual(payload.get("operator_outbox_open_count"), 2)
        self.assertEqual(payload.get("alerts"), ["operator_outbox_open"])
        timeouts = [
            float(call.kwargs.get("timeout"))
            for call in mocked.call_args_list
            if call.kwargs.get("timeout") is not None
        ]
        self.assertIn(3.0, timeouts)

    def test_local_first_status_restores_disk_maintenance_when_surfaces_fetch_fails(self):
        disk_state = {
            "last_regression_status": "OK",
            "last_regression_stale": False,
            "last_core_thinning_sync": {
                "order_count": 8,
                "executable_count": 0,
                "satisfied_active_count": 8,
                "owner_verdict": {
                    "owner": "core_thinning",
                    "evidence": {"order_count": 8, "executable_count": 0, "satisfied_active_count": 8},
                },
            },
        }
        ollama_down = {
            "ok": False,
            "server_ok": False,
            "status": "tags_unreachable",
            "tags_ok": False,
            "chat_route_ok": False,
            "api_contract_status": "tags_unreachable",
        }

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_first"), \
             mock.patch.object(autonomy_maintenance, "_load_state", return_value=disk_state), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", side_effect=TimeoutError("slow surfaces")), \
             mock.patch.object(autonomy_maintenance.nova_core, "ollama_health_payload", return_value=ollama_down):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion({"alerts": []})

        self.assertEqual(payload.get("signal_ingestion_status_source"), "local_dependency_probe")
        self.assertEqual(payload.get("ollama_api_contract_status"), "tags_unreachable")
        self.assertEqual(payload.get("last_regression_status"), "OK")
        self.assertEqual(int(payload.get("core_thinning_order_count", 0) or 0), 8)
        maintenance = dict(payload.get("autonomy_maintenance") or {})
        self.assertEqual(maintenance.get("last_regression_status"), "OK")
        self.assertEqual(int((maintenance.get("last_core_thinning_sync") or {}).get("order_count", 0) or 0), 8)

    def test_local_first_status_restores_missing_thinning_from_disk_when_regression_preseeded(self):
        disk_state = {
            "last_regression_status": "OK",
            "last_core_thinning_sync": {
                "order_count": 8,
                "executable_count": 0,
                "satisfied_active_count": 8,
            },
        }
        fallback = {
            "alerts": [],
            "autonomy_maintenance": {"last_regression_status": "OK"},
            "last_regression_status": "OK",
        }

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_first"), \
             mock.patch.object(autonomy_maintenance, "_load_state", return_value=disk_state), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", side_effect=TimeoutError("slow surfaces")), \
             mock.patch.object(autonomy_maintenance.nova_core, "ollama_health_payload", return_value={"ok": True, "server_ok": True}):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("last_regression_status"), "OK")
        self.assertEqual(int(payload.get("core_thinning_order_count", 0) or 0), 8)
        maintenance = dict(payload.get("autonomy_maintenance") or {})
        self.assertEqual(int((maintenance.get("last_core_thinning_sync") or {}).get("order_count", 0) or 0), 8)

    def test_local_dependency_probe_enriches_layer_maturity_observe_mode(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}

        observe_policy = {
            "layers": {
                "leah": {"mode": "observe", "promoted_capabilities": []},
                "codegen": {"mode": "observe", "promoted_capabilities": []},
            }
        }
        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_only"), \
             mock.patch.object(autonomy_maintenance.nova_core, "load_policy", return_value=observe_policy), \
             mock.patch.object(autonomy_maintenance, "_probe_local_ollama_health", return_value={"ok": True, "server_ok": True}), \
             mock.patch.object(autonomy_maintenance, "_probe_local_port_ownership", return_value={"status": "ok"}):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertTrue(payload.get("suppress_capability_gap_signals"))
        self.assertEqual((payload.get("layer_maturity") or {}).get("leah_observe_mode"), True)
        self.assertEqual((payload.get("layer_maturity") or {}).get("codegen_observe_mode"), True)

    def test_local_dependency_probe_enriches_frontdoor_cli_surfaces(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_only"), \
             mock.patch.object(autonomy_maintenance, "_probe_local_ollama_health", return_value={"ok": True, "server_ok": True}), \
             mock.patch.object(autonomy_maintenance, "_probe_local_port_ownership", return_value={"status": "ok"}):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("frontdoor_cli_status"), "ok")
        self.assertTrue((payload.get("cli_http_parity") or {}).get("ok"))
        self.assertGreaterEqual(int(payload.get("backend_command_count") or 0), 4)
        self.assertIsInstance(payload.get("backend_commands"), list)

    def test_local_dependency_probe_enriches_runtime_control_surfaces(self):
        from services.work_tree_signal_ingestion import _control_status_runtime_signals

        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}
        guard_status = {"running": True, "status": "running", "pid": 101}
        core_status = {"running": True, "status": "running", "pid": 202, "heartbeat_age_sec": 2}
        webui_status = {"running": True, "status": "running", "pid": 303}

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_only"), \
             mock.patch.object(autonomy_maintenance, "_probe_local_ollama_health", return_value={"ok": True, "server_ok": True}), \
             mock.patch.object(autonomy_maintenance, "_probe_local_port_ownership", return_value={"status": "ok"}), \
             mock.patch.object(autonomy_maintenance, "_maintenance_guard_status_payload", return_value=guard_status), \
             mock.patch.object(autonomy_maintenance, "_maintenance_core_status_payload", return_value=core_status), \
             mock.patch.object(autonomy_maintenance, "_maintenance_webui_status_payload", return_value=webui_status):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("guard"), guard_status)
        self.assertEqual(payload.get("core"), core_status)
        self.assertEqual(payload.get("webui"), webui_status)
        self.assertTrue(payload.get("maintenance_scheduler_active"))
        self.assertEqual(int(payload.get("core_heartbeat_age_sec") or 0), 2)
        self.assertEqual(_control_status_runtime_signals(payload), [])

    def test_local_first_preserves_http_root_closure_inventory(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}
        slim_http = {
            "status_kind": "signal_ingestion_surfaces",
            "root_closure_inventory": {
                "ok": True,
                "gap_count": 0,
                "gap_roots": [],
                "roots": [
                    {"root_id": "runtime_core", "ok": True},
                    {"root_id": "model_runtime", "ok": True},
                ],
            },
            "root_closure_inventory_ok": True,
            "root_closure_inventory_gap_count": 0,
            "release_status": {"latest_readiness_state": "ready"},
        }

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(slim_http).encode("utf-8")

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_first"), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", return_value=_Response()), \
             mock.patch.object(autonomy_maintenance, "_probe_local_ollama_health", return_value={"ok": True, "server_ok": True}), \
             mock.patch.object(autonomy_maintenance, "_probe_local_port_ownership", return_value={"status": "ok"}):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("root_closure_inventory_gap_count"), 0)
        self.assertTrue(payload.get("root_closure_inventory_ok"))
        from services.work_tree_signal_ingestion import _root_closure_inventory_signals_from_status

        self.assertEqual(_root_closure_inventory_signals_from_status(payload), [])

    def test_merge_authoritative_wiring_status_keys_pulls_web_enabled_from_http(self):
        fallback = {"alerts": []}
        http_payload = {
            "web_enabled": True,
            "guard": {"ok": True},
            "core": {"ok": True},
            "webui": {"ok": True},
            "runtime_summary": {"ok": True},
            "memory_health": {"ok": True},
            "work_tree_open_task_count": 0,
        }

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(http_payload).encode("utf-8")

        with mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", return_value=_Response()):
            merged = autonomy_maintenance._merge_authoritative_wiring_status_keys(fallback)

        self.assertTrue(merged.get("web_enabled"))
        self.assertFalse(autonomy_maintenance._status_payload_missing_root_closure_truth_markers(merged))

    def test_local_dependency_probe_closes_core_gate_roots_without_http(self):
        from services.layer_maturity_policy import CORE_GATE_ROOT_IDS, evaluate_core_gate

        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}
        release_status = {
            "latest_readiness_state": "ready",
            "latest_source_changed_after_build": False,
            "runtime_drift_expected": False,
        }

        release_truth = {
            "suppress_closure_inventory_signals": False,
            "latest_readiness_state": "ready",
            "runtime_drift_expected": False,
        }
        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_only"), \
             mock.patch.object(autonomy_maintenance, "_probe_local_ollama_health", return_value={"ok": True, "server_ok": True, "version": "0.12.3", "api_contract_status": "ok", "chat_route_ok": True}), \
             mock.patch.object(autonomy_maintenance, "_probe_local_port_ownership", return_value={"status": "ok"}), \
             mock.patch.object(autonomy_maintenance, "_local_release_status_for_signal_ingestion", return_value=release_status), \
             mock.patch.object(autonomy_maintenance, "enrich_release_status", side_effect=lambda payload: dict(payload or {})), \
             mock.patch.object(autonomy_maintenance, "build_release_runtime_truth_summary", return_value=release_truth), \
             mock.patch("services.layer_maturity_policy.release_drift_suppresses_closure_signals", return_value=False):
            payload = autonomy_maintenance._apply_release_runtime_truth_to_status_payload(
                autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback),
                state={},
            )

        inventory = payload.get("root_closure_inventory") or {}
        roots_by_id = {
            str(row.get("root_id") or ""): row
            for row in list(inventory.get("roots") or [])
            if isinstance(row, dict)
        }
        for root_id in CORE_GATE_ROOT_IDS:
            self.assertTrue((roots_by_id.get(root_id) or {}).get("ok"), root_id)
        live_closure = payload.get("live_closure_inventory") or {}
        self.assertEqual(live_closure.get("proof_scope"), "live_closure")
        core_gate = evaluate_core_gate(payload)
        self.assertFalse(core_gate.get("drift_blocked"))
        self.assertEqual(core_gate.get("missing_roots"), [])
        if int(live_closure.get("gap_count", 0) or 0) > 0:
            self.assertFalse(core_gate.get("ok"))
            self.assertTrue(core_gate.get("live_closure_gap_roots"))
        else:
            self.assertTrue(core_gate.get("ok"))
        self.assertIn("operator_macros", payload)
        self.assertIn("operator_outbox", payload)
        self.assertIn("requests_total", payload)
        self.assertIn("chat_login_enabled", payload)

    def test_apply_release_runtime_truth_adds_drift_summary_and_http_probe(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}
        state: dict = {}
        slim_http = {
            "release_status": {
                "latest_readiness_state": "source-changed-after-build",
                "latest_source_changed_after_build": True,
                "latest_version": "2026.06.29.1",
            },
            "ollama_api_up": True,
            "ollama_health": {"ok": True},
            "ollama_version": "0.12.3",
            "ollama_api_contract_status": "ok",
            "ollama_chat_route_ok": True,
            "port_ownership": {"status": "ok"},
        }

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(slim_http).encode("utf-8")

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_first"), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", return_value=_Response()), \
             mock.patch.object(autonomy_maintenance, "_local_release_status_for_signal_ingestion", return_value={}):
            payload = autonomy_maintenance._apply_release_runtime_truth_to_status_payload(
                autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback),
                state=state,
            )

        self.assertTrue((payload.get("release_runtime_truth") or {}).get("suppress_closure_inventory_signals"))
        self.assertTrue(payload.get("http_model_runtime_probe_ok"))
        self.assertEqual(state.get("last_http_model_runtime_probe", {}).get("ok"), True)
        self.assertTrue((state.get("last_release_runtime_truth") or {}).get("runtime_drift_expected"))

    def test_release_drift_invalidates_control_status_cache_once(self):
        calls: list[str] = []

        class _FakeNovaHttp:
            @staticmethod
            def _invalidate_control_status_cache():
                calls.append("invalidated")

        with mock.patch.dict("sys.modules", {"nova_http": _FakeNovaHttp()}):
            autonomy_maintenance._LAST_KNOWN_RELEASE_DRIFT_STATE = ""
            autonomy_maintenance._maybe_invalidate_control_status_cache_for_release_drift(
                {"latest_readiness_state": "source-changed-after-build"}
            )
            autonomy_maintenance._maybe_invalidate_control_status_cache_for_release_drift(
                {"latest_readiness_state": "source-changed-after-build"}
            )

        self.assertEqual(calls, ["invalidated"])

    def test_live_control_status_timeout_preserves_local_ollama_failure_for_ingestion(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}
        ollama_down = {
            "ok": False,
            "server_ok": False,
            "status": "tags_unreachable",
            "info": "tags failed",
            "tags_ok": False,
            "chat_route_ok": False,
            "model_available": False,
            "chat_model": "llama3.2:3b",
            "api_contract_status": "tags_unreachable",
        }

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "http_full"), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", side_effect=TimeoutError("slow status")), \
             mock.patch.object(autonomy_maintenance.nova_core, "ollama_health_payload", return_value=ollama_down):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("signal_ingestion_status_source"), "local_dependency_probe")
        self.assertFalse(payload.get("ollama_server_ok"))
        self.assertFalse(payload.get("ollama_tags_ok"))
        self.assertEqual(payload.get("ollama_health_status"), "tags_unreachable")
        self.assertEqual(payload.get("ollama_api_contract_status"), "tags_unreachable")

    def test_sync_signal_intake_work_tree_uses_local_validation_truth_when_http_falls_back(self):
        self._isolated_work_tree_db()
        state = {
            "last_regression_status": "OK",
            "last_regression_stale": False,
        }
        clean_memory_pulse = {
            "memory_health_status": "ok",
            "memory_health_issue_count": 0,
            "memory_health_issues": [],
            "memory_health": {"status": "ok", "issue_count": 0},
        }
        validation_truth = {
            "ok": False,
            "status": "llm_unavailable_in_green_regression",
            "current_window_failure_count": 5,
            "current_window_llm_unavailable_count": 5,
            "hidden_by_green_regression": True,
            "latest_regression_status": "OK",
            "latest_regression_at": "2026-05-15 00:08:43",
            "latest_failure": {
                "path": "runtime/validation/actions/2026-05-15_00-08-28_861_fe70e851.json",
                "failure_kind": "llm_service_unavailable",
                "final_answer": "(error: LLM service unavailable)",
            },
        }

        release_patch, maturity_patch = self._patch_signal_intake_external_signals()
        with release_patch, maturity_patch, mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value=clean_memory_pulse), \
             mock.patch.object(autonomy_maintenance.nova_core, "mem_enabled", return_value=True), \
             mock.patch.object(autonomy_maintenance.VALIDATION_ARTIFACT_TRUTH_SERVICE, "payload", return_value=validation_truth), \
             mock.patch.object(autonomy_maintenance, "_live_control_status_payload_for_signal_ingestion", side_effect=lambda payload: payload):
            payload = autonomy_maintenance._sync_signal_intake_work_tree(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertTrue(payload.get("active_regression_failure"))
        self.assertTrue(payload.get("active_validation_artifact_failure"))
        self.assertEqual(payload.get("validation_artifact_failure_count"), 5)
        self.assertEqual(payload.get("created_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branch = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id
        ][0]
        self.assertEqual(str(branch.source_type or ""), "test_ecosystem")
        self.assertEqual(str(branch.work_class or ""), "regression_failure")
        self.assertEqual((branch.source_payload or {}).get("test_ecosystem_signal"), "validation_artifact_truth")

    def test_sync_signal_intake_work_tree_resolves_stale_regression_branch(self):
        self._isolated_work_tree_db()
        live_state = {
            "last_regression_status": "FAILED",
            "last_regression_stale": False,
        }
        clean_memory_pulse = {"memory_health_status": "ok", "memory_health_issue_count": 0, "memory_health_issues": [], "memory_health": {"status": "ok", "issue_count": 0}}
        release_patch, maturity_patch = self._patch_signal_intake_external_signals()
        with release_patch, maturity_patch, mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value=clean_memory_pulse), \
             mock.patch.object(autonomy_maintenance.nova_core, "mem_enabled", return_value=True), \
             mock.patch.object(autonomy_maintenance.VALIDATION_ARTIFACT_TRUTH_SERVICE, "payload", return_value={"ok": True, "status": "ok"}), \
             mock.patch.object(autonomy_maintenance, "_live_control_status_payload_for_signal_ingestion", side_effect=lambda payload: payload):
            autonomy_maintenance._sync_signal_intake_work_tree(live_state)

        stale_state = {
            "last_regression_status": "FAILED",
            "last_regression_stale": True,
        }
        stale_release_patch, stale_maturity_patch = self._patch_signal_intake_external_signals()
        with stale_release_patch, stale_maturity_patch, mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value=clean_memory_pulse), \
             mock.patch.object(autonomy_maintenance.nova_core, "mem_enabled", return_value=True), \
             mock.patch.object(autonomy_maintenance.VALIDATION_ARTIFACT_TRUTH_SERVICE, "payload", return_value={"ok": True, "status": "ok"}), \
             mock.patch.object(autonomy_maintenance, "_live_control_status_payload_for_signal_ingestion", side_effect=lambda payload: payload):
            payload = autonomy_maintenance._sync_signal_intake_work_tree(stale_state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertFalse(payload.get("active_regression_failure"))
        self.assertEqual(payload.get("resolved_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(str(branch.work_class or ""), "regression_failure")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)

    def test_sync_signal_intake_work_tree_passes_memory_health_bootstrap_gap(self):
        self._isolated_work_tree_db()
        state = {
            "last_regression_status": "",
            "last_regression_stale": False,
        }
        memory_pulse = {
            "memory_health_status": "watch",
            "memory_health_issue_count": 2,
            "memory_health_issues": [
                {"code": "learned_facts_missing", "detail": "missing learned facts"},
                {"code": "identity_missing", "detail": "missing identity"},
            ],
            "memory_health": {
                "status": "watch",
                "issue_count": 2,
                "bootstrap": {
                    "memory_enabled": True,
                    "status": "incomplete",
                    "missing": ["learned_facts", "identity"],
                },
            },
            "memory_db_total": 0,
            "memory_events_log_status": "watch",
        }

        release_patch, maturity_patch = self._patch_signal_intake_external_signals()
        with release_patch, maturity_patch, mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value=memory_pulse), \
             mock.patch.object(autonomy_maintenance.nova_core, "mem_enabled", return_value=True), \
             mock.patch.object(autonomy_maintenance.VALIDATION_ARTIFACT_TRUTH_SERVICE, "payload", return_value={"ok": True, "status": "ok"}), \
             mock.patch.object(autonomy_maintenance, "_live_control_status_payload_for_signal_ingestion", side_effect=lambda payload: payload):
            payload = autonomy_maintenance._sync_signal_intake_work_tree(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("created_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(str(branch.source_type or ""), "memory_identity")
        self.assertEqual(str(branch.work_class or ""), "governance_pressure")
        self.assertEqual(str(branch.source_key or ""), "governance_pressure:memory_identity:memory_bootstrap_incomplete:identity_memory")
        self.assertEqual(branch.preferred_tool, "pulse")
        self.assertEqual(branch.allowed_tools, ["pulse"])
        self.assertEqual(len(work_tree.list_branch_tasks(branch.branch_id)), 1)

    def test_sync_generated_queue_work_tree_creates_actionable_branch(self):
        self._isolated_work_tree_db()
        state = {}
        item = {
            "file": "subconscious_demo_family_turn.json",
            "actionable": True,
            "latest_status": "drift",
            "family_id": "demo-family",
            "variation_id": "turn-1",
            "opportunity_reason": "parity_drift",
            "highest_priority": {
                "signal": "fallback_overuse",
                "seam": "followup_dispatch",
                "urgency": "high",
                "rationale": "HTTP and CLI diverged on the same followup.",
            },
            "latest_comparison": {
                "diff_count": 2,
                "flagged_probe_count": 1,
            },
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_generated_work_queue",
            return_value={
                "status": "actionable",
                "count": 1,
                "open_count": 1,
                "actionable_count": 1,
                "blocked_count": 0,
                "items": [item],
                "next_item": item,
            },
        ):
            payload = autonomy_maintenance._sync_generated_queue_work_tree(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("created_count"), 1)
        self.assertEqual(payload.get("actionable_count"), 1)
        tree = work_tree.get_tree(payload.get("tree_id"))
        self.assertIsNotNone(tree)
        self.assertEqual(tree.title, autonomy_maintenance.GENERATED_QUEUE_TREE_TITLE)

        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Repair generated session: subconscious_demo_family_turn.json")
        self.assertEqual(branch.bucket, autonomy_maintenance.GENERATED_QUEUE_BUCKET)
        self.assertEqual(branch.source_type, autonomy_maintenance.GENERATED_QUEUE_SOURCE_TYPE)
        self.assertEqual(branch.source_key, "generated_session::subconscious_demo_family_turn.json")
        self.assertEqual(branch.preferred_tool, "generated_queue_run")
        self.assertEqual(branch.allowed_tools, ["generated_queue_run"])
        self.assertIn("Family: demo-family", branch.notes)
        self.assertIn("Rationale: HTTP and CLI diverged on the same followup.", branch.notes)

        tasks = work_tree.list_branch_tasks(branch.branch_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "run generated session subconscious_demo_family_turn.json")
        self.assertEqual(tasks[0].meta.get("session_file"), "subconscious_demo_family_turn.json")
        self.assertEqual(tasks[0].meta.get("family_id"), "demo-family")
        self.assertEqual(tasks[0].meta.get("variation_id"), "turn-1")
        self.assertTrue(tasks[0].meta.get("recurring_finding_key"))

    def test_sync_generated_queue_work_tree_reopen_bumps_lifecycle_and_task_version(self):
        from services.recurring_finding_lifecycle import KEY_VERSION, read_branch_lifecycle

        self._isolated_work_tree_db()
        state = {}
        item = {
            "file": "subconscious_reopen_turn.json",
            "actionable": True,
            "latest_status": "drift",
            "family_id": "demo-family",
            "variation_id": "turn-2",
            "opportunity_reason": "parity_drift",
        }
        queue_payload = {
            "status": "actionable",
            "count": 1,
            "open_count": 1,
            "actionable_count": 1,
            "blocked_count": 0,
            "items": [item],
            "next_item": item,
        }

        with mock.patch.object(autonomy_maintenance, "_generated_work_queue", return_value=queue_payload):
            first = autonomy_maintenance._sync_generated_queue_work_tree(state)
        tree = work_tree.get_tree(str(first.get("tree_id") or ""))
        branch = next(
            b
            for b in work_tree.list_tree_branches(tree.tree_id)
            if str(b.source_type or "") == autonomy_maintenance.GENERATED_QUEUE_SOURCE_TYPE
        )
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        work_tree.complete_task_with_recurring_finding(task.task_id, completion_action="generated_queue_run", ok=True)
        branch.status = work_tree.BranchStatus.COMPLETE
        branch.resolution_state = "resolved"
        work_tree.touch_branch(branch.branch_id)

        with mock.patch.object(autonomy_maintenance, "_generated_work_queue", return_value=queue_payload):
            second = autonomy_maintenance._sync_generated_queue_work_tree(state)

        self.assertEqual(second.get("reopened_count"), 1)
        branch = work_tree.get_branch(branch.branch_id)
        lifecycle = read_branch_lifecycle(branch.source_payload)
        self.assertGreaterEqual(int(lifecycle.get(KEY_VERSION, 0) or 0), 2)
        reopened_task = work_tree.list_branch_tasks(branch.branch_id)[0]
        self.assertEqual(
            str(getattr(getattr(reopened_task, "status", None), "value", getattr(reopened_task, "status", ""))).lower(),
            "open",
        )
        self.assertGreaterEqual(int((reopened_task.meta or {}).get(KEY_VERSION, 0) or 0), 2)

    def test_execute_generated_queue_planned_action_treats_reported_drift_as_completed_run(self):
        with mock.patch.object(
            autonomy_maintenance,
            "_run_test_session_definition",
            return_value=(
                False,
                "generated session drift",
                {
                    "latest_report": {
                        "status": "drift",
                        "run_id": "demo_run",
                        "report_path": "C:/Nova/runtime/test_sessions/reports/demo_run.json",
                    },
                    "stdout": "runner output tail",
                },
            ),
        ):
            result = autonomy_maintenance._execute_generated_queue_planned_action(
                "generated_queue_run",
                ["subconscious_demo_family_turn.json"],
            )

        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("runner_ok"))
        self.assertEqual(result.get("session_file"), "subconscious_demo_family_turn.json")
        self.assertEqual(result.get("report_status"), "drift")
        self.assertEqual(result.get("report_run_id"), "demo_run")
        self.assertEqual(
            result.get("report_path"),
            "C:/Nova/runtime/test_sessions/reports/demo_run.json",
        )

    def test_run_patch_queue_cleanup_records_reductions(self):
        state = {}
        before = {
            "previews_total": 20,
            "review_previews_total": 9,
            "review_previews_orphaned": 4,
            "review_previews_superseded_total": 6,
        }
        after = {
            "previews_total": 14,
            "review_previews_total": 5,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 2,
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", side_effect=[before, after]), \
             mock.patch.object(autonomy_maintenance, "service_patch_preview_summaries", side_effect=[[], [], []]), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_reject_orphaned_previews",
                 return_value={"ok": True, "count": 4, "failed": []},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_archive_superseded_previews",
                 return_value={"ok": True, "count": 3, "failed": [], "archive_dir": "C:/Nova/updates/previews/archive"},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_archive_preview_report",
                 return_value={"ok": True, "name": "archived.txt"},
             ):
            payload = autonomy_maintenance._run_patch_queue_cleanup(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("orphan_rejected_count"), 4)
        self.assertEqual(payload.get("superseded_archived_count"), 3)
        self.assertEqual(payload.get("review_total_before"), 9)
        self.assertEqual(payload.get("review_total_after"), 5)
        self.assertEqual(payload.get("orphaned_before"), 4)
        self.assertEqual(payload.get("orphaned_after"), 0)
        self.assertEqual(payload.get("superseded_before"), 6)
        self.assertEqual(payload.get("superseded_after"), 2)
        self.assertEqual((state.get("last_patch_cleanup") or {}).get("archive_dir"), "C:/Nova/updates/previews/archive")

    def test_auto_apply_if_eligible_skips_definition_only_zip_without_preview(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zip_path = root / "autonomy_micro_patch_demo.zip"
            with autonomy_maintenance.zipfile.ZipFile(zip_path, "w", compression=autonomy_maintenance.zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("runtime/test_sessions/promoted/demo.json", "{}")
                archive.writestr("nova_patch.json", json.dumps({"patch_revision": 1}, ensure_ascii=True))

            with mock.patch.object(autonomy_maintenance.nova_core, "patch_preview") as preview_mock, \
                 mock.patch.object(autonomy_maintenance.nova_core, "execute_patch_action") as apply_mock:
                result = autonomy_maintenance._auto_apply_if_eligible(zip_path)

            self.assertEqual(result, "skipped_generated_definitions_require_review")
            preview_mock.assert_not_called()
            apply_mock.assert_not_called()

    def test_run_patch_queue_cleanup_rejects_definition_only_noop_preview(self):
        state = {}
        before = {
            "previews_total": 1,
            "previews": [{"name": "preview_noop.txt"}],
            "review_previews_total": 1,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        after = {
            "previews_total": 1,
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        noop_row = {
            "name": "preview_noop.txt",
            "path": "C:/Nova/updates/previews/preview_noop.txt",
            "status": "eligible",
            "decision": "pending",
            "artifact_state": "ok",
            "added_files": ["nova_patch.json"],
            "skipped_files": ["runtime/test_sessions/promoted/demo.json"],
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", side_effect=[before, after]), \
             mock.patch.object(autonomy_maintenance, "service_patch_preview_summaries", side_effect=[[noop_row], [], []]), \
             mock.patch.object(autonomy_maintenance.nova_core, "_record_approval", return_value=True) as record_mock, \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_reject_orphaned_previews",
                 return_value={"ok": True, "count": 0, "failed": []},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_archive_superseded_previews",
                 return_value={"ok": True, "count": 0, "failed": [], "archive_dir": ""},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_archive_preview_report",
                 return_value={"ok": True, "name": "archived.txt"},
             ):
            payload = autonomy_maintenance._run_patch_queue_cleanup(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("noop_rejected_count"), 1)
        self.assertEqual(payload.get("review_total_before"), 1)
        self.assertEqual(payload.get("review_total_after"), 0)
        record_mock.assert_called_once()

    def test_run_patch_queue_cleanup_archives_rejected_previews(self):
        state = {}
        before = {
            "previews_total": 3,
            "previews": [{"name": "preview_rejected.txt"}],
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        after = {
            "previews_total": 2,
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        rejected_row = {
            "name": "preview_rejected.txt",
            "path": "C:/Nova/updates/previews/preview_rejected.txt",
            "status": "eligible",
            "decision": "rejected",
            "artifact_state": "orphaned",
            "added_files": ["nova_patch.json"],
            "skipped_files": [],
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", side_effect=[before, after]), \
             mock.patch.object(autonomy_maintenance, "service_patch_preview_summaries", side_effect=[[], [rejected_row], []]), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_reject_orphaned_previews",
                 return_value={"ok": True, "count": 0, "failed": []},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_archive_superseded_previews",
                 return_value={"ok": True, "count": 0, "failed": [], "archive_dir": "C:/Nova/updates/previews/archive"},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_archive_preview_report",
                 return_value={"ok": True, "name": "preview_rejected.txt"},
             ) as archive_mock:
            payload = autonomy_maintenance._run_patch_queue_cleanup(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("rejected_archived_count"), 1)
        archive_mock.assert_called_once()

    def test_run_patch_queue_cleanup_archives_stale_noneligible_previews(self):
        state = {}
        before = {
            "previews_total": 3,
            "previews": [{"name": "preview_incompatible.txt"}],
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        after = {
            "previews_total": 2,
            "review_previews_total": 0,
            "review_previews_orphaned": 0,
            "review_previews_superseded_total": 0,
        }
        stale_row = {
            "name": "preview_incompatible.txt",
            "path": "C:/Nova/updates/previews/preview_incompatible.txt",
            "status": "rejected: incompatible base revision",
            "decision": "pending",
            "artifact_state": "ok",
            "added_files": ["nova_patch.json"],
            "skipped_files": ["runtime/test_sessions/promoted/demo.json"],
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", side_effect=[before, after]), \
             mock.patch.object(autonomy_maintenance, "service_patch_preview_summaries", side_effect=[[], [], [stale_row]]), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_reject_orphaned_previews",
                 return_value={"ok": True, "count": 0, "failed": []},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_bulk_archive_superseded_previews",
                 return_value={"ok": True, "count": 0, "failed": [], "archive_dir": "C:/Nova/updates/previews/archive"},
             ), \
             mock.patch.object(
                 autonomy_maintenance,
                 "service_archive_preview_report",
                 return_value={"ok": True, "name": "preview_incompatible.txt"},
             ) as archive_mock:
            payload = autonomy_maintenance._run_patch_queue_cleanup(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("stale_noneligible_archived_count"), 1)
        archive_mock.assert_called_once()

    def test_sync_patch_queue_work_tree_creates_apply_branch(self):
        self._isolated_work_tree_db()
        state = {}
        row = {
            "name": "preview_demo_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_demo_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "demo_patch.zip",
            "zip_exists": True,
            "zip_path": "C:/Nova/updates/demo_patch.zip",
            "artifact_state": "ok",
            "artifact_reason": "",
            "review_bucket": "approved",
            "collapsed_count": 1,
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [row]}):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("apply_ready_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Apply preview: preview_demo_patch.zip.txt")
        self.assertEqual(branch.preferred_tool, "patch_preview_apply")
        self.assertEqual(list(branch.allowed_tools), autonomy_maintenance.PATCH_QUEUE_EXECUTE_TOOLS)
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].meta.get("patch_preview"), "preview_demo_patch.zip.txt")
        self.assertTrue(tasks[0].meta.get("recurring_finding_key"))

    def test_sync_patch_queue_work_tree_reopen_bumps_lifecycle_and_task_version(self):
        from services.recurring_finding_lifecycle import KEY_VERSION, read_branch_lifecycle

        self._isolated_work_tree_db()
        state = {}
        row = {
            "name": "preview_reopen_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_reopen_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "reopen_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "approved",
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [row]}):
            first = autonomy_maintenance._sync_patch_queue_work_tree(state)
        tree = work_tree.get_tree(str(first.get("tree_id") or ""))
        branch = next(
            item
            for item in work_tree.list_tree_branches(tree.tree_id)
            if str(item.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        )
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        work_tree.complete_task_with_recurring_finding(task.task_id, completion_action="patch_preview_apply", ok=True)
        branch.status = work_tree.BranchStatus.COMPLETE
        branch.resolution_state = "resolved"
        work_tree.touch_branch(branch.branch_id)

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [row]}):
            second = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(second.get("reopened_count"), 1)
        branch = work_tree.get_branch(branch.branch_id)
        lifecycle = read_branch_lifecycle(branch.source_payload)
        self.assertGreaterEqual(int(lifecycle.get(KEY_VERSION, 0) or 0), 2)
        reopened_task = work_tree.list_branch_tasks(branch.branch_id)[0]
        self.assertEqual(
            str(getattr(getattr(reopened_task, "status", None), "value", getattr(reopened_task, "status", ""))).lower(),
            "open",
        )
        self.assertGreaterEqual(int((reopened_task.meta or {}).get(KEY_VERSION, 0) or 0), 2)

    def test_sync_patch_queue_work_tree_keeps_pending_previews_in_review_lane(self):
        self._isolated_work_tree_db()
        state = {}
        selected_row = {
            "name": "preview_selected_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_selected_patch.zip.txt",
            "status": "eligible",
            "decision": "pending",
            "zip_name": "selected_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "pending",
            "preview_kind": "teach_proposal",
            "patch_revision": "4",
            "min_base_revision": "3",
            "mtime": 9,
        }
        other_row = {
            "name": "preview_other_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_other_patch.zip.txt",
            "status": "eligible",
            "decision": "pending",
            "zip_name": "other_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "pending",
            "preview_kind": "autonomy_micro_patch",
            "patch_revision": "4",
            "min_base_revision": "3",
            "mtime": 5,
        }

        with mock.patch.object(
            autonomy_maintenance.nova_core,
            "patch_status_payload",
            return_value={"current_revision": 3, "review_previews": [other_row, selected_row]},
        ):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("approve_ready_count"), 0)
        self.assertEqual(payload.get("pending_count"), 2)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 2)
        for branch in branches:
            self.assertTrue(branch.title.startswith("Review preview:"))
            self.assertEqual(branch.preferred_tool, "find")
            self.assertNotIn("patch_preview_approve", list(branch.allowed_tools or []))

    def test_decide_patch_queue_next_step_prefers_apply_then_approve(self):
        self._isolated_work_tree_db()
        tree = work_tree.initialize_tree("Patch Queue: governed review and apply")
        apply_branch = work_tree.add_branch_to_tree(tree.tree_id, "Apply preview: apply.txt", "patch_queue", tree.root_branch_id)
        approve_branch = work_tree.add_branch_to_tree(tree.tree_id, "Approve preview: approve.txt", "patch_queue", tree.root_branch_id)
        review_branch = work_tree.add_branch_to_tree(tree.tree_id, "Review preview: review.txt", "patch_queue", tree.root_branch_id)
        apply_branch.priority = 90
        approve_branch.priority = 80
        review_branch.priority = 95

        decision = autonomy_maintenance._decide_patch_queue_next_step(
            tree.tree_id,
            [
                {"branch_id": review_branch.branch_id, "recommended_tool": "find"},
                {"branch_id": approve_branch.branch_id, "recommended_tool": "patch_preview_approve"},
                {"branch_id": apply_branch.branch_id, "recommended_tool": "patch_preview_apply"},
            ],
        )
        self.assertEqual(decision.get("branch_id"), apply_branch.branch_id)

        decision = autonomy_maintenance._decide_patch_queue_next_step(
            tree.tree_id,
            [
                {"branch_id": review_branch.branch_id, "recommended_tool": "find"},
                {"branch_id": approve_branch.branch_id, "recommended_tool": "patch_preview_approve"},
            ],
        )
        self.assertIsNone(decision)

    def test_sync_patch_queue_work_tree_reuses_branch_when_preview_transitions(self):
        self._isolated_work_tree_db()
        state = {}
        pending_row = {
            "name": "preview_transition_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_transition_patch.zip.txt",
            "status": "eligible",
            "decision": "pending",
            "zip_name": "transition_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "pending",
        }
        approved_row = dict(pending_row)
        approved_row["decision"] = "approved"
        approved_row["review_bucket"] = "approved"

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [pending_row]}):
            first = autonomy_maintenance._sync_patch_queue_work_tree(state)
        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [approved_row]}):
            second = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(first.get("created_count"), 1)
        self.assertEqual(second.get("updated_count"), 1)
        tree = work_tree.get_tree(str(second.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Apply preview: preview_transition_patch.zip.txt")
        self.assertEqual(branch.preferred_tool, "patch_preview_apply")
        self.assertGreaterEqual(int(branch.evidence_count or 0), 2)
        tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(getattr(task, "status", None), "value", task.status) or "").strip().lower() not in {"complete", "dropped"}
        ]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].meta.get("patch_preview"), "preview_transition_patch.zip.txt")

    def test_run_patch_queue_work_tree_cycle_records_execution(self):
        self._isolated_work_tree_db()
        state = {}
        row = {
            "name": "preview_cycle_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_cycle_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "cycle_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "approved",
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [row]}):
            sync_payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        def _execute(tool_name, tool_args=None):
            self.assertEqual(tool_name, "patch_preview_apply")
            self.assertEqual(tool_args, ["preview_cycle_patch.zip.txt"])
            return {"ok": True, "message": "patch_preview_apply_ok"}

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute), \
             mock.patch.object(
                 autonomy_maintenance,
                 "_sync_patch_queue_work_tree",
                 return_value={
                     "ts": "2026-04-23 00:00:00",
                     "status": "ok",
                     "tree_id": str(sync_payload.get("tree_id") or ""),
                     "tree_title": "Patch Queue",
                     "apply_ready_count": 0,
                     "approve_ready_count": 0,
                     "pending_count": 0,
                     "orphaned_count": 0,
                 },
             ):
            cycle_payload = autonomy_maintenance._run_patch_queue_work_tree_cycle(state)

        self.assertEqual(sync_payload.get("apply_ready_count"), 1)
        self.assertEqual(cycle_payload.get("status"), "ok")
        self.assertEqual(cycle_payload.get("executed_count"), 1)
        self.assertEqual(cycle_payload.get("tree_count"), 1)
        inspect = work_tree.inspect_tree(str(sync_payload.get("tree_id") or ""))
        self.assertIsNotNone(inspect)
        self.assertEqual(inspect.get("counts", {}).get("tasks", {}).get("open"), 0)

    def test_run_active_work_tree_cycle_executes_safe_tree_and_skips_unsafe_tool(self):
        self._isolated_work_tree_db()
        state = {}
        safe_tree = work_tree.initialize_tree(
            "Cli: check queue status",
            meta={"kind": "system", "source": "cli"},
        )
        safe_root = work_tree._BRANCHES[safe_tree.root_branch_id]
        work_tree.add_task_to_branch(safe_root.branch_id, "check queue status")
        work_tree.set_branch_tools(safe_root.branch_id, allowed_tools=["queue_status"], preferred_tool="queue_status")

        unsafe_tree = work_tree.initialize_tree(
            "Cli: update runtime state",
            meta={"kind": "system", "source": "cli"},
        )
        unsafe_root = work_tree._BRANCHES[unsafe_tree.root_branch_id]
        work_tree.add_task_to_branch(unsafe_root.branch_id, "update runtime status accordingly")
        work_tree.set_branch_tools(unsafe_root.branch_id, allowed_tools=["update_now"], preferred_tool="update_now")

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", return_value="Queue is empty."):
            payload = autonomy_maintenance._run_active_work_tree_cycle(state, sync_core_thinning=False)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("executed_count"), 1)
        self.assertEqual(payload.get("tree_count"), 2)
        self.assertEqual(payload.get("skipped_tree_count"), 1)
        skipped = payload.get("skipped") or []
        self.assertEqual(skipped[0].get("tool"), "update_now")
        safe_inspect = work_tree.inspect_tree(safe_tree.tree_id)
        unsafe_inspect = work_tree.inspect_tree(unsafe_tree.tree_id)
        self.assertEqual(safe_inspect.get("status"), "complete")
        self.assertEqual(unsafe_inspect.get("status"), "active")
        self.assertEqual((state.get("last_active_work_tree_cycle") or {}).get("executed_count"), 1)

    def test_run_active_work_tree_cycle_executes_os_capability_lane(self):
        self._isolated_work_tree_db()
        state = {}
        tree = work_tree.initialize_tree(
            "OS capability route",
            meta={"kind": "system", "source": "cli"},
        )
        root = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.set_tree_policy(tree.tree_id, allowed_tools=["os_capability"])
        work_tree.set_branch_tools(
            root.branch_id,
            allowed_tools=["os_capability"],
            preferred_tool="os_capability",
        )
        work_tree.add_task_to_branch(
            root.branch_id,
            "Verify Ollama model with registered capability",
            meta={
                "capability_request": {
                    "capability": "verify_ollama_model",
                    "args": {"probe_chat": False},
                }
            },
        )
        calls = []

        with mock.patch.object(
            autonomy_maintenance.nova_core,
            "execute_planned_action",
            side_effect=lambda tool, args=None: calls.append((tool, list(args or []))) or {"ok": True, "status": "success"},
        ):
            payload = autonomy_maintenance._run_active_work_tree_cycle(state, sync_core_thinning=False)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("executed_count"), 1)
        self.assertEqual(calls[0][0], "os_capability")
        self.assertEqual(
            json.loads(calls[0][1][0]),
            {"capability": "verify_ollama_model", "args": {"probe_chat": False}},
        )

    def test_run_active_work_tree_cycle_executes_core_thinning_lane(self):
        self._isolated_work_tree_db()
        state = {}
        thinning_tree = work_tree.initialize_tree(
            "Core Thinning",
            meta={"kind": "core_thinning", "source": "core_thinning", "work_identity_key": "system:core-thinning"},
        )
        root = work_tree._BRANCHES[thinning_tree.root_branch_id]
        work_tree.add_task_to_branch(
            root.branch_id,
            "thin wrapper shim",
            meta={
                "scope": "single_block_only",
                "target": {
                    "file": "C:/Nova/nova_core.py",
                    "function": "_wrapper_shim",
                    "block": "wrapper_candidate",
                    "name": "_wrapper_shim",
                    "start_line": 10,
                    "end_line": 12,
                },
            },
        )
        work_tree.set_branch_tools(root.branch_id, allowed_tools=["core_thinning"], preferred_tool="core_thinning")

        calls = []

        def _execute(tool_name, tool_args=None):
            calls.append((tool_name, list(tool_args or [])))
            return {"ok": True, "scope_ok": True, "verified": True, "message": "core_thinning_checked"}

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute):
            payload = autonomy_maintenance._run_active_work_tree_cycle(state, max_steps=1, max_trees=1, sync_core_thinning=False)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("executed_count"), 1)
        self.assertEqual(payload.get("skipped_tree_count"), 0)
        self.assertEqual(calls[0][0], "core_thinning")
        self.assertIn("_wrapper_shim", calls[0][1][0])
        self.assertEqual((state.get("last_active_work_tree_cycle") or {}).get("executed_count"), 1)

    def test_run_active_work_tree_cycle_executes_release_validation_lane(self):
        self._isolated_work_tree_db()
        state = {}
        release_tree = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        root = work_tree._BRANCHES[release_tree.root_branch_id]
        work_tree.add_task_to_branch(
            root.branch_id,
            "Run release validation profile from current artifact",
            meta={
                "expected_tool": "release_validation_run",
                "allowed_tools": ["release_validation_run"],
            },
        )
        work_tree.set_branch_tools(
            root.branch_id,
            allowed_tools=["release_validation_run"],
            preferred_tool="release_validation_run",
        )

        calls = []

        def _execute(tool_name, tool_args=None):
            calls.append((tool_name, list(tool_args or [])))
            return "Release Validation Run\n- completed: True\n- validation result: pass-with-notes"

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute):
            payload = autonomy_maintenance._run_active_work_tree_cycle(state, max_steps=1, max_trees=1, sync_core_thinning=False)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("executed_count"), 1)
        self.assertEqual(calls[0][0], "release_validation_run")
        self.assertEqual(calls[0][1], [root.branch_id])

    def test_run_active_work_tree_cycle_honors_target_branch_and_task(self):
        self._isolated_work_tree_db()
        state = {}
        tree = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        root = work_tree._BRANCHES[tree.root_branch_id]
        child = work_tree.add_branch_to_tree(tree.tree_id, "Target branch", "planned", root.branch_id)
        work_tree.add_task_to_branch(
            root.branch_id,
            "Read wrong path",
            meta={"expected_tool": "read", "allowed_tools": ["read"], "tool_args": ["wrong.txt"]},
        )
        target_task = work_tree.add_task_to_branch(
            child.branch_id,
            "Read target path",
            meta={"expected_tool": "read", "allowed_tools": ["read"], "tool_args": ["target.txt"]},
        )
        work_tree.set_branch_tools(root.branch_id, allowed_tools=["read"], preferred_tool="read")
        work_tree.set_branch_tools(child.branch_id, allowed_tools=["read"], preferred_tool="read")
        calls = []

        def _execute(tool_name, tool_args=None):
            calls.append((tool_name, list(tool_args or [])))
            return "target file contents"

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute):
            payload = autonomy_maintenance._run_active_work_tree_cycle(
                state,
                max_steps=1,
                max_trees=1,
                target_branch_id=child.branch_id,
                target_task_id=target_task.task_id,
                sync_core_thinning=False,
            )

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("target_branch_id"), child.branch_id)
        self.assertEqual(payload.get("target_task_id"), target_task.task_id)
        self.assertEqual(calls, [("read", ["target.txt"])])
        self.assertEqual(work_tree._TASKS[target_task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_run_active_work_tree_cycle_resolves_target_tree_outside_candidate_window(self):
        state = {}
        signal_candidate = {
            "tree_id": "tree-signal",
            "title": "Signal Intake: Runtime Governance",
            "status": "active",
            "kind": "signal_ingestion",
            "next_step": {
                "branch_id": "branch-signal",
                "branch_title": "Read signal path",
                "recommended_tool": "read",
            },
        }
        core_payload = {
            "tree_id": "tree-core",
            "title": "Core Thinning",
            "status": "active",
            "kind": "core_thinning",
            "next_step": {
                "branch_id": "branch-core",
                "branch_title": "Review wrapper shim",
                "task_id": "task-core",
                "recommended_tool": "core_thinning",
            },
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_active_work_tree_candidates",
            return_value=[signal_candidate] * 8,
        ) as candidates_mock, mock.patch.object(
            autonomy_maintenance.work_tree,
            "get_visual_tree_data",
            return_value=core_payload,
        ), mock.patch.object(
            autonomy_maintenance.work_tree,
            "run_autonomous_loop",
            return_value=[{"action": "executed", "tool": "core_thinning"}],
        ) as loop_mock:
            payload = autonomy_maintenance._run_active_work_tree_cycle(
                state,
                max_steps=1,
                max_trees=1,
                target_tree_id="tree-core",
                target_branch_id="branch-core",
                target_task_id="task-core",
                target_tool="core_thinning",
                sync_core_thinning=False,
            )

        candidates_mock.assert_not_called()
        loop_mock.assert_called_once()
        self.assertEqual(payload.get("status"), "ok")
        self.assertNotEqual(payload.get("status"), "stale_execution_contract")
        self.assertEqual(payload.get("target_tree_id"), "tree-core")
        self.assertEqual(loop_mock.call_args.args[0], "tree-core")

    def test_pin_active_work_keeps_branch_when_inspector_tool_disagrees(self):
        payload = {
            "tree_id": "tree-signal",
            "title": "Signal Intake: Runtime Governance",
            "status": "active",
            "kind": "signal_ingestion",
            "next_step": {
                "branch_id": "branch-other",
                "task_id": "task-other",
                "recommended_tool": "read",
            },
        }
        pin = {
            "branch_id": "branch-storage",
            "title": "Runtime storage watch reports pressure",
            "task_id": "task-storage",
            "task_title": "Inspect storage watch snapshot and runtime archive growth",
            "recommended_tool": "system_check",
        }
        with mock.patch.object(autonomy_maintenance, "_resolve_targeted_work_pin", return_value=pin):
            pinned = autonomy_maintenance._pin_active_work_payload(
                payload,
                branch_target="branch-storage",
                task_target="task-storage",
                tool_target="read",
            )
        self.assertIsNotNone(pinned)
        self.assertEqual((pinned.get("next_step") or {}).get("recommended_tool"), "system_check")
        self.assertEqual((pinned.get("next_step") or {}).get("branch_id"), "branch-storage")

    def test_target_decider_takes_existing_option_when_pin_missing(self):
        decide = autonomy_maintenance._active_work_tree_target_decider(
            "branch_ghost",
            "task_ghost",
            "core_thinning",
        )
        options = [
            {
                "branch_id": "branch_live",
                "task_id": "task_live",
                "recommended_tool": "read",
                "branch_title": "Live pickup stem",
            }
        ]
        picked = decide("tree_live", options)
        self.assertEqual(picked.get("branch_id"), "branch_live")
        self.assertEqual(picked.get("task_id"), "task_live")
        self.assertNotEqual(picked.get("branch_id"), "branch_ghost")

    def test_leftover_complete_shell_pin_refuses_and_stays_visible(self):
        self._isolated_work_tree_db()
        tree = work_tree.initialize_tree(
            "Http: leftover console shell",
            meta={"kind": "system", "source": "http"},
        )
        root = work_tree._BRANCHES[tree.root_branch_id]
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Http leftover ready", "work", root.branch_id)
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
        done = work_tree.add_task_to_branch(
            branch.branch_id,
            "Seeded complete stem",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        work_tree.mark_task_complete(done.task_id)
        self.assertFalse(
            any(
                task.status not in (work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED)
                for task in work_tree.list_branch_tasks(branch.branch_id)
            )
        )
        visual = work_tree.get_visual_tree_data(tree.tree_id)
        self.assertIsNotNone(visual)
        visual["next_step"] = {
            "branch_id": branch.branch_id,
            "task_id": "",
            "recommended_tool": "read",
        }
        pin = autonomy_maintenance._resolve_targeted_work_pin(
            visual,
            branch_target=branch.branch_id,
        )
        self.assertEqual(pin, {})
        live = work_tree.get_branch(branch.branch_id)
        self.assertIsNotNone(live)
        self.assertNotEqual(str(live.resolution_state or "").strip().lower(), "resolved")
        self.assertNotEqual(str(getattr(live.status, "value", live.status) or "").lower(), "archived")
        self.assertNotEqual(str(getattr(work_tree.get_tree(tree.tree_id).status, "value", "") or "").lower(), "archived")
        from services.solution_trail import JUDGMENT_REFUSED, branch_has_active_refuse

        refuse = branch_has_active_refuse(live, has_open_stem=False)
        self.assertIsNotNone(refuse)
        self.assertEqual(str((refuse or {}).get("judgment") or ""), JUDGMENT_REFUSED)
        self.assertEqual(str((refuse or {}).get("reason") or ""), "complete_without_open_stem")
        still = work_tree.get_visual_tree_data(tree.tree_id)
        node_ids = {item.get("id") for item in (still.get("nodes") or [])}
        self.assertIn(branch.branch_id, node_ids)
        node = next(item for item in (still.get("nodes") or []) if item.get("id") == branch.branch_id)
        kind = node.get("branch_memory_kind") or {}
        self.assertEqual(kind.get("kind"), JUDGMENT_REFUSED)
        self.assertTrue(kind.get("controlling"))
        self.assertFalse(any(str(item.get("branch_id")) == branch.branch_id for item in work_tree.list_autonomous_options(tree.tree_id)))

    def test_non_execute_next_step_is_not_eligible_work(self):
        payload = {
            "status": "active",
            "kind": "core_thinning",
            "next_step": {
                "action": "trail_suppressed",
                "branch_id": "branch_mill",
                "recommended_tool": "core_thinning",
            },
        }
        self.assertFalse(autonomy_maintenance._active_work_tree_payload_eligible(payload))

    def test_planner_executable_requires_live_pickup(self):
        self._isolated_work_tree_db()
        tree = work_tree.initialize_tree("Pickup truth")
        root = work_tree._BRANCHES[tree.root_branch_id]
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Review wrapper shim mill", "core_thinning", root.branch_id)
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["core_thinning"], require_explicit_allow=True)
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["core_thinning"], preferred_tool="core_thinning")
        task = work_tree.add_task_to_branch(branch.branch_id, "Review wrapper shim mill")
        live = {
            "tree_id": tree.tree_id,
            "title": tree.title,
            "status": "active",
            "kind": "core_thinning",
            "next_step": {
                "action": "execute",
                "branch_id": branch.branch_id,
                "task_id": task.task_id,
                "recommended_tool": "core_thinning",
            },
        }
        self.assertTrue(autonomy_maintenance._active_work_candidate_is_executable(live))
        from services.observation_spine import apply_repeated_path_to_trail

        apply_repeated_path_to_trail(
            branch_id=branch.branch_id,
            tool_name="core_thinning",
            task_title=task.title,
            input_ref="core_thinning|",
        )
        self.assertFalse(autonomy_maintenance._active_work_candidate_is_executable(live))

    def test_run_active_work_tree_cycle_keeps_task_open_after_tool_failed(self):
        self._isolated_work_tree_db()
        state = {}
        tree = work_tree.initialize_tree(
            "Core Thinning",
            meta={"source": "core_thinning"},
        )
        root = work_tree._BRANCHES[tree.root_branch_id]
        target_task = work_tree.add_task_to_branch(
            root.branch_id,
            "Review wrapper shim",
            meta={"expected_tool": "read", "allowed_tools": ["read"], "tool_args": ["target.txt"]},
        )
        work_tree.set_branch_tools(root.branch_id, allowed_tools=["read"], preferred_tool="read")

        def _execute(tool_name, tool_args=None):
            return {"ok": False, "reason": "repo_hygiene_failed"}

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute):
            payload = autonomy_maintenance._run_active_work_tree_cycle(
                state,
                max_steps=1,
                max_trees=1,
                target_tree_id=tree.tree_id,
                target_branch_id=root.branch_id,
                target_task_id=target_task.task_id,
                target_tool="read",
                sync_core_thinning=False,
            )

        self.assertEqual(payload.get("status"), "tool_failed")
        self.assertEqual(work_tree._TASKS[target_task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_run_active_work_tree_cycle_uses_target_tree_for_pinned_branch(self):
        self._isolated_work_tree_db()
        state = {}
        signal_tree = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        signal_root = work_tree._BRANCHES[signal_tree.root_branch_id]
        work_tree.add_task_to_branch(
            signal_root.branch_id,
            "Read signal path",
            meta={"expected_tool": "read", "allowed_tools": ["read"], "tool_args": ["signal.txt"]},
        )
        work_tree.set_branch_tools(signal_root.branch_id, allowed_tools=["read"], preferred_tool="read")

        core_tree = work_tree.initialize_tree(
            "Core Thinning",
            meta={"source": "core_thinning"},
        )
        core_root = work_tree._BRANCHES[core_tree.root_branch_id]
        target_task = work_tree.add_task_to_branch(
            core_root.branch_id,
            "Review wrapper shim",
            meta={"expected_tool": "core_thinning", "allowed_tools": ["core_thinning"], "tool_args": ["core"]},
        )
        work_tree.set_branch_tools(core_root.branch_id, allowed_tools=["core_thinning"], preferred_tool="core_thinning")
        calls = []

        def _execute(tool_name, tool_args=None):
            calls.append((tool_name, list(tool_args or [])))
            return {"ok": True}

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute):
            payload = autonomy_maintenance._run_active_work_tree_cycle(
                state,
                max_steps=1,
                max_trees=1,
                target_tree_id=core_tree.tree_id,
                target_branch_id=core_root.branch_id,
                target_task_id=target_task.task_id,
                target_tool="core_thinning",
                sync_core_thinning=False,
            )

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("target_tree_id"), core_tree.tree_id)
        self.assertEqual(payload.get("processed")[0].get("tree_id"), core_tree.tree_id)
        self.assertEqual(calls, [("core_thinning", ["core"])])

    def test_operator_continue_work_answer_feeds_next_active_work_tree_cycle(self):
        self._isolated_work_tree_db()
        state = {}
        tree = work_tree.initialize_tree(
            "Signal Intake: Operator Continuation",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        root = work_tree._BRANCHES[tree.root_branch_id]
        wait_task = work_tree.add_task_to_branch(root.branch_id, "Wait for operator context")
        work_tree.mark_task_blocked(wait_task.task_id, "pending_operator_context")
        next_task = work_tree.add_task_to_branch(
            root.branch_id,
            "Synthesize memory bootstrap judgment from collected evidence",
            meta={
                "expected_tool": "memory_bootstrap_judgment",
                "allowed_tools": ["memory_bootstrap_judgment"],
            },
        )
        work_tree.set_branch_tools(
            root.branch_id,
            allowed_tools=["memory_bootstrap_judgment"],
            preferred_tool="memory_bootstrap_judgment",
        )

        with tempfile.TemporaryDirectory() as td:
            outbox_path = Path(td) / "operator_outbox.jsonl"
            notice = OPERATOR_OUTBOX_SERVICE.append_notice(
                outbox_path,
                source="work_tree",
                severity="attention",
                title="Nova needs operator information",
                message="I need operator context before continuing this branch.",
                dedupe_key=f"work_tree|blocked_task|{root.branch_id}|{wait_task.task_id}|pending_operator_context",
                payload={
                    "tree_id": tree.tree_id,
                    "tree_title": tree.title,
                    "branch_id": root.branch_id,
                    "branch_title": root.title,
                    "task": {
                        "task_id": wait_task.task_id,
                        "title": wait_task.title,
                        "status": "blocked",
                    },
                    "request_kind": "operator_information",
                    "blocked_reason": "pending_operator_context",
                },
                now_fn=lambda: 3000.0,
                uuid_fn=lambda: "noticego",
            )
            event_id = str((notice.get("event") or {}).get("id") or "")
            response = OPERATOR_OUTBOX_SERVICE.respond_to_notice(
                outbox_path,
                event_id=event_id,
                message="Use this as the missing operator context and keep moving.",
                responder="operator",
                resolution="continue_work",
                work_tree_module=work_tree,
                now_fn=lambda: 3005.0,
                uuid_fn=lambda: "responsego",
            )

        calls = []

        def _execute(tool_name, tool_args=None):
            calls.append((tool_name, list(tool_args or [])))
            return "Memory Bootstrap Judgment\n- verdict: continue from operator context"

        with mock.patch.object(autonomy_maintenance.nova_core, "execute_planned_action", side_effect=_execute):
            payload = autonomy_maintenance._run_active_work_tree_cycle(
                state,
                max_steps=1,
                max_trees=1,
                sync_core_thinning=False,
            )

        evidence_tools = [row.get("tool_name") for row in work_tree.list_branch_evidence(root.branch_id)]
        inspect = work_tree.inspect_tree(tree.tree_id)
        self.assertTrue(response.get("ok"))
        self.assertEqual((response.get("work_tree") or {}).get("task_completed"), True)
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("executed_count"), 1)
        self.assertEqual(calls, [("memory_bootstrap_judgment", [])])
        self.assertEqual(work_tree._TASKS[wait_task.task_id].status, work_tree.TaskStatus.COMPLETE)
        self.assertEqual(work_tree._TASKS[next_task.task_id].status, work_tree.TaskStatus.COMPLETE)
        self.assertIn("operator_response", evidence_tools)
        self.assertIn("memory_bootstrap_judgment", evidence_tools)
        self.assertEqual((inspect or {}).get("counts", {}).get("open_tasks"), 0)

    def test_work_tree_pressure_truth_prefers_module_counts_over_stale_payload(self):
        with mock.patch(
            "autonomy_maintenance.build_work_tree_pressure_snapshot_from_module",
            return_value={
                "open_task_count": 1,
                "working_count": 0,
                "blocked_count": 0,
                "operator_hold_count": 0,
                "pending_count": 1,
                "status": "open",
            },
        ):
            pressure = autonomy_maintenance._work_tree_pressure_truth(
                {
                    "counts": {
                        "open_tasks": 9,
                        "blocked": 4,
                        "pending": 3,
                    },
                    "trees": [],
                }
            )

        self.assertEqual(pressure.get("open_task_count"), 1)
        self.assertEqual(pressure.get("blocked_branch_count"), 0)
        self.assertEqual(pressure.get("operator_hold_branch_count"), 0)

    def test_work_tree_snapshot_uses_active_candidate_execution_truth(self):
        snapshot = autonomy_maintenance._work_tree_snapshot_for_orchestrator(
            {"counts": {"active": 30, "open_tasks": 95, "blocked": 37}},
            [
                {
                    "tree_id": "tree-core",
                    "title": "Core Thinning",
                    "status": "active",
                    "kind": "core_thinning",
                    "next_step": {
                        "branch_id": "branch-core",
                        "branch_title": "Review wrapper shim",
                        "recommended_tool": "core_thinning",
                    },
                },
                {
                    "tree_id": "tree-update",
                    "title": "Cli: update runtime",
                    "status": "active",
                    "kind": "system",
                    "next_step": {
                        "branch_id": "branch-update",
                        "branch_title": "Update now",
                        "recommended_tool": "update_now",
                    },
                },
            ],
        )

        self.assertEqual(snapshot.get("active_candidate_count"), 2)
        self.assertEqual(snapshot.get("active_executable_count"), 1)
        self.assertEqual(snapshot.get("active_unsafe_count"), 1)
        self.assertEqual((snapshot.get("branches") or [])[0].get("recommended_tool"), "core_thinning")
        self.assertTrue((snapshot.get("branches") or [])[0].get("executable"))
        self.assertFalse((snapshot.get("branches") or [])[1].get("executable"))

    def test_orchestrator_executed_lane_cycle_preserves_active_cycle_truth(self):
        cycle = autonomy_maintenance._orchestrator_executed_lane_cycle(
            {
                "execution": {
                    "action_type": "active_work_tree_run_next",
                    "result": "success",
                    "extra": {
                        "cycle": {
                            "status": "ok",
                            "tree_count": 8,
                            "executed_count": 1,
                        }
                    },
                }
            },
            "active_work_tree_run_next",
        )

        self.assertEqual(cycle.get("status"), "ok")
        self.assertEqual(cycle.get("executed_count"), 1)
        self.assertTrue(cycle.get("orchestrator_owned"))
        self.assertEqual(cycle.get("orchestrator_action_type"), "active_work_tree_run_next")
        self.assertEqual(
            autonomy_maintenance._orchestrator_executed_lane_cycle(
                {"execution": {"action_type": "generated_queue_run_next"}},
                "active_work_tree_run_next",
            ),
            {},
        )

    def test_run_active_work_tree_cycle_stops_after_one_attempt(self):
        state = {}
        candidates = [
            {
                "tree_id": "tree-blocked",
                "title": "Core Thinning",
                "status": "active",
                "kind": "core_thinning",
                "next_step": {
                    "branch_id": "branch-blocked",
                    "branch_title": "Review wrapper shim",
                    "recommended_tool": "core_thinning",
                },
            },
            {
                "tree_id": "tree-pulse",
                "title": "Cli: nova pulse",
                "status": "active",
                "kind": "system",
                "next_step": {
                    "branch_id": "branch-pulse",
                    "branch_title": "Run pulse",
                    "recommended_tool": "pulse",
                },
            },
        ]

        with mock.patch.object(autonomy_maintenance, "_active_work_tree_candidates", return_value=candidates), \
             mock.patch.object(
                 autonomy_maintenance.work_tree,
                 "run_autonomous_loop",
                 return_value=[
                     {
                         "action": "scope_blocked",
                         "tree_id": "tree-blocked",
                         "tool": "core_thinning",
                     }
                 ],
             ) as loop_mock:
            payload = autonomy_maintenance._run_active_work_tree_cycle(state, max_steps=1, max_trees=2, sync_core_thinning=False)

        loop_mock.assert_called_once()
        self.assertEqual(payload.get("status"), "scope_blocked")
        self.assertEqual(payload.get("attempted_count"), 1)
        self.assertEqual(payload.get("executed_count"), 0)
        self.assertEqual(payload.get("processed_tree_count"), 1)
        self.assertEqual((state.get("last_active_work_tree_cycle") or {}).get("status"), "scope_blocked")

    def test_run_active_work_tree_cycle_climbs_primary_tree_with_step_budget(self):
        """Step budget must climb one ladder, not force max_steps=1 forever."""
        state = {}
        candidates = [
            {
                "tree_id": "tree-release",
                "title": "Signal Intake: Runtime Governance",
                "status": "active",
                "kind": "signal_ingestion",
                "next_step": {
                    "branch_id": "branch-release",
                    "branch_title": "Release package is stale behind live source",
                    "recommended_tool": "release_rebuild_verify",
                },
            },
            {
                "tree_id": "tree-pulse",
                "title": "Cli: nova pulse",
                "status": "active",
                "kind": "system",
                "next_step": {
                    "branch_id": "branch-pulse",
                    "branch_title": "Run pulse",
                    "recommended_tool": "pulse",
                },
            },
        ]

        with mock.patch.object(autonomy_maintenance, "_active_work_tree_candidates", return_value=candidates), \
             mock.patch.object(
                 autonomy_maintenance.work_tree,
                 "run_autonomous_loop",
                 return_value=[
                     {"action": "executed", "tool": "release_rebuild_verify"},
                     {"action": "executed", "tool": "release_validation_run"},
                     {"action": "executed", "tool": "release_promotion_judgment"},
                 ],
             ) as loop_mock:
            payload = autonomy_maintenance._run_active_work_tree_cycle(
                state, max_steps=3, max_trees=2, sync_core_thinning=False
            )

        loop_mock.assert_called_once()
        self.assertEqual(loop_mock.call_args.kwargs.get("max_steps"), 3)
        self.assertEqual(payload.get("executed_count"), 3)
        self.assertEqual(payload.get("attempted_count"), 3)
        self.assertEqual(payload.get("processed_tree_count"), 1)
        self.assertEqual(payload.get("status"), "ok")

    def test_run_active_work_tree_cycle_empty_history_still_consumes_attempt(self):
        state = {}
        candidates = [
            {
                "tree_id": "tree-empty",
                "title": "Core Thinning",
                "status": "active",
                "kind": "core_thinning",
                "next_step": {
                    "branch_id": "branch-empty",
                    "branch_title": "Review wrapper shim",
                    "recommended_tool": "core_thinning",
                },
            },
            {
                "tree_id": "tree-pulse",
                "title": "Cli: nova pulse",
                "status": "active",
                "kind": "system",
                "next_step": {
                    "branch_id": "branch-pulse",
                    "branch_title": "Run pulse",
                    "recommended_tool": "pulse",
                },
            },
        ]

        with mock.patch.object(autonomy_maintenance, "_active_work_tree_candidates", return_value=candidates), \
             mock.patch.object(autonomy_maintenance.work_tree, "run_autonomous_loop", return_value=[]) as loop_mock:
            payload = autonomy_maintenance._run_active_work_tree_cycle(state, max_steps=1, max_trees=2, sync_core_thinning=False)

        loop_mock.assert_called_once()
        self.assertEqual(payload.get("status"), "idle")
        self.assertEqual(payload.get("attempted_count"), 1)
        self.assertEqual(payload.get("executed_count"), 0)
        self.assertEqual(payload.get("processed_tree_count"), 1)

    def test_run_active_work_tree_cycle_resyncs_core_thinning_before_execution(self):
        state = {}
        stale_candidate = {
            "tree_id": "tree-core",
            "title": "Core Thinning",
            "status": "active",
            "kind": "core_thinning",
            "next_step": {
                "branch_id": "branch-stale",
                "branch_title": "Review stale wrapper shim",
                "recommended_tool": "core_thinning",
            },
        }
        refreshed_candidate = {
            "tree_id": "tree-core",
            "title": "Core Thinning",
            "status": "active",
            "kind": "core_thinning",
            "next_step": {
                "branch_id": "branch-refreshed",
                "branch_title": "Review refreshed wrapper shim",
                "recommended_tool": "core_thinning",
            },
        }
        sync_payload = {
            "status": "ok",
            "tree_id": "tree-core",
            "added_count": 0,
            "deduped_count": 7,
            "resolved_count": 1,
        }

        with mock.patch.object(
            autonomy_maintenance,
            "_active_work_tree_candidates",
            side_effect=[[stale_candidate], [refreshed_candidate]],
        ) as candidates_mock, \
             mock.patch.object(autonomy_maintenance, "_sync_core_thinning_work_tree", return_value=sync_payload) as sync_mock, \
             mock.patch.object(autonomy_maintenance.work_tree, "run_autonomous_loop", return_value=[]) as loop_mock:
            payload = autonomy_maintenance._run_active_work_tree_cycle(state, max_steps=1, max_trees=2)

        self.assertEqual(candidates_mock.call_count, 2)
        sync_mock.assert_called_once_with(state)
        loop_mock.assert_called_once_with(
            "tree-core",
            max_steps=1,
            execute_planned_action_fn=autonomy_maintenance._active_work_tree_execute_planned_action,
            decide_next_step_fn=autonomy_maintenance._active_work_tree_failure_aware_decider,
        )
        self.assertEqual((payload.get("core_thinning_sync") or {}).get("resolved_count"), 1)
        self.assertEqual(payload.get("attempted_count"), 1)
        self.assertEqual(payload.get("processed")[0].get("last_action"), "")

    def test_retire_legacy_patch_update_trees_drops_open_tasks_and_completes_tree(self):
        self._isolated_work_tree_db()
        state = {}
        legacy_tree = work_tree.initialize_tree(
            "Cli: please patch apply updates.zip",
            meta={"kind": "system", "source": "cli"},
        )
        legacy_root = work_tree._BRANCHES[legacy_tree.root_branch_id]
        task = work_tree.add_task_to_branch(legacy_root.branch_id, "please patch apply updates.zip")
        work_tree.set_branch_tools(legacy_root.branch_id, allowed_tools=["patch_apply"], preferred_tool="patch_apply")

        safe_tree = work_tree.initialize_tree(
            "Cli: check queue status",
            meta={"kind": "system", "source": "cli"},
        )
        safe_root = work_tree._BRANCHES[safe_tree.root_branch_id]
        work_tree.add_task_to_branch(safe_root.branch_id, "check queue status")
        work_tree.set_branch_tools(safe_root.branch_id, allowed_tools=["queue_status"], preferred_tool="queue_status")

        payload = autonomy_maintenance._retire_legacy_patch_update_trees(state)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("retired_count"), 1)
        legacy_inspect = work_tree.inspect_tree(legacy_tree.tree_id)
        safe_inspect = work_tree.inspect_tree(safe_tree.tree_id)
        self.assertEqual(legacy_inspect.get("status"), "complete")
        self.assertEqual((legacy_inspect.get("counts") or {}).get("tasks", {}).get("dropped"), 1)
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.DROPPED)
        self.assertEqual(safe_inspect.get("status"), "active")
        ready_branches = legacy_inspect.get("ready_branches") or []
        self.assertFalse(ready_branches)
        self.assertEqual((state.get("last_legacy_tree_retirement") or {}).get("retired_count"), 1)

    def test_run_patch_queue_work_tree_cycle_executes_only_operator_approved_apply(self):
        state = {
            "last_patch_queue_sync": {
                "ts": "2026-04-23 00:00:00",
                "status": "ok",
                "tree_id": "tree_demo",
                "tree_title": "Patch Queue",
                "apply_ready_count": 1,
                "approve_ready_count": 0,
            }
        }

        with mock.patch.object(
            autonomy_maintenance.work_tree,
            "run_autonomous_loop",
            side_effect=[
                [{"action": "executed", "tool": "patch_preview_apply"}],
            ],
        ) as run_loop_mock, \
            mock.patch.object(
                autonomy_maintenance,
                "_sync_patch_queue_work_tree",
                side_effect=[
                    {
                        "ts": "2026-04-23 00:00:02",
                        "status": "ok",
                        "tree_id": "tree_demo",
                        "tree_title": "Patch Queue",
                        "apply_ready_count": 0,
                        "approve_ready_count": 0,
                    },
                ],
            ):
            cycle_payload = autonomy_maintenance._run_patch_queue_work_tree_cycle(state)

        self.assertEqual(run_loop_mock.call_count, 1)
        self.assertEqual(cycle_payload.get("status"), "ok")
        self.assertEqual(cycle_payload.get("executed_count"), 1)
        self.assertEqual(cycle_payload.get("apply_ready_count"), 0)
        self.assertEqual(cycle_payload.get("approve_ready_count"), 0)
        self.assertEqual(len(cycle_payload.get("history") or []), 1)

    def test_sync_patch_queue_work_tree_reuses_legacy_seeded_branch(self):
        self._isolated_work_tree_db()
        state = {}
        tree = work_tree.initialize_tree(
            "Patch Queue: approved preview apply",
            meta={
                "kind": "system",
                "source": "autonomy",
                "patch_queue": True,
                "execution_policy": {
                    "allowed_tools": ["patch_preview_apply", "patch_rollback"],
                    "require_explicit_allow": True,
                },
            },
        )
        legacy_branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            "Apply preview: preview_legacy_patch.zip.txt",
            "patch_queue",
            tree.root_branch_id,
        )
        legacy_branch.allowed_tools = ["patch_preview_apply", "patch_rollback"]
        legacy_branch.preferred_tool = "patch_rollback"
        work_tree.add_task_to_branch(
            legacy_branch.branch_id,
            "apply approved preview preview_legacy_patch.zip.txt",
        )
        work_tree.touch_branch(legacy_branch.branch_id)

        row = {
            "name": "preview_legacy_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_legacy_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "legacy_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "approved",
        }

        with mock.patch.object(autonomy_maintenance.nova_core, "patch_status_payload", return_value={"review_previews": [row]}):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("created_count"), 0)
        self.assertEqual(payload.get("updated_count"), 1)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and autonomy_maintenance._is_patch_queue_managed_branch(tree, branch)
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.branch_id, legacy_branch.branch_id)
        self.assertEqual(branch.source_type, autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE)
        self.assertEqual(branch.source_key, "patch_preview::preview_legacy_patch.zip.txt")
        self.assertEqual(branch.preferred_tool, "patch_preview_apply")

    def test_sync_patch_queue_work_tree_keeps_incompatible_base_preview_in_review_lane(self):
        self._isolated_work_tree_db()
        state = {}
        row = {
            "name": "preview_base_mismatch_patch.zip.txt",
            "path": "C:/Nova/updates/previews/preview_base_mismatch_patch.zip.txt",
            "status": "eligible",
            "decision": "approved",
            "zip_name": "base_mismatch_patch.zip",
            "zip_exists": True,
            "artifact_state": "ok",
            "review_bucket": "approved",
            "min_base_revision": "4",
        }

        with mock.patch.object(
            autonomy_maintenance.nova_core,
            "patch_status_payload",
            return_value={"current_revision": 3, "review_previews": [row]},
        ):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("apply_ready_count"), 0)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Review preview: preview_base_mismatch_patch.zip.txt")
        self.assertEqual(branch.preferred_tool, "find")
        self.assertEqual(list(branch.allowed_tools), autonomy_maintenance.PATCH_QUEUE_REVIEW_TOOLS)
        self.assertIn("waiting for the required patch revision", str(branch.notes or "").lower())

        cycle_payload = autonomy_maintenance._run_patch_queue_work_tree_cycle(state)
        self.assertEqual(cycle_payload.get("status"), "idle")
        self.assertEqual(cycle_payload.get("reason"), "no_apply_ready_preview")

    def test_webui_health_requires_live_pid_port_and_http(self):
        process = {"pid": 4242, "create_time": 1.0, "cmdline": ["python", "nova_http.py"]}
        with mock.patch.object(autonomy_maintenance.runtime_processes, "logical_service_processes", return_value=[process]), \
             mock.patch.object(autonomy_maintenance, "_nova_http_direct_process_alive", return_value=True), \
             mock.patch.object(autonomy_maintenance, "_operator_webui_port_open", return_value=True), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", side_effect=TimeoutError("slow")):
            payload = autonomy_maintenance._webui_health_for_orchestrator()

        self.assertFalse(payload.get("running"))
        self.assertEqual(payload.get("status"), "degraded")
        self.assertFalse(payload.get("http_ok"))
        self.assertTrue(payload.get("port_open"))

    def test_ensure_operator_webui_running_waits_on_transient_degraded_health(self):
        state = {}
        health = {"running": False, "pid": 5150, "http_ok": False, "port_open": True}
        with mock.patch.object(autonomy_maintenance, "_probe_operator_webui_health", return_value=health), \
             mock.patch.object(autonomy_maintenance, "_nova_http_direct_process_alive", return_value=True), \
             mock.patch.object(autonomy_maintenance, "_operator_webui_port_open", return_value=True):
            payload = autonomy_maintenance._ensure_operator_webui_running(state)

        self.assertEqual(payload.get("status"), "degraded")
        self.assertEqual(payload.get("action"), "wait")
        self.assertEqual(state.get("operator_webui_degraded_count"), 1)

    def test_ensure_operator_webui_running_uses_launcher_when_port_is_down(self):
        state = {}
        health = {"running": False, "pid": None, "http_ok": False, "port_open": False}
        launcher = autonomy_maintenance.ROOT / "scripts" / "start_webui_detached.py"
        python_exe = autonomy_maintenance.ROOT / ".venv" / "Scripts" / "python.exe"
        if not launcher.exists() or not python_exe.exists():
            self.skipTest("webui launcher prerequisites missing")
        with mock.patch.object(autonomy_maintenance, "_probe_operator_webui_health", side_effect=[health, {"running": True, "pid": 9001, "http_ok": True, "port_open": True}]), \
             mock.patch.object(autonomy_maintenance, "_operator_webui_port_open", return_value=False), \
             mock.patch.object(autonomy_maintenance.subprocess, "run", return_value=mock.Mock(returncode=0)) as mocked_run, \
             mock.patch.object(autonomy_maintenance.time, "sleep", return_value=None):
            payload = autonomy_maintenance._ensure_operator_webui_running(state)

        self.assertEqual(payload.get("action"), "started")
        self.assertEqual(payload.get("status"), "running")
        command = [str(token) for token in list(mocked_run.call_args.args[0])]
        self.assertTrue(any("start_webui_detached.py" in token for token in command))
        self.assertFalse(any("webui-start" in token for token in command))

    def test_ensure_operator_webui_running_reclaims_stuck_open_port_after_degraded_threshold(self):
        state = {"operator_webui_degraded_count": 3}
        stuck = {"running": False, "pid": 5150, "http_ok": False, "port_open": True}
        healthy = {"running": True, "pid": 9001, "http_ok": True, "port_open": True}
        launcher = autonomy_maintenance.ROOT / "scripts" / "start_webui_detached.py"
        python_exe = autonomy_maintenance.ROOT / ".venv" / "Scripts" / "python.exe"
        if not launcher.exists() or not python_exe.exists():
            self.skipTest("webui launcher prerequisites missing")
        with mock.patch.object(
                 autonomy_maintenance,
                 "_probe_operator_webui_health",
                 side_effect=[stuck, healthy],
             ), \
             mock.patch.object(autonomy_maintenance, "_nova_http_direct_process_alive", return_value=True), \
             mock.patch.object(autonomy_maintenance, "_operator_webui_port_open", return_value=False), \
             mock.patch.object(
                 autonomy_maintenance.runtime_processes,
                 "logical_service_processes",
                 return_value=[{"pid": 5150, "create_time": 1.0, "cmdline": ["python", "nova_http.py"]}],
             ), \
             mock.patch.object(autonomy_maintenance, "_terminate_operator_webui_pid", return_value=True) as terminate_mock, \
             mock.patch.object(autonomy_maintenance.subprocess, "run", return_value=mock.Mock(returncode=0)) as mocked_run, \
             mock.patch.object(autonomy_maintenance.time, "sleep", return_value=None):
            payload = autonomy_maintenance._ensure_operator_webui_running(state)

        self.assertIn(payload.get("action"), {"started", "reclaimed_started"})
        self.assertEqual(payload.get("status"), "running")
        terminate_mock.assert_called()
        mocked_run.assert_called_once()

    def test_webui_health_reconciles_duplicate_http_processes(self):
        processes = [
            {"pid": 7001, "create_time": 10.0, "cmdline": ["python", "nova_http.py"]},
            {"pid": 7002, "create_time": 12.0, "cmdline": ["python", "nova_http.py"]},
        ]
        with mock.patch.object(
            autonomy_maintenance.runtime_processes,
            "logical_service_processes",
            side_effect=[processes, [processes[1]]],
        ), mock.patch.object(
            autonomy_maintenance,
            "_nova_http_direct_process_alive",
            return_value=True,
        ), mock.patch.object(
            autonomy_maintenance,
            "_terminate_operator_webui_pid",
            return_value=True,
        ) as terminate_mock, mock.patch.object(
            autonomy_maintenance,
            "_operator_webui_port_open",
            return_value=True,
        ), mock.patch("urllib.request.urlopen") as urlopen_mock:
            response = mock.Mock()
            response.__enter__ = mock.Mock(return_value=response)
            response.__exit__ = mock.Mock(return_value=False)
            response.status = 200
            urlopen_mock.return_value = response

            payload = autonomy_maintenance._webui_health_for_orchestrator()

            terminate_mock.assert_called_once()
            self.assertEqual(terminate_mock.call_args.args[0], 7001)
        self.assertEqual(payload.get("pid"), 7002)
        self.assertEqual(payload.get("process_count"), 1)
        self.assertEqual((payload.get("duplicate_reconcile") or {}).get("terminated_count"), 1)


if __name__ == "__main__":
    unittest.main()
