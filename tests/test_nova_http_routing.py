import unittest
import inspect

from services.nova_http_routing import execute_http_routing_sequence


class _FakeSession:
    def __init__(self):
        self.pending_action = None
        self.pending_correction_target = ""
        self.conversation_state = {"kind": "idle"}
        self.prefer_web_for_data_queries = False
        self.continuation_used_last_turn = False

    def apply_state_update(self, payload, fallback_state=None):
        self.conversation_state = payload if isinstance(payload, dict) else fallback_state

    def set_pending_action(self, payload):
        self.pending_action = payload

    def set_prefer_web_for_data_queries(self, enabled):
        self.prefer_web_for_data_queries = bool(enabled)

    def mark_continuation_used(self):
        self.continuation_used_last_turn = True

    def set_retrieval_state(self, payload):
        self.conversation_state = payload


class _FakeFulfillmentService:
    def __init__(self, result=None):
        self.calls = []
        self.result = result if isinstance(result, dict) else {}

    def maybe_run_fulfillment_flow(self, routed_text, session, turns, pending_action=None):
        self.calls.append((routed_text, pending_action))
        return dict(self.result)


def _call_route(**overrides):
    session = overrides.pop("session", _FakeSession())
    fulfillment = overrides.pop("fulfillment", _FakeFulfillmentService())
    ledger = overrides.pop("ledger", {})
    del fulfillment
    return execute_http_routing_sequence(
        text=overrides.pop("text", "hello"),
        routed_text=overrides.pop("routed_text", "hello"),
        turns=overrides.pop("turns", [("user", "hello")]),
        turn_acts=overrides.pop("turn_acts", []),
        intent_rule=overrides.pop("intent_rule", {}),
        session=session,
        conversation_state=overrides.pop("conversation_state", session.conversation_state),
        ledger=ledger,
        should_clarify_unlabeled_numeric_turn=overrides.pop("should_clarify_unlabeled_numeric_turn", lambda *_args, **_kwargs: False),
        unlabeled_numeric_turn_reply=overrides.pop("unlabeled_numeric_turn_reply", lambda text: f"clarify:{text}"),
        build_routing_decision=overrides.pop("build_routing_decision", lambda text, **kwargs: {"text": text, **kwargs}),
        handle_supervisor_intent=overrides.pop("handle_supervisor_intent", lambda *_args, **_kwargs: (False, "", None, {})),
        supervisor_has_route=overrides.pop("supervisor_has_route", lambda rule: bool(rule.get("intent") or rule.get("action")) if isinstance(rule, dict) else False),
        should_warn_supervisor_bypass=overrides.pop("should_warn_supervisor_bypass", lambda _text: False),
        emit_supervisor_intent_trace=overrides.pop("emit_supervisor_intent_trace", lambda *args, **kwargs: None),
        evaluate_supervisor_rules=overrides.pop("evaluate_supervisor_rules", lambda *_args, **_kwargs: {}),
        execute_registered_supervisor_rule=overrides.pop("execute_registered_supervisor_rule", lambda *_args, **_kwargs: (False, "", None)),
        make_conversation_state=overrides.pop("make_conversation_state", lambda kind, **data: {"kind": kind, **data}),
        action_ledger_add_step=overrides.pop("action_ledger_add_step", lambda *args, **kwargs: None),
        ensure_reply=overrides.pop("ensure_reply", lambda text: text),
    )


class TestNovaHttpRoutingSequence(unittest.TestCase):
    def test_routing_sequence_has_no_identity_only_block_surface(self):
        signature = inspect.signature(execute_http_routing_sequence)

        self.assertNotIn("identity_only_block_kind", signature.parameters)
        self.assertNotIn("identity_only_block_reply", signature.parameters)

    def test_routing_sequence_does_not_handle_retired_weather_supervisor_intent(self):
        result = _call_route(
            text="weather current location",
            routed_text="weather current location",
            intent_rule={"intent": "weather_lookup", "weather_mode": "current_location"},
            handle_supervisor_intent=lambda *_args, **_kwargs: (True, "Sunny.", {"kind": "weather"}, {"reply_contract": "weather.current"}),
        )

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("decision_stage"), "supervisor_intent")

    def test_routing_sequence_does_not_own_mixed_turn_clarification(self):
        result = _call_route(
            text="this is context and can you use it",
            routed_text="this is context and can you use it",
            turn_acts=["inform", "ask", "mixed"],
        )

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("decision_stage"), "mixed_turn_clarify")

    def test_routing_sequence_does_not_auto_use_saved_location_weather_before_supervisor_intent(self):
        session = _FakeSession()
        session.conversation_state = {"kind": "location_recall"}

        result = _call_route(
            session=session,
            text="weather now",
            routed_text="weather now",
            conversation_state={"kind": "location_recall"},
            intent_rule={"intent": "weather_lookup"},
            handle_supervisor_intent=lambda *_args, **_kwargs: (True, "What location should I use for the weather lookup?", {"kind": "weather"}, {}),
        )

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("decision_stage"), "supervisor_intent")
        self.assertEqual(session.conversation_state, {"kind": "location_recall"})

    def test_routing_sequence_rejects_removed_grounded_self_report_intent(self):
        result = _call_route(
            text="what is your health percentage at?",
            routed_text="what is your health percentage at?",
            intent_rule={"intent": "grounded_self_report", "report_mode": "health"},
            handle_supervisor_intent=lambda *_args, **_kwargs: (
                True,
                "Live health score is 95/100.",
                None,
                {"reply_contract": "grounded_self_report.health"},
            ),
        )

        self.assertFalse(result.get("handled"))
        self.assertNotEqual(result.get("decision_stage"), "supervisor_intent")

    def test_routing_sequence_does_not_allow_removed_profile_supervisor_rule(self):
        result = _call_route(
            text="who made you?",
            routed_text="who made you?",
            intent_rule={"intent": "assistant_name"},
            should_warn_supervisor_bypass=lambda _text: True,
            evaluate_supervisor_rules=lambda *_args, **_kwargs: {
                "intent": "developer_identity_followup",
                "reply_contract": "identity.creator",
                "reply_outcome": {"kind": "followup"},
                "grounded": True,
            },
        )

        self.assertFalse(result.get("handled"))

    def test_routing_sequence_does_not_use_location_fallback_after_supervisor(self):
        fulfillment = _FakeFulfillmentService()

        result = _call_route(
            fulfillment=fulfillment,
            text="what is the name of the city",
            routed_text="what is the name of the city",
        )

        self.assertFalse(result.get("handled"))
        self.assertEqual(fulfillment.calls, [])


if __name__ == "__main__":
    unittest.main()
