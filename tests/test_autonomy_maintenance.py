import json
import os
import tempfile
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

    def test_run_temporal_feed_pass_reads_ics_and_surfaces_pressure(self):
        state: dict = {}
        with tempfile.TemporaryDirectory() as td:
            ics_path = Path(td) / "calendar.ics"
            ics_path.write_text(
                "\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "SUMMARY:PEIMS deadline",
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

        def _capture_status_payload(status_payload):
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
                        "title": "PEIMS deadline",
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

            def _sync_signal(state, kidney_summary=None, temporal_feed=None):
                order.append("signal")
                payload = {
                    "ts": "2026-05-14 18:00:00",
                    "status": "ok",
                    "result_count": 1,
                    "resolved_count": 1,
                    "subconscious_signal_count": 0,
                    "active_regression_failure": False,
                }
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
                 mock.patch.object(autonomy_maintenance, "_autonomy_policy_settings", return_value={"enabled": True, "mode": "advisory"}):
                packet = autonomy_maintenance._run_autonomy_orchestrator_advisory(state, {"mode": "enforce"})

            self.assertEqual(packet.get("decision"), "recommend_action")
            self.assertEqual((packet.get("action") or {}).get("act"), "generated_queue_run_next")
            self.assertEqual((state.get("last_autonomy_orchestrator") or {}).get("ledger_status"), "recorded")
            rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("decision"), "recommend_action")
            self.assertIn("candidate_actions", rows[0])
            self.assertEqual(rows[0].get("execution_result"), "blocked")
            self.assertEqual((rows[0].get("execution") or {}).get("result"), "blocked")

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

    def test_run_once_marks_failed_regression_stale_when_regression_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            latest_path = runtime_dir / "subconscious_runs" / "latest.json"
            latest_path.parent.mkdir(parents=True, exist_ok=True)
            latest_path.write_text(json.dumps({"generated_at": "2026-04-23 08:00:00", "families": []}, ensure_ascii=True), encoding="utf-8")
            state_path = runtime_dir / "autonomy_maintenance_state.json"
            log_path = runtime_dir / "autonomy_maintenance.log"
            state_path.write_text(
                json.dumps(
                    {
                        "last_regression_date": "2026-04-23",
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
                def _mock_sync_signal(state, kidney_summary=None, temporal_feed=None):
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
            self.assertTrue(state.get("last_regression_stale"))
            self.assertEqual((state.get("last_generated_queue_run") or {}).get("status"), "clear")
            self.assertTrue(bool((state.get("last_signal_ingestion") or {}).get("last_regression_stale")))

    def test_sync_signal_intake_work_tree_creates_regression_branch_for_live_failure(self):
        self._isolated_work_tree_db()
        state = {
            "last_regression_status": "FAILED",
            "last_regression_stale": False,
        }

        with mock.patch.object(
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
        self.assertEqual(mocked.call_args.kwargs.get("timeout"), 10.0)

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

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_first"), \
             mock.patch.object(autonomy_maintenance, "CONTROL_STATUS_SURFACES_TIMEOUT_SEC", 3.0), \
             mock.patch.object(autonomy_maintenance, "_probe_local_ollama_health", return_value={"ok": True, "server_ok": True}), \
             mock.patch.object(autonomy_maintenance, "_probe_local_port_ownership", return_value={"status": "ok"}), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", return_value=_Response()) as mocked:
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("signal_ingestion_status_source"), "local_first_with_http_surfaces")
        self.assertEqual(payload.get("operator_outbox_open_count"), 2)
        self.assertEqual(payload.get("alerts"), ["operator_outbox_open"])
        self.assertEqual(mocked.call_args.kwargs.get("timeout"), 3.0)

    def test_local_first_status_falls_back_to_local_when_surfaces_fetch_fails(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}
        ollama_down = {
            "ok": False,
            "server_ok": False,
            "status": "tags_unreachable",
            "tags_ok": False,
            "chat_route_ok": False,
            "api_contract_status": "tags_unreachable",
        }

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_first"), \
             mock.patch.object(autonomy_maintenance.urllib.request, "urlopen", side_effect=TimeoutError("slow surfaces")), \
             mock.patch.object(autonomy_maintenance.nova_core, "ollama_health_payload", return_value=ollama_down):
            payload = autonomy_maintenance._live_control_status_payload_for_signal_ingestion(fallback)

        self.assertEqual(payload.get("signal_ingestion_status_source"), "local_dependency_probe")
        self.assertEqual(payload.get("ollama_api_contract_status"), "tags_unreachable")

    def test_local_dependency_probe_enriches_layer_maturity_observe_mode(self):
        fallback = {"alerts": [], "autonomy_maintenance": {"last_regression_status": ""}}

        with mock.patch.object(autonomy_maintenance, "SIGNAL_INGESTION_STATUS_MODE", "local_only"), \
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

        with mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value=clean_memory_pulse), \
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
        with mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value=clean_memory_pulse), \
             mock.patch.object(autonomy_maintenance.nova_core, "mem_enabled", return_value=True), \
             mock.patch.object(autonomy_maintenance.VALIDATION_ARTIFACT_TRUTH_SERVICE, "payload", return_value={"ok": True, "status": "ok"}), \
             mock.patch.object(autonomy_maintenance, "_live_control_status_payload_for_signal_ingestion", side_effect=lambda payload: payload):
            autonomy_maintenance._sync_signal_intake_work_tree(live_state)

        stale_state = {
            "last_regression_status": "FAILED",
            "last_regression_stale": True,
        }
        with mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value=clean_memory_pulse), \
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

        with mock.patch.object(autonomy_maintenance.nova_core, "build_pulse_payload", return_value=memory_pulse), \
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

    def test_sync_patch_queue_work_tree_selects_single_auto_approval_branch(self):
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
            "preview_kind": "autonomy_micro_patch",
            "patch_revision": "4",
            "min_base_revision": "3",
            "mtime": 5,
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
            "preview_kind": "teach_proposal",
            "patch_revision": "4",
            "min_base_revision": "3",
            "mtime": 9,
        }

        with mock.patch.object(
            autonomy_maintenance.nova_core,
            "patch_status_payload",
            return_value={"current_revision": 3, "review_previews": [other_row, selected_row]},
        ):
            payload = autonomy_maintenance._sync_patch_queue_work_tree(state)

        self.assertEqual(payload.get("approve_ready_count"), 1)
        self.assertEqual(payload.get("pending_count"), 1)
        tree = work_tree.get_tree(str(payload.get("tree_id") or ""))
        self.assertIsNotNone(tree)
        branches = [
            branch for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.branch_id != tree.root_branch_id and str(branch.source_type or "") == autonomy_maintenance.PATCH_QUEUE_SOURCE_TYPE
        ]
        self.assertEqual(len(branches), 2)
        approve_branch = next(branch for branch in branches if branch.title.startswith("Approve preview:"))
        review_branch = next(branch for branch in branches if branch.title.startswith("Review preview:"))
        self.assertEqual(approve_branch.title, "Approve preview: preview_selected_patch.zip.txt")
        self.assertEqual(approve_branch.preferred_tool, "patch_preview_approve")
        self.assertEqual(list(approve_branch.allowed_tools), autonomy_maintenance.PATCH_QUEUE_EXECUTE_TOOLS)
        self.assertIn("auto-approval lane", str(approve_branch.notes or "").lower())
        approve_tasks = work_tree.list_branch_tasks(approve_branch.branch_id)
        self.assertEqual(len(approve_tasks), 1)
        self.assertEqual(approve_tasks[0].meta.get("patch_preview"), "preview_selected_patch.zip.txt")
        self.assertEqual(review_branch.preferred_tool, "find")

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
        self.assertEqual(decision.get("branch_id"), approve_branch.branch_id)

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
            execute_planned_action_fn=autonomy_maintenance.nova_core.execute_planned_action,
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

    def test_run_patch_queue_work_tree_cycle_resyncs_from_approve_into_apply(self):
        state = {
            "last_patch_queue_sync": {
                "ts": "2026-04-23 00:00:00",
                "status": "ok",
                "tree_id": "tree_demo",
                "tree_title": "Patch Queue",
                "apply_ready_count": 0,
                "approve_ready_count": 1,
            }
        }

        with mock.patch.object(
            autonomy_maintenance.work_tree,
            "run_autonomous_loop",
            side_effect=[
                [{"action": "executed", "tool": "patch_preview_approve"}],
                [{"action": "executed", "tool": "patch_preview_apply"}],
            ],
        ) as run_loop_mock, \
            mock.patch.object(
                autonomy_maintenance,
                "_sync_patch_queue_work_tree",
                side_effect=[
                    {
                        "ts": "2026-04-23 00:00:01",
                        "status": "ok",
                        "tree_id": "tree_demo",
                        "tree_title": "Patch Queue",
                        "apply_ready_count": 1,
                        "approve_ready_count": 0,
                    },
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

        self.assertEqual(run_loop_mock.call_count, 2)
        self.assertEqual(cycle_payload.get("status"), "ok")
        self.assertEqual(cycle_payload.get("executed_count"), 2)
        self.assertEqual(cycle_payload.get("apply_ready_count"), 0)
        self.assertEqual(cycle_payload.get("approve_ready_count"), 0)
        self.assertEqual(len(cycle_payload.get("history") or []), 2)

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


if __name__ == "__main__":
    unittest.main()
