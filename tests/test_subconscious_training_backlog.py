import unittest

import nova_core
from conversation_manager import ConversationSession
from subconscious_training_backlog import build_training_backlog


class TestSubconsciousTrainingBacklog(unittest.TestCase):
    def test_repeated_weak_cracks_generate_candidate_tests(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])

        nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")
        nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")

        snapshot = nova_core._get_subconscious_snapshot(session)
        backlog = build_training_backlog(snapshot)
        signals = [item.signal for item in backlog.candidate_tests]

        self.assertTrue(backlog.replan_requested)
        self.assertIn("route_unclear", signals)
        self.assertIn("route_fit_weak", signals)
        self.assertEqual(backlog.record_window, {"count": 2, "cap": 12})

    def test_clear_fulfillment_miss_generates_high_priority_candidates(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes(
            "Show me workable options without collapsing too early.",
            session,
            [("user", "Show me workable options without collapsing too early.")],
        )

        nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")

        snapshot = nova_core._get_subconscious_snapshot(session)
        backlog = build_training_backlog(snapshot)
        by_signal = {item.signal: item for item in backlog.candidate_tests}

        self.assertTrue(backlog.replan_requested)
        self.assertEqual(by_signal["fulfillment_missed"].priority, "high")
        self.assertEqual(by_signal["fallback_overuse"].priority, "high")
        self.assertIn("still active", by_signal["fulfillment_missed"].rationale.lower())

    def test_clean_supervisor_snapshot_stays_empty(self):
        session = ConversationSession()
        session.set_pending_action(
            {
                "kind": "weather_lookup",
                "status": "awaiting_location",
                "saved_location_available": True,
                "preferred_tool": "weather_current_location",
            }
        )
        probe = nova_core._probe_turn_routes("go ahead", session, [], pending_action=session.pending_action)

        nova_core._update_subconscious_state(session, probe, chosen_route="supervisor_owned")

        snapshot = nova_core._get_subconscious_snapshot(session)
        backlog = build_training_backlog(snapshot)

        self.assertFalse(backlog.replan_requested)
        self.assertEqual(backlog.candidate_tests, [])
        self.assertEqual(backlog.deferred_signals, [])

    def test_backlog_builder_is_read_only_for_snapshot(self):
        session = ConversationSession()
        probe = nova_core._probe_turn_routes("how are you doing today ?", session, [])
        nova_core._update_subconscious_state(session, probe, chosen_route="generic_fallback")
        snapshot = nova_core._get_subconscious_snapshot(session)
        baseline = {
            "replan_requested": snapshot.get("replan_requested"),
            "active_recent_signals": list(snapshot.get("active_recent_signals") or []),
            "crack_counts": dict(snapshot.get("crack_counts") or {}),
            "recent_pressure_records": [dict(item) for item in list(snapshot.get("recent_pressure_records") or [])],
            "record_window": dict(snapshot.get("record_window") or {}),
        }

        backlog = build_training_backlog(snapshot)

        self.assertFalse(backlog.replan_requested)
        self.assertEqual(snapshot, baseline)


if __name__ == "__main__":
    unittest.main()