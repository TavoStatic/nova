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

    def test_maintenance_child_timed_out_after_max_age(self):
        """Hung --once must not block the 5-minute timer forever."""
        self.assertFalse(
            nova_guard._maintenance_child_timed_out(
                launched_at=100.0,
                now=100.0 + nova_guard.MAINTENANCE_MAX_AGE_SECONDS,
                max_age_sec=nova_guard.MAINTENANCE_MAX_AGE_SECONDS,
            )
        )
        self.assertTrue(
            nova_guard._maintenance_child_timed_out(
                launched_at=100.0,
                now=100.0 + nova_guard.MAINTENANCE_MAX_AGE_SECONDS + 1.0,
                max_age_sec=nova_guard.MAINTENANCE_MAX_AGE_SECONDS,
            )
        )
        self.assertFalse(
            nova_guard._maintenance_child_timed_out(
                launched_at=0.0,
                now=10_000.0,
                max_age_sec=nova_guard.MAINTENANCE_MAX_AGE_SECONDS,
            )
        )

    def test_maintenance_tick_terminates_hung_child_and_relaunches(self):
        attempt = nova_guard.GuardAttempt(state=nova_guard.STATE_RUNNING, heartbeat_seen_at=1.0)
        hung = mock.Mock()
        hung.poll.return_value = None
        hung.pid = 99999
        new_proc = mock.Mock()
        new_proc.pid = 100001

        with mock.patch.object(nova_guard, "_MAINTENANCE_PROC", hung), \
            mock.patch.object(nova_guard, "_MAINTENANCE_LAUNCHED_AT", 100.0), \
            mock.patch.object(nova_guard, "_LAST_MAINTENANCE_LAUNCH", 100.0), \
            mock.patch("nova_guard.time.time", return_value=100.0 + nova_guard.MAINTENANCE_MAX_AGE_SECONDS + 5.0), \
            mock.patch("nova_guard._is_maintenance_already_running", return_value=False), \
            mock.patch("nova_guard.subprocess.Popen", return_value=new_proc) as popen_mock, \
            mock.patch("nova_guard.open", mock.mock_open()), \
            mock.patch("nova_guard.log"):
            nova_guard._maintenance_tick(attempt)
            # Patch is still active — module global was reassigned to the new child.
            self.assertIs(nova_guard._MAINTENANCE_PROC, new_proc)

        hung.terminate.assert_called()
        popen_mock.assert_called_once()

    def test_spawn_core_adopts_existing_live_core(self):
        with mock.patch.object(nova_guard, "_live_core_pid", return_value=4242), \
            mock.patch.object(nova_guard, "log", lambda _msg: None), \
            mock.patch.object(nova_guard.subprocess, "Popen") as popen_mock:
            pid = nova_guard.spawn_core("initial_start")

        self.assertEqual(pid, 4242)
        popen_mock.assert_not_called()

    def test_start_new_attempt_does_not_clear_when_core_already_live(self):
        attempt = nova_guard.GuardAttempt()
        with mock.patch.object(nova_guard, "_live_core_pid", return_value=5151), \
            mock.patch.object(nova_guard, "_clear_core_runtime_artifacts") as clear_mock, \
            mock.patch.object(nova_guard, "spawn_core") as spawn_mock, \
            mock.patch.object(nova_guard, "_process_create_time", return_value=51.0), \
            mock.patch.object(nova_guard, "_derive_boot_timeout_seconds", return_value=20.0), \
            mock.patch.object(nova_guard, "time") as time_mock, \
            mock.patch.object(nova_guard, "log", lambda _msg: None):
            time_mock.time.return_value = 100.0
            nova_guard.start_new_attempt(attempt, "initial_start")

        self.assertEqual(attempt.pid, 5151)
        clear_mock.assert_not_called()
        spawn_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
