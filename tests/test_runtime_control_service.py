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
    def test_runtime_artifact_show_action_preserves_message_and_detail(self):
        ok, msg, extra, detail = RUNTIME_CONTROL_SERVICE.runtime_artifact_show_action(
            {"artifact": "guard.log", "lines": 20},
            runtime_artifact_detail_payload_fn=lambda name, max_lines=0: {"ok": True, "name": name, "max_lines": max_lines},
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "runtime_artifact_show_ok")
        self.assertEqual((extra.get("artifact") or {}).get("name"), "guard.log")
        self.assertEqual(detail, "runtime_artifact_show_ok:guard.log")

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