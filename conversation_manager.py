from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConversationSession:
    conversation_state: Optional[dict] = None
    prefer_web_for_data_queries: bool = False
    pending_action: Optional[dict] = None
    pending_correction_target: str = ""
    continuation_used_last_turn: bool = False
    last_reflection: Optional[dict] = None

    def reset_turn_flags(self) -> None:
        self.continuation_used_last_turn = False

    def active_subject(self) -> str:
        state = self.conversation_state if isinstance(self.conversation_state, dict) else {}
        kind = str(state.get("kind") or "").strip()
        subject = str(state.get("subject") or "").strip()
        if kind and subject:
            return f"{kind}:{subject}"
        return kind

    def set_conversation_state(self, state: Optional[dict]) -> None:
        self.conversation_state = state if isinstance(state, dict) else None

    def state_kind(self) -> str:
        state = self.conversation_state if isinstance(self.conversation_state, dict) else {}
        return str(state.get("kind") or "").strip()

    def retrieval_state(self) -> Optional[dict]:
        if self.state_kind() != "retrieval":
            return None
        return self.conversation_state if isinstance(self.conversation_state, dict) else None

    def set_retrieval_state(self, state: Optional[dict]) -> None:
        if isinstance(state, dict) and str(state.get("kind") or "").strip() == "retrieval":
            self.conversation_state = state
            return
        if state is None and self.state_kind() == "retrieval":
            self.conversation_state = None

    def apply_state_update(self, next_state: Optional[dict], fallback_state: Optional[dict] = None) -> None:
        if isinstance(next_state, dict):
            self.conversation_state = next_state
            return
        self.conversation_state = fallback_state if isinstance(fallback_state, dict) else None

    def set_pending_action(self, action: Optional[dict]) -> None:
        self.pending_action = action if isinstance(action, dict) else None

    def set_pending_correction_target(self, target: Optional[str]) -> None:
        self.pending_correction_target = str(target or "").strip()

    def clear_pending_correction_target(self) -> None:
        self.pending_correction_target = ""

    def set_prefer_web_for_data_queries(self, enabled: bool) -> None:
        self.prefer_web_for_data_queries = bool(enabled)

    def mark_continuation_used(self) -> None:
        self.continuation_used_last_turn = True

    def set_last_reflection(self, reflection: Optional[dict]) -> None:
        self.last_reflection = reflection if isinstance(reflection, dict) else None

    def ledger_fields(self) -> dict:
        return {
            "active_subject": self.active_subject(),
            "continuation_used": self.continuation_used_last_turn,
        }

    def reflection_summary(self) -> dict:
        overrides = ["prefer_web_for_data_queries"] if self.prefer_web_for_data_queries else []
        summary = {
            "active_subject": self.active_subject(),
            "continuation_used": self.continuation_used_last_turn,
            "overrides_active": overrides,
        }
        if isinstance(self.last_reflection, dict):
            summary["probe_summary"] = str(self.last_reflection.get("probe_summary") or "")
            summary["probe_results"] = list(self.last_reflection.get("probe_results") or [])
        return summary


class ConversationManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}

    def get(self, session_id: str) -> ConversationSession:
        sid = str(session_id or "").strip() or "default"
        session = self._sessions.get(sid)
        if session is None:
            session = ConversationSession()
            self._sessions[sid] = session
        return session

    def peek(self, session_id: str) -> Optional[ConversationSession]:
        sid = str(session_id or "").strip() or "default"
        return self._sessions.get(sid)

    def drop(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if sid:
            self._sessions.pop(sid, None)

    def clear(self) -> None:
        self._sessions.clear()
