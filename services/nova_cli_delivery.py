from __future__ import annotations

from typing import Callable


def apply_cli_outcome_to_ledger(
    *,
    pending_action_ledger: dict | None,
    outcome: dict,
    default_planner_decision: str,
    update_reply_fields: bool = False,
    coerce_grounded: bool = False,
) -> None:
    if pending_action_ledger is None:
        return

    pending_action_ledger["planner_decision"] = str(outcome.get("planner_decision") or default_planner_decision)
    grounded = outcome.get("grounded")
    if coerce_grounded and "grounded" in outcome:
        pending_action_ledger["grounded"] = bool(grounded)
    elif isinstance(grounded, bool):
        pending_action_ledger["grounded"] = grounded

    if update_reply_fields:
        pending_action_ledger["reply_contract"] = str(outcome.get("reply_contract") or "")
        pending_action_ledger["reply_outcome"] = dict(outcome.get("reply_outcome") or {})


def apply_cli_handled_outcome(
    *,
    pending_action_ledger: dict | None,
    outcome: dict,
    default_planner_decision: str,
    session_turns: list[tuple[str, str]],
    print_fn: Callable[..., None],
    speak_chunked_fn: Callable[[str], None],
    say_done_fn: Callable[[str], None],
    update_reply_fields: bool = False,
    coerce_grounded: bool = False,
    clear_pending_action_fn: Callable[[], None] | None = None,
    sync_pending_conversation_tracking_fn: Callable[[], None] | None = None,
) -> dict:
    apply_cli_outcome_to_ledger(
        pending_action_ledger=pending_action_ledger,
        outcome=outcome,
        default_planner_decision=default_planner_decision,
        update_reply_fields=update_reply_fields,
        coerce_grounded=coerce_grounded,
    )

    if outcome.get("clear_pending_action") and callable(clear_pending_action_fn):
        clear_pending_action_fn()
        if callable(sync_pending_conversation_tracking_fn):
            sync_pending_conversation_tracking_fn()

    return emit_cli_reply_outcome(
        reply_text=str(outcome.get("reply") or ""),
        planner_decision=str(outcome.get("planner_decision") or default_planner_decision),
        session_turns=session_turns,
        print_fn=print_fn,
        speak_chunked_fn=speak_chunked_fn,
        say_done_fn=say_done_fn,
    )


def emit_cli_reply_outcome(
    *,
    reply_text: str,
    planner_decision: str,
    session_turns: list[tuple[str, str]],
    print_fn: Callable[..., None],
    speak_chunked_fn: Callable[[str], None],
    say_done_fn: Callable[[str], None],
) -> dict:
    reply = str(reply_text or "")
    decision = str(planner_decision or "deterministic")
    if decision == "run_tool":
        print_fn(f"Nova (tool output):\n{reply}\n", flush=True)
        session_turns.append(("assistant", reply.strip()[:350] if reply.strip() else reply))
        say_done_fn("Done.")
        return {"spoken_mode": "tool_done", "assistant_turn": session_turns[-1][1]}

    print_fn(f"Nova: {reply}\n", flush=True)
    session_turns.append(("assistant", reply))
    speak_chunked_fn(reply)
    return {"spoken_mode": "assistant_reply", "assistant_turn": reply}