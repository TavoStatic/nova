import unittest

from services.nova_http_turn_finalization import HTTP_TURN_FINALIZATION_SERVICE


class _FakeSession:
    def __init__(self):
        self.pending_action = {"kind": "weather_followup"}
        self.continuation_used_last_turn = True
        self._active_subject = "identity_profile:developer"
        self._reflection_summary = {"overrides_active": ["memory_guard"]}
        self.retrieval_state = None
        self.updated_state = None

    def active_subject(self):
        return self._active_subject

    def reflection_summary(self):
        return dict(self._reflection_summary)

    def set_pending_action(self, payload):
        self.pending_action = payload

    def set_retrieval_state(self, payload):
        self.retrieval_state = payload

    def apply_state_update(self, payload, fallback_state=None):
        self.updated_state = {"state": payload, "fallback_state": fallback_state}


class TestNovaHttpTurnFinalizationService(unittest.TestCase):
    def test_finalize_http_reply_builds_reflection_and_finalizes_ledger(self):
        session = _FakeSession()
        ledger = {"turn_acts": ["developer_profile"]}
        captured = {}

        def fake_build_turn_reflection(session_obj, **kwargs):
            captured["reflection_session"] = session_obj
            captured["current_decision"] = kwargs.get("current_decision")
            return {"reflection": "ok"}

        def fake_finalize_action_ledger_record(record, **kwargs):
            captured["finalized_record"] = record
            captured["finalize_kwargs"] = kwargs

        reply = HTTP_TURN_FINALIZATION_SERVICE.finalize_http_reply(
            "Gus is my developer.",
            session=session,
            session_id="s-http",
            user_input="who is your developer?",
            ledger=ledger,
            routing_decision={"decision_stage": "reply"},
            build_turn_reflection_fn=fake_build_turn_reflection,
            finalize_action_ledger_record_fn=fake_finalize_action_ledger_record,
            finalize_routing_decision_fn=lambda routing, **kwargs: {"merged": routing, "planner_decision": kwargs.get("planner_decision")},
            action_ledger_route_summary_fn=lambda record: f"route_summary:{len(record.get('turn_acts') or [])}",
            planner_decision="deterministic",
            tool="developer_profile",
            tool_args={"query": "who is your developer?"},
            tool_result="Gus is my developer.",
            grounded=True,
            reply_contract="identity.profile",
            reply_outcome={"kind": "profile"},
        )

        self.assertEqual(reply, "Gus is my developer.")
        self.assertIs(captured["reflection_session"], session)
        self.assertEqual(captured["current_decision"]["route_summary"], "route_summary:1")
        self.assertEqual(captured["current_decision"]["routing_decision"], {"merged": {"decision_stage": "reply"}, "planner_decision": "deterministic"})
        self.assertEqual(captured["finalize_kwargs"]["routing_decision"], {"decision_stage": "reply"})
        self.assertEqual(captured["finalize_kwargs"]["reply_outcome"], {"kind": "profile"})

    def test_apply_reply_outcome_updates_pending_and_retrieval_state(self):
        session = _FakeSession()
        events = []

        payload = HTTP_TURN_FINALIZATION_SERVICE.apply_reply_outcome(
            session=session,
            meta={
                "planner_decision": "run_tool",
                "tool": "weather_current_location",
                "tool_args": {"zip": "78521"},
                "tool_result": "Sunny and warm.",
                "grounded": True,
                "pending_action": {"kind": "weather_followup", "zip": "78521"},
                "reply_contract": "weather.current",
                "reply_outcome": {"kind": "weather"},
            },
            routed_text="weather now",
            turns=[("user", "weather now")],
            fallback_state={"kind": "location_memory"},
            behavior_record_event_fn=events.append,
            infer_post_reply_conversation_state_fn=lambda routed_text, **kwargs: {"kind": "retrieval", "topic": routed_text, "planner_decision": kwargs.get("planner_decision")},
        )

        self.assertEqual(events, ["tool_route"])
        self.assertEqual(session.pending_action, {"kind": "weather_followup", "zip": "78521"})
        self.assertEqual(session.retrieval_state, {"kind": "retrieval", "topic": "weather now", "planner_decision": "run_tool"})
        self.assertEqual(payload["tool"], "weather_current_location")
        self.assertEqual(payload["reply_contract"], "weather.current")
        self.assertEqual(payload["reply_outcome"], {"kind": "weather"})

    def test_finalize_reply_sequence_result_handles_writeback_and_finalization(self):
        session = _FakeSession()
        events = []
        appended = []
        captured = {}

        def fake_build_turn_reflection(session_obj, **kwargs):
            captured["reflection_session"] = session_obj
            captured["current_decision"] = kwargs.get("current_decision")
            return {"reflection": "ok"}

        def fake_finalize_action_ledger_record(record, **kwargs):
            captured["finalized_record"] = record
            captured["finalize_kwargs"] = kwargs

        reply = HTTP_TURN_FINALIZATION_SERVICE.finalize_reply_sequence_result(
            "Sunny and warm.",
            session=session,
            session_id="s-http",
            user_input="weather now",
            ledger={"turn_acts": ["weather_lookup"]},
            routing_decision={"decision_stage": "reply"},
            meta={
                "planner_decision": "run_tool",
                "tool": "weather_current_location",
                "tool_args": {"zip": "78521"},
                "tool_result": "Sunny and warm.",
                "grounded": True,
                "pending_action": {"kind": "weather_followup", "zip": "78521"},
                "reply_contract": "weather.current",
                "reply_outcome": {"kind": "weather"},
            },
            routed_text="weather now",
            turns=[("user", "weather now")],
            fallback_state={"kind": "location_memory"},
            append_session_turn_fn=lambda sid, role, text: appended.append((sid, role, text)),
            behavior_record_event_fn=events.append,
            infer_post_reply_conversation_state_fn=lambda routed_text, **kwargs: {"kind": "retrieval", "topic": routed_text, "planner_decision": kwargs.get("planner_decision")},
            build_turn_reflection_fn=fake_build_turn_reflection,
            finalize_action_ledger_record_fn=fake_finalize_action_ledger_record,
            finalize_routing_decision_fn=lambda routing, **kwargs: {"merged": routing, "planner_decision": kwargs.get("planner_decision")},
            action_ledger_route_summary_fn=lambda record: f"route_summary:{len(record.get('turn_acts') or [])}",
        )

        self.assertEqual(reply, "Sunny and warm.")
        self.assertEqual(events, ["tool_route"])
        self.assertEqual(appended, [("s-http", "assistant", "Sunny and warm.")])
        self.assertEqual(captured["current_decision"]["planner_decision"], "run_tool")
        self.assertEqual(captured["finalize_kwargs"]["tool"], "weather_current_location")


if __name__ == "__main__":
    unittest.main()