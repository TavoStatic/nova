import unittest

import nova_core


class TestGreetingLogic(unittest.TestCase):
    def test_greeting_with_how_are_you_is_warmer(self):
        out = nova_core._build_greeting_reply("Hi nova!! how are you doing today ?", active_user="Gus")
        self.assertEqual(out, "Hey Gus. I'm doing good today. What's going on?")

    def test_quick_smalltalk_ignores_synthetic_runner_user(self):
        out = nova_core._quick_smalltalk_reply("hi nova", active_user="runner")
        self.assertEqual(out, "Hello.")

    def test_quick_smalltalk_ready_to_work_reply(self):
        out = nova_core._quick_smalltalk_reply("ready to get to work?")
        self.assertEqual(out, "Ready when you are. What's the task for today?")

    def test_non_greeting_returns_none(self):
        out = nova_core._build_greeting_reply("list the domains", active_user="Gus")
        self.assertIsNone(out)

    def test_greeting_with_followup_request_does_not_short_circuit(self):
        out = nova_core._build_greeting_reply(
            "Hi nova this is Gus.. can you give me the weather for your current physical location?",
            active_user="Gus",
        )
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
