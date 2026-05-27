from __future__ import annotations

import unittest

import nova_core
from conversation_manager import ConversationSession
from subconscious_route_probe import analyze_route_pressure


def _probe(user_text: str, session: ConversationSession, turns=None, pending_action=None) -> dict:
    return nova_core._probe_turn_routes(
        user_text,
        session,
        list(turns or []),
        pending_action=pending_action,
    )


class TestSubconsciousFallbackSeams(unittest.TestCase):
    def test_route_probe_does_not_turn_sample_text_into_supervisor_ownership(self):
        samples = [
            "go ahead",
            "yes please use the saved location",
            "web continue",
            "please patch apply updates.zip",
            "patch rollback",
            "Show me workable options without collapsing too early.",
        ]

        for text in samples:
            with self.subTest(text=text):
                session = ConversationSession()
                result = _probe(text, session)
                routes = result.get("routes") or {}
                self.assertFalse((routes.get("supervisor_owned") or {}).get("viable"))

    def test_weak_route_pressure_records_unclear_fit_without_overclaiming_owner(self):
        session = ConversationSession()
        probe_result = _probe("what now", session)

        record = analyze_route_pressure(probe_result, chosen_route="generic_fallback")

        self.assertIn("route_unclear", record.signals)
        self.assertIn("route_fit_weak", record.signals)
        self.assertNotIn("fallback_overuse", record.signals)

    def test_fulfillment_viability_comes_from_existing_state_not_request_wording(self):
        session = ConversationSession()

        without_state = _probe("Show me workable options without collapsing too early.", session)
        self.assertFalse((without_state.get("routes", {}).get("fulfillment_applicable") or {}).get("viable"))

        session.fulfillment_state = {"intent": "existing"}
        with_state = _probe("continue the current comparison", session)
        self.assertTrue((with_state.get("routes", {}).get("fulfillment_applicable") or {}).get("viable"))
        self.assertEqual(with_state.get("comparison_strength"), "clear")


if __name__ == "__main__":
    unittest.main()
