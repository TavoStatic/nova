from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.runtime_analytics import RuntimeAnalyticsService, RUNTIME_ANALYTICS_SERVICE


class TestRuntimeAnalyticsService(unittest.TestCase):
    """
    Owner: services/runtime_analytics.py
    Anti-drift: nova_http._runtime_restart_analytics_payload must remain a thin
    wrapper around RUNTIME_ANALYTICS_SERVICE.restart_analytics_payload.
    """

    def setUp(self):
        self.svc = RuntimeAnalyticsService()

    def _write_history(self, entries: list, td: str) -> Path:
        p = Path(td) / "guard_boot_history.json"
        p.write_text(json.dumps(entries), encoding="utf-8")
        return p

    # -- empty / missing file paths --

    def test_missing_file_returns_default_payload(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "guard_boot_history.json"
            payload = self.svc.restart_analytics_payload(boot_history_path=missing)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["flap_level"], "info")

    def test_corrupt_file_returns_danger_payload(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "guard_boot_history.json"
            p.write_text("NOT JSON{{{", encoding="utf-8")
            payload = self.svc.restart_analytics_payload(boot_history_path=p)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["flap_level"], "danger")

    def test_empty_list_returns_default_payload(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_history([], td)
            payload = self.svc.restart_analytics_payload(boot_history_path=p)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 0)

    # -- outcome classification --

    def test_all_successes_returns_good_level(self):
        # Space entries 2h apart so _count_since(3600) stays below 3
        entries = [
            {"ts": 1700000000 + i * 7200, "success": True, "total_observed_s": 5.0}
            for i in range(4)
        ]
        with tempfile.TemporaryDirectory() as td:
            p = self._write_history(entries, td)
            payload = self.svc.restart_analytics_payload(
                boot_history_path=p, now=1700030000
            )
        self.assertEqual(payload["flap_level"], "good")
        self.assertEqual(payload["consecutive_failures"], 0)
        self.assertEqual(payload["success_count"], 4)
        self.assertEqual(payload["failure_count"], 0)

    def test_three_consecutive_failures_triggers_danger(self):
        entries = [
            {"ts": 1710000000, "success": False, "reason": "boot_timeout", "total_observed_s": 12.0},
            {"ts": 1710000300, "success": False, "reason": "heartbeat_stale", "total_observed_s": 10.0},
            {"ts": 1710000600, "success": False, "reason": "boot_timeout", "total_observed_s": 11.0},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = self._write_history(entries, td)
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000700)
        self.assertEqual(payload["flap_level"], "danger")
        self.assertEqual(payload["consecutive_failures"], 3)
        self.assertEqual(payload["recent_restart_count_15m"], 3)
        self.assertIn("instability", str(payload.get("flap_summary") or "").lower())

    def test_one_failure_triggers_warn(self):
        entries = [
            {"ts": 1710000000, "success": True, "total_observed_s": 5.0},
            {"ts": 1710000300, "success": False, "reason": "heartbeat_stale", "total_observed_s": 10.0},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = self._write_history(entries, td)
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000400)
        self.assertEqual(payload["flap_level"], "warn")
        self.assertEqual(payload["consecutive_failures"], 1)

    def test_avg_success_boot_sec_computed(self):
        entries = [
            {"ts": 1710000000, "success": True, "total_observed_s": 4.0},
            {"ts": 1710000300, "success": True, "total_observed_s": 6.0},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = self._write_history(entries, td)
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000400)
        self.assertAlmostEqual(payload["avg_success_boot_sec"], 5.0)

    def test_recent_outcomes_capped_at_six(self):
        entries = [
            {"ts": 1710000000 + i * 60, "success": i % 2 == 0, "total_observed_s": 5.0}
            for i in range(10)
        ]
        with tempfile.TemporaryDirectory() as td:
            p = self._write_history(entries, td)
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710001000)
        self.assertLessEqual(len(payload["recent_outcomes"]), 6)

    def test_last_success_age_computed(self):
        entries = [
            {"ts": 1710000000, "success": True, "total_observed_s": 5.0},
            {"ts": 1710000300, "success": False, "reason": "timeout", "total_observed_s": 10.0},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = self._write_history(entries, td)
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000700)
        self.assertEqual(payload["last_success_age_sec"], 700)

    # -- anti-drift: nova_http must delegate --

    def test_nova_http_delegates_to_service(self):
        """nova_http._runtime_restart_analytics_payload must delegate to RUNTIME_ANALYTICS_SERVICE."""
        import inspect
        import nova_http
        src = inspect.getsource(nova_http._runtime_restart_analytics_payload)
        self.assertIn("RUNTIME_ANALYTICS_SERVICE", src,
                      "nova_http._runtime_restart_analytics_payload must delegate to RUNTIME_ANALYTICS_SERVICE")
        self.assertIn("restart_analytics_payload", src)

    def test_singleton_exists(self):
        self.assertIsInstance(RUNTIME_ANALYTICS_SERVICE, RuntimeAnalyticsService)


if __name__ == "__main__":
    unittest.main()
