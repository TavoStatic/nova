import unittest

from services.nova_turn_direction import analyze_routing_text
from services.nova_turn_direction import determine_turn_direction
from services.nova_turn_direction import is_explicit_command_like


class TestNovaTurnDirection(unittest.TestCase):
    def test_analyze_routing_text_prefers_supervisor_rewrite(self):
        effective, reason = analyze_routing_text(
            [("user", "do you remember me?")],
            "keep trying",
            evaluate_rules_fn=lambda text, **kwargs: {
                "rewrite_text": "do you remember me?",
                "analysis_reason": "reflective_retry_prior_question",
            },
        )

        self.assertEqual(effective, "do you remember me?")
        self.assertEqual(reason, "reflective_retry_prior_question")

    def test_determine_turn_direction_marks_identity_query_and_bypasses_pattern_routes(self):
        result = determine_turn_direction(
            [("user", "what else do you know about me?")],
            "what else do you know about me?",
            analyze_routing_text_fn=lambda turns, text: (text, ""),
            classify_turn_acts_fn=lambda *args, **kwargs: set(),
            extract_memory_teach_text_fn=lambda text: "",
            is_identity_or_developer_query_fn=lambda text: "remember me" in text.lower() or "what else do you know about me" in text.lower(),
            is_developer_color_lookup_request_fn=lambda text: False,
            is_developer_bilingual_request_fn=lambda text: False,
            is_color_lookup_request_fn=lambda text: False,
            build_greeting_reply_fn=lambda *args, **kwargs: "",
            is_explicit_command_like_fn=is_explicit_command_like,
        )

        self.assertEqual(result.get("primary"), "identity_query")
        self.assertTrue(result.get("identity_focused"))
        self.assertTrue(result.get("bypass_pattern_routes"))

    def test_determine_turn_direction_keeps_explicit_commands_pattern_routable(self):
        result = determine_turn_direction(
            [],
            "web search weather in brownsville",
            analyze_routing_text_fn=lambda turns, text: (text, ""),
            classify_turn_acts_fn=lambda *args, **kwargs: {"command"},
            extract_memory_teach_text_fn=lambda text: "",
            is_identity_or_developer_query_fn=lambda text: False,
            is_developer_color_lookup_request_fn=lambda text: False,
            is_developer_bilingual_request_fn=lambda text: False,
            is_color_lookup_request_fn=lambda text: False,
            build_greeting_reply_fn=lambda *args, **kwargs: "",
            is_explicit_command_like_fn=is_explicit_command_like,
        )

        self.assertEqual(result.get("primary"), "explicit_command")
        self.assertFalse(result.get("bypass_pattern_routes"))


if __name__ == "__main__":
    unittest.main()