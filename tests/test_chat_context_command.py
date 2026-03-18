import unittest

import nova_core


class TestChatContextCommand(unittest.TestCase):
    def test_chat_context_returns_rendered_turns(self):
        turns = [
            ("user", "hello"),
            ("assistant", "Hi there"),
            ("user", "show chat context"),
        ]
        out = nova_core.handle_commands("chat context", session_turns=turns)
        self.assertIn("Current chat context:", out)
        self.assertIn("User: hello", out)
        self.assertIn("Assistant: Hi there", out)

    def test_chat_context_empty_session(self):
        out = nova_core.handle_commands("chat context", session_turns=[])
        self.assertEqual(out, "No chat context is available yet in this session.")


if __name__ == "__main__":
    unittest.main()
