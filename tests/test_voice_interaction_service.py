import unittest
from unittest import mock

from services.voice_interaction import VoiceInteractionService


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def setProperty(self, name, value):
        self.calls.append(("setProperty", name, value))

    def say(self, text):
        self.calls.append(("say", text))

    def runAndWait(self):
        self.calls.append(("runAndWait",))


class TestVoiceInteractionService(unittest.TestCase):
    def test_load_whisper_uses_policy_size_by_default(self):
        created = []

        class _FakeWhisper:
            def __init__(self, size, device=None, compute_type=None):
                created.append((size, device, compute_type))

        service = VoiceInteractionService(speaker_factory=lambda: _FakeEngine(), whisper_model_cls=_FakeWhisper)

        with mock.patch("services.voice_interaction.nova_core.whisper_size", return_value="base"):
            service.load_whisper(device="cpu", compute_type="int8")

        self.assertEqual(created, [("base", "cpu", "int8")])

    def test_record_and_transcribe_delegate_to_nova_core(self):
        service = VoiceInteractionService(speaker_factory=lambda: _FakeEngine(), whisper_model_cls=object)

        with mock.patch("services.voice_interaction.nova_core.record_seconds", return_value="audio") as record_mock, \
            mock.patch("services.voice_interaction.nova_core.transcribe", return_value="hello") as transcribe_mock:
            audio = service.record_seconds(4)
            text = service.transcribe("model", "audio")

        self.assertEqual(audio, "audio")
        self.assertEqual(text, "hello")
        record_mock.assert_called_once_with(4)
        transcribe_mock.assert_called_once_with("model", "audio")

    def test_chat_uses_http_process_chat_by_default(self):
        service = VoiceInteractionService(speaker_factory=lambda: _FakeEngine(), whisper_model_cls=object)

        with mock.patch("nova_http.process_chat", return_value="reply") as chat_mock:
            reply = service.chat("hello", session_id="voice-test", user_id="runner")

        self.assertEqual(reply, "reply")
        chat_mock.assert_called_once_with("voice-test", "hello", user_id="runner")

    def test_chat_defaults_to_shared_voice_session_id(self):
        service = VoiceInteractionService(speaker_factory=lambda: _FakeEngine(), whisper_model_cls=object)

        with mock.patch("nova_http.process_chat", return_value="reply") as chat_mock:
            reply = service.chat("hello")

        self.assertEqual(reply, "reply")
        chat_mock.assert_called_once_with("voice-session", "hello", user_id="")

    def test_chat_falls_back_to_direct_llm_if_http_chat_raises(self):
        service = VoiceInteractionService(speaker_factory=lambda: _FakeEngine(), whisper_model_cls=object)

        with mock.patch("nova_http.process_chat", side_effect=RuntimeError("boom")), \
            mock.patch("services.voice_interaction.nova_core.ollama_chat", return_value="reply") as chat_mock:
            reply = service.chat("hello", session_id="voice-test")

        self.assertEqual(reply, "reply")
        chat_mock.assert_called_once_with("hello", retrieved_context="", language_mix_spanish_pct=0)

    def test_speak_uses_engine_factory(self):
        engine = _FakeEngine()
        service = VoiceInteractionService(speaker_factory=lambda: engine, whisper_model_cls=object)

        service.speak("hello", rate=180)

        self.assertEqual(
            engine.calls,
            [("setProperty", "rate", 180), ("say", "hello"), ("runAndWait",)],
        )


if __name__ == "__main__":
    unittest.main()