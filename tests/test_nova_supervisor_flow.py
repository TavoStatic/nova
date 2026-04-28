import unittest

from services import nova_supervisor_flow


def _runtime_scope() -> dict[str, object]:
    return {
        "remember_name_origin": lambda text: f"remembered:{text}",
        "_make_conversation_state": lambda kind, **data: {"kind": kind, **data},
        "_location_reply": lambda: "location",
        "_is_location_name_query": lambda text: False,
        "_location_name_reply": lambda: "location-name",
        "_location_recall_reply": lambda: "location-recall",
        "_classify_weather_lookup_outcome": lambda outcome: {"reply_contract": "weather.lookup"},
        "_attach_reply_outcome": lambda *_args, **_kwargs: None,
        "execute_planned_action": lambda *args, **kwargs: "tool-result",
        "render_reply": lambda outcome=None: str((outcome or {}).get("reply_text") or (outcome or {}).get("kind") or ""),
        "_last_assistant_turn_text": lambda turns=None: "last assistant",
        "_parse_correction": lambda text: "",
        "_extract_authoritative_correction_text": lambda text: "",
        "_store_supervisor_correction_record": lambda *args, **kwargs: None,
        "learn_from_user_correction": lambda text: (False, ""),
        "_classify_correction_outcome": lambda **kwargs: {"reply_text": "corrected"},
        "mem_enabled": lambda: False,
        "_normalize_correction_for_storage": lambda text: text,
        "_teach_store_example": lambda *args, **kwargs: None,
        "get_active_user": lambda: "tester",
        "_looks_like_correction_cancel": lambda text: False,
        "_looks_like_pending_replacement_text": lambda text: False,
        "_execute_retrieval_followup_outcome": lambda state, text: ("retrieval", state, {"reply_contract": "retrieval"}),
        "_execute_identity_history_outcome": lambda *args, **kwargs: ("history", None, {"reply_contract": "history"}),
        "_open_probe_reply": lambda text, turns=None: ("probe", "probe_kind"),
        "_last_question_recall_reply": lambda text, turns=None: ("question", "question_kind"),
        "_session_fact_recall_reply": lambda rule_result: ("fact", "fact_kind"),
        "_rules_reply": lambda: "Rules go here.",
        "_developer_location_reply": lambda: "developer-location",
        "_developer_identity_followup_reply": lambda **kwargs: "developer-followup",
        "_identity_profile_followup_reply": lambda subject, turns=None: f"profile:{subject}",
        "_classify_web_research_outcome": lambda intent_result, user_text, turns=None: {
            "tool_name": "web_research",
            "query": user_text,
            "reply_contract": "web.research",
            "reply_text": "researched",
        },
        "_make_retrieval_conversation_state": lambda tool_name, query, tool_result: {
            "kind": "retrieval",
            "tool_name": tool_name,
            "query": query,
            "tool_result": tool_result,
        },
        "mem_add": lambda *args, **kwargs: None,
        "_classify_store_fact_outcome": lambda *args, **kwargs: {"reply_text": "stored", "reply_contract": "store.fact"},
        "_classify_set_location_outcome": lambda *args, **kwargs: {"reply_text": "set", "reply_contract": "set.location"},
        "_weather_current_location_available": lambda: False,
        "_execute_weather_lookup_outcome": lambda outcome: ("weather", None, {"reply_contract": "weather.lookup"}),
        "set_location_text": lambda *args, **kwargs: None,
        "_quick_smalltalk_reply": lambda user_text, active_user=None: "",
        "describe_capabilities": lambda: "capabilities",
        "policy_web": lambda: {"enabled": True, "allow_domains": ["example.com"]},
        "_assistant_name_reply": lambda user_text: "Nova",
        "_self_identity_web_challenge_reply": lambda: "identity",
        "_classify_name_origin_outcome": lambda intent_result: {"reply_text": "origin", "reply_contract": "name.origin"},
        "_developer_full_name_reply": lambda: "Gus",
        "hard_answer": lambda user_text: "",
        "_developer_profile_reply": lambda turns=None, user_text="": "profile",
        "_session_recap_reply": lambda turns, user_text: "recap",
    }


class TestNovaSupervisorFlow(unittest.TestCase):
    def test_execute_registered_supervisor_rule_from_runtime_dispatches_rules_list(self):
        handled, reply, next_state = nova_supervisor_flow.execute_registered_supervisor_rule_from_runtime(
            {"action": "rules_list"},
            "what are the rules?",
            None,
            runtime_scope=_runtime_scope(),
        )

        self.assertTrue(handled)
        self.assertEqual(reply, "Rules go here.")
        self.assertIsNone(next_state)

    def test_handle_supervisor_intent_from_runtime_dispatches_capability_query(self):
        handled, reply, next_state, effects = nova_supervisor_flow.handle_supervisor_intent_from_runtime(
            {"intent": "capability_query"},
            "what can you do?",
            runtime_scope=_runtime_scope(),
        )

        self.assertTrue(handled)
        self.assertEqual(reply, "capabilities")
        self.assertIsNone(next_state)
        self.assertIsNone(effects)


if __name__ == "__main__":
    unittest.main()
