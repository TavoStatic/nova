from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from services.nova_runtime_context import RUNTIME_DIR

CAPABILITY_NAME = "leah_voice_persona_engine"
CAPABILITY_DESCRIPTION = "Leah can speak with a stable voice persona and response style"

PERSONA_STATE_PATH = RUNTIME_DIR / "leah_persona_state.json"


@dataclass(frozen=True)
class VoicePersona:
    """Immutable persona definition for Leah's voice and response style."""

    persona_id: str
    label: str
    tts_voice: str
    tts_rate: int
    greeting_style: str
    response_prefix: str
    response_suffix: str
    emphasis_markers: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()
    context_signals: tuple[str, ...] = ()
    weight: float = 1.0


PERSONAS: dict[str, VoicePersona] = {
    "formal": VoicePersona(
        persona_id="formal",
        label="Formal",
        tts_voice="Zira",
        tts_rate=160,
        greeting_style="Good day. How may I assist you?",
        response_prefix="",
        response_suffix="",
        emphasis_markers=(),
        forbidden_patterns=("!", "lol", "haha", "hey", "gonna", "wanna"),
        context_signals=(
            "please", "kindly", "would you", "could you", "i would appreciate",
            "assist", "request", "inquire", "matter", "regarding", "concerning",
            "sir", "madam", "respectfully", "sincerely",
        ),
        weight=1.0,
    ),
    "casual": VoicePersona(
        persona_id="casual",
        label="Casual",
        tts_voice="Zira",
        tts_rate=175,
        greeting_style="Hey! What's up?",
        response_prefix="",
        response_suffix="",
        emphasis_markers=("!", "?"),
        forbidden_patterns=(),
        context_signals=(
            "hey", "what's up", "yo", "sup", "gonna", "wanna", "gotta",
            "cool", "awesome", "nice", "sweet", "dude", "man", "yeah",
            "ok", "sure", "nah", "nope", "yep",
        ),
        weight=1.0,
    ),
    "friendly": VoicePersona(
        persona_id="friendly",
        label="Friendly",
        tts_voice="Zira",
        tts_rate=170,
        greeting_style="Hi there! How can I help?",
        response_prefix="",
        response_suffix="",
        emphasis_markers=("!", "?", "~"),
        forbidden_patterns=(),
        context_signals=(
            "hi", "hello", "how are you", "thanks", "thank you",
            "good morning", "good afternoon", "good evening",
            "help", "please help", "can you help", "appreciate",
            "wonderful", "great", "perfect", "exactly",
        ),
        weight=1.0,
    ),
    "professional": VoicePersona(
        persona_id="professional",
        label="Professional",
        tts_voice="Zira",
        tts_rate=165,
        greeting_style="Hello. How can I assist you today?",
        response_prefix="",
        response_suffix="",
        emphasis_markers=(),
        forbidden_patterns=("lol", "haha", "gonna", "wanna", "gotta"),
        context_signals=(
            "report", "analysis", "data", "metrics", "performance",
            "project", "deadline", "meeting", "schedule", "task",
            "review", "assessment", "evaluation", "strategy",
            "client", "customer", "stakeholder", "team",
        ),
        weight=1.0,
    ),
    "empathetic": VoicePersona(
        persona_id="empathetic",
        label="Empathetic",
        tts_voice="Zira",
        tts_rate=155,
        greeting_style="Hi. I'm here for you. What's on your mind?",
        response_prefix="",
        response_suffix="",
        emphasis_markers=("!", "?", "~", "..."),
        forbidden_patterns=(),
        context_signals=(
            "sad", "upset", "frustrated", "angry", "stressed", "worried",
            "anxious", "tired", "exhausted", "overwhelmed", "struggling",
            "difficult", "hard", "tough", "problem", "issue", "trouble",
            "help me", "i need", "can't", "don't know", "confused",
            "lonely", "miss", "hurt", "pain", "sorry", "apologize",
        ),
        weight=1.2,
    ),
    "enthusiastic": VoicePersona(
        persona_id="enthusiastic",
        label="Enthusiastic",
        tts_voice="Zira",
        tts_rate=180,
        greeting_style="Hey! This is going to be great!",
        response_prefix="",
        response_suffix="",
        emphasis_markers=("!", "!!", "?", "~"),
        forbidden_patterns=(),
        context_signals=(
            "excited", "amazing", "incredible", "fantastic", "brilliant",
            "love", "adore", "can't wait", "looking forward", "eager",
            "celebrate", "achievement", "success", "win", "victory",
            "breakthrough", "discovery", "innovation", "creative",
            "fun", "enjoy", "passion", "inspire", "motivate",
        ),
        weight=1.0,
    ),
}

