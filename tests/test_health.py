import json
import io
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
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

    def test_run_check_skip_ollama_allows_base_package_profile(self):
        with patch.object(health, "check_heartbeat", return_value=(True, "age=1s")), \
             patch.object(health, "check_state", return_value=(True, "pid=123")), \
             patch.object(health, "check_ollama", return_value=(False, "status=503")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = health.run_check(include_ollama=False)

        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["profile"], "base-package")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["ollama"]["info"], "skipped")
        self.assertFalse(payload["ollama"]["required"])

    def test_run_check_requires_ollama_by_default(self):
        with patch.object(health, "check_heartbeat", return_value=(True, "age=1s")), \
             patch.object(health, "check_state", return_value=(True, "pid=123")), \
             patch.object(health, "check_ollama", return_value=(False, "status=503")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = health.run_check()

        self.assertEqual(code, 1)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["profile"], "runtime")
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["ollama"]["required"])


if __name__ == "__main__":
    unittest.main()
