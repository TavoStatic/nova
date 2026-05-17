from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

try:
    import pyttsx3 as _pyttsx3
except ImportError:  # pragma: no cover
    _pyttsx3 = None  # type: ignore[assignment]

try:
    from faster_whisper import WhisperModel as _WhisperModel
except ImportError:  # pragma: no cover
    _WhisperModel = None  # type: ignore[assignment]

from services.nova_runtime_context import POLICY_PATH


def _policy_whisper_size(policy_path: Path = POLICY_PATH) -> str:
    try:
        payload = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
    return str(models.get("stt_size") or "small").strip() or "small"


def _voice_runtime_not_bound(*_args: Any, **_kwargs: Any):
    raise RuntimeError("voice_runtime_not_bound")


class VoiceInteractionService:
    """Shared voice/chat runtime for CLI-style Nova entrypoints."""

    def __init__(
        self,
        *,
        speaker_factory=None,
        whisper_model_cls=None,
        whisper_size_fn: Callable[[], str] | None = None,
        record_seconds_fn: Callable[[int], Any] | None = None,
        transcribe_fn: Callable[[Any, Any], str] | None = None,
        chat_fn: Callable[[str, str, str], str] | None = None,
        fallback_chat_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._speaker_factory = speaker_factory if speaker_factory is not None else (getattr(_pyttsx3, "init", None) if _pyttsx3 is not None else None)
        self._whisper_model_cls = whisper_model_cls if whisper_model_cls is not None else _WhisperModel
        self._whisper_size_fn = whisper_size_fn or _policy_whisper_size
        self._record_seconds_fn = record_seconds_fn or _voice_runtime_not_bound
        self._transcribe_fn = transcribe_fn or _voice_runtime_not_bound
        self._chat_fn = chat_fn
        self._fallback_chat_fn = fallback_chat_fn

    def whisper_size(self) -> str:
        return str(self._whisper_size_fn() or "small").strip() or "small"

    def load_whisper(self, *, device: str = "cpu", compute_type: str = "int8", size: str | None = None):
        if self._whisper_model_cls is None:
            raise RuntimeError("whisper_model_not_available")
        model_size = str(size or self.whisper_size()).strip() or "small"
        return self._whisper_model_cls(model_size, device=device, compute_type=compute_type)

    def record_seconds(self, seconds: int = 6):
        return self._record_seconds_fn(int(seconds))

    def transcribe(self, model, audio_int16):
        return self._transcribe_fn(model, audio_int16)

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
            if self._chat_fn is None:
                raise RuntimeError("voice_chat_not_bound")
            return self._chat_fn(effective_session_id, normalized_text, str(user_id or ""))
        except Exception:
            if self._fallback_chat_fn is not None:
                return self._fallback_chat_fn(normalized_text)
            return "(error: LLM service unavailable)"

    def speak(self, text: str, *, rate: int = 175) -> None:
        if self._speaker_factory is None:
            raise RuntimeError("speaker_not_available")
        engine = self._speaker_factory()
        engine.setProperty("rate", int(rate))
        engine.say(text)
        engine.runAndWait()


VOICE_INTERACTION_SERVICE = VoiceInteractionService()
