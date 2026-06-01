import unittest

from services.nova_fulfillment_routing import evaluate_fulfillment_route_viability


class _Session:
    def __init__(self, conversation_state=None):
        self.conversation_state = conversation_state


class TestNovaFulfillmentRouting(unittest.TestCase):
    def test_not_viable_without_existing_fulfillment_state(self):
        result = evaluate_fulfillment_route_viability(
            "Show me workable options for getting this done",
            _Session(),
            [("user", "Earlier context")],
            get_fulfillment_state_fn=lambda _session: None,
        )

        self.assertFalse(result.get("viable"))
        self.assertEqual(result.get("comparison_strength"), "weak")
        self.assertIn("no existing fulfillment state", result.get("fit_notes") or [])

    def test_viable_when_existing_fulfillment_state_exists(self):
        result = evaluate_fulfillment_route_viability(
            "revise the current options",
            _Session(),
            [],
            get_fulfillment_state_fn=lambda _session: {"intent": "existing"},
        )

        self.assertTrue(result.get("viable"))
        self.assertEqual(result.get("comparison_strength"), "clear")

    def test_not_viable_when_pending_action_exists(self):
        result = evaluate_fulfillment_route_viability(
            "Show me workable options for getting this done",
            _Session(),
            [],
            pending_action={"kind": "weather_lookup"},
            get_fulfillment_state_fn=lambda _session: None,
        )

        self.assertFalse(result.get("viable"))
        self.assertEqual(result.get("comparison_strength"), "clear")

    def test_not_viable_when_another_conversation_state_is_active(self):
        result = evaluate_fulfillment_route_viability(
            "revise the current options",
            _Session({"kind": "retrieval"}),
            [],
            get_fulfillment_state_fn=lambda _session: None,
        )

        self.assertFalse(result.get("viable"))
        self.assertEqual(result.get("comparison_strength"), "clear")



if __name__ == "__main__":
    unittest.main()
