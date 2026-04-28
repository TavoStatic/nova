import json
import tempfile
import unittest
from pathlib import Path

from services.runtime_heartbeat import heartbeat_log_path
from services.runtime_heartbeat import heartbeat_status_path
from services.runtime_heartbeat import heartbeat_write_once


class TestRuntimeHeartbeatService(unittest.TestCase):
    def test_heartbeat_write_once_records_failure_and_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            heartbeat_file = Path(td) / "runtime" / "core.heartbeat"
            status_file = heartbeat_status_path(heartbeat_file)
            log_file = heartbeat_log_path(heartbeat_file)

            state = heartbeat_write_once(
                heartbeat_file,
                status_file=status_file,
                log_file=log_file,
                write_fn=lambda _path: (_ for _ in ()).throw(PermissionError("locked by scanner")),
            )

            self.assertFalse(state.get("ok"))
            self.assertEqual(state.get("consecutive_failures"), 1)
            self.assertEqual(state.get("total_failures"), 1)
            status_payload = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertIn("locked by scanner", status_payload.get("last_error", ""))
            self.assertIn("heartbeat write failed", log_file.read_text(encoding="utf-8"))

            recovered = heartbeat_write_once(
                heartbeat_file,
                status_file=status_file,
                log_file=log_file,
                state=state,
            )

            self.assertTrue(recovered.get("ok"))
            self.assertEqual(recovered.get("consecutive_failures"), 0)
            self.assertEqual(recovered.get("total_failures"), 1)
            self.assertTrue(recovered.get("recovered_at"))
            self.assertTrue(heartbeat_file.exists())
            self.assertIn("heartbeat write recovered", log_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
