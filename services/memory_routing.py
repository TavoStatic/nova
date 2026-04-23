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

    _EXPLICIT_RECALL_MARKERS = (
        "do you remember",
        "what do you remember",
        "remember about",
        "from earlier",
        "earlier memory",
        "saved memory",
        "stored memory",
        "recall",
    )

    _PREFERENCE_MARKERS = (
        "favorite color",
        "favourite color",
        "favorite colors",
        "favourite colors",
        "color preference",
        "favorite animal",
        "favourite animal",
        "animal preference",
        "what colors do i like",
        "what animals do i like",
    )

    _IDENTITY_MARKERS = (
        "nova name origin",
        "name origin story",
        "creator gus",
        "assistant name",
        "developer name",
    )

    _DEVELOPER_MARKERS = (
        "developer",
        "gus",
        "gustavo",
        "developer profile",
    )

    _GENERAL_MEMORY_MARKERS = (
        "remember",
        "preference",
        "preferences",
        "profile",
        "favorite",
        "favourite",
        "i like",
        "my name",
        "my location",
        "what do you know about",
    )

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
        if any(marker in low for marker in self._IDENTITY_MARKERS):
            return "identity_fallback"
        if any(marker in low for marker in self._PREFERENCE_MARKERS):
            return "user_preferences"
        if any(marker in low for marker in self._EXPLICIT_RECALL_MARKERS):
            return "explicit_recall"
        if any(marker in low for marker in self._DEVELOPER_MARKERS):
            return "developer_profile"
        if any(marker in low for marker in self._GENERAL_MEMORY_MARKERS):
            return "general_context"
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

        if normalized_purpose == "general":
            normalized_purpose = self.infer_purpose(text)

        if self.session_priority_active(conversation_state=conversation_state, pending_action=pending_action):
            if normalized_purpose in {"identity_fallback", "user_preferences", "developer_profile", "explicit_recall", "recent_learning_summary"}:
                return MemoryRecallPlan(True, "durable_user", normalized_purpose, "purpose_override")
            return MemoryRecallPlan(False, "durable_user", normalized_purpose, "session_priority")

        if normalized_purpose in {"identity_fallback", "user_preferences", "developer_profile", "explicit_recall", "general_context", "recent_learning_summary"}:
            return MemoryRecallPlan(True, "durable_user", normalized_purpose, "purpose_match")

        return MemoryRecallPlan(False, "durable_user", normalized_purpose, "not_memory_seeking")