import unittest

from services import nova_voice_runtime


class _FakeTTS:
    def __init__(self):
        self.spoken = []

    def say(self, text):
        self.spoken.append(text)


class _FakeWav:
    @staticmethod
    def write(buf, sample_rate, audio):
        _ = (buf, sample_rate, audio)


class _FakeSegment:
    def __init__(self, text, no_speech_prob=None):
        self.text = text
        self.no_speech_prob = no_speech_prob


class _FakeModel:
    def __init__(self, segments):
        self._segments = list(segments)

    def transcribe(self, _buf, **_kwargs):
        return iter(self._segments), {}


class _FakeSoundDevice:
    class _Default:
        def __init__(self, device):
            self.device = device

    def __init__(self, devices, default_device=(0, 0)):
        self._devices = list(devices)
        self.default = self._Default(default_device)
        self.last_rec_kwargs = None
        self.rec_calls = 0

    def query_devices(self):
        return list(self._devices)

    def rec(self, *args, **kwargs):
        self.rec_calls += 1
        self.last_rec_kwargs = kwargs
        return kwargs.get("_chunk_return", "audio")

    def wait(self):
        return None


class _FallbackFakeSoundDevice(_FakeSoundDevice):
    def __init__(self, devices, fail_device_indexes, default_device=(0, 0)):
        super().__init__(devices, default_device)
        self._fail_device_indexes = set(int(x) for x in fail_device_indexes)

    def rec(self, *args, **kwargs):
        self.rec_calls += 1
        self.last_rec_kwargs = kwargs
        device = int(kwargs.get("device", -1))
        if device in self._fail_device_indexes:
            raise RuntimeError(f"Error opening InputStream: Invalid device [{device}]")
        return "audio"


