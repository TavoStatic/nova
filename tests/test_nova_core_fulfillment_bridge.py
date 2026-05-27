import unittest

import nova_core
from conversation_manager import ConversationSession
from services.subconscious_runtime import SUBCONSCIOUS_SERVICE


class TestNovaCoreFulfillmentBridge(unittest.TestCase):
    def test_probe_turn_routes_reports_weak_route_without_existing_fulfillment_state(self):
        session = ConversationSession()

        probe = nova_core._probe_turn_routes(
            "Show me workable options without collapsing too early.",
            session,
            [("user", "Show me workable options without collapsing too early.")],
        )

        self.assertEqual(probe.get("comparison_strength"), "weak")
        routes = probe.get("routes") or {}
        self.assertFalse((routes.get("fulfillment_applicable") or {}).get("viable"))
        self.assertTrue((routes.get("generic_fallback") or {}).get("viable"))

    def test_probe_turn_routes_reports_fulfillment_viable_from_existing_state(self):
        session = ConversationSession()
        session.fulfillment_state = {"intent": "existing"}

        probe = nova_core._probe_turn_routes("revise the current options", session, [])

        self.assertEqual(probe.get("comparison_strength"), "clear")
        routes = probe.get("routes") or {}
        self.assertTrue((routes.get("fulfillment_applicable") or {}).get("viable"))
        self.assertIn(
            "existing fulfillment state present",
            (routes.get("fulfillment_applicable") or {}).get("fit_notes") or [],
        )

    def test_snapshot_records_weak_route_pressure_without_immediate_replan(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])

        state = SUBCONSCIOUS_SERVICE.update_state(session, probe, chosen_route="generic_fallback")

        self.assertIsInstance(state, nova_core.SubconsciousState)
        self.assertFalse(state.replan_requested)
        self.assertEqual(state.crack_counts.get("route_unclear"), 1)
        self.assertEqual(state.crack_counts.get("route_fit_weak"), 1)
        snapshot = SUBCONSCIOUS_SERVICE.get_snapshot(session)
        self.assertIn("route_unclear", snapshot.get("active_recent_signals") or [])
        self.assertIn("route_fit_weak", snapshot.get("active_recent_signals") or [])

    def test_snapshot_records_supervisor_owned_pressure_without_route_cracks(self):
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "preferred_tool": "weather_current_location",
            }
        )

        probe = nova_core._probe_turn_routes("go ahead", session, [], pending_action=session.pending_action)
        state = SUBCONSCIOUS_SERVICE.update_state(session, probe, chosen_route="supervisor_owned")

        self.assertFalse(state.replan_requested)
        self.assertEqual(state.crack_counts, {})
        snapshot = SUBCONSCIOUS_SERVICE.get_snapshot(session)
        self.assertEqual(snapshot.get("active_recent_signals"), [])
        self.assertEqual(snapshot.get("recent_pressure_records")[0].get("chosen_route"), "supervisor_owned")

    def test_repeated_weak_route_pressure_requests_replan(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])

        SUBCONSCIOUS_SERVICE.update_state(session, probe, chosen_route="generic_fallback")
        second = SUBCONSCIOUS_SERVICE.update_state(session, probe, chosen_route="generic_fallback")

        self.assertTrue(second.replan_requested)
        self.assertEqual(second.crack_counts.get("route_unclear"), 2)
        self.assertEqual(second.crack_counts.get("route_fit_weak"), 2)
        self.assertEqual(
            SUBCONSCIOUS_SERVICE.get_snapshot(session).get("replan_reasons"),
            [
                {"kind": "weak_signal_threshold", "signal": "route_fit_weak", "window_count": 2, "threshold": 2},
            ],
        )


if __name__ == "__main__":
    unittest.main()
