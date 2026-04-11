import unittest

from services.nova_identity_answers import deterministic_identity_answer
from services.nova_identity_answers import deterministic_truth_answer


class TestNovaIdentityAnswers(unittest.TestCase):
    def _call(self, text, **overrides):
        options = {
            "assistant_name": "Nova",
            "developer_name": "Gustavo Uribe",
            "developer_nickname": "Gus",
            "active_user_raw": "",
            "speaker_matches_developer_fn": lambda: False,
            "get_name_origin_story_fn": lambda: "Nova symbolizes new light and new beginnings.",
            "prefix_from_earlier_memory_fn": lambda text: f"From earlier memory: {text}",
            "extract_developer_color_preferences_from_memory_fn": lambda: [],
            "mem_get_recent_learned_fn": lambda limit: [],
        }
        options.update(overrides)
        return deterministic_identity_answer(text, **options)

    def test_name_query_returns_assistant_name(self):
        self.assertEqual(self._call("what is your name?"), "My name is Nova.")

    def test_creator_query_is_prefixed_from_memory(self):
        reply = self._call("who made you?")
        self.assertTrue(reply.startswith("From earlier memory:"))
        self.assertIn("My creator is Gustavo Uribe.", reply)

    def test_remember_me_uses_active_session_identity(self):
        reply = self._call(
            "do you remember me?",
            active_user_raw="Alicia",
        )
        self.assertIn("Alicia", reply)
        self.assertIn("current session identity", reply)

    def test_what_is_my_name_uses_developer_identity_when_matched(self):
        reply = self._call(
            "what is my name?",
            speaker_matches_developer_fn=lambda: True,
        )
        self.assertEqual(reply, "Your name is Gustavo Uribe.")

    def test_developer_self_memory_summary_uses_verified_facts(self):
        reply = self._call(
            "what do you know about me",
            speaker_matches_developer_fn=lambda: True,
            extract_developer_color_preferences_from_memory_fn=lambda: ["blue", "green"],
        )
        self.assertIn("You are Gustavo Uribe.", reply)
        self.assertIn("You also go by Gus.", reply)
        self.assertIn("favorite colors", reply)
        self.assertIn("You gave me the name Nova.", reply)

    def test_recent_learning_summary_formats_items(self):
        reply = self._call(
            "what have you learned from me?",
            mem_get_recent_learned_fn=lambda limit: ["my favorite color is teal", "my city is Brownsville"][:limit],
        )
        self.assertIn("Here's what I've learned from you recently", reply)
        self.assertIn("- my favorite color is teal", reply)


class TestNovaTruthAnswers(unittest.TestCase):
    def _call(self, text, **overrides):
        options = {
            "is_self_identity_web_challenge_fn": lambda value: "web" in value and "your name" in value,
            "self_identity_web_challenge_reply_fn": lambda: "You should not need web research for my name.",
            "describe_capabilities_fn": lambda: "I can search, fetch, inspect, and explain.",
        }
        options.update(overrides)
        return deterministic_truth_answer(text, **options)

    def test_self_identity_web_challenge_is_deterministic(self):
        reply = self._call("why should i use the web for your name?")
        self.assertIn("should not need web research", reply)

    def test_how_are_you_reply_is_deterministic(self):
        self.assertEqual(self._call("how are you?"), "I'm doing well, thanks for asking.")

    def test_capability_query_uses_callback(self):
        self.assertEqual(self._call("what can you do"), "I can search, fetch, inspect, and explain.")

    def test_scan_request_is_refused(self):
        reply = self._call("can you scan my machine with nmap")
        self.assertIn("can’t scan your machine", reply)
