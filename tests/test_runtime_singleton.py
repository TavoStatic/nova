import tempfile
import unittest
from pathlib import Path

from tools.runtime_singleton import acquire_role_singleton, release_role_singleton


class TestRuntimeSingleton(unittest.TestCase):
    def test_file_lock_blocks_second_acquirer(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td)
            ok1, detail1 = acquire_role_singleton("test-role", runtime_dir=runtime, use_mutex=False)
            self.assertTrue(ok1)
            ok2, detail2 = acquire_role_singleton("test-role", runtime_dir=runtime, use_mutex=False)
            self.assertTrue(ok2)
            self.assertIn("already_held_in_process", detail2)
            release_role_singleton("test-role")
            ok3, _detail3 = acquire_role_singleton("test-role", runtime_dir=runtime, use_mutex=False)
            self.assertTrue(ok3)
            release_role_singleton("test-role")

    def test_file_lock_replaces_stale_pid(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td)
            lock = runtime / "stale.singleton.lock"
            lock.write_text("99999999", encoding="utf-8")
            ok, detail = acquire_role_singleton("stale", runtime_dir=runtime, use_mutex=False)
            self.assertTrue(ok, detail)
            release_role_singleton("stale")


if __name__ == "__main__":
    unittest.main()
