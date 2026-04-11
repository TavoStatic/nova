from __future__ import annotations

import re

from .turn_model import TurnUnderstanding


def mentions_location_phrase(text: str) -> bool:
    low = (text or "").lower()
    return any(
        phrase in low
        for phrase in (
            "location",
            "locaiton",
            "physical location",
            "physical locaiton",
        )
    )


def mentions_shared_location(text: str) -> bool:
    low = (text or "").lower()
    return any(
        cue in low
        for cue in (
            "our location",
            "same location",
            "shared location",
            "share the same location",
            "we share the same location",
            "for our location",
        )
    )


def understand_turn(text: str) -> TurnUnderstanding:
    cleaned = (text or "").strip()
    low = cleaned.lower()
    url_match = re.search(r"https?://[\w\-\./:?=&%]+", cleaned)
    return TurnUnderstanding(
        raw_text=text or "",
        text=cleaned,
        low=low,
        url=url_match.group(0) if url_match else "",
        mentions_location=mentions_location_phrase(low),
        mentions_shared_location=mentions_shared_location(low),
        mentions_weather="weather" in low and not low.startswith("web "),
    )