from __future__ import annotations

import re
from typing import Any, Optional

import active_task_constraints as active_tasks
import followup_move_classifier as followup_moves
from services.supervisor_patterns import extract_last_user_question
from services.supervisor_patterns import looks_like_reflective_retry


def reflective_retry_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, entry_point
    if not looks_like_reflective_retry(low):
        return {"handled": False}

    active_subject = active_tasks.manager_active_subject(manager)
    mentions_location_phrase = followup_moves.mentions_location_phrase
    if phase == "handle":
        if (
            active_subject in {"identity_profile:developer", "developer_identity:developer"}
            and mentions_location_phrase(low)
            and any(token in low for token in ("gus", "gustavo", "his", "developer", "creator"))
        ):
            return {
                "handled": True,
                "action": "developer_location",
                "continuation": True,
                "ledger_stage": "developer_location",
                "intent": "developer_location",
                "grounded": True,
            }
        return {"handled": False}

    if mentions_location_phrase(low) and any(token in low for token in ("gus", "gustavo", "his", "developer", "creator")):
        return {
            "handled": False,
            "rewrite_text": str(user_text or "").strip(),
            "analysis_reason": "reflective_retry_location_hint",
        }

    prior_question = extract_last_user_question(list(turns or []), user_text)
    if prior_question:
        return {
            "handled": False,
            "rewrite_text": prior_question,
            "analysis_reason": "reflective_retry_prior_question",
        }
    return {"handled": False}


def apply_correction_rule(
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
    context = active_tasks.resolve_active_task_context(manager)
    raw = str(user_text or "").strip()
    identity_correction_patterns = (
        r"\byour\s+name\s+is\s+[a-z]",
        r"\b(?:his|the\s+developer(?:'s)?)\s+full\s+name\s+is\s+[a-z]",
        r"\bdeveloper(?:'s)?\s+name\s+is\s+[a-z]",
        r"\bcreator(?:'s)?\s+full\s+name\s+is\s+[a-z]",
    )
    if context.is_correction_pending() and raw and "?" not in raw:
        return {
            "handled": True,
            "action": "apply_correction",
            "user_correction_text": user_text,
            "continuation": True,
            "ledger_stage": "correction_feedback",
            "intent": "apply_correction",
            "grounded": True,
        }
    triggers = [
        "wrong", "no,", "actually", "that's not", "not true", "incorrect",
        "mistake", "you lied", "that's wrong", "no it's not", "correction:",
        "you gave me garbage", "garbage back",
    ]
    if any(trigger in low for trigger in triggers) or (
        "?" not in raw and any(re.search(pattern, low) for pattern in identity_correction_patterns)
    ):
        return {
            "handled": True,
            "action": "apply_correction",
            "user_correction_text": user_text,
            "ledger_stage": "correction_feedback",
            "intent": "apply_correction",
            "grounded": True,
        }
    return {"handled": False}