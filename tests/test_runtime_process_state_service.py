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

    def test_matches_relative_script_token_against_process_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "nova_guard.py"
            script.write_text("print('guard')\n", encoding="utf-8")

            matched = RUNTIME_PROCESS_STATE_SERVICE.matches_script_process(
                ["python", "nova_guard.py"],
                script,
                cwd=root,
            )

        self.assertTrue(matched)

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

    def test_cached_logical_service_processes_from_runtime_uses_cache_bundle(self):
        cache = {}
        service_calls = []

        out = RUNTIME_PROCESS_STATE_SERVICE.cached_logical_service_processes_from_runtime(
            Path("guard.py"),
            runtime_scope={
                "_PROCESS_SCAN_CACHE": cache,
                "time": SimpleNamespace(monotonic=lambda: 100.0),
                "_logical_service_processes": lambda script_path, root_pid=None: service_calls.append((script_path, root_pid)) or [{"pid": 10}],
            },
            cache_key="guard",
            max_age_seconds=5.0,
        )

        self.assertEqual(out, [{"pid": 10}])
        self.assertEqual(service_calls, [(Path("guard.py"), None)])
        self.assertIn("guard", cache)

    def test_prune_orphaned_core_artifacts_from_runtime_uses_runtime_scope(self):
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = Path(td)
            state_file = runtime_dir / "core_state.json"
            heartbeat_file = runtime_dir / "core.heartbeat"
            state_file.write_text("{}", encoding="utf-8")
            heartbeat_file.write_text("123", encoding="utf-8")

            RUNTIME_PROCESS_STATE_SERVICE.prune_orphaned_core_artifacts_from_runtime(
                [],
                None,
                False,
                20,
                runtime_scope={
                    "RUNTIME_DIR": runtime_dir,
                    "_artifact_age_seconds": lambda path: 20,
                    "_remove_runtime_artifact": lambda path: Path(path).unlink(),
                },
            )

            self.assertFalse(state_file.exists())
            self.assertFalse(heartbeat_file.exists())


if __name__ == "__main__":
    unittest.main()
