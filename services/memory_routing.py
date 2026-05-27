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
        "general_context",
        "recent_learning_summary",
    }

    _SESSION_PRIORITY_STATES = {"retrieval", "location_recall", "correction_pending"}
    _SESSION_PRIORITY_ACTIONS = {"weather_lookup", "retrieval_followup", "set_location"}

    @staticmethod
    def _normalize_purpose(purpose: str) -> str:
        raw = str(purpose or "general").strip().lower()
        return raw or "general"

    def infer_purpose(self, query: str) -> str:
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
            if normalized_purpose in self._ALLOWED_PURPOSES:
                return MemoryRecallPlan(True, "durable_user", normalized_purpose, "purpose_override")
            return MemoryRecallPlan(False, "durable_user", normalized_purpose, "session_priority")

        if normalized_purpose in self._ALLOWED_PURPOSES:
            return MemoryRecallPlan(True, "durable_user", normalized_purpose, "purpose_match")

        return MemoryRecallPlan(False, "durable_user", normalized_purpose, "not_memory_seeking")
