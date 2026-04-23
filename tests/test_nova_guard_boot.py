import unittest
from unittest import mock

import nova_guard


class TestNovaGuardBoot(unittest.TestCase):
    def _attempt(self, *, started_at=100.0, boot_timeout=20.0):
        return nova_guard.GuardAttempt(
            pid=111,
            create_time=11.1,
            started_at=started_at,
            boot_timeout_seconds=boot_timeout,
            state=nova_guard.STATE_BOOTING,
        )

    def test_observe_boot_progress_attempts_adoption_before_alive_check(self):
        attempt = self._attempt()
        order = []

        def _read_state():
            order.append("read_state")
            return {"pid": 222, "create_time": 22.2}

        def _adopt(_attempt, _state):
            order.append("adopt")
            return True

        def _alive(_attempt):
            order.append("alive")
            return True

        def _state_matches(_attempt, _state):
            order.append("state_matches")
            return True

        with mock.patch("nova_guard.read_core_state", side_effect=_read_state), \
            mock.patch("nova_guard._adopt_runtime_identity_from_state", side_effect=_adopt), \
            mock.patch("nova_guard._attempt_is_alive", side_effect=_alive), \
            mock.patch("nova_guard._runtime_state_matches_attempt", side_effect=_state_matches), \
            mock.patch("nova_guard.is_heartbeat_fresh", return_value=True), \
            mock.patch("nova_guard.log"):
            ok = nova_guard._observe_boot_progress(attempt)

        self.assertTrue(ok)
        self.assertEqual(order[:3], ["read_state", "adopt", "alive"])

    def test_boot_failed_does_not_fail_early_within_boot_window_when_launcher_is_missing(self):
        attempt = self._attempt(started_at=100.0, boot_timeout=20.0)

        with mock.patch("nova_guard.time.time", return_value=110.0), \
            mock.patch("nova_guard.read_core_state", return_value=None), \
            mock.patch("nova_guard._adopt_runtime_identity_from_state", return_value=False), \
            mock.patch("nova_guard._attempt_is_alive", return_value=False), \
            mock.patch("nova_guard._runtime_state_matches_attempt", return_value=False), \
            mock.patch("nova_guard.is_heartbeat_fresh", return_value=False):
            failed, reason = nova_guard._boot_failed(attempt)

        self.assertFalse(failed)
        self.assertEqual(reason, "")

    def test_boot_failed_returns_boot_pid_missing_after_timeout_when_no_runtime_signals(self):
        attempt = self._attempt(started_at=100.0, boot_timeout=20.0)

        with mock.patch("nova_guard.time.time", return_value=130.0), \
            mock.patch("nova_guard.read_core_state", return_value=None), \
            mock.patch("nova_guard._adopt_runtime_identity_from_state", return_value=False), \
            mock.patch("nova_guard._attempt_is_alive", return_value=False), \
            mock.patch("nova_guard._runtime_state_matches_attempt", return_value=False), \
            mock.patch("nova_guard.is_heartbeat_fresh", return_value=False):
            failed, reason = nova_guard._boot_failed(attempt)

        self.assertTrue(failed)
        self.assertEqual(reason, "boot_pid_missing")

    def test_boot_failed_stays_healthy_when_child_is_adopted_and_signals_are_good(self):
        attempt = self._attempt(started_at=100.0, boot_timeout=20.0)

        with mock.patch("nova_guard.time.time", return_value=105.0), \
            mock.patch("nova_guard.read_core_state", return_value={"pid": 222, "create_time": 22.2}), \
            mock.patch("nova_guard._adopt_runtime_identity_from_state", return_value=True), \
            mock.patch("nova_guard._attempt_is_alive", return_value=True), \
            mock.patch("nova_guard._runtime_state_matches_attempt", return_value=True), \
            mock.patch("nova_guard.is_heartbeat_fresh", return_value=True):
            failed, reason = nova_guard._boot_failed(attempt)

        self.assertFalse(failed)
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
