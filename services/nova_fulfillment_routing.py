from __future__ import annotations

from typing import Callable, Optional


def evaluate_fulfillment_route_viability(
    user_text: str,
    session: object,
    recent_turns: list[tuple[str, str]],
    *,
    pending_action: Optional[dict] = None,
    get_fulfillment_state_fn: Callable[[object], object | None],
) -> dict:
    state = get_fulfillment_state_fn(session)
    del user_text, recent_turns
    conversation_state = getattr(session, "conversation_state", None)
    state_kind = str(conversation_state.get("kind") or "").strip().lower() if isinstance(conversation_state, dict) else ""

    if state is not None:
        return {
            "viable": True,
            "fit_notes": ["existing fulfillment state present", "follow-up can replan current fulfillment space"],
            "comparison_strength": "clear",
        }
    if isinstance(pending_action, dict):
        return {
            "viable": False,
            "fit_notes": ["pending action is active", "fulfillment should not interrupt explicit continuation"],
            "comparison_strength": "clear",
        }
    if state_kind and state_kind != "fulfillment":
        return {
            "viable": False,
            "fit_notes": [f"active conversation state is {state_kind}", "fulfillment should not take over another active thread"],
            "comparison_strength": "clear",
        }
    return {
        "viable": False,
        "fit_notes": ["no existing fulfillment state"],
        "comparison_strength": "weak",
    }
