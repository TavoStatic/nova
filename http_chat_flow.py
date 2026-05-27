from __future__ import annotations

from typing import Callable, Any

def prepare_chat_turn(
    *,
    session_id: str,
    text: str,
    session,
    ledger: dict,
    append_session_turn: Callable[[str, str, str], list[tuple[str, str]]],
) -> dict:
    turns = append_session_turn(session_id, "user", text)
    return {
        "turns": turns,
        "routed_text": text,
        "turn_acts": [],
    }


def resume_last_pending_turn(
    session_id: str,
    user_id: str = "",
    *,
    get_active_user: Callable[[], str | None],
    set_active_user: Callable[[str | None], None],
    get_last_session_turn: Callable[[str], tuple[str, str] | None],
    get_session_turns: Callable[[str], list[tuple[str, str]]],
    generate_chat_reply: Callable[[list[tuple[str, str]], str], tuple[str, dict[str, Any]]],
    append_session_turn: Callable[[str, str, str], list[tuple[str, str]]],
    invalidate_control_status_cache: Callable[[], None] | None = None,
) -> dict:
    previous_user = get_active_user()
    set_active_user(user_id or previous_user)
    try:
        sid = (session_id or "").strip()
        if not sid:
            return {"ok": False, "error": "session_id_required"}

        last = get_last_session_turn(sid)
        if not last:
            return {"ok": True, "resumed": False, "reason": "no_turns"}

        role, text = last
        if role != "user":
            return {"ok": True, "resumed": False, "reason": "no_pending_user_turn"}

        turns = get_session_turns(sid)
        reply, _meta = generate_chat_reply(turns, text)
        append_session_turn(sid, "assistant", reply)
        if callable(invalidate_control_status_cache):
            invalidate_control_status_cache()
        return {"ok": True, "resumed": True, "session_id": sid, "reply": reply}
    finally:
        set_active_user(previous_user)


def resume_last_pending_turn_from_runtime(
    session_id: str,
    user_id: str = "",
    *,
    runtime_scope: dict[str, object],
) -> dict:
    return resume_last_pending_turn(
        session_id,
        user_id,
        get_active_user=runtime_scope["nova_core"].get_active_user,
        set_active_user=runtime_scope["nova_core"].set_active_user,
        get_last_session_turn=runtime_scope["_get_last_session_turn"],
        get_session_turns=runtime_scope["_get_session_turns"],
        generate_chat_reply=runtime_scope["_generate_chat_reply"],
        append_session_turn=runtime_scope["_append_session_turn"],
        invalidate_control_status_cache=runtime_scope.get("_invalidate_control_status_cache"),
    )
