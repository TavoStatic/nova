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
