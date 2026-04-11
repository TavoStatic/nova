from __future__ import annotations

from typing import Any, Optional

import active_task_constraints as active_tasks
from services.supervisor_patterns import extract_last_user_question
from services.supervisor_patterns import identity_history_kind
from services.supervisor_patterns import looks_like_developer_profile_query
from services.supervisor_patterns import looks_like_last_question_recall
from services.supervisor_patterns import looks_like_profile_certainty_followup
from services.supervisor_patterns import looks_like_rules_query
from services.supervisor_patterns import looks_like_session_fact_recall
from services.supervisor_patterns import name_origin_query_kind
from services.supervisor_patterns import open_probe_kind


def name_origin_store_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del manager, turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}

    raw = str(user_text or "").strip()
    trigger = (
        "remember this nova" in low
        or "story behind your name" in low
        or "story behing your name" in low
        or "gus gave you your name" in low
        or "gus named you" in low
    )
    if not trigger:
        return {"handled": False}

    store_text = raw
    if "gus gave you your name" in low and "remember this" not in low:
        store_text = "Gus gave me the name Nova."
    elif "gus named you" in low and "remember this" not in low:
        store_text = raw if len(raw) >= 30 else "Gus named me Nova."

    return {
        "handled": True,
        "action": "name_origin_store",
        "store_text": store_text,
        "ledger_stage": "name_origin",
        "intent": "name_origin_store",
        "grounded": True,
    }


def profile_certainty_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, turn, turns, entry_point
    if phase != "handle" or not looks_like_profile_certainty_followup(low):
        return {"handled": False}

    context = active_tasks.resolve_active_task_context(manager)
    if context.is_developer_identity_thread():
        return {
            "handled": True,
            "action": "developer_identity_followup",
            "continuation": True,
            "name_focus": False,
            "ledger_stage": "profile_followup",
            "intent": "conversation_followup",
            "grounded": True,
        }
    if context.is_identity_profile_thread():
        subject = context.identity_profile_subject() or "self"
        return {
            "handled": True,
            "action": "identity_profile_followup",
            "continuation": True,
            "subject": subject or "self",
            "ledger_stage": "profile_followup",
            "intent": "conversation_followup",
            "grounded": True,
        }
    return {"handled": False}


def identity_history_family_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}
    if any(trigger in low for trigger in ("remember this", "learn this", "save this", "store")):
        return {"handled": False}

    context = active_tasks.resolve_active_task_context(manager)
    active_subject = context.active_subject
    outcome_kind = identity_history_kind(user_text, low, active_subject=active_subject)
    if not outcome_kind:
        return {"handled": False}

    subject = "developer"
    if active_subject.startswith("identity_profile:"):
        subject = active_subject.split(":", 1)[1] if ":" in active_subject else "self"
    elif active_subject.startswith("developer_identity"):
        subject = "developer"
    elif outcome_kind == "name_origin":
        subject = "self"

    return {
        "handled": True,
        "action": "identity_history_family",
        "identity_history_kind": outcome_kind,
        "name_origin_query_kind": name_origin_query_kind(low) or "source_recall",
        "subject": subject or "developer",
        "continuation": active_subject.startswith("identity_profile") or active_subject.startswith("developer_identity"),
        "ledger_stage": "identity_history",
        "intent": "identity_history_family",
        "grounded": True,
    }


def open_probe_family_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}
    probe_kind = open_probe_kind(low)
    if not probe_kind:
        return {"handled": False}
    return {
        "handled": True,
        "action": "open_probe_family",
        "open_probe_kind": probe_kind,
        "ledger_stage": "open_probe",
        "intent": "open_probe_family",
        "grounded": False,
    }


def last_question_recall_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, entry_point
    if phase != "handle" or not looks_like_last_question_recall(low):
        return {"handled": False}
    if not extract_last_user_question(list(turns or []), low):
        return {
            "handled": True,
            "action": "last_question_recall",
            "ledger_stage": "session_history",
            "intent": "last_question_recall",
            "grounded": True,
            "last_question_available": False,
        }
    return {
        "handled": True,
        "action": "last_question_recall",
        "ledger_stage": "session_history",
        "intent": "last_question_recall",
        "grounded": True,
        "last_question_available": True,
    }


def session_fact_recall_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del manager, turn, entry_point
    if phase != "handle":
        return {"handled": False}
    target, value = looks_like_session_fact_recall(low, turns=turns, user_text=user_text)
    if not target:
        return {"handled": False}
    return {
        "handled": True,
        "action": "session_fact_recall",
        "ledger_stage": "session_history",
        "intent": "session_fact_recall",
        "grounded": True,
        "fact_target": target,
        "fact_value": value,
    }


def rules_list_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "handle" or not looks_like_rules_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "action": "rules_list",
        "ledger_stage": "policy_rules",
        "intent": "rules_list",
        "grounded": True,
    }


def developer_profile_state_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "state" or not looks_like_developer_profile_query(low):
        return {"handled": False}
    return {
        "handled": False,
        "state_update": {"kind": "identity_profile", "subject": "developer"},
    }