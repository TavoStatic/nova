from __future__ import annotations

from typing import Callable, Optional


def truthful_limit_reply(
    text: str = "",
    *,
    limitation: str = "cannot_verify",
    include_next_step: bool = True,
    normalize_turn_text_fn: Callable[[str], str],
    looks_like_mixed_info_request_turn_fn: Callable[[str], bool],
    is_explicit_request_fn: Callable[[str], bool],
) -> str:
    normalized = normalize_turn_text_fn(text)
    limitation_kind = str(limitation or "cannot_verify").strip().lower() or "cannot_verify"
    if limitation_kind == "cannot_do":
        base = "I can't do that with the tools or permissions I have available right now, and I don't want to pretend I can."
    else:
        base = "I don't know that based on what I can verify right now, and I don't want to make it up."

    learning_invitation = "If you know the answer or want to correct me, tell me and I'll store it so I do better next time."

    if not include_next_step:
        return base + " " + learning_invitation
    if looks_like_mixed_info_request_turn_fn(normalized):
        return base + " Please split the request or tell me which part you want me to handle first. " + learning_invitation
    if is_explicit_request_fn(normalized) or "?" in normalized:
        return base + " If you want, I can ask a clarifying question or use a grounded source or tool if one is available. " + learning_invitation
    return base + " If you want, I can stay on the current thread, ask a clarifying question, or use a grounded source or tool if one is available. " + learning_invitation


def attach_learning_invitation(
    reply_text: str,
    *,
    truthful_limit: bool = False,
    normalize_turn_text_fn: Callable[[str], str],
) -> str:
    reply = str(reply_text or "").strip()
    if not reply:
        return reply

    normalized = normalize_turn_text_fn(reply)
    if "correct me" in normalized and ("store it" in normalized or "do better next time" in normalized):
        return reply

    if not truthful_limit:
        return reply

    suffix = "If you know the answer or want to correct me, tell me and I'll store it so I do better next time."
    return reply + " " + suffix


def truthful_limit_outcome(
    text: str = "",
    *,
    limitation: str = "cannot_verify",
    truthful_limit_reply_fn: Callable[..., str],
) -> dict[str, str]:
    return {
        "intent": "truthful_limit",
        "kind": str(limitation or "cannot_verify").strip().lower() or "cannot_verify",
        "reply_contract": "turn.truthful_limit",
        "reply_text": truthful_limit_reply_fn(text, limitation=limitation),
    }


def open_probe_reply(
    text: str,
    turns: Optional[list[tuple[str, str]]] = None,
    *,
    normalize_turn_text_fn: Callable[[str], str],
    truthful_limit_reply_fn: Callable[[str], str],
) -> tuple[str, str]:
    normalized = normalize_turn_text_fn(text)
    normalized_key = " ".join("".join(ch if ch.isalnum() or ch == " " else " " for ch in normalized).split())
    if normalized_key in {"can you help me a little here", "can you help me here"}:
        return (
            "What kind of help do you want?",
            "safe_fallback",
        )
    if normalized_key in {"what do you think then", "what now", "what next", "okay so what next", "where does that leave us"}:
        return (
            "I don't have enough context to answer that yet. Tell me the topic or decision you want help with, and I'll stay on it.",
            "safe_fallback",
        )
    if any(cue in normalized for cue in ("what are you talking about", "what are you talking", "what ?", "what?")):
        last_assistant = ""
        for role, txt in reversed(list(turns or [])):
            if str(role or "").strip().lower() == "assistant":
                last_assistant = str(txt or "").strip()
                break
        if last_assistant and any(token in last_assistant.lower() for token in ("allowlisted references", "web lookup", "web research")):
            return (
                "You're right. That response drifted into web lookup when you were asking a direct chat question. Ask it again and I'll answer it directly.",
                "clarification",
            )
        return (
            "You're right. I should stay with the current chat instead of jumping to web lookup for that kind of question.",
            "clarification",
        )
    return (
        truthful_limit_reply_fn(text),
        "safe_fallback",
    )


def last_question_recall_reply(
    text: str,
    turns: Optional[list[tuple[str, str]]] = None,
    *,
    extract_last_user_question_fn: Callable[[list[tuple[str, str]], str], str],
) -> tuple[str, str]:
    last_question = extract_last_user_question_fn(list(turns or []), text)
    if last_question:
        return f"Your last question before this one was: {last_question}", "recall"
    return "I don't have an earlier question in this active chat session.", "empty"


def session_fact_recall_reply(rule_result: dict) -> tuple[str, str]:
    target = str((rule_result or {}).get("fact_target") or "").strip().lower()
    value = str((rule_result or {}).get("fact_value") or "").strip()
    if value:
        return value.rstrip(".!?"), target or "fact"
    return "I do not have that fact in this active chat session.", "empty"