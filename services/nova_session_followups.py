from __future__ import annotations

import re
from typing import Callable, Optional


def last_question_recall_reply(
    text: str,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
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


def session_recap_reply(
    turns: list[tuple[str, str]],
    current_text: str,
    *,
    is_session_recap_request_fn: Callable[[str], bool],
) -> str:
    current_low = (current_text or "").strip().lower()
    topics: list[str] = []

    for role, txt in turns:
        if role != "user":
            continue
        clean = re.sub(r"\s+", " ", (txt or "").strip())
        if not clean:
            continue
        low = clean.lower()
        if low == current_low:
            continue
        if is_session_recap_request_fn(clean):
            continue
        if len(clean) > 180:
            clean = clean[:177] + "..."
        topics.append(clean)

    if not topics:
        return "I do not have enough prior user turns in this session to recap yet."

    recent = topics[-6:]
    lines = ["Recap of this session so far:"]
    for index, topic in enumerate(recent, start=1):
        lines.append(f"{index}. {topic}")
    return "\n".join(lines)


def build_session_fact_sheet(
    turns: list[tuple[str, str]],
    max_chars: int = 1200,
    *,
    get_learned_fact_fn: Callable[[str, str], str],
    get_active_user_fn: Callable[[], str],
    get_name_origin_story_fn: Callable[[], str],
    get_saved_location_text_fn: Callable[[], str],
    extract_color_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_developer_color_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_developer_color_preferences_from_memory_fn: Callable[[], list[str]],
    developer_is_bilingual_fn: Callable[[list[tuple[str, str]]], Optional[bool]],
    developer_is_bilingual_from_memory_fn: Callable[[], Optional[bool]],
    extract_animal_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
) -> str:
    lines = []

    assistant_name = get_learned_fact_fn("assistant_name", "Nova").strip()
    developer_name = get_learned_fact_fn("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus").strip()
    active_user = str(get_active_user_fn() or "").strip()
    story = get_name_origin_story_fn().strip()

    if assistant_name:
        lines.append(f"Assistant name: {assistant_name}")
    if developer_name:
        lines.append(f"Developer full name: {developer_name}")
    if developer_nickname:
        lines.append(f"Developer nickname: {developer_nickname}")
    if active_user:
        lines.append(f"Active speaker identity: {active_user}")
    if story:
        lines.append(f"Name origin: {story[:220]}")

    saved_location = get_saved_location_text_fn()
    if saved_location:
        lines.append(f"Stored assistant location: {saved_location}")

    if get_learned_fact_fn("developer_location_relation", "").strip().lower() == "same_as_assistant":
        lines.append("Verified developer location relation: same as assistant")

    user_colors = extract_color_preferences_fn(turns)
    if user_colors:
        lines.append("User-stated color preferences: " + ", ".join(user_colors))

    developer_colors = extract_developer_color_preferences_fn(turns)
    if not developer_colors:
        developer_colors = extract_developer_color_preferences_from_memory_fn()
    if developer_colors:
        lines.append("Developer color preferences: " + ", ".join(developer_colors))

    bilingual = developer_is_bilingual_fn(turns)
    if bilingual is None:
        bilingual = developer_is_bilingual_from_memory_fn()
    if bilingual is True:
        lines.append("Developer languages: English, Spanish")

    animals = extract_animal_preferences_fn(turns)
    if animals:
        lines.append("User-stated animal preferences: " + ", ".join(animals))

    if not lines:
        return ""
    return "\n".join(lines)[:max_chars]
