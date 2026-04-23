import unittest

from services.nova_http_turn_entry import HTTP_TURN_ENTRY_SERVICE


class _FakeSession:
    def __init__(self):
        self.pending_action = None
        self.pending_correction_target = ""
        self.conversation_state = {"kind": "idle"}

    def apply_state_update(self, payload, fallback_state=None):
        self.conversation_state = payload if isinstance(payload, dict) else fallback_state

    def set_pending_action(self, payload):
        self.pending_action = payload


class TestNovaHttpTurnEntryService(unittest.TestCase):
    def test_execute_turn_entry_short_circuits_identity_only_block(self):
        session = _FakeSession()

        result = HTTP_TURN_ENTRY_SERVICE.execute_turn_entry(
            session_id="s-entry-block",
            text="open the browser",
            session=session,
            ledger={},
            conversation_state={"kind": "idle"},
            append_session_turn_fn=lambda *args, **kwargs: None,
            determine_turn_direction_fn=lambda *_args, **_kwargs: "chat",
            auto_adjust_language_mix_fn=lambda *_args, **_kwargs: 0,
            action_ledger_add_step_fn=lambda *args, **kwargs: None,
            evaluate_supervisor_rules_fn=lambda *_args, **_kwargs: {},
            supervisor_has_route_fn=lambda _rule: False,
            runtime_set_location_intent_fn=lambda *_args, **_kwargs: None,
            llm_classify_routing_intent_fn=lambda *_args, **_kwargs: "chat",
            is_identity_only_session_fn=lambda *_args, **_kwargs: True,
            identity_only_block_kind_fn=lambda _text, **_kwargs: "tools",
            identity_only_block_reply_fn=lambda kind: f"blocked:{kind}",
            build_routing_decision_fn=lambda text, **kwargs: {"text": text, "entry_point": kwargs.get("entry_point")},
            handle_supervisor_intent_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not reach supervisor intent")),
            emit_supervisor_intent_trace_fn=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            should_clarify_unlabeled_numeric_turn_fn=lambda *_args, **_kwargs: False,
            unlabeled_numeric_turn_reply_fn=lambda text: f"clarify:{text}",
            make_conversation_state_fn=lambda *args, **kwargs: {"kind": "clarify"},
            mixed_info_request_clarify_reply_fn=lambda text: f"mixed:{text}",
            is_saved_location_weather_query_fn=lambda _text: False,
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual((result.get("flow_result") or {}).get("planner_decision"), "policy_block")
        self.assertEqual((((result.get("flow_result") or {}).get("reply_outcome") or {}).get("blocked_domain")), "tools")
        self.assertEqual((result.get("routing_decision") or {}).get("entry_point"), "http")

    def test_execute_turn_entry_handles_supervisor_intent_and_returns_routing_decision(self):
        session = _FakeSession()

        result = HTTP_TURN_ENTRY_SERVICE.execute_turn_entry(
            session_id="s-entry-supervisor",
            text="what is the weather",
            session=session,
            ledger={},
            conversation_state={"kind": "idle"},
            append_session_turn_fn=lambda *args, **kwargs: None,
            determine_turn_direction_fn=lambda *_args, **_kwargs: "chat",
            auto_adjust_language_mix_fn=lambda *_args, **_kwargs: 0,
            action_ledger_add_step_fn=lambda *args, **kwargs: None,
            evaluate_supervisor_rules_fn=lambda *_args, **_kwargs: {"intent_rule": True},
            supervisor_has_route_fn=lambda _rule: False,
            runtime_set_location_intent_fn=lambda *_args, **_kwargs: None,
            llm_classify_routing_intent_fn=lambda *_args, **_kwargs: "chat",
            is_identity_only_session_fn=lambda *_args, **_kwargs: False,
            identity_only_block_kind_fn=lambda _text, **_kwargs: "",
            identity_only_block_reply_fn=lambda kind: f"blocked:{kind}",
            build_routing_decision_fn=lambda text, **kwargs: {"text": text, "turn_acts": list(kwargs.get("turn_acts") or [])},
            handle_supervisor_intent_fn=lambda *_args, **_kwargs: (True, "Sunny.", {"kind": "weather"}, {"reply_contract": "weather.current"}),
            emit_supervisor_intent_trace_fn=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            should_clarify_unlabeled_numeric_turn_fn=lambda *_args, **_kwargs: False,
            unlabeled_numeric_turn_reply_fn=lambda text: f"clarify:{text}",
            make_conversation_state_fn=lambda *args, **kwargs: {"kind": "clarify"},
            mixed_info_request_clarify_reply_fn=lambda text: f"mixed:{text}",
            is_saved_location_weather_query_fn=lambda _text: False,
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual((result.get("routed_text") or ""), "what is the weather")
        self.assertEqual((result.get("routing_decision") or {}).get("text"), "what is the weather")
        self.assertEqual((result.get("flow_result") or {}).get("reply"), "Sunny.")
        self.assertEqual((result.get("conversation_state") or {}).get("kind"), "weather")

    def test_execute_turn_entry_defers_saved_location_weather_followup(self):
        session = _FakeSession()

        result = HTTP_TURN_ENTRY_SERVICE.execute_turn_entry(
            session_id="s-entry-saved-weather",
            text="weather now",
            session=session,
            ledger={},
            conversation_state={"kind": "location_recall"},
            append_session_turn_fn=lambda *args, **kwargs: None,
            determine_turn_direction_fn=lambda *_args, **_kwargs: "chat",
            auto_adjust_language_mix_fn=lambda *_args, **_kwargs: 0,
            action_ledger_add_step_fn=lambda *args, **kwargs: None,
            evaluate_supervisor_rules_fn=lambda *_args, **_kwargs: {"intent": "weather_lookup"},
            supervisor_has_route_fn=lambda _rule: True,
            runtime_set_location_intent_fn=lambda *_args, **_kwargs: None,
            llm_classify_routing_intent_fn=lambda *_args, **_kwargs: "chat",
            is_identity_only_session_fn=lambda *_args, **_kwargs: False,
            identity_only_block_kind_fn=lambda _text, **_kwargs: "",
            identity_only_block_reply_fn=lambda kind: f"blocked:{kind}",
            build_routing_decision_fn=lambda text, **kwargs: {"text": text},
            handle_supervisor_intent_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("saved-location weather should defer")),
            emit_supervisor_intent_trace_fn=lambda *args, **kwargs: None,
            ensure_reply_fn=lambda text: text,
            should_clarify_unlabeled_numeric_turn_fn=lambda *_args, **_kwargs: False,
            unlabeled_numeric_turn_reply_fn=lambda text: f"clarify:{text}",
            make_conversation_state_fn=lambda *args, **kwargs: {"kind": "clarify"},
            mixed_info_request_clarify_reply_fn=lambda text: f"mixed:{text}",
            is_saved_location_weather_query_fn=lambda text: text == "weather now",
        )

        self.assertFalse(result.get("handled"))
        self.assertEqual((result.get("routed_text") or ""), "weather now")
        self.assertEqual((result.get("conversation_state") or {}).get("kind"), "location_recall")


if __name__ == "__main__":
    unittest.main()