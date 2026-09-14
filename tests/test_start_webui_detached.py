import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.start_webui_detached as launcher


class TestStartWebuiDetached(unittest.TestCase):
    def test_wait_for_http_ready_accepts_ready_child(self):
        with mock.patch.object(launcher, "_http_ready", return_value=True), mock.patch.object(
            launcher, "_pid_exists", return_value=True
        ):
            self.assertTrue(launcher.wait_for_http_ready(123, "127.0.0.1", 8080, timeout=0.1, poll=0.01))

    def test_wait_for_http_ready_reports_immediate_child_exit(self):
        with mock.patch.object(launcher, "_http_ready", return_value=False), mock.patch.object(
            launcher, "_pid_exists", return_value=False
        ):
            self.assertFalse(launcher.wait_for_http_ready(123, "127.0.0.1", 8080, timeout=1, poll=0.01))

    def test_main_creates_logs_passes_paths_and_preserves_pid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = root / "logs"
            with mock.patch.object(launcher, "ROOT", root), mock.patch.object(launcher, "LOG_DIR", logs), mock.patch.object(
                launcher, "HTTP_STDOUT_LOG", logs / "nova_http.out.log"
            ), mock.patch.object(launcher, "HTTP_STDERR_LOG", logs / "nova_http.err.log"), mock.patch.object(
                launcher, "HTTP_EXIT_CODE_FILE", logs / "nova_http.exitcode"
            ), mock.patch.object(launcher, "wait_for_http_ready", return_value=True), mock.patch.object(
                launcher, "spawn_unattached", return_value=(True, 4321, "wmi_created:4321")
            ) as spawn, mock.patch("sys.argv", ["start_webui_detached.py"]):
                (root / ".venv" / "Scripts").mkdir(parents=True)
                (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
                (root / "nova_http.py").write_text("", encoding="utf-8")
                self.assertEqual(launcher.main(), 0)

            kwargs = spawn.call_args.kwargs
            self.assertEqual(kwargs["stdout_path"], logs / "nova_http.out.log")
            self.assertEqual(kwargs["stderr_path"], logs / "nova_http.err.log")
            self.assertEqual(kwargs["exit_code_path"], logs / "nova_http.exitcode")
            self.assertTrue((logs / "nova_http.out.log").exists())
            self.assertTrue((logs / "nova_http.err.log").exists())

    def test_main_surfaces_stderr_when_child_exits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = root / "logs"
            with mock.patch.object(launcher, "ROOT", root), mock.patch.object(launcher, "LOG_DIR", logs), mock.patch.object(
                launcher, "HTTP_STDOUT_LOG", logs / "nova_http.out.log"
            ), mock.patch.object(launcher, "HTTP_STDERR_LOG", logs / "nova_http.err.log"), mock.patch.object(
                launcher, "HTTP_EXIT_CODE_FILE", logs / "nova_http.exitcode"
            ), mock.patch.object(launcher, "wait_for_http_ready", return_value=False), mock.patch.object(
                launcher, "spawn_unattached", return_value=(True, 4321, "wmi_created:4321")
            ), mock.patch("sys.argv", ["start_webui_detached.py"]):
                (root / ".venv" / "Scripts").mkdir(parents=True)
                (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
                (root / "nova_http.py").write_text("", encoding="utf-8")
                logs.mkdir()
                (logs / "nova_http.err.log").write_text("startup exploded\n", encoding="utf-8")
                (logs / "nova_http.exitcode").write_text("1\n", encoding="utf-8")
                with mock.patch("builtins.print") as printed:
                    self.assertEqual(launcher.main(), 1)
                    output = "\n".join(str(call) for call in printed.call_args_list)
                self.assertIn("startup exploded", output)


if __name__ == "__main__":
    unittest.main()
