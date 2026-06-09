import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from services.runtime_control import RUNTIME_CONTROL_SERVICE


class _FakeTimeoutExpired(Exception):
    pass


class _FakePsutil:
    TimeoutExpired = _FakeTimeoutExpired

    def __init__(self, pid_exists=True):
        self._pid_exists = pid_exists
        self.terminated = []

    def pid_exists(self, pid):
        return self._pid_exists

    def Process(self, pid):
        outer = self

        class _Proc:
            def terminate(self):
                outer.terminated.append((pid, "terminate"))

            def wait(self, timeout=None):
                return None

            def kill(self):
                outer.terminated.append((pid, "kill"))

        return _Proc()


class TestRuntimeControlService(unittest.TestCase):
    def test_autonomy_maintenance_summary_flattens_queue_truth(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [],
            select_logical_process=lambda logical, pid=None, create_time=None: None,
        )
        state = {
            "runtime_worker": {"last_cycle_status": "ok"},
            "last_regression_status": "FAILED",
            "last_regression_stale": True,
            "last_generated_queue_run": {
                "status": "blocked",
                "queue_open_count": 3,
                "queue_actionable_count": 0,
                "queue_blocked_count": 3,
                "queue_blocked_reason_counts": {"parity_drift_locked": 3},
                "queue_blocked_files": ["a.json", "b.json", "c.json"],
            },
            "last_work_tree_cycle": {"status": "idle"},
            "last_complete_tree_archive": {"status": "ok", "archived_count": 12, "retained_count": 8},
            "last_autonomy_orchestrator": {
                "ts": "2026-05-06 12:30:00",
                "mode": "advisory",
                "decision": "recommend_action",
                "action": {"act": "generated_queue_run_next"},
                "reason": "Generated Work Queue has 1 actionable item.",
                "rejection_reasons": [],
                "ledger_status": "recorded",
            },
            "last_error": "",
        }

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload=state,
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-04-27",
        )

        self.assertEqual(payload.get("generated_queue_status"), "blocked")
        self.assertEqual(payload.get("last_regression_status"), "FAILED")
        self.assertTrue(payload.get("last_regression_stale"))
        self.assertEqual(payload.get("queue_open_count"), 3)
        self.assertEqual(payload.get("queue_actionable_count"), 0)
        self.assertEqual(payload.get("queue_blocked_count"), 3)
        self.assertEqual(payload.get("queue_blocked_reason_counts"), {"parity_drift_locked": 3})
        self.assertEqual(payload.get("queue_blocked_files"), ["a.json", "b.json", "c.json"])
        self.assertEqual(payload.get("work_tree_status"), "idle")
        self.assertEqual((payload.get("last_complete_tree_archive") or {}).get("archived_count"), 12)
        self.assertEqual((payload.get("last_autonomy_orchestrator") or {}).get("decision"), "recommend_action")
        self.assertEqual(((payload.get("last_autonomy_orchestrator") or {}).get("action") or {}).get("act"), "generated_queue_run_next")
        self.assertEqual((payload.get("last_autonomy_orchestrator") or {}).get("ledger_status"), "recorded")

    def test_autonomy_maintenance_summary_prefers_latest_queue_sync_over_stale_run(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [],
            select_logical_process=lambda logical, pid=None, create_time=None: None,
        )
        state = {
            "runtime_worker": {"last_cycle_status": "ok"},
            "last_generated_queue_run": {
                "status": "actionable",
                "queue_open_count": 1,
                "queue_actionable_count": 1,
                "queue_blocked_count": 0,
                "selected_file": "old.json",
            },
            "last_generated_queue_sync": {
                "status": "ok",
                "queue_status": "clear",
                "open_count": 0,
                "actionable_count": 0,
                "blocked_count": 0,
                "queue_count": 25,
                "ts": "2026-05-15 22:19:12",
            },
        }

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload=state,
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-05-15",
        )

        self.assertEqual(payload.get("generated_queue_status"), "clear")
        self.assertEqual(payload.get("queue_open_count"), 0)
        self.assertEqual(payload.get("queue_actionable_count"), 0)
        self.assertEqual(payload.get("queue_blocked_count"), 0)
        self.assertEqual((payload.get("last_generated_queue_sync") or {}).get("queue_count"), 25)
        self.assertTrue(payload.get("last_generated_queue_run_stale"))

    def test_autonomy_maintenance_summary_marks_missing_runtime_worker_stale(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [],
            select_logical_process=lambda logical, pid=None, create_time=None: None,
        )
        state = {
            "runtime_worker": {
                "last_cycle_status": "running",
                "pid": 4321,
                "create_time": 12.5,
            }
        }

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload=state,
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-04-27",
        )

        worker = dict(payload.get("runtime_worker") or {})
        self.assertEqual(worker.get("last_cycle_status"), "stopped")
        self.assertFalse(worker.get("active"))
        self.assertTrue(worker.get("stale_identity"))
        self.assertIsNone(worker.get("pid"))
        self.assertIsNone(worker.get("create_time"))

    def test_autonomy_maintenance_summary_downgrades_stale_ok_worker_identity(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [],
            select_logical_process=lambda logical, pid=None, create_time=None: None,
        )
        state = {
            "runtime_worker": {
                "last_cycle_status": "ok",
                "pid": 4321,
                "create_time": 12.5,
            }
        }

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload=state,
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-04-27",
        )

        worker = dict(payload.get("runtime_worker") or {})
        self.assertEqual(worker.get("last_cycle_status"), "stopped")
        self.assertFalse(worker.get("active"))
        self.assertTrue(worker.get("stale_identity"))
        self.assertIsNone(worker.get("pid"))
        self.assertIsNone(worker.get("create_time"))

    def test_autonomy_maintenance_summary_does_not_treat_guard_cycle_as_worker_loop(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [
                {
                    "pid": 9876,
                    "create_time": 55.0,
                    "cmdline": ["python.exe", "C:/Nova/autonomy_maintenance.py"],
                }
            ],
            select_logical_process=lambda logical, pid=None, create_time=None: logical[0] if logical else None,
        )
        state = {
            "runtime_worker": {
                "last_cycle_status": "ok",
                "pid": 4321,
                "create_time": 12.5,
            }
        }

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload=state,
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-04-27",
        )

        worker = dict(payload.get("runtime_worker") or {})
        self.assertEqual(worker.get("last_cycle_status"), "stopped")
        self.assertFalse(worker.get("active"))
        self.assertTrue(worker.get("stale_identity"))
        self.assertTrue(worker.get("cycle_process_active"))
        self.assertEqual(worker.get("cycle_process_count"), 1)
        self.assertEqual(worker.get("cycle_process_pids"), [9876])

    def test_autonomy_maintenance_summary_recognizes_loop_worker_process(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [
                {
                    "pid": 9876,
                    "create_time": 55.0,
                    "cmdline": ["python.exe", "C:/Nova/autonomy_maintenance.py", "--loop", "--interval-sec", "300"],
                }
            ],
            select_logical_process=lambda logical, pid=None, create_time=None: logical[0] if logical else None,
        )

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload={"runtime_worker": {"last_cycle_status": "stopped"}},
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-04-27",
        )

        worker = dict(payload.get("runtime_worker") or {})
        self.assertEqual(worker.get("last_cycle_status"), "running")
        self.assertTrue(worker.get("active"))
        self.assertFalse(worker.get("stale_identity"))
        self.assertFalse(worker.get("cycle_process_active"))
        self.assertEqual(worker.get("pid"), 9876)

    def test_autonomy_maintenance_summary_preserves_patch_queue_fields(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [],
            select_logical_process=lambda logical, pid=None, create_time=None: None,
        )
        state = {
            "runtime_worker": {"last_cycle_status": "ok", "interval_sec": 300},
            "last_generated_queue_run": {"status": "blocked", "queue_open_count": 3},
            "last_work_tree_cycle": {"status": "idle", "executed_count": 0, "tree_count": 1},
            "last_patch_queue_sync": {"status": "ok", "review_previews_total": 17},
            "last_patch_cleanup": {
                "status": "ok",
                "orphan_rejected_count": 238,
                "superseded_archived_count": 347,
                "review_total_before": 29,
                "review_total_after": 17,
            },
            "last_kidney_status": {"mode": "enforce", "candidate_count": 19},
        }

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload=state,
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-04-27",
        )

        self.assertEqual((payload.get("last_work_tree_cycle") or {}).get("status"), "idle")
        self.assertEqual((payload.get("last_patch_queue_sync") or {}).get("review_previews_total"), 17)
        self.assertEqual((payload.get("last_patch_cleanup") or {}).get("orphan_rejected_count"), 238)
        self.assertEqual((payload.get("last_patch_cleanup") or {}).get("superseded_archived_count"), 347)
        self.assertEqual((payload.get("last_kidney_status") or {}).get("candidate_count"), 19)


    def test_autonomy_maintenance_summary_passes_through_temporal_feed(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [],
            select_logical_process=lambda logical, pid=None, create_time=None: None,
        )
        state = {
            "runtime_worker": {"last_cycle_status": "ok"},
            "last_temporal_feed": {
                "status": "ok",
                "enabled": True,
                "event_count": 3,
                "surfaced_count": 1,
                "pressure_count": 2,
                "ran_at": "2026-06-08T00:00:00+00:00",
            },
        }

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload=state,
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-06-08",
        )

        feed = payload.get("last_temporal_feed") or {}
        self.assertEqual(feed.get("status"), "ok")
        self.assertTrue(feed.get("enabled"))
        self.assertEqual(feed.get("event_count"), 3)
        self.assertEqual(feed.get("surfaced_count"), 1)
        self.assertEqual(feed.get("pressure_count"), 2)

    def test_autonomy_maintenance_summary_temporal_feed_absent_yields_empty_dict(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [],
            select_logical_process=lambda logical, pid=None, create_time=None: None,
        )
        state = {"runtime_worker": {"last_cycle_status": "ok"}}

        payload = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_summary(
            state_payload=state,
            maintenance_py=Path("c:/Nova/autonomy_maintenance.py"),
            runtime_processes_module=runtime_processes,
            strftime_fn=lambda _fmt: "2026-06-08",
        )

        self.assertIsInstance(payload.get("last_temporal_feed"), dict)
        self.assertEqual(payload.get("last_temporal_feed"), {})

    def test_runtime_artifact_show_action_preserves_message_and_detail(self):
        ok, msg, extra, detail = RUNTIME_CONTROL_SERVICE.runtime_artifact_show_action(
            {"artifact": "guard.log", "lines": 20},
            runtime_artifact_detail_payload_fn=lambda name, max_lines=0: {"ok": True, "name": name, "max_lines": max_lines},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "runtime_artifact_show_ok")
        self.assertEqual((extra.get("artifact") or {}).get("name"), "guard.log")
        self.assertEqual(detail, "runtime_artifact_show_ok:guard.log")

    def test_guard_control_action_from_runtime_routes_restart(self):
        ok, msg, extra, detail = RUNTIME_CONTROL_SERVICE.guard_control_action_from_runtime(
            {"_action": "guard_restart"},
            runtime_scope={
                "_restart_guard": lambda: (True, "guard_restart_requested"),
                "_guard_status_payload": lambda: {"running": True},
                "_core_status_payload": lambda: {"running": True, "pid": 321},
            },
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "guard_restart_requested")
        self.assertEqual((extra.get("guard") or {}).get("running"), True)
        self.assertEqual((extra.get("core") or {}).get("pid"), 321)
        self.assertEqual(detail, "guard_restart_requested")

    def test_core_runtime_action_from_runtime_routes_webui_restart(self):
        ok, msg, extra, detail = RUNTIME_CONTROL_SERVICE.core_runtime_action_from_runtime(
            {"_action": "webui_restart"},
            runtime_scope={
                "_restart_webui": lambda: (True, "webui_restart_requested"),
                "_http_status_payload": lambda: {"running": True, "pid": 8080},
            },
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "webui_restart_requested")
        self.assertEqual((extra.get("webui") or {}).get("pid"), 8080)
        self.assertEqual(detail, "webui_restart_requested")

    def test_autonomy_runtime_action_from_runtime_routes_start(self):
        ok, msg, extra, detail = RUNTIME_CONTROL_SERVICE.autonomy_runtime_action_from_runtime(
            {"_action": "autonomy_maintenance_start"},
            runtime_scope={
                "_start_autonomy_maintenance_worker": lambda: (True, "autonomy_maintenance_start_requested"),
                "_autonomy_maintenance_summary": lambda: {"ok": True, "generated_queue_status": "clear"},
            },
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "autonomy_maintenance_start_requested")
        self.assertEqual((extra.get("autonomy_maintenance") or {}).get("generated_queue_status"), "clear")
        self.assertEqual(detail, "autonomy_maintenance_start_requested")

    def test_start_nova_core_routes_through_guard(self):
        import sys
        ok, msg = RUNTIME_CONTROL_SERVICE.start_nova_core(
            core_py=Path(sys.executable),  # guaranteed to exist on any platform
            core_status_fn=lambda: {"running": False},
            start_guard_fn=lambda: (True, "guard_start_requested"),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "nova_core_start_requested_via_guard")

    def test_stop_core_owned_process_uses_runtime_identity(self):
        runtime_processes = SimpleNamespace(
            read_identity_file=lambda path: (123, 1.0, {}),
            logical_service_processes=lambda core_py: [{"pid": 123, "create_time": 1.0}],
            select_logical_process=lambda logical, pid=None, create_time=None: logical[0],
        )
        fake_psutil = _FakePsutil(pid_exists=True)

        ok, msg = RUNTIME_CONTROL_SERVICE.stop_core_owned_process(
            runtime_dir=Path("c:/Nova/runtime"),
            core_py=Path("c:/Nova/nova_core.py"),
            runtime_processes_module=runtime_processes,
            psutil_module=fake_psutil,
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "core_stop_requested:123")
        self.assertEqual(fake_psutil.terminated, [(123, "terminate")])

    def test_restart_webui_schedules_and_shutdowns(self):
        calls = []

        ok, msg = RUNTIME_CONTROL_SERVICE.restart_webui(
            venv_python=Path("c:/Nova/.venv/Scripts/python.exe"),
            http_py=Path("c:/Nova/nova_http.py"),
            bind_host="127.0.0.1",
            bind_port=8080,
            base_dir=Path("c:/Nova"),
            schedule_detached_start_fn=lambda command, delay_seconds=0.0, cwd=None: calls.append((command, delay_seconds, cwd)) or (True, "delayed_start_scheduled"),
            shutdown_http_server_later_fn=lambda delay_seconds=0.0: (True, "http_shutdown_requested"),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "webui_restart_requested")
        self.assertEqual(calls[0][1], 1.5)

    def test_restart_webui_reports_start_when_no_server_is_available(self):
        calls = []

        ok, msg = RUNTIME_CONTROL_SERVICE.restart_webui(
            venv_python=Path("c:/Nova/.venv/Scripts/python.exe"),
            http_py=Path("c:/Nova/nova_http.py"),
            bind_host="127.0.0.1",
            bind_port=8080,
            base_dir=Path("c:/Nova"),
            schedule_detached_start_fn=lambda command, delay_seconds=0.0, cwd=None: calls.append((command, delay_seconds, cwd)) or (True, "delayed_start_scheduled"),
            shutdown_http_server_later_fn=lambda delay_seconds=0.0: (False, "http_server_unavailable"),
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "webui_start_requested")
        self.assertEqual(calls[0][1], 1.5)

    def test_start_autonomy_maintenance_worker_starts_detached_loop(self):
        calls = []

        class _FakeSubprocess:
            DEVNULL = object()
            DETACHED_PROCESS = 1
            CREATE_NEW_PROCESS_GROUP = 2
            CREATE_NO_WINDOW = 4

            @staticmethod
            def Popen(command, **kwargs):
                calls.append((command, kwargs))
                return object()

        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [],
            select_logical_process=lambda logical, pid=None, create_time=None: None,
        )

        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)
            maintenance_py = base_dir / "autonomy_maintenance.py"
            maintenance_py.write_text("print('ok')\n", encoding="utf-8")
            venv_python = base_dir / "python.exe"
            venv_python.write_text("", encoding="utf-8")
            state_path = base_dir / "runtime" / "autonomy_maintenance_state.json"

            ok, msg = RUNTIME_CONTROL_SERVICE.start_autonomy_maintenance_worker(
                venv_python=venv_python,
                maintenance_py=maintenance_py,
                state_path=state_path,
                base_dir=base_dir,
                interval_sec=120,
                runtime_processes_module=runtime_processes,
                subprocess_module=_FakeSubprocess,
            )

        self.assertTrue(ok)
        self.assertEqual(msg, "autonomy_maintenance_start_requested")
        self.assertEqual(calls[0][0], [str(venv_python), str(maintenance_py), "--loop", "--interval-sec", "120"])

    def test_stop_autonomy_maintenance_worker_uses_runtime_worker_identity(self):
        runtime_processes = SimpleNamespace(
            logical_service_processes=lambda _script: [{"pid": 456, "create_time": 2.5}],
            select_logical_process=lambda logical, pid=None, create_time=None: logical[0],
        )
        fake_psutil = _FakePsutil(pid_exists=True)

        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)
            maintenance_py = base_dir / "autonomy_maintenance.py"
            maintenance_py.write_text("print('ok')\n", encoding="utf-8")
            state_path = base_dir / "runtime" / "autonomy_maintenance_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                '{"runtime_worker": {"pid": 456, "create_time": 2.5}}',
                encoding="utf-8",
            )

            ok, msg = RUNTIME_CONTROL_SERVICE.stop_autonomy_maintenance_worker(
                state_path=state_path,
                maintenance_py=maintenance_py,
                runtime_processes_module=runtime_processes,
                psutil_module=fake_psutil,
            )

        self.assertTrue(ok)
        self.assertEqual(msg, "autonomy_maintenance_stop_requested:456")
        self.assertEqual(fake_psutil.terminated, [(456, "terminate")])

    def test_core_stop_action_returns_guard_and_core_status(self):
        ok, msg, extra, detail = RUNTIME_CONTROL_SERVICE.core_stop_action(
            stop_core_owned_process_fn=lambda: (True, "core_stop_requested:123"),
            guard_status_payload_fn=lambda: {"running": True, "status": "running"},
            core_status_payload_fn=lambda: {"running": False, "status": "stopped"},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "core_stop_requested:123")
        self.assertEqual(detail, msg)
        self.assertTrue((extra.get("guard") or {}).get("running"))
        self.assertEqual((extra.get("core") or {}).get("status"), "stopped")

    def test_autonomy_maintenance_start_action_returns_summary(self):
        ok, msg, extra, detail = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_start_action(
            start_autonomy_maintenance_worker_fn=lambda: (True, "autonomy_maintenance_start_requested"),
            autonomy_maintenance_summary_fn=lambda: {"runtime_worker": {"last_cycle_status": "running"}},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "autonomy_maintenance_start_requested")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("autonomy_maintenance") or {}).get("runtime_worker", {}).get("last_cycle_status"), "running")

    def test_autonomy_maintenance_stop_action_returns_summary(self):
        ok, msg, extra, detail = RUNTIME_CONTROL_SERVICE.autonomy_maintenance_stop_action(
            stop_autonomy_maintenance_worker_fn=lambda: (True, "autonomy_maintenance_stop_requested:456"),
            autonomy_maintenance_summary_fn=lambda: {"runtime_worker": {"last_cycle_status": "stopped"}},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "autonomy_maintenance_stop_requested:456")
        self.assertEqual(detail, msg)
        self.assertEqual((extra.get("autonomy_maintenance") or {}).get("runtime_worker", {}).get("last_cycle_status"), "stopped")


if __name__ == "__main__":
    unittest.main()
