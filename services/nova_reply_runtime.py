from __future__ import annotations

from typing import Callable, Optional


def apply_reply_runtime_effects(
    *,
    planner_decision: str,
    tool: str,
    tool_result: str,
    final_reply: str = "",
    active_state: Optional[dict] = None,
    behavior_record_event_fn: Callable[[str], None],
    extract_urls_fn: Callable[[str], list[str]],
    detect_identity_conflict_fn: Optional[Callable[[], bool]] = None,
) -> dict:
    decision = str(planner_decision or "").strip()
    tool_name = str(tool or "").strip()
    tool_output = str(tool_result or "")
    reply_text = str(final_reply or "")

    if decision in {"truth_hierarchy", "deterministic", "grounded_lookup"}:
        behavior_record_event_fn("deterministic_hit")
    elif decision in {"command", "run_tool"}:
        behavior_record_event_fn("tool_route")
    elif decision == "llm_fallback":
        behavior_record_event_fn("llm_fallback")

    identity_conflict = False
    if decision == "deterministic" and tool_name == "hard_answer" and callable(detect_identity_conflict_fn):
        identity_conflict = bool(detect_identity_conflict_fn())
        if identity_conflict:
            behavior_record_event_fn("conflict_detected")

    recent_tool_context = ""
    recent_web_urls: list[str] = []
    context_updated = False
    if decision in {"run_tool", "command"} and tool_output.strip():
        recent_tool_context = tool_output.strip()[:2500]
        recent_web_urls = list(extract_urls_fn(tool_output) or [])
        context_updated = True
    elif (
        decision == "conversation_followup"
        and reply_text.strip()
        and isinstance(active_state, dict)
        and str(active_state.get("kind") or "").strip() == "retrieval"
    ):
        recent_tool_context = reply_text.strip()[:2500]
        recent_web_urls = list(extract_urls_fn(reply_text) or [])
        context_updated = True

    return {
        "identity_conflict": identity_conflict,
        "context_updated": context_updated,
        "recent_tool_context": recent_tool_context,
        "recent_web_urls": recent_web_urls,
    }