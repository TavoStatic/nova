from __future__ import annotations

from typing import Callable, Optional


def evaluate_fulfillment_route_viability(
    user_text: str,
    session: object,
    recent_turns: list[tuple[str, str]],
    *,
    pending_action: Optional[dict] = None,
    get_fulfillment_state_fn: Callable[[object], object | None],
    looks_like_affirmative_followup_fn: Callable[[str], bool],
) -> dict:
    state = get_fulfillment_state_fn(session)
    text = str(user_text or "").strip()
    low = text.lower()
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
    if len(text.split()) < 4:
        return {
            "viable": False,
            "fit_notes": ["turn is too short", "not enough information to open a fulfillment space"],
            "comparison_strength": "weak",
        }
    if low in {"yes", "no", "ok", "okay", "continue", "go ahead"} or looks_like_affirmative_followup_fn(text):
        return {
            "viable": False,
            "fit_notes": ["turn looks like a short continuation", "fulfillment should not guess from a minimal follow-up"],
            "comparison_strength": "weak",
        }

    model_space_cues = (
        " options",
        " option ",
        " ways",
        " way to",
        " approaches",
        " approach ",
        " compare ",
        " tradeoff",
        " trade-off",
        " path ",
        " paths",
        " best way",
        " how should i",
        " what are my options",
        " help me decide",
        " help me figure out",
        " help me choose",
        " show me workable",
        " show me options",
    )
    starts_like_model_space = low.startswith((
        "compare ",
        "show me ",
        "help me decide",
        "help me choose",
        "how should i ",
        "what are my options",
    ))
    cue_match = any(cue in f" {low} " for cue in model_space_cues)
    if starts_like_model_space or cue_match:
        notes = ["turn suggests multiple possible ways forward", "fulfillment comparison may be useful"]
        if recent_turns:
            notes.append("recent turns are available for intent context")
        return {
            "viable": True,
            "fit_notes": notes,
            "comparison_strength": "clear",
        }
    return {
        "viable": False,
        "fit_notes": ["no model-space cues detected", "generic fallback is a safer default"],
        "comparison_strength": "weak",
    }