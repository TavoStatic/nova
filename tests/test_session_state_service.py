"""
Tests for SessionStateService.
"""
import unittest
from services.session_state import SessionStateService, SubconsciousState


class MockSession:
    """Mock session object for testing."""
    pass


class TestSessionStateService(unittest.TestCase):
    """Test session state management."""

    def test_fulfillment_state_get_set(self):
        """Test get/set fulfillment state."""
        session = MockSession()
        
        # Initially None
        self.assertIsNone(SessionStateService.get_fulfillment_state(session))
        
        # Set and retrieve
        state = {"status": "active", "items": ["a", "b"]}
        SessionStateService.set_fulfillment_state(session, state)
        self.assertEqual(SessionStateService.get_fulfillment_state(session), state)
        
        # Set None
        SessionStateService.set_fulfillment_state(session, None)
        self.assertIsNone(SessionStateService.get_fulfillment_state(session))

    def test_fulfillment_state_ignores_invalid(self):
        """Test that non-dict values are ignored."""
        session = MockSession()
        SessionStateService.set_fulfillment_state(session, "not a dict")
        self.assertIsNone(SessionStateService.get_fulfillment_state(session))

    def test_subconscious_state_get_set(self):
        """Test get/set subconscious state."""
        session = MockSession()
        
        # Initially None
        self.assertIsNone(SessionStateService.get_subconscious_state(session))
        
        # Create and set
        state = SubconsciousState(replan_requested=True, crack_counts={"test": 2})
        SessionStateService.set_subconscious_state(session, state)
        retrieved = SessionStateService.get_subconscious_state(session)
        self.assertIsNotNone(retrieved)
        self.assertTrue(retrieved.replan_requested)
        self.assertEqual(retrieved.crack_counts.get("test"), 2)

    def test_subconscious_snapshot_empty(self):
        """Test snapshot for session with no state."""
        session = MockSession()
        snapshot = SessionStateService.get_subconscious_snapshot(
            session,
            {"signal_handling_rules": {}, "crack_accumulation_rules": {}},
            10
        )
        self.assertFalse(snapshot["replan_requested"])
        self.assertEqual(snapshot["replan_reasons"], [])
        self.assertEqual(snapshot["crack_counts"], {})
        self.assertEqual(snapshot["weak_signal_window_counts"], {})
        self.assertEqual(len(snapshot["recent_pressure_records"]), 0)

    def test_subconscious_snapshot_with_state(self):
        """Test snapshot captures state correctly."""
        session = MockSession()
        state = SubconsciousState(
            replan_requested=True,
            crack_counts={"weak_signal": 2, "other": 1}
        )
        SessionStateService.set_subconscious_state(session, state)
        
        snapshot = SessionStateService.get_subconscious_snapshot(
            session,
            {"signal_handling_rules": {}, "crack_accumulation_rules": {}},
            10
        )
        self.assertTrue(snapshot["replan_requested"])
        self.assertEqual(snapshot["replan_reasons"], [])
        self.assertEqual(snapshot["crack_counts"]["weak_signal"], 2)

    def test_update_subconscious_state_uses_per_signal_window_thresholds(self):
        session = MockSession()
        charter = {
            "signal_handling_rules": {
                "replan_immediate_signals": [],
                "weak_crack_signals": ["route_unclear", "route_fit_weak"],
            },
            "crack_accumulation_rules": {
                "weak_crack_repeat_threshold": 9,
                "weak_crack_repeat_thresholds": {
                    "route_unclear": 3,
                    "route_fit_weak": 2,
                },
            },
        }
        probe_result = {
            "user_text": "hello",
            "comparison_strength": "weak",
            "routes": {
                "supervisor_owned": {"viable": False, "fit_notes": []},
                "fulfillment_applicable": {"viable": False, "fit_notes": []},
                "generic_fallback": {"viable": True, "fit_notes": []},
            },
        }

        first = SessionStateService.update_subconscious_state(session, probe_result, charter, 10, chosen_route="generic_fallback")

        self.assertIsNotNone(first)
        self.assertFalse(first.replan_requested)
        second = SessionStateService.update_subconscious_state(session, probe_result, charter, 10, chosen_route="generic_fallback")
        self.assertIsNotNone(second)
        self.assertTrue(second.replan_requested)
        self.assertEqual(second.weak_signal_window_counts.get("route_unclear"), 2)
        self.assertEqual(second.weak_signal_window_counts.get("route_fit_weak"), 2)
        self.assertEqual(second.replan_reasons, [{"kind": "weak_signal_threshold", "signal": "route_fit_weak", "window_count": 2, "threshold": 2}])
        third = SessionStateService.update_subconscious_state(session, probe_result, charter, 10, chosen_route="generic_fallback")
        self.assertIsNotNone(third)
        self.assertTrue(third.replan_requested)
        self.assertEqual(third.crack_counts.get("route_unclear"), 3)
        self.assertEqual(third.crack_counts.get("route_fit_weak"), 3)
        self.assertEqual(third.weak_signal_window_counts.get("route_unclear"), 3)
        self.assertEqual(third.weak_signal_window_counts.get("route_fit_weak"), 3)
        self.assertEqual(
            third.replan_reasons,
            [
                {"kind": "weak_signal_threshold", "signal": "route_fit_weak", "window_count": 3, "threshold": 2},
                {"kind": "weak_signal_threshold", "signal": "route_unclear", "window_count": 3, "threshold": 3},
            ],
        )

    def test_update_subconscious_state_windowed_counts_decay_replan_pressure(self):
        session = MockSession()
        charter = {
            "signal_handling_rules": {
                "replan_immediate_signals": [],
                "weak_crack_signals": ["route_unclear", "route_fit_weak"],
            },
            "crack_accumulation_rules": {
                "weak_crack_repeat_threshold": 2,
                "weak_crack_repeat_thresholds": {
                    "route_unclear": 2,
                    "route_fit_weak": 2,
                },
            },
        }
        weak_probe = {
            "user_text": "hello",
            "comparison_strength": "weak",
            "routes": {
                "supervisor_owned": {"viable": False, "fit_notes": []},
                "fulfillment_applicable": {"viable": False, "fit_notes": []},
                "generic_fallback": {"viable": True, "fit_notes": []},
            },
        }
        quiet_probe = {
            "user_text": "go ahead",
            "comparison_strength": "clear",
            "routes": {
                "supervisor_owned": {"viable": True, "fit_notes": []},
                "fulfillment_applicable": {"viable": False, "fit_notes": []},
                "generic_fallback": {"viable": True, "fit_notes": []},
            },
        }

        SessionStateService.update_subconscious_state(session, weak_probe, charter, 3, chosen_route="generic_fallback")
        second = SessionStateService.update_subconscious_state(session, weak_probe, charter, 3, chosen_route="generic_fallback")
        self.assertIsNotNone(second)
        self.assertTrue(second.replan_requested)
        self.assertEqual(second.weak_signal_window_counts.get("route_unclear"), 2)

        third = SessionStateService.update_subconscious_state(session, quiet_probe, charter, 3, chosen_route="supervisor_owned")
        self.assertIsNotNone(third)
        self.assertTrue(third.replan_requested)

        fourth = SessionStateService.update_subconscious_state(session, quiet_probe, charter, 3, chosen_route="supervisor_owned")
        self.assertIsNotNone(fourth)
        self.assertFalse(fourth.replan_requested)
        self.assertEqual(fourth.weak_signal_window_counts.get("route_unclear"), 1)
        self.assertEqual(fourth.weak_signal_window_counts.get("route_fit_weak"), 1)
        self.assertEqual(fourth.replan_reasons, [])


if __name__ == "__main__":
    unittest.main()
