import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import nova_guard
import nova_http


class TestRuntimeRecovery(unittest.TestCase):
    @staticmethod
    def _fake_process_iter(*rows):
        return [SimpleNamespace(info=row) for row in rows]

    def test_guard_status_payload_uses_pid_exists_and_runtime_flags(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "guard.lock").write_text("{}", encoding="utf-8")
            (runtime_dir / "guard.stop").write_text("stop", encoding="utf-8")
            (runtime_dir / "guard_pid.json").write_text(
                json.dumps({"pid": 4321}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http.psutil.pid_exists", return_value=True) as pid_exists:
                payload = nova_http._guard_status_payload()

            self.assertTrue(payload["running"])
            self.assertEqual(payload["pid"], 4321)
            self.assertTrue(payload["lock_exists"])
            self.assertTrue(payload["stop_flag"])
            pid_exists.assert_called_once_with(4321)

    def test_guard_status_payload_collapses_wrapper_child_pair_to_leaf(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "guard.lock").write_text("{}", encoding="utf-8")
            (runtime_dir / "guard_pid.json").write_text(
                json.dumps({"pid": 7000, "create_time": 70.0}, ensure_ascii=True),
                encoding="utf-8",
            )
            processes = self._fake_process_iter(
                {"pid": 7000, "ppid": 1, "cmdline": [str(nova_http.VENV_PY), str(nova_http.GUARD_PY)], "create_time": 70.0},
                {"pid": 8000, "ppid": 7000, "cmdline": [str(nova_http.VENV_PY), str(nova_http.GUARD_PY)], "create_time": 71.0},
            )

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http.psutil.pid_exists", return_value=True), \
                mock.patch("nova_http.psutil.process_iter", return_value=processes):
                payload = nova_http._guard_status_payload()

            self.assertTrue(payload["running"])
            self.assertEqual(payload["pid"], 8000)
            self.assertEqual(payload["process_count"], 1)

    def test_core_status_payload_treats_fresh_heartbeat_as_running(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "core_state.json").write_text(
                json.dumps({"pid": 9876, "create_time": 12.5}, ensure_ascii=True),
                encoding="utf-8",
            )

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http.psutil.pid_exists", return_value=False) as pid_exists, \
                mock.patch("nova_http._heartbeat_age_seconds", return_value=0):
                payload = nova_http._core_status_payload()

            self.assertTrue(payload["running"])
            self.assertEqual(payload["pid"], 9876)
            self.assertEqual(payload["create_time"], 12.5)
            self.assertEqual(payload["heartbeat_age_sec"], 0)
            pid_exists.assert_called_once_with(9876)

    def test_core_status_payload_ignores_unrelated_live_process_during_heartbeat_only_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "core_state.json").write_text(
                json.dumps({"pid": 9876, "create_time": 12.5}, ensure_ascii=True),
                encoding="utf-8",
            )
            processes = self._fake_process_iter(
                {
                    "pid": 4321,
                    "ppid": 1,
                    "cmdline": [str(nova_http.VENV_PY), str(nova_http.CORE_PY), "--heartbeat", "x", "--statefile", "y"],
                    "create_time": 88.0,
                }
            )

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http.psutil.pid_exists", return_value=False) as pid_exists, \
                mock.patch("nova_http._heartbeat_age_seconds", return_value=0), \
                mock.patch("nova_http.psutil.process_iter", return_value=processes):
                payload = nova_http._core_status_payload()

            self.assertTrue(payload["running"])
            self.assertEqual(payload["status"], "heartbeat_only")
            self.assertEqual(payload["pid"], 9876)
            self.assertEqual(payload["create_time"], 12.5)
            self.assertEqual(payload["process_count"], 1)
            pid_exists.assert_called_once_with(9876)

    def test_core_status_payload_collapses_wrapper_child_pair_to_leaf(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "core_state.json").write_text(
                json.dumps({"pid": 9000, "create_time": 90.0}, ensure_ascii=True),
                encoding="utf-8",
            )
            processes = self._fake_process_iter(
                {"pid": 8500, "ppid": 1, "cmdline": [str(nova_http.VENV_PY), str(nova_http.CORE_PY), "--heartbeat", "x", "--statefile", "y"], "create_time": 89.0},
                {"pid": 9000, "ppid": 8500, "cmdline": [str(nova_http.VENV_PY), str(nova_http.CORE_PY), "--heartbeat", "x", "--statefile", "y"], "create_time": 90.0},
            )

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http.psutil.pid_exists", return_value=True), \
                mock.patch("nova_http._heartbeat_age_seconds", return_value=1), \
                mock.patch("nova_http.psutil.process_iter", return_value=processes):
                payload = nova_http._core_status_payload()

            self.assertTrue(payload["running"])
            self.assertEqual(payload["pid"], 9000)
            self.assertEqual(payload["process_count"], 1)

    def test_http_status_payload_reports_current_process_without_full_scan(self):
        fake_process = mock.Mock()
        fake_process.create_time.return_value = 321.5

        with mock.patch("nova_http.os.getpid", return_value=2468), \
            mock.patch("nova_http.psutil.Process", return_value=fake_process) as process_ctor:
            payload = nova_http._http_status_payload()

        self.assertTrue(payload["running"])
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["pid"], 2468)
        self.assertEqual(payload["create_time"], 321.5)
        self.assertEqual(payload["process_count"], 1)
        process_ctor.assert_called_once_with(2468)

    def test_guard_status_payload_prunes_orphaned_lock_and_pid_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            lock_file = runtime_dir / "guard.lock"
            pid_file = runtime_dir / "guard_pid.json"
            lock_file.write_text("{}", encoding="utf-8")
            pid_file.write_text(json.dumps({"pid": 4321, "create_time": 43.21}, ensure_ascii=True), encoding="utf-8")

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http._logical_service_processes", return_value=[]), \
                mock.patch("nova_http.psutil.pid_exists", return_value=False), \
                mock.patch("nova_http.time.time", return_value=200.0), \
                mock.patch("nova_http._artifact_age_seconds", return_value=100):
                payload = nova_http._guard_status_payload()

            self.assertEqual(payload["status"], "stopped")
            self.assertFalse(payload["lock_exists"])
            self.assertFalse(lock_file.exists())
            self.assertFalse(pid_file.exists())

    def test_cached_logical_service_processes_reuses_recent_fallback_scan(self):
        first_result = [{"pid": 100, "ppid": 1, "create_time": 10.0, "cmdline": ["python", str(nova_http.GUARD_PY)]}]

        with mock.patch.dict(nova_http._PROCESS_SCAN_CACHE, {}, clear=True), \
            mock.patch("nova_http._logical_service_processes", return_value=first_result) as logical, \
            mock.patch("nova_http.time.monotonic", side_effect=[100.0, 103.0]):
            first = nova_http._cached_logical_service_processes(
                nova_http.GUARD_PY,
                cache_key="guard-steady-state",
                max_age_seconds=5.0,
            )
            second = nova_http._cached_logical_service_processes(
                nova_http.GUARD_PY,
                cache_key="guard-steady-state",
                max_age_seconds=5.0,
            )

        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        logical.assert_called_once_with(nova_http.GUARD_PY, root_pid=None)

    def test_guard_status_payload_uses_cached_fallback_only_without_runtime_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http._cached_logical_service_processes", return_value=[]) as cached, \
                mock.patch("nova_http._logical_service_processes", return_value=[]) as logical:
                payload = nova_http._guard_status_payload()

            self.assertEqual(payload["status"], "stopped")
            cached.assert_called_once_with(
                nova_http.GUARD_PY,
                cache_key="guard-steady-state",
                max_age_seconds=nova_http.PROCESS_SCAN_CACHE_TTL_SECONDS,
            )
            logical.assert_not_called()

        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            (runtime_dir / "guard.lock").write_text("{}", encoding="utf-8")

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http._cached_logical_service_processes", return_value=[]) as cached, \
                mock.patch("nova_http._logical_service_processes", return_value=[]) as logical:
                payload = nova_http._guard_status_payload()

            self.assertEqual(payload["status"], "boot_timeout")
            cached.assert_not_called()
            logical.assert_called_once_with(nova_http.GUARD_PY, root_pid=None)

    def test_guard_status_payload_can_skip_fallback_scan_for_fast_control_path(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http._cached_logical_service_processes", return_value=[]) as cached, \
                mock.patch("nova_http._logical_service_processes", return_value=[]) as logical:
                payload = nova_http._guard_status_payload(include_fallback_scan=False)

            self.assertEqual(payload["status"], "stopped")
            self.assertFalse(payload["running"])
            self.assertEqual(payload["process_count"], 0)
            cached.assert_not_called()
            logical.assert_not_called()

    def test_core_status_payload_prunes_orphaned_state_and_stale_heartbeat(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            state_file = runtime_dir / "core_state.json"
            heartbeat_file = runtime_dir / "core.heartbeat"
            state_file.write_text(json.dumps({"pid": 9876, "create_time": 98.76}, ensure_ascii=True), encoding="utf-8")
            heartbeat_file.write_text("100.0", encoding="utf-8")

            with mock.patch.object(nova_http, "RUNTIME_DIR", runtime_dir), \
                mock.patch("nova_http._logical_service_processes", return_value=[]), \
                mock.patch("nova_http.psutil.pid_exists", return_value=False), \
                mock.patch("nova_http._artifact_age_seconds", return_value=100), \
                mock.patch("nova_http._heartbeat_age_seconds", side_effect=[100, None]):
                payload = nova_http._core_status_payload()

            self.assertEqual(payload["status"], "stopped")
            self.assertFalse(payload["state_exists"])
            self.assertIsNone(payload["heartbeat_age_sec"])
            self.assertFalse(state_file.exists())
            self.assertFalse(heartbeat_file.exists())

    def test_acquire_lock_or_exit_replaces_stale_lock(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            lock_file = runtime_dir / "guard.lock"
            pid_file = runtime_dir / "guard_pid.json"
            lock_file.write_text(
                json.dumps(
                    {
                        "pid": 1111,
                        "create_time": 11.0,
                        "command": {
                            "executable": str(nova_guard.VENV_PY),
                            "script": str(nova_guard.GUARD_SCRIPT),
                        },
                        "ts": "old",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with mock.patch.object(nova_guard, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(nova_guard, "LOCK_FILE", lock_file), \
                mock.patch.object(nova_guard, "GUARD_PID_FILE", pid_file), \
                mock.patch.object(nova_guard, "log", lambda _msg: None), \
                mock.patch.object(
                    nova_guard,
                    "_current_guard_identity_payload",
                    return_value={
                        "pid": 2222,
                        "create_time": 22.0,
                        "command": {
                            "executable": str(nova_guard.VENV_PY),
                            "script": str(nova_guard.GUARD_SCRIPT),
                        },
                        "ts": "2026-03-15 17:40:00",
                    },
                ), \
                mock.patch.object(nova_guard, "_lock_belongs_to_live_guard", return_value=False) as lock_matches:
                nova_guard.acquire_lock_or_exit()

            written_lock = json.loads(lock_file.read_text(encoding="utf-8"))
            written_pid = json.loads(pid_file.read_text(encoding="utf-8"))
            self.assertEqual(written_lock["pid"], 2222)
            self.assertEqual(written_lock["create_time"], 22.0)
            self.assertEqual(written_pid["pid"], 2222)
            lock_matches.assert_called_once()

    def test_acquire_lock_or_exit_exits_when_live_guard_exists(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            lock_file = runtime_dir / "guard.lock"
            pid_file = runtime_dir / "guard_pid.json"
            lock_file.write_text(
                json.dumps(
                    {
                        "pid": 3333,
                        "create_time": 33.0,
                        "command": {
                            "executable": str(nova_guard.VENV_PY),
                            "script": str(nova_guard.GUARD_SCRIPT),
                        },
                        "ts": "old",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with mock.patch.object(nova_guard, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(nova_guard, "LOCK_FILE", lock_file), \
                mock.patch.object(nova_guard, "GUARD_PID_FILE", pid_file), \
                mock.patch.object(nova_guard, "log", lambda _msg: None), \
                mock.patch.object(
                    nova_guard,
                    "_current_guard_identity_payload",
                    return_value={
                        "pid": 4444,
                        "create_time": 44.0,
                        "command": {
                            "executable": str(nova_guard.VENV_PY),
                            "script": str(nova_guard.GUARD_SCRIPT),
                        },
                        "ts": "2026-03-15 17:40:00",
                    },
                ), \
                mock.patch.object(nova_guard, "_lock_belongs_to_live_guard", return_value=True), \
                self.assertRaises(SystemExit) as raised:
                nova_guard.acquire_lock_or_exit()

            self.assertEqual(raised.exception.code, 0)
            self.assertFalse(pid_file.exists())
            retained_lock = json.loads(lock_file.read_text(encoding="utf-8"))
            self.assertEqual(retained_lock["pid"], 3333)

    def test_lock_identity_rejects_pid_reuse_with_wrong_command(self):
        fake_process = mock.Mock()
        fake_process.create_time.return_value = 55.0
        fake_process.cmdline.return_value = [r"C:\Windows\System32\svchost.exe"]

        with mock.patch("nova_guard.psutil.Process", return_value=fake_process):
            self.assertFalse(
                nova_guard._lock_belongs_to_live_guard(
                    {
                        "pid": 5555,
                        "create_time": 55.0,
                        "command": {
                            "executable": str(nova_guard.VENV_PY),
                            "script": str(nova_guard.GUARD_SCRIPT),
                        },
                    }
                )
            )

    def test_supervisor_tick_does_not_respawn_while_booting(self):
        attempt = nova_guard.GuardAttempt(
            pid=1111,
            create_time=10.0,
            started_at=100.0,
            state=nova_guard.STATE_BOOTING,
        )

        with mock.patch("nova_guard._boot_succeeded", return_value=False), \
            mock.patch("nova_guard._boot_failed", return_value=(False, "")), \
            mock.patch("nova_guard.start_new_attempt") as start_new_attempt:
            nova_guard.supervisor_tick(attempt)

        self.assertEqual(attempt.state, nova_guard.STATE_BOOTING)
        start_new_attempt.assert_not_called()

    def test_supervisor_tick_marks_running_attempt_failed_without_immediate_respawn(self):
        attempt = nova_guard.GuardAttempt(
            pid=2222,
            create_time=11.0,
            started_at=100.0,
            state=nova_guard.STATE_RUNNING,
        )

        with mock.patch("nova_guard._runtime_failed", return_value=(True, "heartbeat_stale")), \
            mock.patch("nova_guard.start_new_attempt") as start_new_attempt:
            nova_guard.supervisor_tick(attempt)

        self.assertEqual(attempt.state, nova_guard.STATE_FAILED)
        self.assertEqual(attempt.failure_reason, "heartbeat_stale")
        start_new_attempt.assert_not_called()

    def test_supervisor_tick_resolves_failed_attempt_into_restart_wait(self):
        attempt = nova_guard.GuardAttempt(
            pid=3333,
            create_time=12.0,
            started_at=100.0,
            state=nova_guard.STATE_FAILED,
            failure_reason="boot_timeout",
        )

        with mock.patch("nova_guard._resolve_attempt", return_value=True) as resolve_attempt, \
            mock.patch("nova_guard.time.time", return_value=200.0):
            nova_guard.supervisor_tick(attempt)

        resolve_attempt.assert_called_once_with(attempt)
        self.assertEqual(attempt.state, nova_guard.STATE_RESTART_WAIT)
        self.assertEqual(attempt.next_restart_at, 202.0)
        self.assertEqual(attempt.restart_count, 1)

    def test_supervisor_tick_waits_for_resolution_before_restart_wait(self):
        attempt = nova_guard.GuardAttempt(
            pid=3333,
            create_time=12.0,
            started_at=100.0,
            state=nova_guard.STATE_FAILED,
            failure_reason="boot_timeout",
        )

        with mock.patch("nova_guard._resolve_attempt", return_value=False) as resolve_attempt:
            nova_guard.supervisor_tick(attempt)

        resolve_attempt.assert_called_once_with(attempt)
        self.assertEqual(attempt.state, nova_guard.STATE_FAILED)
        self.assertIsNone(attempt.next_restart_at)

    def test_start_new_attempt_uses_observed_boot_window(self):
        attempt = nova_guard.GuardAttempt()

        with mock.patch("nova_guard._clear_core_runtime_artifacts"), \
            mock.patch("nova_guard.spawn_core", return_value=7777), \
            mock.patch("nova_guard._process_create_time", return_value=77.0), \
            mock.patch("nova_guard._derive_boot_timeout_seconds", return_value=42.0), \
            mock.patch("nova_guard.time.time", return_value=123.0), \
            mock.patch.object(nova_guard, "log", lambda _msg: None):
            nova_guard.start_new_attempt(attempt, "restart")

        self.assertEqual(attempt.pid, 7777)
        self.assertEqual(attempt.create_time, 77.0)
        self.assertEqual(attempt.boot_timeout_seconds, 42.0)
        self.assertEqual(attempt.state, nova_guard.STATE_BOOTING)
        self.assertIsNone(attempt.state_seen_at)
        self.assertIsNone(attempt.heartbeat_seen_at)

    def test_observe_boot_progress_adopts_runtime_child_from_wrapper(self):
        attempt = nova_guard.GuardAttempt(
            pid=7000,
            create_time=70.0,
            started_at=100.0,
            state=nova_guard.STATE_BOOTING,
            resolution_targets=[(7000, 70.0)],
        )
        state = {"pid": 8000, "create_time": 80.0}

        with mock.patch("nova_guard._attempt_is_alive", return_value=True), \
            mock.patch("nova_guard.time.time", return_value=110.0), \
            mock.patch("nova_guard.read_core_state", return_value=state), \
            mock.patch("nova_guard._state_matches_identity", side_effect=lambda incoming_state, pid, create_time: incoming_state["pid"] == pid and incoming_state["create_time"] == create_time), \
            mock.patch("nova_guard._process_identity", return_value=(7000, 70.0)), \
            mock.patch("nova_guard._identity_in_process_tree", side_effect=lambda root, target: root == (7000, 70.0) and target == (8000, 80.0)), \
            mock.patch("nova_guard.is_heartbeat_fresh", return_value=True), \
            mock.patch.object(nova_guard, "log", lambda _msg: None):
            success = nova_guard._observe_boot_progress(attempt)

        self.assertTrue(success)
        self.assertEqual(attempt.pid, 8000)
        self.assertEqual(attempt.create_time, 80.0)
        self.assertEqual(attempt.state_seen_at, 110.0)
        self.assertEqual(attempt.heartbeat_seen_at, 110.0)
        self.assertIn((7000, 70.0), attempt.resolution_targets)
        self.assertIn((8000, 80.0), attempt.resolution_targets)

    def test_supervisor_tick_waits_for_restart_deadline(self):
        attempt = nova_guard.GuardAttempt(
            state=nova_guard.STATE_RESTART_WAIT,
            restart_count=1,
            next_restart_at=250.0,
        )

        with mock.patch("nova_guard.time.time", return_value=240.0), \
            mock.patch("nova_guard.start_new_attempt") as start_new_attempt:
            nova_guard.supervisor_tick(attempt)

        self.assertEqual(attempt.state, nova_guard.STATE_RESTART_WAIT)
        start_new_attempt.assert_not_called()

    def test_supervisor_tick_restarts_only_after_restart_wait_expires(self):
        attempt = nova_guard.GuardAttempt(
            state=nova_guard.STATE_RESTART_WAIT,
            restart_count=1,
            next_restart_at=250.0,
        )

        with mock.patch("nova_guard.time.time", return_value=260.0), \
            mock.patch("nova_guard.start_new_attempt") as start_new_attempt:
            nova_guard.supervisor_tick(attempt)
            self.assertEqual(attempt.state, nova_guard.STATE_IDLE)
            nova_guard.supervisor_tick(attempt)

        start_new_attempt.assert_called_once_with(attempt, "restart")

    def test_powershell_webui_status_uses_logical_processes(self):
        script = (Path(__file__).resolve().parent.parent / "nova.ps1").read_text(encoding="utf-8")

        self.assertIn("function Get-NovaHttpLogicalProcesses", script)
        self.assertIn("function Wait-NovaHttpStopped([int]$bindPort=0, [int]$timeoutSeconds=8)", script)
        self.assertIn("$leaf = @($all | Where-Object { -not $parentIds.ContainsKey([int]$_.ProcessId) })", script)
        self.assertIn('$procs = Get-NovaHttpLogicalProcesses', script)
        self.assertIn('Stop-NovaHttpProcesses | Out-Null', script)
        self.assertIn('if (-not (Wait-NovaHttpStopped ([int]$bindPort) 8)) {', script)
        self.assertIn('function Wait-NovaHttpReady([string]$bindHost, [string]$bindPort, [int]$timeoutSeconds=18)', script)
        self.assertIn('$url = "http://" + $bindHost + ":" + $bindPort + "/api/health"', script)
        self.assertIn('$response = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 6', script)
        self.assertIn('if (-not (Wait-NovaHttpReady $bindHost $bindPort 18)) {', script)
        self.assertIn('Write-Host ("[FAIL] webui process did not become ready on http://" + $bindHost + ":" + $bindPort + "/api/health")', script)
        self.assertIn('$r = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 8', script)
        self.assertIn('Write-Host ("[FAIL] Requested port " + $bindPort + " is still occupied by non-Nova listener(s): " + $owners)', script)
        self.assertIn('if (-not (Wait-NovaHttpStopped 0 8)) {', script)

        stop_idx = script.index('Stop-NovaHttpProcesses | Out-Null')
        wait_idx = script.index('if (-not (Wait-NovaHttpStopped ([int]$bindPort) 8)) {')
        occupied_idx = script.index('$occupied = @(Get-NetTCPConnection -LocalPort ([int]$bindPort) -State Listen -ErrorAction SilentlyContinue)')
        fail_idx = script.index('Write-Host ("[FAIL] Requested port " + $bindPort + " is still occupied by non-Nova listener(s): " + $owners)')

        self.assertLess(stop_idx, wait_idx)
        self.assertLess(wait_idx, occupied_idx)
        self.assertLess(occupied_idx, fail_idx)

    def test_command_center_ui_renders_runtime_process_note(self):
        base = Path(__file__).resolve().parent.parent
        html = (base / "templates" / "control.html").read_text(encoding="utf-8")
        script = (base / "static" / "control.js").read_text(encoding="utf-8")

        self.assertIn('id="runtimeNoteBar"', html)
        self.assertIn("const runtimeNoteBar = document.getElementById('runtimeNoteBar');", script)
        self.assertIn("runtimeNoteBar.textContent = String(latestStatus.runtime_process_note || '');", script)

    def test_command_center_ui_separates_live_sessions_and_test_runs(self):
        base = Path(__file__).resolve().parent.parent
        html = (base / "templates" / "control.html").read_text(encoding="utf-8")
        script = (base / "static" / "control.js").read_text(encoding="utf-8")

        self.assertIn('id="testRunSelect"', html)
        self.assertIn('id="testRunProbeBox"', html)
        self.assertIn('id="testSessionDefinitionSelect"', html)
        self.assertIn('id="testRunDriftGrid"', html)
        self.assertIn("runtime/test_sessions", html)
        self.assertIn("const testRunSelect = document.getElementById('testRunSelect');", script)
        self.assertIn("const testSessionDefinitionSelect = document.getElementById('testSessionDefinitionSelect');", script)
        self.assertIn("getJson('/api/control/test-sessions')", script)
        self.assertIn("bindClick('btnTestRunExecute'", script)
        self.assertIn("bindClick('btnTestRunsRefresh'", script)

    def test_chat_ui_includes_browser_voice_controls(self):
        script = (Path(__file__).resolve().parent.parent / "nova_http.py").read_text(encoding="utf-8")

        self.assertIn('id="btnToggleAudio"', script)
        self.assertIn('id="btnMic"', script)
        self.assertIn("const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;", script)
        self.assertIn("window.speechSynthesis.speak(utterance);", script)


if __name__ == "__main__":
    unittest.main()