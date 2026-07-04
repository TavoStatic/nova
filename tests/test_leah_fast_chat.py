from __future__ import annotations

import unittest

from services.leah_fast_chat import leah_fast_chat_enabled


class TestLeahFastChat(unittest.TestCase):
    def test_enabled_for_http_when_policy_flag_set(self) -> None:
        policy = {"layers": {"leah": {"fast_chat": True}}}
        self.assertTrue(leah_fast_chat_enabled(policy, input_source="http"))

    def test_disabled_for_cli_even_when_flag_set(self) -> None:
        policy = {"layers": {"leah": {"fast_chat": True}}}
        self.assertFalse(leah_fast_chat_enabled(policy, input_source="typed"))

    def test_disabled_when_flag_missing(self) -> None:
        policy = {"layers": {"leah": {"mode": "active"}}}
        self.assertFalse(leah_fast_chat_enabled(policy, input_source="http"))


if __name__ == "__main__":
    unittest.main()