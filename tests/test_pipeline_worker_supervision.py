import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from services.pipeline_worker_supervision import (
    acquire_worker_lease,
    pid_alive,
    ensure_pipeline_worker_running,
    ensure_pipeline_workers_for_ids,
    read_worker_heartbeat,
    read_worker_lease,
    reconcile_duplicate_pipeline_worker_processes,
    reconcile_pipeline_worker_scope,
    reconcile_pipeline_workers_for_ids,
    runtime_pipeline_worker_ids,
    stop_pipeline_worker,
    summarize_pipeline_workers,
    write_worker_heartbeat,
    write_worker_lease,
    worker_heartbeat_path,
    worker_lease_path,
)


class TestPipelineWorkerSupervision(unittest.TestCase):
    def _mock_supervised_spawn(self, runtime_root: Path, *, pid: int):
        def _popen(*_args, **_kwargs):
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=pid)
            write_worker_heartbeat(
                "data_connector",
                runtime_root=runtime_root,
                status="running",
                detail="worker_started",
                pid=pid,
            )
            return mock.Mock(pid=pid, poll=mock.Mock(return_value=None))

        return _popen

    def test_pid_alive_uses_pid_exists_not_signal_zero(self) -> None:
        with mock.patch("os.kill", side_effect=OSError(87, "The parameter is incorrect")) as kill_mock, \
             mock.patch("psutil.pid_exists", return_value=True) as exists_mock:
            self.assertTrue(pid_alive(4242))
        exists_mock.assert_called_once_with(4242)
        kill_mock.assert_not_called()

    def test_write_and_read_fresh_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            live_pid = 4242
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=live_pid)
            write_worker_heartbeat("data_connector", runtime_root=runtime_root, status="running", pid=live_pid)
            heartbeat = read_worker_heartbeat(
                "data_connector",
                runtime_root=runtime_root,
                stale_after_sec=30,
                pid_alive_fn=lambda pid: int(pid) == live_pid,
            )
            self.assertTrue(heartbeat["present"])
            self.assertTrue(heartbeat["fresh"])
            self.assertTrue(heartbeat["supervised_ok"])

    def test_stale_heartbeat_is_not_supervised(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            live_pid = 5150
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=live_pid)
            write_worker_heartbeat(
                "data_connector",
                runtime_root=runtime_root,
                status="running",
                pid=live_pid,
                now_fn=lambda: 100.0,
            )
            heartbeat = read_worker_heartbeat(
                "data_connector",
                runtime_root=runtime_root,
                stale_after_sec=10,
                now_fn=lambda: 200.0,
                pid_alive_fn=lambda pid: int(pid) == live_pid,
            )
            self.assertTrue(heartbeat["present"])
            self.assertFalse(heartbeat["fresh"])
            self.assertFalse(heartbeat["supervised_ok"])

    def test_summarize_pipeline_workers_reports_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            summary = summarize_pipeline_workers(
                ["data_connector"],
                runtime_root=runtime_root,
                now_fn=time.time,
            )
            self.assertEqual(summary["status"], "missing")
            self.assertEqual(summary["missing_count"], 1)

    def test_live_matching_lease_prevents_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            live_pid = 9001
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=live_pid)
            write_worker_heartbeat(
                "data_connector",
                runtime_root=runtime_root,
                status="idle",
                pid=live_pid,
            )
            worker_script = runtime_root / "scripts" / "pipeline_worker.py"
            worker_script.parent.mkdir(parents=True, exist_ok=True)
            worker_script.write_text("# stub", encoding="utf-8")
            venv_python = runtime_root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("", encoding="utf-8")
            popen_mock = mock.Mock()
            result = ensure_pipeline_worker_running(
                "data_connector",
                worker_script=worker_script,
                venv_python=venv_python,
                runtime_root=runtime_root,
                subprocess_module=mock.Mock(Popen=popen_mock),
                pid_alive_fn=lambda pid: int(pid) == live_pid,
            )
            self.assertEqual(result["status"], "already_running")
            popen_mock.assert_not_called()

    def test_dead_lease_allows_single_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=8800)
            worker_script = runtime_root / "scripts" / "pipeline_worker.py"
            worker_script.parent.mkdir(parents=True, exist_ok=True)
            worker_script.write_text("# stub", encoding="utf-8")
            venv_python = runtime_root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("", encoding="utf-8")
            popen_mock = mock.Mock(side_effect=self._mock_supervised_spawn(runtime_root, pid=8801))
            result = ensure_pipeline_worker_running(
                "data_connector",
                worker_script=worker_script,
                venv_python=venv_python,
                runtime_root=runtime_root,
                subprocess_module=mock.Mock(Popen=popen_mock, CREATE_NEW_PROCESS_GROUP=0),
                os_name="nt",
                pid_alive_fn=lambda pid: int(pid) == 8801,
            )
            self.assertEqual(result["status"], "start_requested")
            self.assertEqual(result["lease_owner_pid"], 8801)
            popen_mock.assert_called_once()
            lease = read_worker_lease("data_connector", runtime_root=runtime_root, pid_alive_fn=lambda pid: int(pid) == 8801)
            self.assertEqual(lease.get("lease_owner_pid"), 8801)

    def test_conflicting_live_workers_surface_duplicate_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            live_pid = 7700
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=live_pid)
            worker_script = runtime_root / "scripts" / "pipeline_worker.py"
            worker_script.parent.mkdir(parents=True, exist_ok=True)
            worker_script.write_text("# stub", encoding="utf-8")
            venv_python = runtime_root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("", encoding="utf-8")
            popen_mock = mock.Mock()
            result = ensure_pipeline_worker_running(
                "data_connector",
                worker_script=worker_script,
                venv_python=venv_python,
                runtime_root=runtime_root,
                subprocess_module=mock.Mock(Popen=popen_mock),
                pid_alive_fn=lambda pid: int(pid) == live_pid,
            )
            self.assertEqual(result["status"], "duplicate_ownership")
            self.assertEqual(result["conflicting_owner_pid"], live_pid)
            popen_mock.assert_not_called()

    def test_concurrent_ensure_creates_one_worker_lease(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            worker_script = runtime_root / "scripts" / "pipeline_worker.py"
            worker_script.parent.mkdir(parents=True, exist_ok=True)
            worker_script.write_text("# stub", encoding="utf-8")
            venv_python = runtime_root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("", encoding="utf-8")
            start_barrier = threading.Barrier(2)
            results: list[dict] = []
            pid_counter = {"value": 9100}
            pid_lock = threading.Lock()

            def _next_pid() -> int:
                with pid_lock:
                    pid_counter["value"] += 1
                    return pid_counter["value"]

            def _ensure_once() -> None:
                start_barrier.wait()
                spawned_pid = _next_pid()
                popen_mock = mock.Mock(side_effect=self._mock_supervised_spawn(runtime_root, pid=spawned_pid))
                results.append(
                    ensure_pipeline_worker_running(
                        "data_connector",
                        worker_script=worker_script,
                        venv_python=venv_python,
                        runtime_root=runtime_root,
                        subprocess_module=mock.Mock(Popen=popen_mock, CREATE_NEW_PROCESS_GROUP=0),
                        os_name="nt",
                        pid_alive_fn=lambda pid: int(pid) >= 9101,
                    )
                )

            threads = [threading.Thread(target=_ensure_once) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            statuses = [str(item.get("status") or "") for item in results]
            self.assertEqual(len(results), 2)
            self.assertEqual(sum(1 for status in statuses if status == "start_requested"), 1)
            self.assertTrue(all(status in {"start_requested", "duplicate_ownership", "already_running"} for status in statuses))
            lease = read_worker_lease("data_connector", runtime_root=runtime_root, pid_alive_fn=lambda pid: int(pid) >= 9101)
            self.assertTrue(lease.get("present"))

    def test_reconcile_clears_dead_lease_and_stale_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=8800)
            write_worker_heartbeat(
                "data_connector",
                runtime_root=runtime_root,
                status="running",
                pid=8800,
                now_fn=lambda: 100.0,
            )
            tmp_path = worker_heartbeat_path("data_connector", runtime_root=runtime_root).with_name("worker.heartbeat.99999.tmp")
            tmp_path.write_text("{}", encoding="utf-8")

            result = reconcile_pipeline_worker_scope(
                "data_connector",
                runtime_root=runtime_root,
                pid_alive_fn=lambda _pid: False,
            )

            self.assertEqual(result["status"], "dead_lease_cleared")
            self.assertIn("released_dead_lease", result.get("actions") or [])
            self.assertIn("removed_stale_heartbeat", result.get("actions") or [])
            self.assertFalse(read_worker_lease("data_connector", runtime_root=runtime_root).get("present"))
            self.assertFalse(worker_heartbeat_path("data_connector", runtime_root=runtime_root).exists())
            self.assertFalse(tmp_path.exists())

    def test_reconcile_duplicate_pipeline_worker_processes_terminates_non_keeper(self) -> None:
        terminated: list[int] = []
        processes = [
            {"pid": 8800, "create_time": 10.0, "cmdline": ["python", "pipeline_worker.py", "--pipeline", "data_connector"]},
            {"pid": 8801, "create_time": 11.0, "cmdline": ["python", "pipeline_worker.py", "--pipeline", "data_connector"]},
        ]
        with mock.patch(
            "services.pipeline_worker_supervision.pipeline_worker_processes_for_id",
            return_value=processes,
        ):
            result = reconcile_duplicate_pipeline_worker_processes(
                "data_connector",
                keeper_pid=8801,
                terminate_pid_fn=lambda pid: terminated.append(int(pid)) or True,
            )

        self.assertEqual(result["terminated_count"], 1)
        self.assertEqual(terminated, [8800])

    def test_reconcile_terminates_duplicate_workers_even_when_supervised_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            keeper_pid = 8805
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=keeper_pid)
            write_worker_heartbeat(
                "data_connector",
                runtime_root=runtime_root,
                status="idle",
                pid=keeper_pid,
                now_fn=lambda: 100.0,
            )
            terminated: list[int] = []

            with mock.patch(
                "services.pipeline_worker_supervision.pipeline_worker_processes_for_id",
                return_value=[
                    {"pid": 8804, "create_time": 9.0},
                    {"pid": keeper_pid, "create_time": 10.0},
                ],
            ):
                result = reconcile_pipeline_worker_scope(
                    "data_connector",
                    runtime_root=runtime_root,
                    now_fn=lambda: 100.0,
                    pid_alive_fn=lambda pid: int(pid) == keeper_pid,
                    terminate_pid_fn=lambda pid: terminated.append(int(pid)) or True,
                )

            self.assertEqual(result["status"], "no_action")
            self.assertEqual(terminated, [8804])
            self.assertIn("terminated_duplicate_worker_processes", result.get("actions") or [])

    def test_reconcile_reclaims_live_unsupervised_owner(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            live_pid = 8801
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=live_pid)
            write_worker_heartbeat(
                "data_connector",
                runtime_root=runtime_root,
                status="running",
                pid=live_pid,
                now_fn=lambda: 100.0,
            )
            terminated: list[int] = []

            result = reconcile_pipeline_worker_scope(
                "data_connector",
                runtime_root=runtime_root,
                stale_after_sec=10,
                now_fn=lambda: 500.0,
                pid_alive_fn=lambda pid: int(pid) == live_pid,
                terminate_pid_fn=lambda pid: terminated.append(int(pid)) or True,
            )

            self.assertEqual(result["status"], "orphan_reclaimed")
            self.assertEqual(terminated, [live_pid])
            self.assertFalse(read_worker_lease("data_connector", runtime_root=runtime_root).get("present"))
            self.assertFalse(worker_heartbeat_path("data_connector", runtime_root=runtime_root).exists())

    def test_reconcile_then_ensure_starts_worker_after_dead_lease(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=8802)
            write_worker_heartbeat("data_connector", runtime_root=runtime_root, status="running", pid=8802)
            worker_script = runtime_root / "scripts" / "pipeline_worker.py"
            worker_script.parent.mkdir(parents=True, exist_ok=True)
            worker_script.write_text("# stub", encoding="utf-8")
            venv_python = runtime_root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("", encoding="utf-8")

            reconcile_pipeline_workers_for_ids(
                ["data_connector"],
                runtime_root=runtime_root,
                pid_alive_fn=lambda _pid: False,
            )
            popen_mock = mock.Mock(side_effect=self._mock_supervised_spawn(runtime_root, pid=8803))
            result = ensure_pipeline_worker_running(
                "data_connector",
                worker_script=worker_script,
                venv_python=venv_python,
                runtime_root=runtime_root,
                subprocess_module=mock.Mock(Popen=popen_mock, CREATE_NEW_PROCESS_GROUP=0),
                os_name="nt",
                pid_alive_fn=lambda pid: int(pid) == 8803,
            )

            self.assertEqual(result["status"], "start_requested")
            popen_mock.assert_called_once()

    def test_foreign_heartbeat_does_not_steal_live_lease(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            lease_pid = 8800
            foreign_pid = 8801
            alive = {lease_pid, foreign_pid}
            with mock.patch(
                "services.pipeline_worker_supervision.pid_alive",
                side_effect=lambda pid, pid_alive_fn=None: (
                    bool(pid_alive_fn(pid)) if pid_alive_fn is not None else int(pid) in alive
                ),
            ):
                write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=lease_pid)
                write_worker_heartbeat(
                    "data_connector",
                    runtime_root=runtime_root,
                    status="running",
                    pid=foreign_pid,
                )
                lease = read_worker_lease(
                    "data_connector",
                    runtime_root=runtime_root,
                    pid_alive_fn=lambda pid: int(pid) in alive,
                )
                heartbeat = read_worker_heartbeat(
                    "data_connector",
                    runtime_root=runtime_root,
                    pid_alive_fn=lambda pid: int(pid) in alive,
                )
            self.assertEqual(lease.get("lease_owner_pid"), lease_pid)
            self.assertEqual(heartbeat.get("pid"), foreign_pid)
            self.assertFalse(heartbeat.get("supervised_ok"))

    def test_reconcile_terminates_foreign_heartbeat_owner(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            lease_pid = 8800
            foreign_pid = 8801
            alive = {lease_pid, foreign_pid}
            terminated: list[int] = []
            with mock.patch(
                "services.pipeline_worker_supervision.pid_alive",
                side_effect=lambda pid, pid_alive_fn=None: (
                    bool(pid_alive_fn(pid)) if pid_alive_fn is not None else int(pid) in alive
                ),
            ):
                write_worker_lease("data_connector", runtime_root=runtime_root, lease_owner_pid=lease_pid)
                write_worker_heartbeat(
                    "data_connector",
                    runtime_root=runtime_root,
                    status="running",
                    pid=foreign_pid,
                )
                result = reconcile_pipeline_worker_scope(
                    "data_connector",
                    runtime_root=runtime_root,
                    pid_alive_fn=lambda pid: int(pid) in alive,
                    terminate_pid_fn=lambda pid: terminated.append(int(pid)) or True,
                )

            self.assertEqual(result["status"], "orphan_reclaimed")
            self.assertEqual(terminated, [foreign_pid])
            self.assertIn("terminated_foreign_heartbeat_owner", result.get("actions") or [])
            self.assertFalse(read_worker_lease("data_connector", runtime_root=runtime_root).get("present"))
            self.assertFalse(worker_heartbeat_path("data_connector", runtime_root=runtime_root).exists())

    def test_ensure_reports_start_failed_when_child_exits_quickly(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            worker_script = runtime_root / "scripts" / "pipeline_worker.py"
            worker_script.parent.mkdir(parents=True, exist_ok=True)
            worker_script.write_text("# stub", encoding="utf-8")
            venv_python = runtime_root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("", encoding="utf-8")
            proc = mock.Mock(pid=8804, poll=mock.Mock(return_value=1))
            popen_mock = mock.Mock(return_value=proc)
            result = ensure_pipeline_worker_running(
                "data_connector",
                worker_script=worker_script,
                venv_python=venv_python,
                runtime_root=runtime_root,
                subprocess_module=mock.Mock(Popen=popen_mock, CREATE_NEW_PROCESS_GROUP=0),
                os_name="nt",
                pid_alive_fn=lambda _pid: False,
            )
            self.assertEqual(result["status"], "start_failed")
            self.assertIn(
                str(result.get("detail") or ""),
                {"child_exited_before_supervision", "worker_supervision_timeout"},
            )
            self.assertFalse(read_worker_lease("data_connector", runtime_root=runtime_root).get("present"))

    def test_heartbeat_write_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            path = worker_heartbeat_path("data_connector", runtime_root=runtime_root)
            observed: list[str] = []

            original_replace = Path.replace

            def _spy_replace(self, target):  # type: ignore[no-untyped-def]
                observed.append(self.name)
                return original_replace(self, target)

            with mock.patch.object(Path, "replace", _spy_replace):
                write_worker_heartbeat("data_connector", runtime_root=runtime_root, status="running", pid=6001)
            self.assertTrue(path.exists())
            self.assertTrue(any(name.endswith(".tmp") for name in observed))

    def test_heartbeat_write_retries_replace_when_target_is_contended(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            path = worker_heartbeat_path("data_connector", runtime_root=runtime_root)
            original_replace = Path.replace
            attempts = {"count": 0}

            def _flaky_replace(self, target):  # type: ignore[no-untyped-def]
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise PermissionError(13, "Access is denied")
                return original_replace(self, target)

            with mock.patch.object(Path, "replace", _flaky_replace):
                write_worker_heartbeat("data_connector", runtime_root=runtime_root, status="running", pid=6002)
            self.assertTrue(path.exists())
            self.assertGreaterEqual(attempts["count"], 3)

    def test_ensure_pipeline_workers_for_ids_isolates_per_pipeline_failure(self) -> None:
        """One pipeline raising must not abort ensure for the rest."""
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            worker_script = runtime_root / "scripts" / "pipeline_worker.py"
            worker_script.parent.mkdir(parents=True, exist_ok=True)
            worker_script.write_text("# stub", encoding="utf-8")
            venv_python = runtime_root / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("", encoding="utf-8")

            def _side_effect(pipeline_id, **_kwargs):
                if pipeline_id == "edfi":
                    raise SystemError("<function PurePath.__str__ ... returned a result with an exception set>")
                return {
                    "ok": True,
                    "status": "already_running",
                    "pipeline_id": pipeline_id,
                    "heartbeat": {},
                    "lease": {},
                }

            with mock.patch(
                "services.pipeline_worker_supervision.ensure_pipeline_worker_running",
                side_effect=_side_effect,
            ):
                result = ensure_pipeline_workers_for_ids(
                    ["edfi", "data_connector"],
                    worker_script=worker_script,
                    venv_python=venv_python,
                    runtime_root=runtime_root,
                )

            self.assertEqual(result.get("worker_count"), 2)
            self.assertEqual(result.get("failed_count"), 1)
            self.assertEqual(result.get("running_count"), 1)
            workers = {str(item.get("pipeline_id")): item for item in list(result.get("workers") or [])}
            self.assertFalse(bool(workers["edfi"].get("ok")))
            self.assertEqual(workers["edfi"].get("status"), "start_failed")
            self.assertTrue(bool(workers["data_connector"].get("ok")))

    def test_runtime_pipeline_worker_ids_finds_lease_and_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            write_worker_lease("edfi_bisd", runtime_root=runtime_root, lease_owner_pid=30440)
            write_worker_heartbeat("reports", runtime_root=runtime_root, status="running", pid=43748)
            (runtime_root / "pipelines" / "idle").mkdir(parents=True)
            self.assertEqual(
                runtime_pipeline_worker_ids(runtime_root=runtime_root),
                ["edfi_bisd", "reports"],
            )

    def test_stop_pipeline_worker_terminates_live_owner_and_clears_lease(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime_root = Path(td)
            live_pid = 30440
            write_worker_lease("edfi_bisd", runtime_root=runtime_root, lease_owner_pid=live_pid)
            write_worker_heartbeat("edfi_bisd", runtime_root=runtime_root, status="running", pid=live_pid)
            terminated: list[int] = []
            result = stop_pipeline_worker(
                "edfi_bisd",
                runtime_root=runtime_root,
                pid_alive_fn=lambda pid: int(pid) == live_pid,
                terminate_pid_fn=lambda pid: terminated.append(int(pid)) or True,
            )
            self.assertEqual(result.get("status"), "stopped")
            self.assertEqual(terminated, [live_pid])
            self.assertFalse(read_worker_lease("edfi_bisd", runtime_root=runtime_root).get("present"))
            self.assertFalse(worker_heartbeat_path("edfi_bisd", runtime_root=runtime_root).exists())


if __name__ == "__main__":
    unittest.main()