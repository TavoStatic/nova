from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from services.nova_runtime_context import RUNTIME_DIR
from services.type_utils import _as_dict, _as_float, _as_int, _text

CAPABILITY_NAME = "leah_emotional_state_model"
CAPABILITY_DESCRIPTION = "Leah can track a simple emotional state model for replies"

EMOTIONAL_STATE_PATH = RUNTIME_DIR / "leah_emotional_state.json"

BASELINE_VALENCE = 0.0
BASELINE_AROUSAL = 0.3
BASELINE_CONFIDENCE = 0.8
BASELINE_EMOTION = "neutral"


@dataclass
class EmotionalState:
    """Represents Leah's current emotional state dimensions and category."""

    valence: float = BASELINE_VALENCE  # -1.0 (negative) to +1.0 (positive)
    arousal: float = BASELINE_AROUSAL  # 0.0 (calm) to 1.0 (excited/alert)
    confidence: float = BASELINE_CONFIDENCE  # 0.0 (uncertain) to 1.0 (confident)
    primary_emotion: str = BASELINE_EMOTION
    intensity: float = 0.3
    updated_at: float = 0.0
    turn_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valence": round(float(self.valence), 3),
            "arousal": round(float(self.arousal), 3),
            "confidence": round(float(self.confidence), 3),
            "primary_emotion": str(self.primary_emotion),
            "intensity": round(float(self.intensity), 3),
            "updated_at": float(self.updated_at),
            "turn_count": int(self.turn_count),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmotionalState:
        if not isinstance(data, dict):
            return cls()
        return cls(
            valence=_clamp_range(_as_float(data.get("valence"), BASELINE_VALENCE), -1.0, 1.0),
            arousal=_clamp_range(_as_float(data.get("arousal"), BASELINE_AROUSAL), 0.0, 1.0),
            confidence=_clamp_range(_as_float(data.get("confidence"), BASELINE_CONFIDENCE), 0.0, 1.0),
            primary_emotion=_text(data.get("primary_emotion"), default=BASELINE_EMOTION),
            intensity=_clamp_range(_as_float(data.get("intensity"), 0.3), 0.0, 1.0),
            updated_at=_as_float(data.get("updated_at"), 0.0),
            turn_count=_as_int(data.get("turn_count"), 0),
        )


def _clamp_range(val: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, val))


# Signal keyword patterns
POSITIVE_SIGNALS = (
    "thanks", "thank you", "great", "good", "excellent", "awesome", "love",
    "perfect", "happy", "well done", "nice", "fantastic", "wonderful", "brilliant",
    "glad", "appreciate", "helpful", "working", "solved", "fixed",
)

NEGATIVE_SIGNALS = (
    "error", "fail", "failed", "failure", "broken", "bad", "wrong", "frustrated",
    "stuck", "issue", "bug", "problem", "slow", "annoyed", "terrible", "horrible",
    "difficult", "hard", "crash", "crashed", "hanging", "timeout",
)

CURIOSITY_SIGNALS = (
    "why", "how", "what if", "explain", "tell me", "wonder", "curious",
    "interesting", "explore", "discover", "understand", "learn",
)

FOCUS_SIGNALS = (
    "code", "function", "test", "refactor", "fix", "debug", "commit",
    "spec", "build", "architecture", "design", "module", "service",
    "syntax", "class", "type", "method", "variable", "script",
)


def derive_primary_emotion(valence: float, arousal: float, confidence: float) -> str:
    """Categorize primary emotion from (valence, arousal, confidence) values."""
    if valence < -0.25:
        if arousal > 0.5:
            return "empathetic"
        return "reassuring"
    elif valence > 0.25:
        if arousal > 0.5:
            return "encouraging"
        return "friendly"
    else:
        if arousal > 0.6:
            return "curious"
        elif confidence > 0.7:
            return "focused"
        return "thoughtful"


def derive_emotion_instruction(state: EmotionalState) -> str:
    """Generate Lehman prompt instruction corresponding to current emotional state."""
    emo = state.primary_emotion.lower()
    if emo == "empathetic":
        return "Emotional posture: Empathetic and supportive. Acknowledge frustration and offer clear, calm assistance."
    elif emo == "reassuring":
        return "Emotional posture: Reassuring and composed. Provide steady, reliable guidance."
    elif emo == "encouraging":
        return "Emotional posture: Encouraging and positive. Maintain optimistic, constructive momentum."
    elif emo == "friendly":
        return "Emotional posture: Friendly and warm. Keep interaction pleasant and helpful."
    elif emo == "curious":
        return "Emotional posture: Curious and engaged. Explore ideas and details with active interest."
    elif emo == "focused":
        return "Emotional posture: Focused and objective. Direct attention to technical execution and facts."
    elif emo == "thoughtful":
        return "Emotional posture: Thoughtful and balanced. Consider context carefully."
    return "Emotional posture: Balanced and clear."


