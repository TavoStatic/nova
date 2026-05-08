import unittest

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
    return execute_http_routing_sequence(
        text=overrides.pop("text", "hello"),
        routed_text=overrides.pop("routed_text", "hello"),
        identity_only_block_kind=overrides.pop("identity_only_block_kind", ""),
        turns=overrides.pop("turns", [("user", "hello")]),
        turn_acts=overrides.pop("turn_acts", []),
        intent_rule=overrides.pop("intent_rule", {}),
        session=session,
        conversation_state=overrides.pop("conversation_state", session.conversation_state),
        ledger=ledger,
        identity_only_block_reply=overrides.pop("identity_only_block_reply", lambda kind: f"blocked:{kind}"),
        should_clarify_unlabeled_numeric_turn=overrides.pop("should_clarify_unlabeled_numeric_turn", lambda *_args, **_kwargs: False),
        unlabeled_numeric_turn_reply=overrides.pop("unlabeled_numeric_turn_reply", lambda text: f"clarify:{text}"),
        mixed_info_request_clarify_reply=overrides.pop("mixed_info_request_clarify_reply", lambda text: f"mixed:{text}"),
        build_routing_decision=overrides.pop("build_routing_decision", lambda text, **kwargs: {"text": text, **kwargs}),
        handle_supervisor_intent=overrides.pop("handle_supervisor_intent", lambda *_args, **_kwargs: (False, "", None, {})),
        supervisor_has_route=overrides.pop("supervisor_has_route", lambda rule: bool(rule.get("intent") or rule.get("action")) if isinstance(rule, dict) else False),
        should_warn_supervisor_bypass=overrides.pop("should_warn_supervisor_bypass", lambda _text: False),
        emit_supervisor_intent_trace=overrides.pop("emit_supervisor_intent_trace", lambda *args, **kwargs: None),
        is_web_research_override_request=overrides.pop("is_web_research_override_request", lambda _text: False),
        learn_self_identity_binding=overrides.pop("learn_self_identity_binding", lambda _text: (False, "")),
        evaluate_supervisor_rules=overrides.pop("evaluate_supervisor_rules", lambda *_args, **_kwargs: {}),
        execute_registered_supervisor_rule=overrides.pop("execute_registered_supervisor_rule", lambda *_args, **_kwargs: (False, "", None)),
        fulfillment_flow_service=fulfillment,
        fast_smalltalk_reply=overrides.pop("fast_smalltalk_reply", lambda _text: None),
        learn_contextual_developer_facts=overrides.pop("learn_contextual_developer_facts", lambda *_args: (False, "")),
        infer_profile_conversation_state=overrides.pop("infer_profile_conversation_state", lambda _text: None),
        make_conversation_state=overrides.pop("make_conversation_state", lambda kind, **data: {"kind": kind, **data}),
        learn_contextual_self_facts=overrides.pop("learn_contextual_self_facts", lambda *_args, **_kwargs: (False, "")),
        extract_memory_teach_text=overrides.pop("extract_memory_teach_text", lambda _text: ""),
        mem_enabled=overrides.pop("mem_enabled", lambda: False),
        store_location_fact_reply=overrides.pop("store_location_fact_reply", lambda *_args, **_kwargs: ""),
        weather_for_saved_location=overrides.pop("weather_for_saved_location", lambda: ""),
        is_saved_location_weather_query=overrides.pop("is_saved_location_weather_query", lambda _text: False),
        get_saved_location_text=overrides.pop("get_saved_location_text", lambda: ""),
        store_declarative_fact_outcome=overrides.pop("store_declarative_fact_outcome", lambda *_args, **_kwargs: None),
        render_reply=overrides.pop("render_reply", lambda outcome: str(outcome)),
        consume_conversation_followup=overrides.pop("consume_conversation_followup", lambda *_args, **_kwargs: (False, "", None)),
        conversation_active_subject=overrides.pop("conversation_active_subject", lambda state: str((state or {}).get("kind") or "")),
        developer_work_guess_turn=overrides.pop("developer_work_guess_turn", lambda _text: ("", None)),
        developer_location_turn=overrides.pop("developer_location_turn", lambda *_args, **_kwargs: ("", None)),
        action_ledger_add_step=overrides.pop("action_ledger_add_step", lambda *args, **kwargs: None),
        ensure_reply=overrides.pop("ensure_reply", lambda text: text),
    )


