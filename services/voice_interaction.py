from __future__ import annotations

try:
    import pyttsx3 as _pyttsx3
except ImportError:  # pragma: no cover
    _pyttsx3 = None  # type: ignore[assignment]

try:
    from faster_whisper import WhisperModel as _WhisperModel
except ImportError:  # pragma: no cover
    _WhisperModel = None  # type: ignore[assignment]

import nova_core


class VoiceInteractionService:
    """Shared voice/chat runtime for CLI-style Nova entrypoints."""

    def __init__(self, *, speaker_factory=None, whisper_model_cls=None) -> None:
        self._speaker_factory = speaker_factory if speaker_factory is not None else (getattr(_pyttsx3, "init", None) if _pyttsx3 is not None else None)
        self._whisper_model_cls = whisper_model_cls if whisper_model_cls is not None else _WhisperModel

    def whisper_size(self) -> str:
        return str(nova_core.whisper_size() or "small").strip() or "small"

    def load_whisper(self, *, device: str = "cpu", compute_type: str = "int8", size: str | None = None):
        model_size = str(size or self.whisper_size()).strip() or "small"
        return self._whisper_model_cls(model_size, device=device, compute_type=compute_type)

    def record_seconds(self, seconds: int = 6):
        return nova_core.record_seconds(seconds)

    def transcribe(self, model, audio_int16):
        return nova_core.transcribe(model, audio_int16)

    def chat(
        self,
        text: str,
        *,
        session_id: str = "",
        user_id: str = "",
    ) -> str:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return "Okay."

        effective_session_id = str(session_id or "voice-session").strip() or "voice-session"
        try:
            import nova_http

            return nova_http.process_chat(effective_session_id, normalized_text, user_id=user_id)
        except Exception:
            return nova_core.ollama_chat(
                normalized_text,
                retrieved_context="",
                language_mix_spanish_pct=0,
            )

    def speak(self, text: str, *, rate: int = 175) -> None:
        engine = self._speaker_factory()
        engine.setProperty("rate", int(rate))
        engine.say(text)
        engine.runAndWait()


VOICE_INTERACTION_SERVICE = VoiceInteractionService()