class _SilentAdaptiveFakeSoundDevice(_FakeSoundDevice):
    def __init__(self, devices, default_device=(0, 0)):
        super().__init__(devices, default_device)
        import numpy as np

        self._np = np

    def rec(self, *args, **kwargs):
        self.rec_calls += 1
        self.last_rec_kwargs = kwargs
        frames = int(args[0]) if args else 3200
        channels = int(kwargs.get("channels", 1) or 1)
        return self._np.zeros((frames, channels), dtype=self._np.int16)


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

    def test_record_seconds_uses_named_preferred_input_device(self):
        fake_sd = _FakeSoundDevice(
            devices=[
                {"name": "NVIDIA Virtual Audio Device", "max_input_channels": 2},
                {"name": "USB Audio Device Microphone", "max_input_channels": 1},
            ],
            default_device=(0, 0),
        )
        runtime_scope = {
            "sd": fake_sd,
            "VOICE_IMPORT_ERR": "",
            "np": None,
        }

        audio = nova_voice_runtime.record_seconds(
            2,
            ensure_voice_deps_fn=lambda: True,
            runtime_scope=runtime_scope,
            sample_rate=16000,
            channels=1,
            preferred_input_device="usb audio",
            print_fn=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(audio, "audio")
        self.assertEqual(fake_sd.last_rec_kwargs.get("device"), 1)
        self.assertEqual(runtime_scope.get("VOICE_INPUT_DEVICE_INDEX"), 1)
        self.assertIn("USB Audio Device", str(runtime_scope.get("VOICE_INPUT_DEVICE_NAME") or ""))

    def test_record_seconds_auto_avoids_virtual_default_device(self):
        fake_sd = _FakeSoundDevice(
            devices=[
                {"name": "NVIDIA Virtual Audio Device", "max_input_channels": 2},
                {"name": "Realtek Microphone", "max_input_channels": 1},
            ],
            default_device=(0, 0),
        )
        runtime_scope = {
            "sd": fake_sd,
            "VOICE_IMPORT_ERR": "",
            "np": None,
        }

        _ = nova_voice_runtime.record_seconds(
            2,
            ensure_voice_deps_fn=lambda: True,
            runtime_scope=runtime_scope,
            sample_rate=16000,
            channels=1,
            preferred_input_device="auto",
            print_fn=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(fake_sd.last_rec_kwargs.get("device"), 1)

    def test_record_seconds_auto_deprioritizes_mic_array_vs_dedicated_mic(self):
        fake_sd = _FakeSoundDevice(
            devices=[
                {"name": "Microphone Array (Realtek)", "max_input_channels": 4},
                {"name": "Microphone (Realtek HD Audio Mic input)", "max_input_channels": 2},
            ],
            default_device=(0, 0),
        )
        runtime_scope = {
            "sd": fake_sd,
            "VOICE_IMPORT_ERR": "",
            "np": None,
        }

        _ = nova_voice_runtime.record_seconds(
            2,
            ensure_voice_deps_fn=lambda: True,
            runtime_scope=runtime_scope,
            sample_rate=16000,
            channels=1,
            preferred_input_device="auto",
            print_fn=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(fake_sd.last_rec_kwargs.get("device"), 1)

    def test_record_seconds_uses_device_native_capture_channels(self):
        fake_sd = _FakeSoundDevice(
            devices=[
                {"name": "Microphone Array (Realtek)", "max_input_channels": 4},
            ],
            default_device=(0, 0),
        )
        runtime_scope = {
            "sd": fake_sd,
            "VOICE_IMPORT_ERR": "",
            "np": None,
        }

        _ = nova_voice_runtime.record_seconds(
            2,
            ensure_voice_deps_fn=lambda: True,
            runtime_scope=runtime_scope,
            sample_rate=16000,
            channels=1,
            preferred_input_device="auto",
            print_fn=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(int(fake_sd.last_rec_kwargs.get("channels") or 0), 4)

    def test_record_seconds_falls_back_when_selected_device_is_invalid(self):
        fake_sd = _FallbackFakeSoundDevice(
            devices=[
                {"name": "Headset (Bluetooth Microphone)", "max_input_channels": 1},
                {"name": "Microphone (Realtek HD Audio Mic input)", "max_input_channels": 2},
            ],
            fail_device_indexes={0},
            default_device=(0, 0),
        )
        runtime_scope = {
            "sd": fake_sd,
            "VOICE_IMPORT_ERR": "",
            "np": None,
        }

        audio = nova_voice_runtime.record_seconds(
            2,
            ensure_voice_deps_fn=lambda: True,
            runtime_scope=runtime_scope,
            sample_rate=16000,
            channels=1,
            preferred_input_device="auto",
            print_fn=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(audio, "audio")
        self.assertEqual(int(runtime_scope.get("VOICE_INPUT_DEVICE_INDEX") or -1), 1)
        self.assertEqual(int(runtime_scope.get("VOICE_WORKING_INPUT_DEVICE_INDEX") or -1), 1)

    def test_record_seconds_stops_after_silence_when_speech_detected(self):
        class _AdaptiveFakeSD(_FakeSoundDevice):
            def __init__(self, devices, default_device=(0, 0)):
                super().__init__(devices, default_device)
                import numpy as np

                self._np = np

            def rec(self, *args, **kwargs):
                self.rec_calls += 1
                self.last_rec_kwargs = kwargs
                frames = int(args[0]) if args else 3200
                # One loud chunk (speech), then repeated silence.
                if self.rec_calls == 1:
                    return self._np.full((frames, 1), 2000, dtype=self._np.int16)
                return self._np.zeros((frames, 1), dtype=self._np.int16)

        fake_sd = _AdaptiveFakeSD(
            devices=[
                {"name": "Microphone Array (Realtek)", "max_input_channels": 2},
            ],
            default_device=(0, 0),
        )

        runtime_scope = {
            "sd": fake_sd,
            "VOICE_IMPORT_ERR": "",
            "np": __import__("numpy"),
        }

        audio = nova_voice_runtime.record_seconds(
            10,
            ensure_voice_deps_fn=lambda: True,
            runtime_scope=runtime_scope,
            sample_rate=16000,
            channels=1,
            preferred_input_device="auto",
            print_fn=lambda *_args, **_kwargs: None,
        )

        self.assertTrue(hasattr(audio, "shape"))
        # Should stop early (after speech + trailing silence), not consume full 10s.
        self.assertLess(fake_sd.rec_calls, 15)

    def test_record_seconds_raises_clear_error_when_no_speech_detected(self):
        fake_sd = _SilentAdaptiveFakeSoundDevice(
            devices=[
                {"name": "Microphone (Realtek HD Audio Mic input)", "max_input_channels": 2},
            ],
            default_device=(0, 0),
        )
        runtime_scope = {
            "sd": fake_sd,
            "VOICE_IMPORT_ERR": "",
            "np": __import__("numpy"),
        }

        with self.assertRaises(RuntimeError) as ctx:
            nova_voice_runtime.record_seconds(
                3,
                ensure_voice_deps_fn=lambda: True,
                runtime_scope=runtime_scope,
                sample_rate=16000,
                channels=1,
                preferred_input_device="auto",
                print_fn=lambda *_args, **_kwargs: None,
            )

        self.assertIn("No speech was detected from the microphone", str(ctx.exception))
        self.assertIn("No speech was detected", str(runtime_scope.get("VOICE_LAST_CAPTURE_ERROR") or ""))

    def test_transcribe_raises_clear_error_for_no_speech_like_phrase(self):
        runtime_scope = {
            "wav": _FakeWav(),
            "VOICE_IMPORT_ERR": "",
        }
        model = _FakeModel([_FakeSegment("Thank you.", 0.96)])

        with self.assertRaises(RuntimeError) as ctx:
            nova_voice_runtime.transcribe(
                model,
                [0, 1200, -1600, 2500, -2100, 900],
                ensure_voice_deps_fn=lambda: True,
                runtime_scope=runtime_scope,
                sample_rate=16000,
            )

        self.assertIn("did not produce usable speech", str(ctx.exception))
        self.assertIn("did not produce usable speech", str(runtime_scope.get("VOICE_LAST_CAPTURE_ERROR") or ""))

    def test_transcribe_keeps_valid_speech(self):
        runtime_scope = {
            "wav": _FakeWav(),
            "VOICE_IMPORT_ERR": "",
        }
        model = _FakeModel([_FakeSegment("Open queue status please")])

        text = nova_voice_runtime.transcribe(
            model,
            [0, 1200, -1600, 2500, -2100, 900],
            ensure_voice_deps_fn=lambda: True,
            runtime_scope=runtime_scope,
            sample_rate=16000,
        )

        self.assertEqual(text, "Open queue status please")


if __name__ == "__main__":
    unittest.main()
