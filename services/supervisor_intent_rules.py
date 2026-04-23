from __future__ import annotations

from typing import Any

import active_task_constraints as active_tasks
from services.supervisor_patterns import looks_like_assistant_name_query
from services.supervisor_patterns import looks_like_capability_query
from services.supervisor_patterns import looks_like_creator_query
from services.supervisor_patterns import looks_like_developer_full_name_query
from services.supervisor_patterns import looks_like_developer_profile_query
from services.supervisor_patterns import looks_like_policy_domain_query
from services.supervisor_patterns import looks_like_self_identity_web_challenge
from services.supervisor_patterns import looks_like_smalltalk
from services.supervisor_patterns import name_origin_query_kind


def smalltalk_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, turn, kwargs
    context = active_tasks.resolve_active_task_context(manager)
    if context.is_correction_pending():
        return {"handled": False}
    if not looks_like_smalltalk(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "smalltalk",
        "confidence": 0.95,
    }


def capability_query_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not looks_like_capability_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "capability_query",
        "confidence": 0.95,
    }


def policy_domain_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not looks_like_policy_domain_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "policy_domain_query",
        "confidence": 0.95,
    }


def assistant_name_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not looks_like_assistant_name_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "assistant_name",
        "confidence": 0.95,
    }


def self_identity_web_challenge_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not looks_like_self_identity_web_challenge(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "self_identity_web_challenge",
        "confidence": 0.95,
    }


def name_origin_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if (
        "remember this nova" in low
        or "gus gave you your name" in low
        or "gus named you" in low
    ):
        return {"handled": False}
    query_kind = name_origin_query_kind(low)
    if not query_kind:
        return {"handled": False}
    return {
        "handled": True,
        "intent": "name_origin",
        "name_origin_query_kind": query_kind,
        "confidence": 0.94,
    }


def developer_full_name_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not looks_like_developer_full_name_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "developer_full_name",
        "confidence": 0.95,
    }


def developer_profile_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if looks_like_creator_query(low):
        return {
            "handled": True,
            "intent": "creator_identity",
            "confidence": 0.94,
        }
    if not looks_like_developer_profile_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "developer_profile",
        "confidence": 0.92,
    }


def session_summary_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    triggers = [
        "what happened", "recap", "summarize", "digest", "review chat",
        "what did we talk about", "session summary", "what's going on",
    ]
    if any(trigger in low for trigger in triggers):
        return {
            "handled": True,
            "intent": "session_summary",
            "target": "current_session_only",
            "confidence": 0.95,
        }
    return {"handled": False}