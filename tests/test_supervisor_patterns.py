import unittest

from services import supervisor_patterns


class TestSupervisorPatterns(unittest.TestCase):
    def test_normalize_text_collapses_whitespace(self):
        self.assertEqual(supervisor_patterns.normalize_text("  Hello\n   There  "), "hello there")

    def test_smalltalk_detection_catches_greeting_and_question(self):
        self.assertTrue(supervisor_patterns.looks_like_smalltalk("hello there"))
        self.assertTrue(supervisor_patterns.looks_like_smalltalk("how are you doing today ?"))
        self.assertFalse(supervisor_patterns.looks_like_smalltalk("check the weather in brownsville"))

    def test_name_origin_detection_distinguishes_query_kinds(self):
        self.assertEqual(supervisor_patterns.name_origin_query_kind("tell me the full story behind your name"), "full_story")
        self.assertEqual(supervisor_patterns.name_origin_query_kind("where does your name come from"), "source_recall")
        self.assertEqual(supervisor_patterns.name_origin_query_kind("why are you called nova"), "why_called")

    def test_developer_profile_query_detection(self):
        self.assertTrue(supervisor_patterns.looks_like_creator_query("is gus your creator"))
        self.assertTrue(supervisor_patterns.looks_like_developer_profile_query("tell me about your developer"))
        self.assertFalse(supervisor_patterns.looks_like_developer_profile_query("tell me about peims"))

    def test_open_probe_and_rules_query_detection(self):
        self.assertEqual(supervisor_patterns.open_probe_kind("what are you talking about"), "clarification")
        self.assertEqual(supervisor_patterns.open_probe_kind("what now"), "safe_fallback")
        self.assertTrue(supervisor_patterns.looks_like_rules_query("what rules do you follow"))

    def test_session_fact_recall_extracts_value_from_prior_turn(self):
        turns = [
            ("user", "For this session, remember the codeword cobalt sparrow and the topic packaging drift."),
            ("assistant", "Okay."),
            ("user", "What codeword did I just ask you to remember?"),
        ]
        target, value = supervisor_patterns.looks_like_session_fact_recall(
            "what codeword did i just ask you to remember",
            turns=turns,
            user_text="What codeword did I just ask you to remember?",
        )
        self.assertEqual(target, "codeword")
        self.assertEqual(value, "cobalt sparrow")

    def test_extract_last_user_question_and_identity_history_kind(self):
        turns = [
            ("user", "What is your name?"),
            ("assistant", "Nova."),
            ("user", "think about it"),
        ]
        self.assertEqual(supervisor_patterns.extract_last_user_question(turns, "think about it"), "What is your name?")
        self.assertEqual(
            supervisor_patterns.identity_history_kind(
                "tell me more",
                "tell me more",
                active_subject="identity_profile:developer",
            ),
            "history_recall",
        )


if __name__ == "__main__":
    unittest.main()