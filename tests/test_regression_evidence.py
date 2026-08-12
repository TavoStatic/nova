import unittest

from services.regression_evidence import (
    apply_regression_status_payload,
    regression_evidence_stale,
    regression_failure_active,
    regression_failure_is_lock_contention,
)


class TestRegressionEvidence(unittest.TestCase):
    def test_same_day_failed_regression_is_not_stale(self):
        self.assertFalse(
            regression_evidence_stale(
                status_label="FAILED",
                regression_date="2026-07-13",
                today="2026-07-13",
            )
        )
        self.assertTrue(
            regression_failure_active(
                status_label="FAILED",
                stale=False,
            )
        )

    def test_prior_day_failed_regression_is_stale(self):
        self.assertTrue(
            regression_evidence_stale(
                status_label="FAILED",
                regression_date="2026-07-12",
                today="2026-07-13",
            )
        )
        self.assertFalse(
            regression_failure_active(
                status_label="FAILED",
                stale=True,
            )
        )

    def test_apply_regression_status_payload_preserves_failed_tests(self):
        import time

        state: dict = {}
        today = time.strftime("%Y-%m-%d")
        apply_regression_status_payload(
            state,
            {
                "generated_at": f"{today} 00:03:32",
                "date": today,
                "status": "FAILED",
                "lanes": ["behavior"],
                "returncode": 1,
                "detail": "behavior lane",
                "failed_lane": "behavior",
                "failed_tests": ["tests.test_http_session_manager.TestHttpSessionManager.test_control_action_pulse_status_returns_structured_payload"],
                "source": "scripts/run_regression.py",
            },
        )
        self.assertEqual(state.get("last_regression_status"), "FAILED")
        self.assertFalse(state.get("last_regression_stale"))
        self.assertEqual(state.get("last_regression_failed_lane"), "behavior")
        self.assertEqual(len(state.get("last_regression_failed_tests") or []), 1)
        self.assertIn("failed_tests=", str(state.get("last_regression_tail") or ""))

    def test_already_running_failed_is_not_active_regression_failure(self):
        tail = "[FAIL] regression already running (pid=5812, lanes=unit, behavior, integration)"
        self.assertTrue(
            regression_failure_is_lock_contention(
                status_label="FAILED",
                failed_tests=[],
                failed_lane="",
                tail=tail,
            )
        )
        self.assertFalse(
            regression_failure_active(
                status_label="FAILED",
                stale=False,
                failed_tests=[],
                failed_lane="",
                tail=tail,
            )
        )

    def test_lock_contention_is_not_mission_regression_blocker(self):
        from services.nova_mission_owner_verdicts import _regression_blocker

        tail = "[FAIL] regression already running (pid=5812, lanes=unit)"
        blocker = _regression_blocker(
            status_label="FAILED",
            stale=False,
            evidence={
                "last_regression_failed_tests": [],
                "last_regression_failed_lane": "",
                "last_regression_tail": tail,
            },
        )
        self.assertIsNone(blocker)

    def test_lock_contention_keeps_regression_evidence_current(self):
        from services.nova_mission_owner_verdicts import _regression_evidence_current

        tail = "[FAIL] regression already running (pid=5812, lanes=unit, behavior)"
        self.assertTrue(
            _regression_evidence_current(
                status_label="FAILED",
                stale=False,
                evidence={
                    "last_regression_failed_tests": [],
                    "last_regression_failed_lane": "",
                    "last_regression_tail": tail,
                },
            )
        )


if __name__ == "__main__":
    unittest.main()