class TestNovaHttpRoutingSequence(unittest.TestCase):
    def test_routing_sequence_short_circuits_identity_only_block(self):
        result = _call_route(
            text="open the browser",
            routed_text="open the browser",
            identity_only_block_kind="tools",
            handle_supervisor_intent=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not reach supervisor intent")),
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("decision_stage"), "identity_only_mode")
        self.assertEqual((result.get("flow_result") or {}).get("planner_decision"), "policy_block")

    def test_routing_sequence_handles_supervisor_intent(self):
        result = _call_route(
            text="what is the weather",
            routed_text="what is the weather",
            intent_rule={"intent": "weather_lookup"},
            handle_supervisor_intent=lambda *_args, **_kwargs: (True, "Sunny.", {"kind": "weather"}, {"reply_contract": "weather.current"}),
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("decision_stage"), "supervisor_intent")
        self.assertEqual((result.get("flow_result") or {}).get("reply"), "Sunny.")
        self.assertEqual((result.get("conversation_state") or {}).get("kind"), "weather")

    def test_routing_sequence_handles_saved_location_weather_before_supervisor_intent(self):
        session = _FakeSession()
        session.conversation_state = {"kind": "location_recall"}

        result = _call_route(
            session=session,
            text="weather now",
            routed_text="weather now",
            conversation_state={"kind": "location_recall"},
            intent_rule={"intent": "weather_lookup"},
            weather_for_saved_location=lambda: "Brownsville, TX: Sunny.",
            is_saved_location_weather_query=lambda text: text == "weather now",
            handle_supervisor_intent=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("saved-location weather should handle first")),
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("decision_stage"), "saved_location_weather")
        self.assertIn("Brownsville", (result.get("flow_result") or {}).get("reply", ""))

    def test_routing_sequence_returns_web_override_before_later_branches(self):
        fulfillment = _FakeFulfillmentService()
        session = _FakeSession()

        result = _call_route(
            session=session,
            fulfillment=fulfillment,
            text="all you need is the Web",
            routed_text="all you need is the Web",
            is_web_research_override_request=lambda _text: True,
            learn_self_identity_binding=lambda _text: (_ for _ in ()).throw(AssertionError("should not reach identity binding")),
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("decision_stage"), "web_research_override")
        self.assertEqual((result.get("flow_result") or {}).get("intent"), "session_override")
        self.assertTrue(session.prefer_web_for_data_queries)
        self.assertEqual(fulfillment.calls, [])

    def test_routing_sequence_handles_registered_supervisor_rule_and_returns_routing_decision(self):
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
            execute_registered_supervisor_rule=lambda *_args, **_kwargs: (
                True,
                "Gus made me.",
                {"kind": "identity_profile", "subject": "developer"},
            ),
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual(result.get("decision_stage"), "registered_supervisor_rule")
        self.assertEqual((result.get("flow_result") or {}).get("intent"), "developer_identity_followup")
        self.assertEqual((result.get("routing_decision") or {}).get("handle_result", {}).get("intent"), "developer_identity_followup")

    def test_routing_sequence_does_not_use_location_fallback_after_supervisor(self):
        fulfillment = _FakeFulfillmentService()

        result = _call_route(
            fulfillment=fulfillment,
            text="what is the name of the city",
            routed_text="what is the name of the city",
        )

        self.assertFalse(result.get("handled"))
        self.assertEqual(fulfillment.calls, [("what is the name of the city", None)])


if __name__ == "__main__":
    unittest.main()
