import unittest

import http_chat_flow


class TestHttpChatFlow(unittest.TestCase):
    def test_prepare_chat_turn_resolves_intent_without_identity_only_block(self):
        class _Session:
            def __init__(self):
                self.pending_action = {"kind": "x"}
                self.language_mix_spanish_pct = 0
                self._subject = "demo"

            def active_subject(self):
                return self._subject

            def set_language_mix_spanish_pct(self, value):
                self.language_mix_spanish_pct = value

        session = _Session()
        ledger = {}
        calls = {"steps": 0}
        out = http_chat_flow.prepare_chat_turn(
            session_id="clean_slate_session",
            text="I wonder if it's going to rain",
            session=session,
            ledger=ledger,
            append_session_turn=lambda sid, role, text: [(role, text)],
            determine_turn_direction=lambda turns, text, active_subject=None, pending_action=None: {
                "effective_query": text,
                "turn_acts": ["ask"],
                "primary": "question",
                "analysis_reason": "intent",
                "identity_focused": False,
                "bypass_pattern_routes": False,
            },
            auto_adjust_language_mix=lambda pct, routed: pct,
            action_ledger_add_step=lambda *a, **k: calls.__setitem__("steps", calls["steps"] + 1),
            evaluate_supervisor_rules=lambda routed_text, **_: {},
            supervisor_has_route=lambda rule: bool(rule),
            runtime_set_location_intent=lambda routed_text, **_: {"intent": "weather_lookup", "handled": True},
        )
        self.assertEqual(out.get("routed_text"), "I wonder if it's going to rain")
        self.assertEqual(out.get("intent_rule", {}).get("intent"), "weather_lookup")
        self.assertEqual(ledger.get("turn_acts"), ["ask"])
        self.assertEqual(calls["steps"], 1)

    def test_prepare_chat_turn_falls_back_on_direction_error(self):
        class _Session:
            def __init__(self):
                self.pending_action = None
                self.language_mix_spanish_pct = 0

            def active_subject(self):
                return ""

            def set_language_mix_spanish_pct(self, value):
                self.language_mix_spanish_pct = value

        out = http_chat_flow.prepare_chat_turn(
            session_id="s1",
            text="hello",
            session=_Session(),
            ledger={},
            append_session_turn=lambda sid, role, text: [(role, text)],
            determine_turn_direction=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
            auto_adjust_language_mix=lambda pct, routed: pct,
            action_ledger_add_step=lambda *a, **k: None,
            evaluate_supervisor_rules=lambda routed_text, **_: {},
            supervisor_has_route=lambda rule: False,
            runtime_set_location_intent=lambda routed_text, **_: None,
        )
        self.assertEqual(out.get("routed_text"), "hello")
        self.assertEqual(out.get("turn_acts"), [])

    def test_apply_numeric_clarify_outcome_handled(self):
        class _Session:
            def __init__(self):
                self.state = None

            def apply_state_update(self, state, fallback_state=None):
                self.state = state or fallback_state

        calls = []
        session = _Session()
        out = http_chat_flow.apply_numeric_clarify_outcome(
            has_intent_route=False,
            routed_text="42",
            pending_action={"kind": "weather"},
            current_state={"kind": "weather_clarify"},
            session=session,
            ledger={},
            should_clarify_unlabeled_numeric_turn=lambda text, **kwargs: text == "42",
            unlabeled_numeric_turn_reply=lambda text: f"which field uses {text}?",
            make_conversation_state=lambda kind, **kwargs: {"kind": kind, **kwargs},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("reply"), "which field uses 42?")
        self.assertEqual(out.get("planner_decision"), "ask_clarify")
        self.assertFalse(bool(out.get("grounded")))
        self.assertEqual(out.get("intent"), "numeric_clarify")
        self.assertEqual(session.state, {"kind": "numeric_reference_clarify", "value": "42"})
        self.assertEqual(out.get("conversation_state"), {"kind": "numeric_reference_clarify", "value": "42"})
        self.assertIn(("numeric_clarify", "blocked"), calls)

    def test_apply_numeric_clarify_outcome_not_handled_when_route_owned(self):
        out = http_chat_flow.apply_numeric_clarify_outcome(
            has_intent_route=True,
            routed_text="42",
            pending_action=None,
            current_state={},
            session=object(),
            ledger={},
            should_clarify_unlabeled_numeric_turn=lambda text, **kwargs: True,
            unlabeled_numeric_turn_reply=lambda text: text,
            make_conversation_state=lambda kind, **kwargs: {"kind": kind, **kwargs},
            action_ledger_add_step=lambda *a, **k: None,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_handled_supervisor_intent_weather_clarify_is_unhandled(self):
        class _Session:
            def __init__(self):
                self.pending_action = None
                self.conversation_state = {"kind": "initial"}

            def set_pending_action(self, value):
                self.pending_action = value

            def apply_state_update(self, state, fallback_state=None):
                self.conversation_state = state or fallback_state

        session = _Session()
        calls = []
        out = http_chat_flow.apply_handled_supervisor_intent(
            intent_rule={"intent": "weather_lookup", "weather_mode": "clarify", "rule_name": "weather_rule"},
            routed_text="will it rain",
            intent_msg="Where are you located?",
            intent_state={"kind": "weather"},
            intent_effects={"pending_action": {"kind": "weather", "step": "location"}},
            session=session,
            conversation_state={"kind": "before"},
            ledger={},
            emit_supervisor_intent_trace=lambda rule, user_text="": calls.append(("trace", user_text)),
            action_ledger_add_step=lambda *a, **k: calls.append(("step", a[1], a[2], k.get("tool", ""))),
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))
        self.assertEqual(out.get("planner_decision"), "unhandled")
        self.assertFalse(out.get("grounded"))
        self.assertIsNone(session.pending_action)
        self.assertEqual(out.get("intent"), "weather_lookup")
        self.assertEqual(session.conversation_state, {"kind": "initial"})
        self.assertEqual(calls, [])

    def test_apply_handled_supervisor_intent_web_research_is_unhandled(self):
        class _Session:
            def __init__(self):
                self.pending_action = None
                self.conversation_state = {}

            def set_pending_action(self, value):
                self.pending_action = value

            def apply_state_update(self, state, fallback_state=None):
                self.conversation_state = state or fallback_state

        out = http_chat_flow.apply_handled_supervisor_intent(
            intent_rule={"intent": "web_research_family", "tool_name": "web_research", "query": "fallback"},
            routed_text="research attendance",
            intent_msg="summary",
            intent_state={"kind": "retrieval"},
            intent_effects={"reply_outcome": {"query": "peims attendance"}},
            session=_Session(),
            conversation_state={"kind": "before"},
            ledger={},
            emit_supervisor_intent_trace=lambda *a, **k: None,
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))
        self.assertEqual(out.get("planner_decision"), "unhandled")
        self.assertFalse(out.get("grounded"))
        self.assertEqual(out.get("intent"), "web_research_family")

    def test_apply_registered_supervisor_rule_handled(self):
        class _Session:
            def __init__(self):
                self.applied = None
                self.continuation_used_last_turn = False

            def apply_state_update(self, state):
                self.applied = state

            def mark_continuation_used(self):
                self.continuation_used_last_turn = True

        session = _Session()
        calls = []
        out = http_chat_flow.apply_registered_supervisor_rule(
            handled_rule=True,
            general_rule={
                "continuation": True,
                "ledger_stage": "registered_rule",
                "rule_name": "rules_list",
                "grounded": True,
                "intent": "rules_list",
                "reply_contract": "rules.list",
                "reply_outcome": {"kind": "list"},
            },
            rule_reply="I follow strict rules.",
            rule_state={"kind": "rules"},
            session=session,
            ledger={},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2], k.get("rule", ""))),
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "rules_list")
        self.assertEqual(out.get("reply_contract"), "rules.list")
        self.assertEqual(session.applied, {"kind": "rules"})
        self.assertTrue(session.continuation_used_last_turn)
        self.assertIn(("registered_rule", "matched", "rules_list"), calls)

    def test_apply_registered_supervisor_rule_not_handled(self):
        out = http_chat_flow.apply_registered_supervisor_rule(
            handled_rule=False,
            general_rule={},
            rule_reply="",
            rule_state=None,
            session=object(),
            ledger={},
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))

    def test_resume_requires_session_id(self):
        out = http_chat_flow.resume_last_pending_turn(
            "",
            "",
            get_active_user=lambda: "",
            set_active_user=lambda _value: None,
            get_last_session_turn=lambda _sid: None,
            get_session_turns=lambda _sid: [],
            generate_chat_reply=lambda turns, text: ("ok", {}),
            append_session_turn=lambda sid, role, text: [],
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "session_id_required")

    def test_resume_no_turns(self):
        out = http_chat_flow.resume_last_pending_turn(
            "s1",
            "gus",
            get_active_user=lambda: "gus",
            set_active_user=lambda _value: None,
            get_last_session_turn=lambda _sid: None,
            get_session_turns=lambda _sid: [],
            generate_chat_reply=lambda turns, text: ("ok", {}),
            append_session_turn=lambda sid, role, text: [],
        )
        self.assertTrue(out.get("ok"))
        self.assertFalse(out.get("resumed"))
        self.assertEqual(out.get("reason"), "no_turns")

    def test_resume_no_pending_user_turn(self):
        out = http_chat_flow.resume_last_pending_turn(
            "s1",
            "gus",
            get_active_user=lambda: "gus",
            set_active_user=lambda _value: None,
            get_last_session_turn=lambda _sid: ("assistant", "done"),
            get_session_turns=lambda _sid: [("assistant", "done")],
            generate_chat_reply=lambda turns, text: ("ok", {}),
            append_session_turn=lambda sid, role, text: [],
        )
        self.assertTrue(out.get("ok"))
        self.assertFalse(out.get("resumed"))
        self.assertEqual(out.get("reason"), "no_pending_user_turn")

    def test_resume_success(self):
        added = []
        active = {"value": "old"}
        invalidations = []

        def _set(value):
            active["value"] = value

        out = http_chat_flow.resume_last_pending_turn(
            "s1",
            "gus",
            get_active_user=lambda: active["value"],
            set_active_user=_set,
            get_last_session_turn=lambda _sid: ("user", "hello"),
            get_session_turns=lambda _sid: [("user", "hello")],
            generate_chat_reply=lambda turns, text: ("reply", {}),
            append_session_turn=lambda sid, role, text: added.append((sid, role, text)) or [],
            invalidate_control_status_cache=lambda: invalidations.append("called"),
        )

        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("resumed"))
        self.assertEqual(out.get("reply"), "reply")
        self.assertEqual(added, [("s1", "assistant", "reply")])
        self.assertEqual(invalidations, ["called"])
        self.assertEqual(active["value"], "old")

    def test_resume_success_from_runtime_scope(self):
        added = []
        active = {"value": "old"}
        invalidations = []

        def _set(value):
            active["value"] = value

        out = http_chat_flow.resume_last_pending_turn_from_runtime(
            "s1",
            "gus",
            runtime_scope={
                "nova_core": type(
                    "CoreStub",
                    (),
                    {
                        "get_active_user": staticmethod(lambda: active["value"]),
                        "set_active_user": staticmethod(_set),
                    },
                )(),
                "_get_last_session_turn": lambda _sid: ("user", "hello"),
                "_get_session_turns": lambda _sid: [("user", "hello")],
                "_generate_chat_reply": lambda turns, text: ("reply", {}),
                "_append_session_turn": lambda sid, role, text: added.append((sid, role, text)) or [],
                "_invalidate_control_status_cache": lambda: invalidations.append("called"),
            },
        )

        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("resumed"))
        self.assertEqual(out.get("reply"), "reply")
        self.assertEqual(added, [("s1", "assistant", "reply")])
        self.assertEqual(invalidations, ["called"])
        self.assertEqual(active["value"], "old")

    def test_apply_fulfillment_flow_not_dict_result(self):
        ledger = {}
        out = http_chat_flow.apply_fulfillment_flow(
            fulfillment_result=None,
            ledger=ledger,
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_fulfillment_flow_no_reply_text(self):
        ledger = {}
        out = http_chat_flow.apply_fulfillment_flow(
            fulfillment_result={"reply": "", "planner_decision": "fulfill"},
            ledger=ledger,
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: "",
        )
        self.assertFalse(out.get("handled"))

    def test_apply_fulfillment_flow_handled(self):
        ledger = {}
        steps = []

        def _log_step(*args, **kwargs):
            steps.append(args)

        out = http_chat_flow.apply_fulfillment_flow(
            fulfillment_result={
                "reply": "It will be sunny tomorrow",
                "planner_decision": "weather_forecast",
                "grounded": True,
            },
            ledger=ledger,
            action_ledger_add_step=_log_step,
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("reply"), "It will be sunny tomorrow")
        self.assertEqual(out.get("planner_decision"), "weather_forecast")
        self.assertTrue(out.get("grounded"))
        self.assertEqual(out.get("intent"), "fulfillment_flow")
        self.assertIn(({}, "fulfillment_flow", "handled", "weather_forecast"), steps)

    def test_apply_fulfillment_flow_default_grounded(self):
        ledger = {}
        out = http_chat_flow.apply_fulfillment_flow(
            fulfillment_result={
                "reply": "Answer",
            },
            ledger=ledger,
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertTrue(out.get("grounded"))

    def test_apply_conversation_followup_outcome_handled_retrieval(self):
        class _Session:
            def __init__(self):
                self.conversation_state = {"kind": "before"}
                self.continuation_used_last_turn = False
                self.retrieval_state = None

            def mark_continuation_used(self):
                self.continuation_used_last_turn = True

            def set_retrieval_state(self, state):
                self.retrieval_state = state
                self.conversation_state = state

            def apply_state_update(self, state):
                self.conversation_state = state

        calls = []
        session = _Session()
        out = http_chat_flow.apply_conversation_followup_outcome(
            handled_followup=True,
            followup_msg="Could you clarify that?",
            next_state={"kind": "retrieval", "subject": "developer"},
            conversation_state={"kind": "developer_profile"},
            session=session,
            ledger={},
            conversation_active_subject=lambda state: str((state or {}).get("kind") or ""),
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2], k.get("active_subject", ""))),
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("planner_decision"), "conversation_followup")
        self.assertEqual(out.get("intent"), "conversation_followup")
        self.assertEqual(session.retrieval_state, {"kind": "retrieval", "subject": "developer"})
        self.assertTrue(session.continuation_used_last_turn)
        self.assertIn(("conversation_followup", "used", "developer_profile"), calls)

    def test_apply_conversation_followup_outcome_not_handled(self):
        class _Session:
            def __init__(self):
                self.conversation_state = {"kind": "before"}

            def apply_state_update(self, state):
                self.conversation_state = state

            def mark_continuation_used(self):
                raise AssertionError("should not mark continuation when not handled")

            def set_retrieval_state(self, state):
                raise AssertionError("should not set retrieval when not handled")

        session = _Session()
        out = http_chat_flow.apply_conversation_followup_outcome(
            handled_followup=False,
            followup_msg="",
            next_state={"kind": "identity_profile"},
            conversation_state={"kind": "before"},
            session=session,
            ledger={},
            conversation_active_subject=lambda state: "",
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))
        self.assertEqual(out.get("conversation_state"), {"kind": "identity_profile"})
        self.assertEqual(session.conversation_state, {"kind": "identity_profile"})

if __name__ == "__main__":
    unittest.main()
