from __future__ import annotations

from typing import Callable, Optional


def evaluate_fulfillment_route_viability(
    user_text: str,
    session: object,
    recent_turns: list[tuple[str, str]],
    *,
    pending_action: Optional[dict] = None,
    get_fulfillment_state_fn: Callable[[object], object | None],
    semantic_observation: Optional[dict] = None,
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

    # Fresh turn — use semantic observation to determine if fulfillment is worth attempting.
    # Fulfillment applies when the routing model identified a meaningful outward or action intent
    # but no specific tool was selected, meaning the request needs interpretation and planning.
    observation = semantic_observation if isinstance(semantic_observation, dict) else {}
    answer_target = str(observation.get("answer_target") or "").strip().lower()
    tool = str(observation.get("tool") or "").strip().lower()
    fulfillment_targets = {"tool_action", "external_world"}
    if answer_target in fulfillment_targets and tool in {"", "none"}:
        return {
            "viable": True,
            "fit_notes": [
                f"fresh turn with answer_target={answer_target!r} and no tool selected",
                "fulfillment may interpret and plan a response",
            ],
            "comparison_strength": "clear",
        }

    return {
        "viable": False,
        "fit_notes": ["no existing fulfillment state", f"answer_target={answer_target!r} does not warrant fulfillment"],
        "comparison_strength": "weak",
    }
