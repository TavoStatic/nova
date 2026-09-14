import unittest
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

from tools.runtime_detach import quote_windows_command, spawn_unattached


class TestRuntimeDetach(unittest.TestCase):
    def test_quote_windows_command_wraps_spaces(self):
        text = quote_windows_command([r"C:\Nova\.venv\Scripts\python.exe", r"C:\Nova\nova_guard.py"])
        self.assertEqual(text, r"C:\Nova\.venv\Scripts\python.exe C:\Nova\nova_guard.py")
        quoted = quote_windows_command([r"C:\Program Files\python.exe", "nova_http.py"])
        self.assertIn(r'"C:\Program Files\python.exe"', quoted)

    def test_spawn_unattached_prefers_wmi_result(self):
        calls = []

        def create(command, cwd):
            calls.append((command, cwd))
            return True, 31072, "wmi_created:31072"

        with mock.patch("tools.runtime_detach.os.name", "nt"):
            ok, pid, detail = spawn_unattached(
                ["python.exe", "nova_guard.py"],
                cwd=Path("."),
                wmi_create_fn=create,
                popen_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("popen should not run")),
            )
        self.assertTrue(ok)
        self.assertEqual(pid, 31072)
        self.assertIn("wmi_created", detail)
        self.assertEqual(calls[0][0], "python.exe nova_guard.py")

    def test_http_redirect_options_are_opt_in_for_wmi_callers(self):
        calls = []

        def create(command, cwd):
            calls.append(command)
            return True, 31072, "wmi_created:31072"

        with mock.patch("tools.runtime_detach.os.name", "nt"):
            ok, pid, _detail = spawn_unattached(
                ["python.exe", "nova_http.py", "--port", "8080"],
                cwd=Path("."),
                stdout_path=Path("logs/nova_http.out.log"),
                stderr_path=Path("logs/nova_http.err.log"),
                exit_code_path=Path("logs/nova_http.exitcode"),
                wmi_create_fn=create,
            )

        self.assertTrue(ok)
        self.assertEqual(pid, 31072)
        self.assertIn("nova_http.py", calls[0])
        self.assertIn("nova_http.out.log", calls[0])
        self.assertIn("nova_http.err.log", calls[0])
        self.assertIn("nova_http.exitcode", calls[0])

    def test_existing_posix_caller_behavior_is_unchanged_without_redirects(self):
        class _Proc:
            pid = 99

        captured = {}

        def starter(*args, **kwargs):
            captured.update(kwargs)
            return _Proc()

        with mock.patch("tools.runtime_detach.os.name", "posix"):
            ok, pid, detail = spawn_unattached(
                ["python", "nova_guard.py"], cwd=Path("."), popen_fn=starter
            )

        self.assertTrue(ok)
        self.assertEqual(pid, 99)
        self.assertEqual(detail, "posix_detached")
        self.assertIs(captured["stdout"], subprocess.DEVNULL)
        self.assertIs(captured["stderr"], subprocess.DEVNULL)
        self.assertTrue(captured["start_new_session"])

    @unittest.skipUnless(os.name == "nt", "Windows WMI integration test")
    def test_windows_redirected_child_records_output_and_exit_code(self):
        from tools.runtime_detach import spawn_unattached

        with tempfile.TemporaryDirectory(prefix="nova detach test ") as temp_dir:
            root = Path(temp_dir)
            script = root / "write output.py"
            stdout_path = root / "stdout log.txt"
            stderr_path = root / "stderr log.txt"
            exit_path = root / "exit code.txt"
            script.write_text(
                "import sys\n"
                "print('stdout marker', flush=True)\n"
                "print('stderr marker', file=sys.stderr, flush=True)\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
            )

            ok, wrapper_pid, detail = spawn_unattached(
                [sys.executable, str(script)],
                cwd=root,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                exit_code_path=exit_path,
            )
            self.assertTrue(ok, detail)
            self.assertGreater(wrapper_pid or 0, 0)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not exit_path.exists():
                time.sleep(0.05)

            self.assertEqual(exit_path.read_text(encoding="utf-8").strip(), "7")
            self.assertIn("stdout marker", stdout_path.read_text(encoding="utf-8"))
            self.assertIn("stderr marker", stderr_path.read_text(encoding="utf-8"))
            self.assertFalse(_pid_alive(wrapper_pid))

    @unittest.skipUnless(os.name == "nt", "Windows WMI integration test")
    def test_windows_redirected_child_stays_detached_with_spaced_paths(self):
        from tools.runtime_detach import spawn_unattached

        with tempfile.TemporaryDirectory(prefix="nova detach long ") as temp_dir:
            root = Path(temp_dir)
            script = root / "long running.py"
            ready_path = root / "child ready.txt"
            stop_path = root / "child stop.txt"
            stdout_path = root / "stdout log.txt"
            stderr_path = root / "stderr log.txt"
            exit_path = root / "exit code.txt"
            script.write_text(
                "import pathlib, time\n"
                f"ready = pathlib.Path(r'{ready_path}')\n"
                f"stop = pathlib.Path(r'{stop_path}')\n"
                "ready.write_text('ready', encoding='utf-8')\n"
                "while not stop.exists(): time.sleep(0.05)\n",
                encoding="utf-8",
            )
            try:
                ok, wrapper_pid, detail = spawn_unattached(
                    [sys.executable, str(script)],
                    cwd=root,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    exit_code_path=exit_path,
                )
                self.assertTrue(ok, detail)
                self.assertGreater(wrapper_pid or 0, 0)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not ready_path.exists():
                    time.sleep(0.05)
                self.assertTrue(ready_path.exists())
                self.assertTrue(_pid_alive(wrapper_pid))
                children = _child_processes(wrapper_pid)
                self.assertTrue(children)
                self.assertTrue(any(_pid_alive(child.pid) for child in children))
            finally:
                stop_path.write_text("stop", encoding="utf-8")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and _pid_alive(wrapper_pid):
                    time.sleep(0.05)
                for child in _child_processes(wrapper_pid):
                    _terminate_process(child.pid)
                _terminate_process(wrapper_pid)

    def test_spawn_unattached_windows_fails_out_loud_when_wmi_fails(self):
        with mock.patch("tools.runtime_detach.os.name", "nt"):
            ok, pid, detail = spawn_unattached(
                ["python.exe", "nova_guard.py"],
                cwd=Path("."),
                wmi_create_fn=lambda command, cwd: (False, None, "wmi_failed"),
                popen_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("popen must not run")),
            )
        self.assertFalse(ok)
        self.assertIsNone(pid)
        self.assertEqual(detail, "wmi_failed")

    def test_spawn_unattached_posix_uses_new_session(self):
        class _Proc:
            pid = 99

        with mock.patch("tools.runtime_detach.os.name", "posix"):
            ok, pid, detail = spawn_unattached(
                ["python", "nova_guard.py"],
                cwd=Path("."),
                popen_fn=lambda *args, **kwargs: _Proc(),
            )
        self.assertTrue(ok)
        self.assertEqual(pid, 99)
        self.assertEqual(detail, "posix_detached")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    import psutil

    return psutil.pid_exists(pid)


def _child_processes(pid: int | None):
    if not pid:
        return []
    import psutil

    try:
        return psutil.Process(pid).children(recursive=True)
    except psutil.Error:
        return []


def _terminate_process(pid: int | None) -> None:
    if not pid:
        return
    import psutil

    try:
        process = psutil.Process(pid)
        process.terminate()
        process.wait(timeout=2)
    except (psutil.Error, TimeoutError):
        try:
            process.kill()
        except (psutil.Error, UnboundLocalError):
            pass

