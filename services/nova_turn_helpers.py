from __future__ import annotations

import re
from typing import Callable


def retrieval_status_reply(text: str) -> str:
    lowered = (text or "").strip().lower()
    if lowered in {"retrieving data", "retreiving data", "retrieving info", "retrieving information"}:
        return "What data do you want me to retrieve?"
    return ""


def is_location_request(user_text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    normalized = normalize_turn_text_fn(user_text)
    if not normalized:
        return False
    return any(
        cue in normalized
        for cue in (
            "where is nova",
            "where are you",
            "your location",
            "what is your location",
            "what is your current location",
            "what is your current physical location",
            "where are you located",
            "where is nova located",
        )
    )


def location_reply(
    *,
    runtime_device_location_payload_fn: Callable[[], dict],
    get_saved_location_text_fn: Callable[[], str],
) -> str:
    live = runtime_device_location_payload_fn()
    if live.get("available") and not live.get("stale"):
        accuracy = live.get("accuracy_m")
        accuracy_note = f" Accuracy about {int(round(float(accuracy)))}m." if accuracy is not None else ""
        return f"My current device location is {live.get('coords_text')}.{accuracy_note}"
    preview = get_saved_location_text_fn()
    if preview:
        return f"My location is {preview}."
    return "I don't have a stored location yet. You can tell me: 'My location is ...'"


def is_web_research_override_request(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    lowered = normalize_turn_text_fn(text)
    if not lowered:
        return False
    phrases = (
        "just use the web",
        "use the web for this",
        "only need web",
        "all you need is the web",
        "all you need is web",
        "need is the web",
        "no database",
        "dont use the database",
        "don't use the database",
        "use web instead",
        "search online instead",
    )
    return any(phrase in lowered for phrase in phrases)


def uses_prior_reference(user_text: str) -> bool:
    lowered = (user_text or "").strip().lower()
    if not lowered:
        return False
    triggers = [
        "that information", "that info", "that", "those", "it",
        "from that", "from those", "summarize that", "give me that",
        "can you give me that", "use that",
    ]
    return any(trigger in lowered for trigger in triggers)


def extract_memory_teach_text(
    text: str,
    *,
    memory_should_keep_text_fn: Callable[[str], tuple[bool, str]],
) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    cues = ["remember that", "remember this", "can you remember", "think you can remember"]
    if not any(cue in lowered for cue in cues):
        return ""

    cleaned = re.sub(
        r"(?is)\b(?:can\s+you\s+remember\s+that|think\s+you\s+can\s+remember\s+that|remember\s+that|remember\s+this)\b\s*\??",
        "",
        raw,
    ).strip(" .,!?")
    if not cleaned:
        return ""
    keep, _reason = memory_should_keep_text_fn(cleaned)
    return cleaned if keep else ""