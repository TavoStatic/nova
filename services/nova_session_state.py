from __future__ import annotations


def apply_reply_session_updates(
    session,
    *,
    meta: dict | None,
    routed_text: str,
    turns: list[tuple[str, str]],
    fallback_state,
    infer_post_reply_conversation_state,
):
    payload = meta if isinstance(meta, dict) else {}
    pending_next = payload.get("pending_action")
    session.set_pending_action(pending_next if isinstance(pending_next, dict) and pending_next else None)

    next_state = infer_post_reply_conversation_state(
        routed_text,
        planner_decision=str(payload.get("planner_decision") or "deterministic"),
        tool=str(payload.get("tool") or ""),
        tool_args=payload.get("tool_args") if isinstance(payload.get("tool_args"), dict) else {},
        tool_result=str(payload.get("tool_result") or ""),
        turns=turns,
        fallback_state=fallback_state,
    )
    if isinstance(next_state, dict) and str(next_state.get("kind") or "").strip() == "retrieval":
        session.set_retrieval_state(next_state)
    else:
        session.apply_state_update(next_state, fallback_state=fallback_state)
    return next_state