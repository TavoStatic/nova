import tempfile
import unittest
from pathlib import Path

from services.pipeline_worker_supervision import (
    read_worker_heartbeat,
    read_worker_lease,
    write_worker_heartbeat,
    write_worker_lease,
)


class TestPipelineWorkerSupervision(unittest.TestCase):
    def test_fresh_generic_worker_heartbeat_is_supervised(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td)
            write_worker_lease("example_connector", runtime_root=runtime, lease_owner_pid=4242)
            write_worker_heartbeat("example_connector", runtime_root=runtime, status="running", pid=4242)
            heartbeat = read_worker_heartbeat(
                "example_connector",
                runtime_root=runtime,
                stale_after_sec=30,
                pid_alive_fn=lambda pid: int(pid) == 4242,
            )
            self.assertTrue(heartbeat["present"])
            self.assertTrue(heartbeat["fresh"])
            self.assertTrue(heartbeat["supervised_ok"])

    def test_stale_generic_worker_heartbeat_is_not_supervised(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td)
            write_worker_lease("example_connector", runtime_root=runtime, lease_owner_pid=4242)
            write_worker_heartbeat(
                "example_connector",
                runtime_root=runtime,
                status="running",
                pid=4242,
                now_fn=lambda: 100.0,
            )
            heartbeat = read_worker_heartbeat(
                "example_connector",
                runtime_root=runtime,
                stale_after_sec=10,
                now_fn=lambda: 200.0,
                pid_alive_fn=lambda pid: True,
            )
            self.assertTrue(heartbeat["present"])
            self.assertFalse(heartbeat["fresh"])
            self.assertFalse(heartbeat["supervised_ok"])

    def test_worker_lease_is_readable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td)
            write_worker_lease("example_connector", runtime_root=runtime, lease_owner_pid=4242)
            lease = read_worker_lease("example_connector", runtime_root=runtime, pid_alive_fn=lambda pid: True)
            self.assertTrue(lease["present"])
            self.assertEqual(lease["lease_owner_pid"], 4242)


if __name__ == "__main__":
    unittest.main()