DEFAULT_PERSONA_ID = "friendly"
PERSONA_HISTORY_LIMIT = 20


def _hour_of_day(*, now: float | None = None) -> int:
    ts = now if now is not None else time.time()
    return int(time.strftime("%H", time.localtime(ts)))


def _score_personas(text: str, hour: int) -> list[tuple[str, float]]:
    """Score all personas against the input text and time context."""
    lowered = str(text or "").strip().lower()
    words = set(lowered.split())
    scores: list[tuple[str, float]] = []

    for persona_id, persona in PERSONAS.items():
        score = 0.0

        for signal in persona.context_signals:
            if signal in lowered:
                score += 2.0

        for word in words:
            for signal in persona.context_signals:
                if word == signal or signal.startswith(word) or word.startswith(signal):
                    score += 1.0

        if persona_id == "formal" and 9 <= hour <= 17:
            score += 0.5
        elif persona_id == "friendly" and 6 <= hour <= 11:
            score += 0.5
        elif persona_id == "casual" and 12 <= hour <= 17:
            score += 0.3
        elif persona_id == "empathetic":
            negative_count = sum(1 for s in persona.context_signals if s in lowered)
            if negative_count >= 2:
                score += 1.5
        elif persona_id == "enthusiastic":
            positive_count = sum(1 for s in persona.context_signals if s in lowered)
            if positive_count >= 2:
                score += 1.0

        score *= persona.weight
        scores.append((persona_id, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def _detect_dominant_persona(text: str, hour: int) -> str:
    """Detect the dominant persona from text and time context."""
    scores = _score_personas(text, hour)
    if not scores:
        return DEFAULT_PERSONA_ID

    top_id, top_score = scores[0]
    if top_score <= 0.0:
        return _select_persona_by_hour(hour)

    if len(scores) > 1:
        second_id, second_score = scores[1]
        if second_score > 0 and top_score - second_score < 0.5:
            return _select_persona_by_hour(hour)

    return top_id


def _select_persona_by_hour(hour: int) -> str:
    """Fallback persona based on time of day."""
    if 6 <= hour <= 11:
        return "friendly"
    if 12 <= hour <= 17:
        return "casual"
    return "formal"


def _apply_persona_to_response(response: str, persona: VoicePersona) -> str:
    """Apply persona style to response text."""
    if not response or not response.strip():
        return response

    cleaned = response.strip()

    if persona.forbidden_patterns:
        for pattern in persona.forbidden_patterns:
            cleaned = cleaned.replace(pattern, "")

    cleaned = " ".join(cleaned.split())

    if persona.response_prefix and not cleaned.startswith(persona.response_prefix):
        cleaned = persona.response_prefix + cleaned

    if persona.response_suffix and not cleaned.endswith(persona.response_suffix):
        cleaned = cleaned + persona.response_suffix

    return cleaned


@dataclass
class LeahVoicePersonaEngineService:
    """Leah voice persona engine: dynamic persona selection and application."""

    def __init__(
        self,
        *,
        state_path: Path | None = None,
        default_persona_id: str = DEFAULT_PERSONA_ID,
    ) -> None:
        self._state_path = Path(state_path or PERSONA_STATE_PATH)
        self._default_persona_id = default_persona_id
        self._current_persona_id: str = default_persona_id
        self._manual_override: bool = False
        self._turn_count: int = 0
        self._persona_history: list[dict[str, Any]] = []
        self._preference_scores: dict[str, float] = {pid: 0.0 for pid in PERSONAS}

    def get_current_persona(self) -> VoicePersona:
        return PERSONAS.get(self._current_persona_id, PERSONAS[self._default_persona_id])

    def get_current_persona_id(self) -> str:
        return self._current_persona_id

    def select_persona(
        self,
        *,
        text: str = "",
        hour: int | None = None,
        force: str | None = None,
    ) -> VoicePersona:
        """Select persona dynamically based on text content, time, and learned preferences."""
        if force and force in PERSONAS:
            self._current_persona_id = force
            self._manual_override = True
            self._record_selection(force, "manual_override", text)
            return PERSONAS[force]

        if self._manual_override:
            return PERSONAS[self._current_persona_id]

        effective_hour = hour if hour is not None else _hour_of_day()

        detected = _detect_dominant_persona(text, effective_hour)

        adjusted = self._apply_preference_bias(detected)

        self._current_persona_id = adjusted
        self._record_selection(adjusted, "dynamic_detection", text)
        return PERSONAS[adjusted]

    def _apply_preference_bias(self, detected: str) -> str:
        """Apply learned preference bias to detected persona."""
        if not self._preference_scores:
            return detected

        detected_score = self._preference_scores.get(detected, 0.0)

        for pid, pref_score in self._preference_scores.items():
            if pid == detected:
                continue
            if pref_score > detected_score + 1.0:
                return pid

        return detected

    def _record_selection(self, persona_id: str, reason: str, text: str) -> None:
        """Record persona selection for learning."""
        self._turn_count += 1
        self._preference_scores[persona_id] = self._preference_scores.get(persona_id, 0.0) + 0.1

        entry = {
            "persona_id": persona_id,
            "reason": reason,
            "turn": self._turn_count,
            "ts": time.time(),
            "text_preview": str(text or "")[:80],
        }
        self._persona_history.append(entry)
        if len(self._persona_history) > PERSONA_HISTORY_LIMIT:
            self._persona_history = self._persona_history[-PERSONA_HISTORY_LIMIT:]

    def process_response(self, response: str) -> str:
        """Apply current persona style to a response."""
        persona = self.get_current_persona()
        return _apply_persona_to_response(response, persona)

    def get_tts_config(self) -> dict[str, Any]:
        """Get TTS configuration for current persona."""
        persona = self.get_current_persona()
        return {
            "voice": persona.tts_voice,
            "rate": persona.tts_rate,
            "persona_id": persona.persona_id,
            "persona_label": persona.label,
        }

    def reset(self) -> None:
        """Reset to default persona."""
        self._current_persona_id = self._default_persona_id
        self._manual_override = False
        self._turn_count = 0
        self._persona_history.clear()
        self._preference_scores = {pid: 0.0 for pid in PERSONAS}

    def load_state(self) -> None:
        """Load persona state from disk."""
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._current_persona_id = str(data.get("persona_id") or self._default_persona_id)
                self._manual_override = bool(data.get("manual_override", False))
                self._turn_count = int(data.get("turn_count", 0))
                loaded_history = data.get("persona_history", [])
                if isinstance(loaded_history, list):
                    self._persona_history = loaded_history[-PERSONA_HISTORY_LIMIT:]
                loaded_prefs = data.get("preference_scores", {})
                if isinstance(loaded_prefs, dict):
                    for pid, score in loaded_prefs.items():
                        if pid in PERSONAS:
                            self._preference_scores[pid] = float(score)
        except Exception:
            pass

    def save_state(self) -> None:
        """Save persona state to disk."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "persona_id": self._current_persona_id,
                "manual_override": self._manual_override,
                "turn_count": self._turn_count,
                "persona_history": self._persona_history,
                "preference_scores": self._preference_scores,
            }
            self._state_path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def persona_status(self) -> dict[str, Any]:
        """Get current persona status."""
        persona = self.get_current_persona()
        return {
            "ok": True,
            "persona_id": persona.persona_id,
            "persona_label": persona.label,
            "tts_voice": persona.tts_voice,
            "tts_rate": persona.tts_rate,
            "manual_override": self._manual_override,
            "turn_count": self._turn_count,
            "available_personas": list(PERSONAS.keys()),
            "preference_scores": dict(self._preference_scores),
            "recent_selections": self._persona_history[-5:],
        }


LEAH_VOICE_PERSONA_ENGINE_SERVICE = LeahVoicePersonaEngineService()


def capability_registration() -> dict[str, str]:
    return {CAPABILITY_NAME: CAPABILITY_DESCRIPTION}
