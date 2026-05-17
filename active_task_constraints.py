from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import followup_move_classifier as followup_moves


@dataclass(frozen=True)
class ActiveTaskContext:
    active_subject: str = ""
    pending_action: dict[str, Any] | None = None
    retrieval_state: dict[str, Any] | None = None

    def is_correction_pending(self) -> bool:
        return self.active_subject.startswith("correction_pending")

    def is_location_recall(self) -> bool:
        return self.active_subject.startswith("location_recall")

    def is_retrieval_thread(self) -> bool:
        return bool(self.retrieval_state) or self.active_subject.startswith("retrieval:")

    def is_developer_identity_thread(self) -> bool:
        return self.active_subject.startswith("developer_identity")

    def is_identity_profile_thread(self) -> bool:
        return self.active_subject.startswith("identity_profile")

    def identity_profile_subject(self) -> str:
        if not self.is_identity_profile_thread():
            return ""
        return self.active_subject.split(":", 1)[1] if ":" in self.active_subject else "self"


def manager_active_subject(manager: Any) -> str:
    if manager is None:
        return ""
    try:
        active_subject = getattr(manager, "active_subject", None)
        if callable(active_subject):
            return str(active_subject() or "").strip()
    except Exception:
        return ""
    if isinstance(manager, dict):
        kind = str(manager.get("kind") or "").strip()
        subject = str(manager.get("subject") or "").strip()
        if kind and subject:
            return f"{kind}:{subject}"
        return kind
    return ""


def manager_pending_action(manager: Any) -> dict[str, Any]:
    if manager is None:
        return {}
    try:
        pending_action = getattr(manager, "pending_action", None)
        if isinstance(pending_action, dict):
            return pending_action
    except Exception:
        return {}
    if isinstance(manager, dict):
        pending_action = manager.get("pending_action")
        if isinstance(pending_action, dict):
            return pending_action
    return {}


def manager_retrieval_state(manager: Any) -> dict[str, Any]:
    if manager is None:
        return {}
    try:
        retrieval_state = getattr(manager, "retrieval_state", None)
        if callable(retrieval_state):
            state = retrieval_state()
            if isinstance(state, dict) and str(state.get("kind") or "").strip() == "retrieval":
                return state
    except Exception:
        return {}
    try:
        conversation_state = getattr(manager, "conversation_state", None)
        if isinstance(conversation_state, dict) and str(conversation_state.get("kind") or "").strip() == "retrieval":
            return conversation_state
    except Exception:
        return {}
    if isinstance(manager, dict) and str(manager.get("kind") or "").strip() == "retrieval":
        return manager
    return {}


def resolve_active_task_context(manager: Any) -> ActiveTaskContext:
    return ActiveTaskContext(
        active_subject=manager_active_subject(manager),
        pending_action=manager_pending_action(manager),
        retrieval_state=manager_retrieval_state(manager),
    )


def looks_like_current_location_slot_fill(user_text: str) -> bool:
    normalized = " ".join(str(user_text or "").strip().lower().split())
    if not normalized.startswith("use "):
        return False
    tail = normalized[4:].strip(" .,!?")
    if tail.endswith(" nova"):
        tail = tail[:-5].strip()
    pointer_words = {
        "current",
        "currrent",
        "device",
        "physical",
        "runtime",
        "saved",
        "same",
        "location",
        "locaiton",
        "coords",
        "coordinates",
        "your",
        "our",
        "my",
    }
    return bool(set(tail.split()) & pointer_words)


def bind_pending_weather_followup(
    context: ActiveTaskContext,
    user_text: str,
    low: str,
    *,
    move: str = "",
) -> dict[str, Any]:
    pending = context.pending_action if isinstance(context.pending_action, dict) else {}
    if str(pending.get("kind") or "").strip() != "weather_lookup":
        return {}
    if str(pending.get("status") or "").strip() != "awaiting_location":
        return {}

    if looks_like_current_location_slot_fill(user_text) or followup_moves.looks_like_shared_location_reference(low):
        return {
            "intent": "weather_lookup",
            "weather_mode": "current_location",
            "ledger_stage": "weather_lookup",
            "grounded": True,
            "ownership": "explicit",
        }

    location_value = followup_moves.extract_weather_followup_location_candidate(user_text, low)
    if location_value:
        return {
            "intent": "weather_lookup",
            "weather_mode": "explicit_location",
            "location_value": location_value,
            "ledger_stage": "weather_lookup",
            "grounded": True,
            "ownership": "explicit",
        }

    if move == "affirmation" and bool(pending.get("saved_location_available")):
        return {
            "intent": "weather_lookup",
            "weather_mode": "current_location",
            "ledger_stage": "weather_lookup",
            "grounded": True,
            "ownership": "explicit",
        }
    return {}


def bind_retrieval_followup(context: ActiveTaskContext, *, move: str) -> dict[str, Any]:
    if not context.is_retrieval_thread():
        return {}
    if move not in {"meta_question", "selection", "continuation"}:
        return {}
    return {
        "action": "retrieval_followup",
        "continuation": True,
        "ledger_stage": "conversation_followup",
        "intent": "retrieval_followup",
        "grounded": True,
    }


__all__ = [
    "ActiveTaskContext",
    "bind_pending_weather_followup",
    "bind_retrieval_followup",
    "looks_like_current_location_slot_fill",
    "manager_active_subject",
    "manager_pending_action",
    "manager_retrieval_state",
    "resolve_active_task_context",
]
