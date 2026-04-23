"""
Authoritative behavior tests — identity answer service.

Tests what Nova says in response to identity questions.
Does NOT inspect source code or depend on internal function names.
"""
from __future__ import annotations

import unittest

from services.nova_identity_answers import deterministic_identity_answer


def _answer(
    user_text: str,
    *,
    assistant_name: str = "Nova",
    developer_name: str = "Gustavo",
    developer_nickname: str = "Gus",
    active_user_raw: str = "gus",
    is_developer: bool = True,
    name_origin_story: str = "",
    recent_learned: list[str] | None = None,
    color_preferences: list[str] | None = None,
    memory_prefix: str = "",
) -> str | None:
    return deterministic_identity_answer(
        user_text,
        assistant_name=assistant_name,
        developer_name=developer_name,
        developer_nickname=developer_nickname,
        active_user_raw=active_user_raw,
        speaker_matches_developer_fn=lambda: is_developer,
        get_name_origin_story_fn=lambda: name_origin_story,
        prefix_from_earlier_memory_fn=lambda _q: memory_prefix,
        extract_developer_color_preferences_from_memory_fn=lambda: (color_preferences or []),
        mem_get_recent_learned_fn=lambda _n: (recent_learned or []),
    )


class TestIdentityAnswerBehavior(unittest.TestCase):

    # --- Name queries ---

    def test_what_is_your_name_returns_assistant_name(self):
        reply = _answer("what is your name")
        self.assertIsNotNone(reply)
        self.assertIn("Nova", reply)

    def test_whats_your_name_contraction_returns_assistant_name(self):
        reply = _answer("what's your name")
        self.assertIn("Nova", reply)

    def test_who_are_you_returns_assistant_name(self):
        reply = _answer("who are you")
        self.assertIn("Nova", reply)

    # --- Developer recognition ---

    def test_do_you_remember_me_developer_returns_full_name(self):
        reply = _answer("do you remember me", is_developer=True)
        self.assertIsNotNone(reply)
        self.assertIn("Gustavo", reply)

    def test_do_you_remember_me_unknown_user_returns_uncertain(self):
        reply = _answer("do you remember me", is_developer=False, active_user_raw="")
        self.assertIsNotNone(reply)
        self.assertIn("not", reply.lower())

    def test_what_is_my_name_developer_returns_developer_name(self):
        reply = _answer("what is my name", is_developer=True)
        self.assertIn("Gustavo", reply)

    def test_what_is_my_name_unknown_returns_uncertain(self):
        reply = _answer("what is my name", is_developer=False, active_user_raw="")
        self.assertIsNotNone(reply)
        # Should not hallucinate a name
        self.assertNotIn("Gustavo", reply)

    # --- Name origin ---

    def test_why_are_you_called_nova_with_story_includes_story(self):
        reply = _answer(
            "why are you called nova",
            name_origin_story="Nova stands for New Operational Virtual Assistant.",
        )
        self.assertIsNotNone(reply)
        self.assertIn("Nova", reply)

    def test_why_are_you_called_nova_no_story_returns_teach_prompt(self):
        reply = _answer("why are you called nova", name_origin_story="")
        self.assertIsNotNone(reply)
        self.assertIn("remember", reply.lower())

    # --- Non-identity queries return None ---

    def test_unrelated_query_returns_none(self):
        reply = _answer("what is the weather today")
        self.assertIsNone(reply)

    def test_math_query_returns_none(self):
        reply = _answer("what is 2 plus 2")
        self.assertIsNone(reply)

    # --- Custom assistant name ---

    def test_custom_assistant_name_is_used(self):
        reply = _answer("what is your name", assistant_name="Aria")
        self.assertIn("Aria", reply)
        self.assertNotIn("Nova", reply)


if __name__ == "__main__":
    unittest.main()
