from __future__ import annotations

from typing import Callable


def apply_numeric_clarify_outcome(
    *,
    has_intent_route: bool,
    routed_text: str,
    pending_action,
    current_state,
    session,
    ledger: dict,
    should_clarify_unlabeled_numeric_turn: Callable[..., bool],
    unlabeled_numeric_turn_reply: Callable[[str], str],
    make_conversation_state: Callable[..., dict],
    action_ledger_add_step: Callable[..., None],
) -> dict:
    if has_intent_route or not should_clarify_unlabeled_numeric_turn(
        routed_text,
        pending_action=pending_action,
        current_state=current_state,
    ):
        return {"handled": False}

    next_state = make_conversation_state(
        "numeric_reference_clarify",
        value=str(routed_text or "").strip(),
    )
    session.apply_state_update(next_state)
    action_ledger_add_step(ledger, "numeric_clarify", "blocked")
    return {
        "handled": True,
        "reply": unlabeled_numeric_turn_reply(routed_text),
        "planner_decision": "ask_clarify",
        "grounded": False,
        "intent": "numeric_clarify",
        "conversation_state": next_state,
    }
