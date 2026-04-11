from __future__ import annotations

from typing import Callable


def apply_fast_smalltalk(
    *,
    quick_reply: str,
    ledger: dict,
    action_ledger_add_step: Callable[..., None],
) -> dict:
    reply = str(quick_reply or "").strip()
    if not reply:
        return {"handled": False}

    action_ledger_add_step(ledger, "fast_smalltalk", "matched")
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": False,
    }


def apply_identity_binding_learning(
    *,
    identity_learned: bool,
    identity_msg: str,
    ledger: dict,
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not identity_learned:
        return {"handled": False}

    action_ledger_add_step(ledger, "identity_binding", "stored")
    return {
        "handled": True,
        "reply": ensure_reply(identity_msg),
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": "identity_binding",
    }


def apply_developer_profile_learning(
    *,
    learned_profile: bool,
    learned_profile_msg: str,
    text: str,
    session,
    ledger: dict,
    infer_profile_conversation_state: Callable[[str], dict | None],
    make_conversation_state: Callable[..., dict],
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not learned_profile:
        return {"handled": False}

    session.apply_state_update(
        infer_profile_conversation_state(text)
        or make_conversation_state("identity_profile", subject="developer")
    )
    action_ledger_add_step(ledger, "developer_profile", "stored")
    reply = ensure_reply(learned_profile_msg)
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": "developer_profile_store",
    }


def apply_self_profile_learning(
    *,
    learned_self: bool,
    learned_self_msg: str,
    ledger: dict,
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not learned_self:
        return {"handled": False}

    action_ledger_add_step(ledger, "self_profile", "stored")
    reply = ensure_reply(learned_self_msg)
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": "self_profile_store",
    }


def apply_location_store_outcome(
    *,
    location_ack: str,
    conversation_state,
    session,
    ledger: dict,
    make_conversation_state: Callable[..., dict],
    action_ledger_add_step: Callable[..., None],
) -> dict:
    reply = str(location_ack or "").strip()
    if not reply:
        return {"handled": False}

    session.apply_state_update(
        make_conversation_state("location_recall"),
        fallback_state=conversation_state,
    )
    action_ledger_add_step(ledger, "location_memory", "stored")
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": "location_store",
        "conversation_state": session.conversation_state,
    }


def apply_saved_location_weather_outcome(
    *,
    conversation_state,
    routed_text: str,
    weather_for_saved_location: Callable[[], str],
    is_saved_location_weather_query: Callable[[str], bool],
    session,
    ledger: dict,
    make_conversation_state: Callable[..., dict],
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not (
        isinstance(conversation_state, dict)
        and str(conversation_state.get("kind") or "") == "location_recall"
        and is_saved_location_weather_query(routed_text)
    ):
        return {"handled": False}

    weather_reply = str(weather_for_saved_location() or "")
    if not weather_reply:
        return {"handled": False}

    session.apply_state_update(
        make_conversation_state("location_recall"),
        fallback_state=conversation_state,
    )
    action_ledger_add_step(ledger, "weather_lookup", "saved_location")
    reply = ensure_reply(weather_reply)
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": "weather_lookup",
        "conversation_state": session.conversation_state,
    }


def apply_declarative_store_outcome(
    *,
    declarative_outcome,
    ledger: dict,
    action_ledger_add_step: Callable[..., None],
    render_reply: Callable[[dict], str],
) -> dict:
    if not isinstance(declarative_outcome, dict):
        return {"handled": False}

    action_ledger_add_step(ledger, "declarative_memory", "stored")
    reply = str(render_reply(declarative_outcome) or "")
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": "declarative_store",
        "reply_contract": str(declarative_outcome.get("reply_contract") or ""),
        "reply_outcome": declarative_outcome,
    }


def apply_developer_guess_outcome(
    *,
    developer_guess: str,
    next_state,
    session,
    ledger: dict,
    action_ledger_add_step: Callable[..., None],
    ensure_reply: Callable[[str], str],
) -> dict:
    if not str(developer_guess or "").strip():
        return {"handled": False}

    session.apply_state_update(next_state)
    action_ledger_add_step(ledger, "developer_role_guess", "matched")
    reply = ensure_reply(str(developer_guess or ""))
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": "developer_role_guess",
        "conversation_state": session.conversation_state,
    }


def apply_developer_location_outcome(
    *,
    reply_text: str,
    next_state,
    session,
    ledger: dict,
    action_ledger_add_step: Callable[..., None],
) -> dict:
    reply = str(reply_text or "").strip()
    if not reply:
        return {"handled": False}

    session.apply_state_update(next_state)
    action_ledger_add_step(ledger, "developer_location", "matched")
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": "developer_location",
        "conversation_state": session.conversation_state,
    }


def apply_location_conversation_outcome(
    *,
    handled_location: bool,
    location_reply: str,
    next_location_state,
    location_intent: str,
    conversation_state,
    session,
    ensure_reply: Callable[[str], str],
) -> dict:
    if not handled_location:
        return {"handled": False}

    if isinstance(next_location_state, dict):
        session.apply_state_update(next_location_state, fallback_state=conversation_state)
    reply = ensure_reply(str(location_reply or ""))
    return {
        "handled": True,
        "reply": reply,
        "planner_decision": "deterministic",
        "grounded": True,
        "intent": str(location_intent or "location_recall"),
        "conversation_state": session.conversation_state,
    }