class LeahEmotionalStateModelService:
    """Tracks Leah's emotional state transitions and modulates reply posture."""

    def __init__(self, state_path: Path = EMOTIONAL_STATE_PATH):
        self._state_path = state_path
        self._lock = threading.RLock()
        self._state = EmotionalState()
        self._enabled = True
        self.load_state()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def get_state(self) -> EmotionalState:
        with self._lock:
            return EmotionalState(**asdict(self._state))

    def get_instruction(self) -> str:
        with self._lock:
            if not self._enabled:
                return ""
            return derive_emotion_instruction(self._state)

    def analyze_text_signals(self, text: str) -> dict[str, float]:
        """Analyze text for sentiment/emotion signals returning delta shifts."""
        low = str(text or "").lower()
        if not low.strip():
            return {"valence_delta": 0.0, "arousal_delta": 0.0, "confidence_delta": 0.0}

        words = re.findall(r"\b[a-z_']+\b", low)
        word_set = set(words)

        pos_count = sum(1 for w in POSITIVE_SIGNALS if w in low or w in word_set)
        neg_count = sum(1 for w in NEGATIVE_SIGNALS if w in low or w in word_set)
        cur_count = sum(1 for w in CURIOSITY_SIGNALS if w in low or w in word_set)
        foc_count = sum(1 for w in FOCUS_SIGNALS if w in low or w in word_set)

        valence_delta = (pos_count * 0.25) - (neg_count * 0.35)
        arousal_delta = (pos_count * 0.1) + (neg_count * 0.2) + (cur_count * 0.15)
        confidence_delta = (foc_count * 0.1) - (neg_count * 0.1)

        return {
            "valence_delta": _clamp_range(valence_delta, -0.8, 0.8),
            "arousal_delta": _clamp_range(arousal_delta, -0.5, 0.8),
            "confidence_delta": _clamp_range(confidence_delta, -0.5, 0.5),
        }

    def update_state(self, text: str) -> EmotionalState:
        """Update emotional state from input text and apply decay/smoothing."""
        with self._lock:
            if not self._enabled:
                return self.get_state()

            deltas = self.analyze_text_signals(text)

            # Target values with deltas
            target_valence = _clamp_range(self._state.valence + deltas["valence_delta"], -1.0, 1.0)
            target_arousal = _clamp_range(self._state.arousal + deltas["arousal_delta"], 0.0, 1.0)
            target_confidence = _clamp_range(self._state.confidence + deltas["confidence_delta"], 0.0, 1.0)

            # Decay toward baseline if no deltas
            if deltas["valence_delta"] == 0.0:
                target_valence = self._state.valence * 0.85 + BASELINE_VALENCE * 0.15
            if deltas["arousal_delta"] == 0.0:
                target_arousal = self._state.arousal * 0.85 + BASELINE_AROUSAL * 0.15
            if deltas["confidence_delta"] == 0.0:
                target_confidence = self._state.confidence * 0.85 + BASELINE_CONFIDENCE * 0.15

            new_valence = _clamp_range((self._state.valence * 0.6) + (target_valence * 0.4), -1.0, 1.0)
            new_arousal = _clamp_range((self._state.arousal * 0.6) + (target_arousal * 0.4), 0.0, 1.0)
            new_confidence = _clamp_range((self._state.confidence * 0.6) + (target_confidence * 0.4), 0.0, 1.0)

            primary_emotion = derive_primary_emotion(new_valence, new_arousal, new_confidence)
            intensity = _clamp_range(abs(new_valence) * 0.5 + new_arousal * 0.5, 0.0, 1.0)

            self._state = EmotionalState(
                valence=new_valence,
                arousal=new_arousal,
                confidence=new_confidence,
                primary_emotion=primary_emotion,
                intensity=intensity,
                updated_at=time.time(),
                turn_count=self._state.turn_count + 1,
            )

            self._sync_cognitive_workspace()
            self.save_state()
            return self.get_state()

    def _sync_cognitive_workspace(self) -> None:
        """Update CognitiveWorkspace's emotional_equivalents dict if available."""
        try:
            from services.cognitive_workspace import update_workspace

            update_workspace(
                emotional_equivalents={
                    "valence": self._state.valence,
                    "arousal": self._state.arousal,
                    "confidence": self._state.confidence,
                    "intensity": self._state.intensity,
                }
            )
        except Exception:
            pass

    def reset_state(self) -> EmotionalState:
        with self._lock:
            self._state = EmotionalState(updated_at=time.time())
            self._sync_cognitive_workspace()
            self.save_state()
            return self.get_state()

    def load_state(self) -> None:
        with self._lock:
            if not self._state_path.exists():
                return
            try:
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                self._state = EmotionalState.from_dict(data)
            except Exception:
                self._state = EmotionalState()

    def save_state(self) -> None:
        with self._lock:
            try:
                self._state_path.parent.mkdir(parents=True, exist_ok=True)
                self._state_path.write_text(
                    json.dumps(self._state.to_dict(), indent=2, ensure_ascii=True),
                    encoding="utf-8",
                )
            except Exception:
                pass


LEAH_EMOTIONAL_STATE_MODEL_SERVICE = LeahEmotionalStateModelService()
