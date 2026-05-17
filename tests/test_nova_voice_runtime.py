import unittest

from services import nova_voice_runtime


class _FakeTTS:
    def __init__(self):
        self.spoken = []

    def say(self, text):
        self.spoken.append(text)


class TestNovaVoiceRuntime(unittest.TestCase):
    def test_ensure_voice_deps_updates_runtime_scope_from_importer(self):
        runtime_scope = {
            "VOICE_OK": False,
            "VOICE_READY": False,
            "VOICE_IMPORT_ERR": "",
            "sd": None,
            "wav": None,
            "WhisperModel": None,
        }

        ok = nova_voice_runtime.ensure_voice_deps(
            runtime_scope,
            import_voice_modules_fn=lambda: ("sd_mod", "wav_mod", "whisper_mod"),
        )

        self.assertTrue(ok)
        self.assertTrue(runtime_scope["VOICE_READY"])
        self.assertEqual(runtime_scope["sd"], "sd_mod")
        self.assertEqual(runtime_scope["wav"], "wav_mod")
        self.assertEqual(runtime_scope["WhisperModel"], "whisper_mod")

    def test_voice_status_payload_reports_unrequested_voice_without_failure(self):
        payload = nova_voice_runtime.voice_status_payload(
            {
                "VOICE_OK": False,
                "VOICE_READY": False,
                "VOICE_IMPORT_ERR": "",
                "sd": None,
                "wav": None,
                "WhisperModel": None,
                "SAMPLE_RATE": 16000,
                "CHANNELS": 1,
            }
        )

        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("status"), "not_initialized")
        self.assertFalse(payload.get("requested"))
        self.assertEqual(payload.get("sample_rate"), 16000)
        self.assertEqual(payload.get("channels"), 1)

    def test_voice_status_payload_reports_requested_dependency_failure(self):
        runtime_scope = {
            "VOICE_OK": False,
            "VOICE_READY": True,
            "VOICE_IMPORT_ERR": "No module named 'sounddevice'",
            "sd": None,
            "wav": None,
            "WhisperModel": None,
        }

        payload = nova_voice_runtime.voice_status_payload(runtime_scope)

        self.assertFalse(payload.get("ok"))
        self.assertEqual(payload.get("status"), "disabled")
        self.assertTrue(payload.get("requested"))
        self.assertEqual(payload.get("import_error"), "No module named 'sounddevice'")
        self.assertFalse(payload.get("sounddevice_available"))

    def test_speak_chunked_groups_sentences_under_max_len(self):
        tts = _FakeTTS()

        nova_voice_runtime.speak_chunked(
            tts,
            "First sentence. Second sentence is longer. Third one.",
            max_len=30,
        )

        self.assertGreaterEqual(len(tts.spoken), 2)
        self.assertEqual(tts.spoken[0], "First sentence.")


if __name__ == "__main__":
    unittest.main()
