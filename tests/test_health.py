import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import health


class TestHealthCheck(unittest.TestCase):
    def test_check_heartbeat_missing(self):
        with tempfile.TemporaryDirectory() as td:
            hb = Path(td) / "core.heartbeat"
            with patch.object(health, "HEARTBEAT", hb):
                ok, info = health.check_heartbeat(max_age=10)
                self.assertFalse(ok)
                self.assertEqual(info, "missing")

    def test_check_state_invalid_pid(self):
        with tempfile.TemporaryDirectory() as td:
            st = Path(td) / "core_state.json"
            st.write_text(json.dumps({"pid": 0}), encoding="utf-8")
            with patch.object(health, "STATE", st):
                ok, info = health.check_state()
                self.assertFalse(ok)
                self.assertEqual(info, "invalid-pid")

    def test_check_heartbeat_stale(self):
        with tempfile.TemporaryDirectory() as td:
            hb = Path(td) / "core.heartbeat"
            hb.write_text("x", encoding="utf-8")
            stale_mtime = 1_000.0
            os.utime(hb, (stale_mtime, stale_mtime))
            with patch.object(health, "HEARTBEAT", hb), patch("health.time.time", return_value=1_100.0):
                ok, info = health.check_heartbeat(max_age=10)
                self.assertFalse(ok)
                self.assertTrue(info.startswith("age="))


if __name__ == "__main__":
    unittest.main()
