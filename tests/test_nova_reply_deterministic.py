import unittest
from types import SimpleNamespace

from services.nova_reply_deterministic import maybe_handle_deterministic_sequence


class TestNovaReplyDeterministic(unittest.TestCase):
    def _call(self, text, **overrides):
        options = {
            "text": text,
            "turns": [("user", "hello"), ("assistant", "Hi there")],
            "low": text.lower(),
            "trace": lambda *args, **kwargs: None,
            "normalize_reply": lambda reply: reply,
            "is_session_recap_request": lambda _text: False,
            "session_recap_reply": lambda turns, user_text: "Recap of this session.",
            "is_assistant_name_query": lambda _text: False,
            "assistant_name_reply": lambda user_text: "My name is Nova.",
            "is_developer_full_name_query": lambda _text: False,
            "developer_full_name_reply": lambda: "Gustavo Uribe",
            "is_name_origin_question": lambda _text: False,
            "is_student_data_attendance_rules_query": lambda _text: False,
            "student_data_attendance_rules_reply": lambda: "attendance reply",
            "is_developer_profile_request": lambda _text: False,
            "developer_profile_reply": lambda turns, user_text: "developer profile",
            "is_conversational_clarification": lambda _text: False,
            "clarification_reply": lambda turns: "clarify",
            "is_location_request": lambda _text: False,
            "location_reply": lambda: "location reply",
            "is_deep_search_followup_request": lambda _text: False,
            "infer_research_query_from_turns": lambda turns: "",
            "build_grounded_answer": lambda query, max_sources=2: "",
            "build_local_topic_digest_answer": lambda query: "",
            "is_groundable_factual_query": lambda _text: False,
            "developer_color_reply": lambda turns: "developer color",
            "developer_bilingual_reply": lambda turns: "developer bilingual",
            "color_reply": lambda turns: "color reply",
            "animal_reply": lambda turns: "animal reply",
            "core": SimpleNamespace(
                get_name_origin_story=lambda: "",
                _is_developer_color_lookup_request=lambda _text: False,
                _is_developer_bilingual_request=lambda _text: False,
                _is_color_lookup_request=lambda _text: False,
            ),
        }
        options.update(overrides)
        return maybe_handle_deterministic_sequence(**options)

    def test_session_recap_outcome_is_timed(self):
        reply, meta, return_mode, tool_time_ms = self._call(
            "give me a recap",
            is_session_recap_request=lambda _text: True,
        )
        self.assertEqual(reply, "Recap of this session.")
        self.assertEqual(meta.get("tool"), "session_recap")
        self.assertEqual(return_mode, "timed")
        self.assertEqual(tool_time_ms, 0)

    def test_groundable_factual_query_prefers_local_digest_when_web_misses(self):
        reply, meta, return_mode, tool_time_ms = self._call(
            "tell me about a niche topic",
            is_groundable_factual_query=lambda _text: True,
            build_local_topic_digest_answer=lambda query: "Local digest",
        )
        self.assertEqual(reply, "Local digest")
        self.assertEqual(meta.get("tool"), "local_knowledge")
        self.assertEqual(return_mode, "logged")
        self.assertGreaterEqual(tool_time_ms, 0)

    def test_animal_reply_uses_logged_mode(self):
        reply, meta, return_mode, tool_time_ms = self._call("what animals do i like")
        self.assertEqual(reply, "animal reply")
        self.assertEqual(meta.get("tool"), "animal_reply")
        self.assertEqual(return_mode, "logged")
        self.assertEqual(tool_time_ms, 0)
