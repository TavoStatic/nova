import unittest
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
        with mock.patch("tools.runtime_detach.os.name", "nt"):
            ok, pid, detail = spawn_unattached(
                ["python.exe", "nova_guard.py"],
                cwd=Path("."),
                wmi_create_fn=lambda command, cwd: (True, 31072, "wmi_created:31072"),
                popen_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("popen should not run")),
            )
        self.assertTrue(ok)
        self.assertEqual(pid, 31072)
        self.assertIn("wmi_created", detail)

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
