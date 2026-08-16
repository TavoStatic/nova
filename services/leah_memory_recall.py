from __future__ import annotations

"""Leah memory recall capability.

Gates and routes memory recall for Leah conversations. Does not duplicate
Nova's memory system — wraps it with Leah-specific routing logic so recall
only fires when the operator's query actually benefits from prior memory.

Dependency-injected: takes mem_recall_fn and mem_enabled_fn as constructor
arguments. Wire these from nova_core in nova_http.py.
"""

from typing import Any, Callable

CAPABILITY_NAME = "leah_memory_recall"
CAPABILITY_DESCRIPTION = "Leah can retrieve prior conversation and pattern memory for continuity"

# Queries shorter than this are not worth a memory lookup
_MIN_QUERY_LENGTH = 8

# Keywords that suggest the operator is asking something recall-worthy
_RECALL_CUES = (
    "what did",
    "last time",
    "remember",
    "recall",
    "earlier",
    "before",
    "again",
    "same as",
    "like before",
    "you said",
    "we discussed",
    "from memory",
    "what have you learned",
    "learned from me",
)

# Keywords that strongly suggest an operational status question — skip recall
_STATUS_CUES = (
    "what's running",
    "what is running",
    "sync status",
    "did the sync",
    "pipeline",
    "health",
    "blocked",
    "queue",
    "heartbeat",
    "is nova",
)


def _query_warrants_recall(query: str) -> bool:
    """True when the query is likely to benefit from durable memory lookup."""
    text = str(query or "").strip().lower()
    if len(text) < _MIN_QUERY_LENGTH:
        return False
    # Pure status questions don't benefit from memory — they need live data
    if any(cue in text for cue in _STATUS_CUES):
        return False
    # Explicit recall cues always warrant a lookup
    if any(cue in text for cue in _RECALL_CUES):
        return True
    return False


class LeahMemoryRecallService:
    """Gate and serve memory recall for Leah conversations.

    Usage:
        svc = LeahMemoryRecallService(
            mem_recall_fn=nova_core.mem_recall,
            mem_enabled_fn=nova_core.mem_enabled,
        )
        context = svc.recall_for_turn("what did we discuss about the sync schedule?")
        # Returns formatted recall string to inject into conversation, or ""
    """

    def __init__(
        self,
        *,
        mem_recall_fn: Callable[..., str] | None = None,
        mem_enabled_fn: Callable[[], bool] | None = None,
    ) -> None:
        self._mem_recall_fn = mem_recall_fn
        self._mem_enabled_fn = mem_enabled_fn

    def _enabled(self) -> bool:
        if self._mem_enabled_fn is None:
            return False
        try:
            return bool(self._mem_enabled_fn())
        except Exception:
            return False

    def recall_for_turn(
        self,
        query: str,
        *,
        purpose: str = "general_context",
        conversation_state: dict[str, Any] | None = None,
        pending_action: dict[str, Any] | None = None,
    ) -> str:
        """Return formatted memory recall string for this Leah turn, or empty string.

        Args:
            query: The operator's message text for this turn.
            purpose: Memory recall purpose hint. Defaults to "general_context".
            conversation_state: Optional conversation state dict for routing.
            pending_action: Optional pending action dict for routing.

        Returns:
            Formatted recall string (may be multi-line) or "" if nothing recalled.
        """
        if not self._enabled():
            return ""
        if not self._mem_recall_fn:
            return ""
        query_text = str(query or "").strip()
        if not _query_warrants_recall(query_text):
            return ""
        try:
            result = self._mem_recall_fn(
                query_text,
                purpose=purpose,
                conversation_state=conversation_state,
                pending_action=pending_action,
            )
            return str(result or "").strip()
        except Exception:
            return ""

    def recall_from_recent_turns(
        self,
        turns: list[tuple[str, str]],
        *,
        max_turns_to_scan: int = 3,
    ) -> str:
        """Scan the most recent user turns and return recall if any warrant a lookup.

        Used when recovering a session — scans recent turns to re-hydrate context
        that memory might contain for the operator's recurring patterns.

        Args:
            turns: List of (role, text) tuples from the session.
            max_turns_to_scan: How many recent user turns to check.

        Returns:
            Formatted recall string or "".
        """
        if not self._enabled() or not self._mem_recall_fn:
            return ""
        user_turns = [
            text for role, text in (turns or [])
            if str(role or "").strip().lower() == "user" and str(text or "").strip()
        ]
        recent = user_turns[-max_turns_to_scan:] if user_turns else []
        for query_text in reversed(recent):
            result = self.recall_for_turn(query_text, purpose="general_context")
            if result:
                return result
        return ""

    def inject_into_message(self, message: str, recall_context: str) -> str:
        """Prepend recall context to a Leah message if recall found something.

        Injects a clearly-labelled block so Nova knows the source.

        Args:
            message: The operator's original message.
            recall_context: Result from recall_for_turn() or recall_from_recent_turns().

        Returns:
            Original message unchanged if no recall. Message with prepended context block otherwise.
        """
        msg = str(message or "").strip()
        ctx = str(recall_context or "").strip()
        if not ctx:
            return msg
        lines = [
            "[LEAH memory context]",
            "Nova recalled the following from prior sessions relevant to this turn.",
            "Use this as background — do not repeat it unless the operator asks.",
            ctx,
            "",
            msg,
        ]
        return "\n".join(lines).strip()


def capability_registration() -> dict[str, str]:
    return {CAPABILITY_NAME: CAPABILITY_DESCRIPTION}
