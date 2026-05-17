from __future__ import annotations

import re
from typing import Callable, Optional

def analyze_routing_text(
    turns: list[tuple[str, str]],
    text: str,
    *,
    evaluate_rules_fn: Callable[..., dict],
) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        return raw, ""
    rule_result = evaluate_rules_fn(raw, turns=turns, phase="rewrite")
    rewrite_text = str(rule_result.get("rewrite_text") or "").strip()
    if rewrite_text:
        return rewrite_text, str(rule_result.get("analysis_reason") or rule_result.get("rule_name") or "")
    return raw, ""


def is_explicit_command_like(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    if low in {"weather current location", "weather current"}:
        return True
    if low.startswith((
        "weather for ",
        "weather in ",
        "weather at ",
        "check weather for ",
        "check weather in ",
        "check weather at ",
    )):
        return True
    command_prefixes = (
        "screen",
        "camera ",
        "web ",
        "pulse",
        "nova pulse",
        "nova status",
        "self status",
        "status events",
        "update now",
        "update now confirm",
        "update now cancel",
        "apply update now",
        "location coords",
        "domains",
        "policy allow",
        "chat context",
        "ls",
        "read ",
        "find ",
        "health",
        "capabilities",
        "inspect",
        "behavior ",
        "learning ",
        "memory ",
        "mem ",
    )
    return any(low == prefix.strip() or low.startswith(prefix) for prefix in command_prefixes)


def determine_turn_direction(
    turns: list[tuple[str, str]],
    text: str,
    *,
    active_subject: str = "",
    pending_action: Optional[dict] = None,
    analyze_routing_text_fn: Callable[[list[tuple[str, str]], str], tuple[str, str]],
    classify_turn_acts_fn: Callable[..., set[str]],
    extract_memory_teach_text_fn: Callable[[str], str],
    is_identity_or_developer_query_fn: Callable[[str], bool],
    is_developer_color_lookup_request_fn: Callable[[str], bool],
    is_developer_bilingual_request_fn: Callable[[str], bool],
    is_color_lookup_request_fn: Callable[[str], bool],
    build_greeting_reply_fn: Callable[..., str],
    is_explicit_command_like_fn: Callable[[str], bool],
) -> dict:
    effective_query, analysis_reason = analyze_routing_text_fn(turns, text)
    low = (effective_query or "").strip().lower()
    raw_low = (text or "").strip().lower()
    turn_acts = classify_turn_acts_fn(
        effective_query,
        turns=turns,
        active_subject=active_subject,
        pending_action=pending_action,
    )

    primary = "general_chat"
    if "command" in turn_acts:
        primary = "explicit_command"
    elif "inform" in turn_acts and "mixed" not in turn_acts:
        primary = "generic_declarative"
    elif build_greeting_reply_fn(effective_query, active_user=""):
        primary = "greeting"

    identity_focused = False
    bypass_pattern_routes = False
    return {
        "primary": primary,
        "effective_query": effective_query,
        "analysis_reason": analysis_reason,
        "turn_acts": turn_acts,
        "identity_focused": identity_focused,
        "bypass_pattern_routes": bypass_pattern_routes,
    }
