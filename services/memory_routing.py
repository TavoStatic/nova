from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MemoryRecallPlan:
    allow: bool
    lane: str
    purpose: str
    reason: str


class MemoryRoutingService:
    """Plan durable recall so memory reads happen intentionally."""

    _ALLOWED_PURPOSES = {
        "identity_fallback",
        "user_preferences",
        "developer_profile",
        "explicit_recall",
        "recent_learning_summary",
    }

    _SESSION_PRIORITY_STATES = {"retrieval", "location_recall", "correction_pending"}
    _SESSION_PRIORITY_ACTIONS = {"weather_lookup", "retrieval_followup", "set_location"}

    @staticmethod
    def _normalize_purpose(purpose: str) -> str:
        raw = str(purpose or "general").strip().lower()
        return raw or "general"

    def infer_purpose(self, query: str) -> str:
        low = str(query or "").strip().lower()
        if not low:
            return "general"
        if any(
            cue in low
            for cue in (
                "what have you learned",
                "learned from me",
                "recent learning",
            )
        ):
            return "recent_learning_summary"
        if any(
            cue in low
            for cue in (
                "favorite color",
                "favourite color",
                "fav color",
                "preference",
                "what colors",
                "what colour",
            )
        ):
            return "user_preferences"
        if any(
            cue in low
            for cue in (
                "developer",
                "creator",
                "who made you",
                "who built you",
                "gustavo",
                " gus",
            )
        ):
            return "developer_profile"
        if any(
            cue in low
            for cue in (
                "remember",
                "recall",
                "earlier",
                "before",
                "what did",
                "you said",
                "we discussed",
                "from memory",
                "last time",
                "again",
                "same as",
                "like before",
            )
        ):
            return "explicit_recall"
        if any(cue in low for cue in ("who am i", "my name is", "identity")):
            return "identity_fallback"
        return "general"

    def session_priority_active(
        self,
        *,
        conversation_state: Optional[dict] = None,
        pending_action: Optional[dict] = None,
    ) -> bool:
        state_kind = ""
        if isinstance(conversation_state, dict):
            state_kind = str(conversation_state.get("kind") or "").strip().lower()
        if state_kind in self._SESSION_PRIORITY_STATES:
            return True

        action_kind = ""
        if isinstance(pending_action, dict):
            action_kind = str(pending_action.get("kind") or "").strip().lower()
        return action_kind in self._SESSION_PRIORITY_ACTIONS

    def plan_durable_recall(
        self,
        query: str,
        *,
        purpose: str = "general",
        conversation_state: Optional[dict] = None,
        pending_action: Optional[dict] = None,
    ) -> MemoryRecallPlan:
        text = str(query or "").strip()
        normalized_purpose = self._normalize_purpose(purpose)
        if len(text) < 8:
            return MemoryRecallPlan(False, "durable_user", normalized_purpose, "too_short")

        if normalized_purpose in {"general", "general_context"}:
            original_purpose = normalized_purpose
            normalized_purpose = self.infer_purpose(text)
            # If inference didn't find a specific purpose, preserve the caller's original
            # purpose when it was already in the allowed set — don't silently downgrade
            # "general_context" (allowed) to "general" (not allowed).
            if normalized_purpose == "general" and original_purpose in self._ALLOWED_PURPOSES:
                normalized_purpose = original_purpose

        if self.session_priority_active(conversation_state=conversation_state, pending_action=pending_action):
            if normalized_purpose in self._ALLOWED_PURPOSES:
                return MemoryRecallPlan(True, "durable_user", normalized_purpose, "purpose_override")
            return MemoryRecallPlan(False, "durable_user", normalized_purpose, "session_priority")

        if normalized_purpose in self._ALLOWED_PURPOSES:
            return MemoryRecallPlan(True, "durable_user", normalized_purpose, "purpose_match")

        return MemoryRecallPlan(False, "durable_user", normalized_purpose, "not_memory_seeking")


MEMORY_ROUTING_SERVICE = MemoryRoutingService()
