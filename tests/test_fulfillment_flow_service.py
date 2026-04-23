import unittest
from types import SimpleNamespace

from services.fulfillment_flow import FulfillmentFlowService


class _Session:
    pass


class TestFulfillmentFlowService(unittest.TestCase):
    def test_should_attempt_when_fulfillment_route_is_clear(self):
        service = FulfillmentFlowService(
            probe_turn_routes_fn=lambda *_args, **_kwargs: {
                "comparison_strength": "clear",
                "routes": {
                    "supervisor_owned": {"viable": False},
                    "fulfillment_applicable": {"viable": True},
                },
            },
            update_subconscious_state_fn=lambda *_args, **_kwargs: None,
            session_state_service=SimpleNamespace(
                get_fulfillment_state=lambda _session: None,
                set_fulfillment_state=lambda *_args, **_kwargs: None,
            ),
        )

        self.assertTrue(service.should_attempt_fulfillment_flow("compare options", _Session(), []))

    def test_should_not_attempt_when_supervisor_route_wins(self):
        service = FulfillmentFlowService(
            probe_turn_routes_fn=lambda *_args, **_kwargs: {
                "comparison_strength": "clear",
                "routes": {
                    "supervisor_owned": {"viable": True},
                    "fulfillment_applicable": {"viable": True},
                },
            },
            update_subconscious_state_fn=lambda *_args, **_kwargs: None,
            session_state_service=SimpleNamespace(
                get_fulfillment_state=lambda _session: None,
                set_fulfillment_state=lambda *_args, **_kwargs: None,
            ),
        )

        self.assertFalse(service.should_attempt_fulfillment_flow("compare options", _Session(), []))

    def test_render_single_result_reply(self):
        choice_set = SimpleNamespace(
            mode=SimpleNamespace(value="single_result"),
            selected_model_id="direct",
            options=[
                SimpleNamespace(
                    model_id="direct",
                    label="Direct path",
                    why_distinct=["fastest route"],
                    tradeoffs=["requires more commitment"],
                )
            ],
        )

        reply = FulfillmentFlowService.render_fulfillment_reply(choice_set)

        self.assertIn("one current fulfillment result", reply)
        self.assertIn("Direct path", reply)
        self.assertIn("fastest route", reply)
        self.assertIn("requires more commitment", reply)

    def test_render_multi_choice_reply(self):
        choice_set = SimpleNamespace(
            mode=SimpleNamespace(value="multi_choice"),
            plurality_reason="different tradeoffs remain active",
            options=[
                SimpleNamespace(label="Guided path", why_distinct=["lower friction"], tradeoffs=["slower upfront"]),
                SimpleNamespace(label="Direct path", why_distinct=["faster timing"], tradeoffs=["higher commitment"]),
            ],
        )

        reply = FulfillmentFlowService.render_fulfillment_reply(choice_set)

        self.assertIn("multiple meaningful fulfillment paths", reply)
        self.assertIn("Guided path: lower friction", reply)
        self.assertIn("Direct path: faster timing", reply)
        self.assertIn("different tradeoffs remain active", reply)

    def test_maybe_run_marks_generic_fallback_when_not_viable(self):
        recorded = []
        service = FulfillmentFlowService(
            probe_turn_routes_fn=lambda *_args, **_kwargs: {
                "comparison_strength": "weak",
                "routes": {
                    "supervisor_owned": {"viable": False},
                    "fulfillment_applicable": {"viable": False},
                },
            },
            update_subconscious_state_fn=lambda session, probe, chosen_route=None: recorded.append((session, probe, chosen_route)),
            session_state_service=SimpleNamespace(
                get_fulfillment_state=lambda _session: None,
                set_fulfillment_state=lambda *_args, **_kwargs: None,
            ),
        )
        session = _Session()

        result = service.maybe_run_fulfillment_flow("hello", session, [])

        self.assertIsNone(result)
        self.assertEqual(recorded[0][2], "generic_fallback")


if __name__ == "__main__":
    unittest.main()