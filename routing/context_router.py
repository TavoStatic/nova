from __future__ import annotations

import re
from typing import Optional

from .turn_model import RouteDecision, TurnUnderstanding


_QUESTION_STARTERS = {
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "which",
}

_LOCATION_PREFIXES = (
    "use ",
    "try ",
    "check ",
    "look up ",
    "lookup ",
    "search ",
    "search for ",
    "for ",
    "in ",
    "at ",
    "the location is ",
    "my location is ",
    "location is ",
)


def _pending_weather_location_request(config: Optional[dict]) -> bool:
    payload = config if isinstance(config, dict) else {}
    pending = payload.get("pending_action") if isinstance(payload.get("pending_action"), dict) else {}
    return (
        str(pending.get("kind") or "").strip() == "weather_lookup"
        and str(pending.get("status") or "").strip() == "awaiting_location"
    )


def _points_to_runtime_location(turn: TurnUnderstanding) -> bool:
    low = turn.low
    if not turn.mentions_location:
        return False
    return bool(
        re.search(r"\b(?:your|nova|current|device|runtime|local)\b", low)
        or turn.mentions_shared_location
    )


def _strip_location_answer_prefix(value: str) -> str:
    candidate = value.strip(" \t\r\n.,!?")
    lowered = candidate.lower()
    changed = True
    while changed and candidate:
        changed = False
        for prefix in _LOCATION_PREFIXES:
            if lowered.startswith(prefix):
                candidate = candidate[len(prefix):].strip(" \t\r\n.,!?")
                lowered = candidate.lower()
                changed = True
                break
    return candidate


def _looks_like_location_answer(turn: TurnUnderstanding) -> str:
    text = turn.text.strip()
    if not text or text.endswith("?"):
        return ""
    first = (text.split(maxsplit=1)[0] if text.split() else "").strip(" ,.!?").lower()
    if first in _QUESTION_STARTERS:
        return ""
    candidate = _strip_location_answer_prefix(text)
    if not candidate:
        return ""
    if _points_to_runtime_location(TurnUnderstanding(
        raw_text=turn.raw_text,
        text=candidate,
        low=candidate.lower(),
        url=turn.url,
        mentions_location="location" in candidate.lower() or "locaiton" in candidate.lower(),
        mentions_shared_location=turn.mentions_shared_location,
        mentions_weather=turn.mentions_weather,
    )):
        return ""
    low_candidate = candidate.lower()
    if any(word in low_candidate for word in ("question", "asking", "asked", "because", "conversation")):
        return ""
    if re.fullmatch(r"\d{5}(?:-\d{4})?", candidate):
        return candidate
    if re.fullmatch(r"-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?", candidate):
        return candidate
    words = re.findall(r"[A-Za-z][A-Za-z.'-]*|\d{5}(?:-\d{4})?", candidate)
    if 1 <= len(words) <= 8 and len(candidate) <= 80:
        return candidate
    return ""


def classify_contextual_route(
    turn: TurnUnderstanding,
    *,
    config: Optional[dict] = None,
    base_route: RouteDecision,
) -> RouteDecision:
    if base_route.kind != "none":
        return base_route
    if _pending_weather_location_request(config):
        if _points_to_runtime_location(turn):
            return RouteDecision(kind="direct_tool", tool="weather_current_location")
        location = _looks_like_location_answer(turn)
        if location:
            return RouteDecision(kind="direct_tool", tool="weather_location", args=(location,))
    return base_route
