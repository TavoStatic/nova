import unittest

import http_chat_flow


class TestHttpChatFlow(unittest.TestCase):
    def test_prepare_chat_turn_resolves_intent_and_block(self):
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
            llm_classify_routing_intent=lambda routed_text, turns=None: None,
            is_identity_only_session=lambda sid: True,
            identity_only_block_kind=lambda routed_text, intent_result=None: "weather",
        )
        self.assertEqual(out.get("routed_text"), "I wonder if it's going to rain")
        self.assertEqual(out.get("intent_rule", {}).get("intent"), "weather_lookup")
        self.assertEqual(out.get("identity_only_block_kind"), "weather")
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
            llm_classify_routing_intent=lambda routed_text, turns=None: None,
            is_identity_only_session=lambda sid: False,
            identity_only_block_kind=lambda routed_text, intent_result=None: "",
        )
        self.assertEqual(out.get("routed_text"), "hello")
        self.assertEqual(out.get("turn_acts"), [])
        self.assertEqual(out.get("identity_only_block_kind"), "")

    def test_apply_identity_only_mode_block_handled(self):
        calls = []
        out = http_chat_flow.apply_identity_only_mode_block(
            routed_text="what's the weather",
            intent_rule={"intent": "weather_lookup"},
            identity_only_block_kind="weather",
            ledger={},
            build_routing_decision=lambda text, **kwargs: {"final_owner": "pending", "input_preview": text},
            identity_only_block_reply=lambda block_kind: f"blocked:{block_kind}",
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2], a[3] if len(a) > 3 else "", k.get("blocked_domain", ""))),
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("reply"), "blocked:weather")
        self.assertEqual(out.get("planner_decision"), "policy_block")
        self.assertFalse(bool(out.get("grounded")))
        self.assertEqual(out.get("intent"), "policy_block")
        self.assertEqual(out.get("reply_contract"), "policy.identity_only_mode")
        self.assertEqual((out.get("reply_outcome") or {}).get("blocked_domain"), "weather")
        self.assertEqual((out.get("routing_decision") or {}).get("input_preview"), "what's the weather")
        self.assertIn(("policy_gate", "blocked", "identity_only_mode", "weather"), calls)

    def test_apply_identity_only_mode_block_not_handled(self):
        out = http_chat_flow.apply_identity_only_mode_block(
            routed_text="hello",
            intent_rule={},
            identity_only_block_kind="",
            ledger={},
            build_routing_decision=lambda text, **kwargs: {},
            identity_only_block_reply=lambda block_kind: "",
            action_ledger_add_step=lambda *a, **k: None,
        )
        self.assertFalse(out.get("handled"))

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

    def test_apply_mixed_turn_clarify_handled(self):
        calls = []
        out = http_chat_flow.apply_mixed_turn_clarify(
            turn_acts=["ask", "mixed"],
            correction_pending=False,
            routed_text="tell me the weather and save Dallas",
            ledger={},
            mixed_info_request_clarify_reply=lambda text: f"clarify:{text}",
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("reply"), "clarify:tell me the weather and save Dallas")
        self.assertEqual(out.get("planner_decision"), "ask_clarify")
        self.assertEqual(out.get("intent"), "clarify_mixed_turn")
        self.assertEqual(out.get("reply_contract"), "turn.clarify_mixed_intent")
        self.assertEqual((out.get("reply_outcome") or {}).get("kind"), "mixed_info_request")
        self.assertIn(("mixed_turn_clarify", "blocked"), calls)

    def test_apply_mixed_turn_clarify_not_handled_when_correction_pending(self):
        out = http_chat_flow.apply_mixed_turn_clarify(
            turn_acts=["mixed"],
            correction_pending=True,
            routed_text="mixed turn",
            ledger={},
            mixed_info_request_clarify_reply=lambda text: text,
            action_ledger_add_step=lambda *a, **k: None,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_supervisor_bypass_safe_fallback_handled(self):
        calls = []
        routing_decision = {"final_owner": "planner"}
        out = http_chat_flow.apply_supervisor_bypass_safe_fallback(
            warn_supervisor_bypass=True,
            reply_contract="",
            routed_text="tell me anything",
            turns=[("user", "tell me anything")],
            routing_decision=routing_decision,
            ledger={},
            open_probe_reply=lambda text, turns=None: (f"safe:{text}", "safe_fallback"),
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2], a[3] if len(a) > 3 else "")),
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("reply"), "safe:tell me anything")
        self.assertEqual(out.get("reply_contract"), "open_probe.safe_fallback")
        self.assertEqual(out.get("planner_decision"), "deterministic")
        self.assertFalse(bool((out.get("meta") or {}).get("grounded", True)))
        self.assertEqual((out.get("routing_decision") or {}).get("final_owner"), "supervisor_handle")
        self.assertIn(("open_probe", "matched", "safe_fallback"), calls)

    def test_apply_supervisor_bypass_safe_fallback_not_handled_for_truthful_limit(self):
        out = http_chat_flow.apply_supervisor_bypass_safe_fallback(
            warn_supervisor_bypass=True,
            reply_contract="turn.truthful_limit",
            routed_text="tell me anything",
            turns=[],
            routing_decision={"final_owner": "planner"},
            ledger={},
            open_probe_reply=lambda text, turns=None: (text, "safe_fallback"),
            action_ledger_add_step=lambda *a, **k: None,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_handled_supervisor_intent_weather_clarify(self):
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
        self.assertEqual(out.get("planner_decision"), "ask_clarify")
        self.assertFalse(out.get("grounded"))
        self.assertEqual(session.pending_action, {"kind": "weather", "step": "location"})
        self.assertEqual(out.get("intent"), "weather_lookup")
        self.assertEqual(session.conversation_state, {"kind": "weather"})
        self.assertIn(("trace", "will it rain"), calls)

    def test_apply_handled_supervisor_intent_web_research(self):
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
        self.assertEqual(out.get("planner_decision"), "run_tool")
        self.assertEqual(out.get("tool"), "web_research")
        self.assertEqual(out.get("tool_args"), {"args": ["peims attendance"]})
        self.assertEqual(out.get("tool_result"), "summary")
        self.assertTrue(out.get("grounded"))

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

    def test_apply_fast_smalltalk_handled(self):
        calls = []
        out = http_chat_flow.apply_fast_smalltalk(
            quick_reply="Hey there!",
            ledger={},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("reply"), "Hey there!")
        self.assertEqual(out.get("planner_decision"), "deterministic")
        self.assertFalse(out.get("grounded"))
        self.assertIn(("fast_smalltalk", "matched"), calls)

    def test_apply_fast_smalltalk_not_handled(self):
        out = http_chat_flow.apply_fast_smalltalk(
            quick_reply="",
            ledger={},
            action_ledger_add_step=lambda *a, **k: None,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_web_research_override_handled(self):
        class _Session:
            def __init__(self):
                self.prefer_web_for_data_queries = False

            def set_prefer_web_for_data_queries(self, value):
                self.prefer_web_for_data_queries = bool(value)

        calls = []
        session = _Session()
        out = http_chat_flow.apply_web_research_override(
            text="just use the web for this",
            session=session,
            ledger={},
            is_web_research_override_request=lambda text: True,
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2], a[3] if len(a) > 3 else "")),
        )
        self.assertTrue(out.get("handled"))
        self.assertTrue(session.prefer_web_for_data_queries)
        self.assertEqual(out.get("planner_decision"), "deterministic")
        self.assertTrue(bool(out.get("grounded")))
        self.assertEqual(out.get("intent"), "session_override")
        self.assertIn(("session_override", "enabled", "prefer_web_for_data_queries"), calls)

    def test_apply_web_research_override_not_handled(self):
        class _Session:
            def __init__(self):
                self.prefer_web_for_data_queries = False

            def set_prefer_web_for_data_queries(self, value):
                self.prefer_web_for_data_queries = bool(value)

        session = _Session()
        out = http_chat_flow.apply_web_research_override(
            text="hello there",
            session=session,
            ledger={},
            is_web_research_override_request=lambda text: False,
            action_ledger_add_step=lambda *a, **k: None,
        )
        self.assertFalse(out.get("handled"))
        self.assertFalse(session.prefer_web_for_data_queries)

    def test_apply_identity_binding_learning_handled(self):
        calls = []
        out = http_chat_flow.apply_identity_binding_learning(
            identity_learned=True,
            identity_msg="Bound identity.",
            ledger={},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("reply"), "Bound identity.")
        self.assertEqual(out.get("planner_decision"), "deterministic")
        self.assertTrue(bool(out.get("grounded")))
        self.assertEqual(out.get("intent"), "identity_binding")
        self.assertIn(("identity_binding", "stored"), calls)

    def test_apply_identity_binding_learning_not_handled(self):
        out = http_chat_flow.apply_identity_binding_learning(
            identity_learned=False,
            identity_msg="",
            ledger={},
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_developer_profile_learning_handled(self):
        class _Session:
            def __init__(self):
                self.conversation_state = {}

            def apply_state_update(self, state):
                self.conversation_state = state

        calls = []
        session = _Session()
        out = http_chat_flow.apply_developer_profile_learning(
            learned_profile=True,
            learned_profile_msg="Stored your profile note.",
            text="I am a backend developer",
            session=session,
            ledger={},
            infer_profile_conversation_state=lambda text: {"kind": "identity_profile", "subject": "developer"},
            make_conversation_state=lambda kind, subject="": {"kind": kind, "subject": subject},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "developer_profile_store")
        self.assertEqual(out.get("reply"), "Stored your profile note.")
        self.assertEqual(session.conversation_state, {"kind": "identity_profile", "subject": "developer"})
        self.assertIn(("developer_profile", "stored"), calls)

    def test_apply_developer_profile_learning_not_handled(self):
        out = http_chat_flow.apply_developer_profile_learning(
            learned_profile=False,
            learned_profile_msg="",
            text="hello",
            session=object(),
            ledger={},
            infer_profile_conversation_state=lambda text: None,
            make_conversation_state=lambda kind, subject="": {"kind": kind, "subject": subject},
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_self_profile_learning_handled(self):
        calls = []
        out = http_chat_flow.apply_self_profile_learning(
            learned_self=True,
            learned_self_msg="Saved a self note.",
            ledger={},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "self_profile_store")
        self.assertEqual(out.get("reply"), "Saved a self note.")
        self.assertIn(("self_profile", "stored"), calls)

    def test_apply_self_profile_learning_not_handled(self):
        out = http_chat_flow.apply_self_profile_learning(
            learned_self=False,
            learned_self_msg="",
            ledger={},
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_location_store_outcome_handled(self):
        class _Session:
            def __init__(self):
                self.conversation_state = {"kind": "before"}

            def apply_state_update(self, state, fallback_state=None):
                self.conversation_state = state or fallback_state

        calls = []
        session = _Session()
        out = http_chat_flow.apply_location_store_outcome(
            location_ack="Location saved.",
            conversation_state={"kind": "before"},
            session=session,
            ledger={},
            make_conversation_state=lambda kind: {"kind": kind},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "location_store")
        self.assertEqual(out.get("reply"), "Location saved.")
        self.assertEqual(session.conversation_state, {"kind": "location_recall"})
        self.assertIn(("location_memory", "stored"), calls)

    def test_apply_location_store_outcome_not_handled(self):
        out = http_chat_flow.apply_location_store_outcome(
            location_ack="",
            conversation_state={"kind": "before"},
            session=object(),
            ledger={},
            make_conversation_state=lambda kind: {"kind": kind},
            action_ledger_add_step=lambda *a, **k: None,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_saved_location_weather_outcome_handled(self):
        class _Session:
            def __init__(self):
                self.conversation_state = {"kind": "before"}

            def apply_state_update(self, state, fallback_state=None):
                self.conversation_state = state or fallback_state

        calls = []
        session = _Session()
        out = http_chat_flow.apply_saved_location_weather_outcome(
            conversation_state={"kind": "location_recall"},
            routed_text="will it rain there",
            weather_for_saved_location=lambda: "Rain expected.",
            is_saved_location_weather_query=lambda text: True,
            session=session,
            ledger={},
            make_conversation_state=lambda kind: {"kind": kind},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "weather_lookup")
        self.assertEqual(out.get("reply"), "Rain expected.")
        self.assertEqual(session.conversation_state, {"kind": "location_recall"})
        self.assertIn(("weather_lookup", "saved_location"), calls)

    def test_apply_saved_location_weather_outcome_not_handled(self):
        out = http_chat_flow.apply_saved_location_weather_outcome(
            conversation_state={"kind": "other"},
            routed_text="weather",
            weather_for_saved_location=lambda: "Rain expected.",
            is_saved_location_weather_query=lambda text: True,
            session=object(),
            ledger={},
            make_conversation_state=lambda kind: {"kind": kind},
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_declarative_store_outcome_handled(self):
        calls = []
        outcome = {"reply_contract": "fact.stored", "kind": "fact"}
        out = http_chat_flow.apply_declarative_store_outcome(
            declarative_outcome=outcome,
            ledger={},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
            render_reply=lambda payload: "Stored.",
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "declarative_store")
        self.assertEqual(out.get("reply"), "Stored.")
        self.assertEqual(out.get("reply_contract"), "fact.stored")
        self.assertEqual(out.get("reply_outcome"), outcome)
        self.assertIn(("declarative_memory", "stored"), calls)

    def test_apply_declarative_store_outcome_not_handled(self):
        out = http_chat_flow.apply_declarative_store_outcome(
            declarative_outcome=None,
            ledger={},
            action_ledger_add_step=lambda *a, **k: None,
            render_reply=lambda payload: "",
        )
        self.assertFalse(out.get("handled"))

    def test_apply_developer_guess_outcome_handled(self):
        class _Session:
            def __init__(self):
                self.conversation_state = {"kind": "before"}

            def apply_state_update(self, state):
                self.conversation_state = state

        calls = []
        session = _Session()
        out = http_chat_flow.apply_developer_guess_outcome(
            developer_guess="Are you a software engineer?",
            next_state={"kind": "developer_profile"},
            session=session,
            ledger={},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "developer_role_guess")
        self.assertEqual(out.get("reply"), "Are you a software engineer?")
        self.assertEqual(session.conversation_state, {"kind": "developer_profile"})
        self.assertIn(("developer_role_guess", "matched"), calls)

    def test_apply_developer_guess_outcome_not_handled(self):
        out = http_chat_flow.apply_developer_guess_outcome(
            developer_guess="",
            next_state=None,
            session=object(),
            ledger={},
            action_ledger_add_step=lambda *a, **k: None,
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_developer_location_outcome_handled(self):
        class _Session:
            def __init__(self):
                self.conversation_state = {"kind": "before"}

            def apply_state_update(self, state):
                self.conversation_state = state

        calls = []
        session = _Session()
        out = http_chat_flow.apply_developer_location_outcome(
            reply_text="You mentioned Brownsville earlier.",
            next_state={"kind": "developer_location"},
            session=session,
            ledger={},
            action_ledger_add_step=lambda *a, **k: calls.append((a[1], a[2])),
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "developer_location")
        self.assertEqual(out.get("reply"), "You mentioned Brownsville earlier.")
        self.assertEqual(session.conversation_state, {"kind": "developer_location"})
        self.assertIn(("developer_location", "matched"), calls)

    def test_apply_developer_location_outcome_not_handled(self):
        out = http_chat_flow.apply_developer_location_outcome(
            reply_text="",
            next_state=None,
            session=object(),
            ledger={},
            action_ledger_add_step=lambda *a, **k: None,
        )
        self.assertFalse(out.get("handled"))

    def test_apply_location_conversation_outcome_handled(self):
        class _Session:
            def __init__(self):
                self.conversation_state = {"kind": "before"}

            def apply_state_update(self, state, fallback_state=None):
                self.conversation_state = state or fallback_state

        session = _Session()
        out = http_chat_flow.apply_location_conversation_outcome(
            handled_location=True,
            location_reply="I can use your saved location.",
            next_location_state={"kind": "location_recall"},
            location_intent="location_recall",
            conversation_state={"kind": "before"},
            session=session,
            ensure_reply=lambda text: text,
        )
        self.assertTrue(out.get("handled"))
        self.assertEqual(out.get("intent"), "location_recall")
        self.assertEqual(out.get("reply"), "I can use your saved location.")
        self.assertEqual(session.conversation_state, {"kind": "location_recall"})

    def test_apply_location_conversation_outcome_not_handled(self):
        out = http_chat_flow.apply_location_conversation_outcome(
            handled_location=False,
            location_reply="",
            next_location_state=None,
            location_intent="",
            conversation_state={"kind": "before"},
            session=object(),
            ensure_reply=lambda text: text,
        )
        self.assertFalse(out.get("handled"))

if __name__ == "__main__":
    unittest.main()
