from __future__ import annotations

import os

import json
import shutil
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from services.runtime_analytics import RuntimeAnalyticsService, RUNTIME_ANALYTICS_SERVICE


WORK_TMP_ROOT = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            missing = case_dir / "guard_boot_history.json"
            payload = self.svc.restart_analytics_payload(boot_history_path=missing)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["flap_level"], "info")

    def test_corrupt_file_returns_danger_payload(self):
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = case_dir / "guard_boot_history.json"
            p.write_text("NOT JSON{{{", encoding="utf-8")
            payload = self.svc.restart_analytics_payload(boot_history_path=p)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["flap_level"], "danger")

    def test_empty_list_returns_default_payload(self):
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history([], str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 0)

    # -- outcome classification --

    def test_all_successes_returns_good_level(self):
        # Space entries 2h apart so _count_since(3600) stays below 3
        entries = [
            {"ts": 1700000000 + i * 7200, "success": True, "total_observed_s": 5.0}
            for i in range(4)
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(
                boot_history_path=p, now=1700030000
            )
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
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
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000700)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
        self.assertEqual(payload["flap_level"], "danger")
        self.assertEqual(payload["consecutive_failures"], 3)
        self.assertEqual(payload["recent_restart_count_15m"], 3)
        self.assertIn("instability", str(payload.get("flap_summary") or "").lower())

    def test_one_failure_triggers_warn(self):
        entries = [
            {"ts": 1710000000, "success": True, "total_observed_s": 5.0},
            {"ts": 1710000300, "success": False, "reason": "heartbeat_stale", "total_observed_s": 10.0},
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000400)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
        self.assertEqual(payload["flap_level"], "warn")
        self.assertEqual(payload["consecutive_failures"], 1)

    def test_planned_operator_restarts_do_not_become_pressure(self):
        entries = [
            {
                "ts": 1710000000 + i * 60,
                "success": True,
                "reason": "running",
                "start_reason": "initial_start",
                "restart_origin": "operator",
                "restart_action": "guard_restart",
                "planned_restart": True,
                "provenance_complete": True,
                "total_observed_s": 5.0,
            }
            for i in range(4)
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000400)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(payload["recent_restart_count_1h"], 4)
        self.assertEqual(payload["pressure_restart_count_1h"], 0)
        self.assertEqual(payload["planned_restart_count_1h"], 4)
        self.assertFalse(payload["restart_pressure_active"])
        self.assertEqual(payload["flap_level"], "good")

    def test_unattributed_successful_boots_report_provenance_gap_not_pressure(self):
        entries = [
            {"ts": 1710000000 + i * 60, "success": True, "reason": "running", "total_observed_s": 5.0}
            for i in range(3)
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000300)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(payload["pressure_restart_count_1h"], 0)
        self.assertEqual(payload["restart_origin_gap_count_1h"], 3)
        self.assertEqual(payload["restart_origin_active_gap_count_1h"], 3)
        self.assertEqual(payload["restart_provenance_status"], "incomplete")
        self.assertEqual(payload["flap_level"], "good")

    def test_older_unattributed_boots_become_legacy_gap_after_current_provenance(self):
        entries = [
            {"ts": 1710000000, "success": True, "reason": "running", "total_observed_s": 5.0},
            {"ts": 1710000060, "success": True, "reason": "running", "total_observed_s": 5.0},
            {
                "ts": 1710000120,
                "success": True,
                "reason": "running",
                "start_reason": "initial_start",
                "restart_origin": "operator",
                "restart_action": "guard_restart_after_stop",
                "planned_restart": True,
                "provenance_complete": True,
                "total_observed_s": 5.0,
            },
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000300)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(payload["restart_origin_gap_count_1h"], 2)
        self.assertEqual(payload["restart_origin_active_gap_count_1h"], 0)
        self.assertEqual(payload["restart_origin_legacy_gap_count_1h"], 2)
        self.assertEqual(payload["restart_provenance_status"], "legacy_incomplete")
        self.assertFalse(payload["restart_pressure_active"])

    def test_supervised_recovery_restarts_are_pressure(self):
        entries = [
            {
                "ts": 1710000000 + i * 60,
                "success": True,
                "reason": "running",
                "start_reason": "restart",
                "restart_origin": "guard_supervisor",
                "restart_action": "supervised_restart",
                "planned_restart": False,
                "provenance_complete": True,
                "total_observed_s": 5.0,
            }
            for i in range(3)
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000300)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(payload["pressure_restart_count_1h"], 3)
        self.assertTrue(payload["restart_pressure_active"])
        self.assertEqual(payload["flap_level"], "warn")

    def test_repeated_heartbeat_stale_restarts_warn_even_below_generic_pressure_threshold(self):
        base = int(time.mktime(time.strptime("2024-03-09 16:00:00", "%Y-%m-%d %H:%M:%S")))
        entries = [
            {
                "ts": base + 64,
                "success": True,
                "reason": "running",
                "start_reason": "restart",
                "restart_origin": "guard_supervisor",
                "restart_action": "supervised_restart",
                "planned_restart": False,
                "provenance_complete": True,
                "total_observed_s": 4.0,
            },
            {
                "ts": base + 364,
                "success": True,
                "reason": "running",
                "start_reason": "restart",
                "restart_origin": "guard_supervisor",
                "restart_action": "supervised_restart",
                "planned_restart": False,
                "provenance_complete": True,
                "total_observed_s": 4.0,
            },
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            guard_log = case_dir / "guard.log"
            guard_log.write_text(
                "\n".join([
                    "2024-03-09 16:00:59 | [GUARD] Core attempt failed: heartbeat_stale",
                    "2024-03-09 16:05:59 | [GUARD] Core attempt failed: heartbeat_stale",
                ]),
                encoding="utf-8",
            )
            payload = self.svc.restart_analytics_payload(
                boot_history_path=p,
                guard_log_path=guard_log,
                now=base + 400,
            )
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(payload["pressure_restart_count_1h"], 2)
        self.assertEqual(payload["heartbeat_stale_restart_count_1h"], 2)
        self.assertTrue(payload["restart_pressure_active"])
        self.assertEqual(payload["flap_level"], "warn")
        self.assertEqual(payload["latest_restart_cause_reason"], "heartbeat_stale")
        self.assertEqual(payload["recent_outcomes"][0]["restart_cause_reason"], "heartbeat_stale")

    def test_avg_success_boot_sec_computed(self):
        entries = [
            {"ts": 1710000000, "success": True, "total_observed_s": 4.0},
            {"ts": 1710000300, "success": True, "total_observed_s": 6.0},
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000400)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
        self.assertAlmostEqual(payload["avg_success_boot_sec"], 5.0)

    def test_recent_outcomes_capped_at_six(self):
        entries = [
            {"ts": 1710000000 + i * 60, "success": i % 2 == 0, "total_observed_s": 5.0}
            for i in range(10)
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710001000)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
        self.assertLessEqual(len(payload["recent_outcomes"]), 6)

    def test_last_success_age_computed(self):
        entries = [
            {"ts": 1710000000, "success": True, "total_observed_s": 5.0},
            {"ts": 1710000300, "success": False, "reason": "timeout", "total_observed_s": 10.0},
        ]
        case_dir = _workspace_case_dir("runtime_analytics")
        try:
            p = self._write_history(entries, str(case_dir))
            payload = self.svc.restart_analytics_payload(boot_history_path=p, now=1710000700)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)
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
