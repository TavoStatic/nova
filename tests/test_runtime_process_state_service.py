import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.runtime_process_state import RUNTIME_PROCESS_STATE_SERVICE


class TestRuntimeProcessStateService(unittest.TestCase):
    def test_logical_leaf_processes_filters_parent_launcher(self):
        leaves = RUNTIME_PROCESS_STATE_SERVICE.logical_leaf_processes(
            [
                {"pid": 10, "ppid": 1, "create_time": 1.0},
                {"pid": 11, "ppid": 10, "create_time": 2.0},
            ]
        )

        self.assertEqual(leaves, [{"pid": 11, "ppid": 10, "create_time": 2.0}])

    def test_prune_orphaned_guard_artifacts_removes_old_files(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            lock_file = runtime_dir / "guard.lock"
            pid_file = runtime_dir / "guard_pid.json"
            lock_file.write_text("x", encoding="utf-8")
            pid_file.write_text("x", encoding="utf-8")

            RUNTIME_PROCESS_STATE_SERVICE.prune_orphaned_guard_artifacts(
                [],
                None,
                False,
                runtime_dir=runtime_dir,
                artifact_age_seconds_fn=lambda path: 20,
                remove_runtime_artifact_fn=lambda path: Path(path).unlink(),
            )

            self.assertFalse(lock_file.exists())
            self.assertFalse(pid_file.exists())


if __name__ == "__main__":
    unittest.main()