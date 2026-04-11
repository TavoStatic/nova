import unittest

from services.nova_fulfillment_routing import evaluate_fulfillment_route_viability


class _Session:
    def __init__(self, conversation_state=None):
        self.conversation_state = conversation_state


class TestNovaFulfillmentRouting(unittest.TestCase):
    def test_viable_when_model_space_cues_present(self):
        result = evaluate_fulfillment_route_viability(
            "Show me workable options for getting this done",
            _Session(),
            [("user", "Earlier context")],
            get_fulfillment_state_fn=lambda _session: None,
            looks_like_affirmative_followup_fn=lambda _text: False,
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
            looks_like_affirmative_followup_fn=lambda _text: False,
        )

        self.assertFalse(result.get("viable"))
        self.assertEqual(result.get("comparison_strength"), "clear")


if __name__ == "__main__":
    unittest.main()