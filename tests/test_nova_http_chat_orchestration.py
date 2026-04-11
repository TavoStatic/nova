import unittest

from services.nova_http_chat_orchestration import HTTP_CHAT_ORCHESTRATION_SERVICE


class _FakeSession:
    def __init__(self):
        self.pending_action = None
        self.conversation_state = {"kind": "idle"}
        self.prefer_web_for_data_queries = False

    def set_pending_action(self, payload):
        self.pending_action = payload

    def set_prefer_web_for_data_queries(self, enabled):
        self.prefer_web_for_data_queries = bool(enabled)

    def apply_state_update(self, payload, fallback_state=None):
        self.conversation_state = payload

    def mark_continuation_used(self):
        pass

    def set_retrieval_state(self, payload):
        self.conversation_state = payload


class _FakeFulfillmentService:
    def __init__(self):
        self.calls = []

    def maybe_run_fulfillment_flow(self, routed_text, session, turns, pending_action=None):
        self.calls.append((routed_text, pending_action))
        return {}


class TestNovaHttpChatOrchestrationService(unittest.TestCase):
    def test_execute_post_intent_sequence_returns_web_override_before_later_branches(self):
        fulfillment = _FakeFulfillmentService()

        result = HTTP_CHAT_ORCHESTRATION_SERVICE.execute_post_intent_sequence(
            text="all you need is the Web",
            routed_text="all you need is the Web",
            turns=[("user", "all you need is the Web")],
            session=_FakeSession(),
            ledger={},
            conversation_state={"kind": "idle"},
            intent_rule={},
            routing_decision=None,
            supervisor_has_route_fn=lambda _rule: False,
            should_warn_supervisor_bypass_fn=lambda _text: False,
            is_web_research_override_request_fn=lambda _text: True,
            action_ledger_add_step_fn=lambda *args, **kwargs: None,
            learn_self_identity_binding_fn=lambda _text: (_ for _ in ()).throw(AssertionError("should not reach identity binding")),
            ensure_reply_fn=lambda text: text,
            evaluate_supervisor_handle_rules_fn=lambda *_args, **_kwargs: {},
            execute_registered_supervisor_rule_fn=lambda *_args, **_kwargs: (False, "", None),
            build_routing_decision_fn=lambda *args, **kwargs: {},
            fulfillment_flow_service=fulfillment,
            fast_smalltalk_reply_fn=lambda _text: None,
            is_developer_profile_request_fn=lambda _text: False,
            developer_profile_reply_fn=lambda *_args: "",
            learn_contextual_developer_facts_fn=lambda *_args: (False, ""),
            infer_profile_conversation_state_fn=lambda _text: None,
            make_conversation_state_fn=lambda *args, **kwargs: {"kind": "identity_profile"},
            learn_contextual_self_facts_fn=lambda *_args, **_kwargs: (False, ""),
            extract_memory_teach_text_fn=lambda _text: "",
            mem_enabled_fn=lambda: False,
            store_location_fact_reply_fn=lambda *_args, **_kwargs: "",
            weather_for_saved_location_fn=lambda: "",
            is_saved_location_weather_query_fn=lambda _text: False,
            store_declarative_fact_outcome_fn=lambda *_args, **_kwargs: None,
            render_reply_fn=lambda outcome: str(outcome),
            consume_conversation_followup_fn=lambda *_args, **_kwargs: (False, "", {"kind": "idle"}),
            conversation_active_subject_fn=lambda _state: "",
            developer_work_guess_turn_fn=lambda _text: ("", None),
            developer_location_turn_fn=lambda *_args, **_kwargs: ("", None),
            handle_location_conversation_turn_fn=lambda *_args, **_kwargs: (False, "", None, ""),
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual((result.get("flow_result") or {}).get("planner_decision"), "deterministic")
        self.assertEqual(fulfillment.calls, [])

    def test_execute_post_intent_sequence_handles_registered_supervisor_rule_and_returns_routing_decision(self):
        session = _FakeSession()
        fulfillment = _FakeFulfillmentService()

        result = HTTP_CHAT_ORCHESTRATION_SERVICE.execute_post_intent_sequence(
            text="who made you?",
            routed_text="who made you?",
            turns=[("user", "who made you?")],
            session=session,
            ledger={},
            conversation_state={"kind": "idle"},
            intent_rule={"intent": "assistant_name"},
            routing_decision=None,
            supervisor_has_route_fn=lambda _rule: False,
            should_warn_supervisor_bypass_fn=lambda _text: True,
            is_web_research_override_request_fn=lambda _text: False,
            action_ledger_add_step_fn=lambda *args, **kwargs: None,
            learn_self_identity_binding_fn=lambda _text: (False, ""),
            ensure_reply_fn=lambda text: text,
            evaluate_supervisor_handle_rules_fn=lambda *_args, **_kwargs: {"intent": "developer_identity_followup", "reply_contract": "identity.creator", "reply_outcome": {"kind": "followup"}, "grounded": True},
            execute_registered_supervisor_rule_fn=lambda *_args, **_kwargs: (True, "Gus made me.", {"kind": "identity_profile", "subject": "developer"}),
            build_routing_decision_fn=lambda text, **kwargs: {"text": text, "handle_intent": ((kwargs.get("handle_result") or {}).get("intent"))},
            fulfillment_flow_service=fulfillment,
            fast_smalltalk_reply_fn=lambda _text: None,
            is_developer_profile_request_fn=lambda _text: False,
            developer_profile_reply_fn=lambda *_args: "",
            learn_contextual_developer_facts_fn=lambda *_args: (False, ""),
            infer_profile_conversation_state_fn=lambda _text: None,
            make_conversation_state_fn=lambda *args, **kwargs: {"kind": "identity_profile"},
            learn_contextual_self_facts_fn=lambda *_args, **_kwargs: (False, ""),
            extract_memory_teach_text_fn=lambda _text: "",
            mem_enabled_fn=lambda: False,
            store_location_fact_reply_fn=lambda *_args, **_kwargs: "",
            weather_for_saved_location_fn=lambda: "",
            is_saved_location_weather_query_fn=lambda _text: False,
            store_declarative_fact_outcome_fn=lambda *_args, **_kwargs: None,
            render_reply_fn=lambda outcome: str(outcome),
            consume_conversation_followup_fn=lambda *_args, **_kwargs: (False, "", {"kind": "idle"}),
            conversation_active_subject_fn=lambda _state: "",
            developer_work_guess_turn_fn=lambda _text: ("", None),
            developer_location_turn_fn=lambda *_args, **_kwargs: ("", None),
            handle_location_conversation_turn_fn=lambda *_args, **_kwargs: (False, "", None, ""),
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual((result.get("flow_result") or {}).get("reply"), "Gus made me.")
        self.assertEqual((result.get("routing_decision") or {}).get("handle_intent"), "developer_identity_followup")
        self.assertTrue(result.get("warn_supervisor_bypass"))
        self.assertEqual(fulfillment.calls, [])

    def test_execute_post_intent_sequence_handles_direct_developer_profile_request_before_later_paths(self):
        session = _FakeSession()
        fulfillment = _FakeFulfillmentService()

        result = HTTP_CHAT_ORCHESTRATION_SERVICE.execute_post_intent_sequence(
            text="who is gus ?",
            routed_text="who is gus ?",
            turns=[("user", "who is gus ?")],
            session=session,
            ledger={},
            conversation_state={"kind": "idle"},
            intent_rule={},
            routing_decision=None,
            supervisor_has_route_fn=lambda _rule: False,
            should_warn_supervisor_bypass_fn=lambda _text: False,
            is_web_research_override_request_fn=lambda _text: False,
            action_ledger_add_step_fn=lambda *args, **kwargs: None,
            learn_self_identity_binding_fn=lambda _text: (False, ""),
            ensure_reply_fn=lambda text: text,
            evaluate_supervisor_handle_rules_fn=lambda *_args, **_kwargs: {},
            execute_registered_supervisor_rule_fn=lambda *_args, **_kwargs: (False, "", None),
            build_routing_decision_fn=lambda *args, **kwargs: {},
            fulfillment_flow_service=fulfillment,
            fast_smalltalk_reply_fn=lambda _text: None,
            is_developer_profile_request_fn=lambda _text: True,
            developer_profile_reply_fn=lambda _turns, _text: "Gustavo Uribe is my developer.",
            learn_contextual_developer_facts_fn=lambda *_args: (_ for _ in ()).throw(AssertionError("should not reach developer learning")),
            infer_profile_conversation_state_fn=lambda _text: None,
            make_conversation_state_fn=lambda *args, **kwargs: {"kind": "identity_profile", "subject": "developer"},
            learn_contextual_self_facts_fn=lambda *_args, **_kwargs: (False, ""),
            extract_memory_teach_text_fn=lambda _text: "",
            mem_enabled_fn=lambda: False,
            store_location_fact_reply_fn=lambda *_args, **_kwargs: "",
            weather_for_saved_location_fn=lambda: "",
            is_saved_location_weather_query_fn=lambda _text: False,
            store_declarative_fact_outcome_fn=lambda *_args, **_kwargs: None,
            render_reply_fn=lambda outcome: str(outcome),
            consume_conversation_followup_fn=lambda *_args, **_kwargs: (False, "", {"kind": "idle"}),
            conversation_active_subject_fn=lambda _state: "",
            developer_work_guess_turn_fn=lambda _text: ("", None),
            developer_location_turn_fn=lambda *_args, **_kwargs: ("", None),
            handle_location_conversation_turn_fn=lambda *_args, **_kwargs: (False, "", None, ""),
        )

        self.assertTrue(result.get("handled"))
        self.assertEqual((result.get("flow_result") or {}).get("reply"), "Gustavo Uribe is my developer.")
        self.assertEqual((result.get("conversation_state") or {}).get("subject"), "developer")
        self.assertEqual(fulfillment.calls, [])


if __name__ == "__main__":
    unittest.main()