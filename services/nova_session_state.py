from __future__ import annotations


def _last_tool_evidence_state(payload: dict) -> dict | None:
    planner_decision = str(payload.get("planner_decision") or "").strip()
    tool = str(payload.get("tool") or "").strip()
    tool_result = str(payload.get("tool_result") or "").strip()
    if planner_decision not in {"command", "run_tool", "grounded_lookup"}:
        return None
    if not tool_result:
        return None
    state = {
        "kind": "last_tool_evidence",
        "subject": tool or planner_decision,
        "tool": tool,
        "tool_result": tool_result[:2500],
    }
    reply_contract = str(payload.get("reply_contract") or "").strip()
    if reply_contract:
        state["reply_contract"] = reply_contract
    return state


def apply_reply_session_updates(
    session,
    *,
    meta: dict | None,
):
    payload = meta if isinstance(meta, dict) else {}
    pending_next = payload.get("pending_action")
    session.set_pending_action(pending_next if isinstance(pending_next, dict) and pending_next else None)
    session.apply_state_update(None, fallback_state=_last_tool_evidence_state(payload))
    return None
