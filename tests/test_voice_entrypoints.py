import unittest
from unittest import mock

import run
import voice


class TestVoiceEntrypoints(unittest.TestCase):
    def test_run_ask_nova_uses_run_cli_session(self):
        with mock.patch.object(run.VOICE_INTERACTION_SERVICE, "chat", return_value="reply") as chat_mock:
            reply = run.ask_nova("hello")

        self.assertEqual(reply, "reply")
        chat_mock.assert_called_once_with("hello", session_id="run-cli")

    def test_voice_ask_nova_uses_voice_cli_session(self):
        with mock.patch.object(voice.VOICE_INTERACTION_SERVICE, "chat", return_value="reply") as chat_mock:
            reply = voice.ask_nova("hello")

        self.assertEqual(reply, "reply")
        chat_mock.assert_called_once_with("hello", session_id="voice-cli")


if __name__ == "__main__":
    unittest.main()