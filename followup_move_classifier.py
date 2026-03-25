from __future__ import annotations

import re
from typing import Optional


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def mentions_location_phrase(low: str) -> bool:
    if not low:
        return False
    return any(token in low for token in (
        "location",
        "locaiton",
        "physical location",
        "physical locaiton",
    ))


def uses_prior_reference(low: str) -> bool:
    if not low:
        return False
    return any(token in low.split() for token in ("that", "this", "it", "there"))


def compact_followup_text(low: str) -> str:
    compact = re.sub(r"[^a-z0-9 ]+", " ", str(low or ""))
    return re.sub(r"\s+", " ", compact).strip()


def looks_like_contextual_continuation(low: str) -> bool:
    compact = compact_followup_text(low)
    return compact in {
        "what did you find",
        "well what did you find",
        "what else",
        "anything else",
        "go on",
        "continue",
        "ok and then",
        "and then",
        "and",
    }


def looks_like_contextual_followup(low: str) -> bool:
    if not low:
        return False
    compact = compact_followup_text(low)
    if looks_like_contextual_continuation(compact):
        return True
    return len(compact.split()) <= 4 and uses_prior_reference(compact)


def extract_retrieval_result_index(low: str) -> Optional[int]:
    normalized = _normalize_text(low)
    if not normalized:
        return None
    match = re.search(r"\b(?:result|source|link|item)\s*(\d{1,2})\b", normalized)
    if match:
        try:
            return max(1, int(match.group(1)))
        except Exception:
            return None
    ordinal_map = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
    }
    for word, index in ordinal_map.items():
        if re.search(rf"\b{word}\b", normalized):
            return index
    return None


def looks_like_retrieval_followup(low: str) -> bool:
    normalized = _normalize_text(low).strip(" .,!?")
    if not normalized:
        return False
    if extract_retrieval_result_index(normalized) is not None:
        return True
    return looks_like_retrieval_continuation(normalized)


def looks_like_retrieval_continuation(low: str) -> bool:
    normalized = _normalize_text(low).strip(" .,!?")
    if not normalized:
        return False
    triggers = {
        "what else",
        "anything else",
        "go on",
        "continue",
        "tell me more",
        "more results",
        "another result",
        "another source",
        "next",
        "next result",
        "next source",
        "more sources",
        "and then",
    }
    if normalized in triggers:
        return True
    return any(token in normalized for token in ("more result", "another source", "another result", "next source", "next result"))


def looks_like_shared_location_reference(low: str) -> bool:
    if not low:
        return False
    normalized = _normalize_text(low)
    return (
        normalized in {"our location", "our location nova", "same location", "shared location"}
        or (("your" in normalized or "our" in normalized) and mentions_location_phrase(normalized))
        or "that location" in normalized
        or "that zip" in normalized
        or "that zip code" in normalized
        or "there" in normalized
    )


def looks_like_retrieval_meta_question(low: str) -> bool:
    normalized = _normalize_text(low)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in (
        "what type of resources",
        "what resources are you trying to fetch",
        "what kind of resources",
        "what sources are you trying to fetch",
        "what are you trying to fetch",
        "what did you find",
        "well what did you find",
    ))


def looks_like_affirmative_followup(low: str) -> bool:
    compact = _normalize_text(low)
    if not compact:
        return False
    return (
        compact in {"yes", "yeah", "yea", "sure", "okay", "ok", "please", "do that", "go ahead"}
        or compact.startswith("yes ")
        or compact.startswith("yeah ")
        or compact.startswith("yea ")
        or compact.startswith("please ")
        or "do that" in compact
    )


def looks_like_explicit_location_declaration(user_text: str) -> bool:
    raw = str(user_text or "").strip()
    if not raw:
        return False
    explicit_patterns = (
        r"^\s*the\s+(\d{5})\s+is\s+the\s+zip\s+code\s+for\s+your\s+current\s+physical\s+location\s*[.!?]*$",
        r"^\s*my\s+zip\s+is\s+(.+?)\s*[.!?]*$",
        r"^\s*set\s+location\s+to\s+(.+?)\s*[.!?]*$",
        r"^\s*(?:my|your|the)(?:\s+(?:current|physical))?\s+location\s+is\s+(.+?)\s*[.!?]*$",
        r"^\s*i\s*(?:am|m)\s+in\s+(.+?)\s*[.!?]*$",
        r"^\s*i\s+am\s+located\s+in\s+(.+?)\s*[.!?]*$",
        r"^\s*you\s+are\s+located\s+in\s+(.+?)\s*[.!?]*$",
        r"^\s*(?:living|based)\s+in\s+(.+?)\s*[.!?]*$",
    )
    return any(re.match(pattern, raw, flags=re.I) for pattern in explicit_patterns)


def _looks_like_clarification_probe(low: str) -> bool:
    if not low:
        return False
    normalized = _normalize_text(low)
    if str(low).strip().endswith("?") and normalized.strip(" .,!?") in {
        "what",
        "why",
        "how",
        "who",
        "where",
        "when",
    }:
        return True
    clarification_cues = (
        "what are you talking about",
        "what are you talking",
        "are you sure about that information",
        "are you sure about that",
        "why i am not asking you",
        "why am i not asking you",
        "you will not find that information",
        "do you need help",
    )
    return any(cue in low for cue in clarification_cues)


def extract_weather_followup_location_candidate(user_text: str, low: str) -> str:
    raw_text = str(user_text or "").strip()
    text = raw_text.strip(" .,!?")
    if not text or "?" in raw_text or _looks_like_clarification_probe(low) or len(text) > 80:
        return ""
    if looks_like_affirmative_followup(low):
        return ""
    if looks_like_explicit_location_declaration(text):
        return ""
    if "weather" in low or uses_prior_reference(low):
        return ""
    if any(token in low for token in ("your location", "our location", "same location", "shared location", "that location", "there")):
        return ""
    return text


def classify_followup_move(user_text: str, low: str) -> str:
    raw = str(user_text or "").strip()
    normalized = _normalize_text(raw)
    if not normalized:
        return ""
    if looks_like_explicit_location_declaration(raw):
        return "declaration"
    if _looks_like_clarification_probe(low):
        return "clarification"
    if extract_retrieval_result_index(normalized) is not None:
        return "selection"
    if looks_like_retrieval_meta_question(low):
        return "meta_question"
    if looks_like_affirmative_followup(low):
        return "affirmation"
    if looks_like_shared_location_reference(low):
        return "reference_answer"
    if looks_like_retrieval_continuation(low) or looks_like_contextual_continuation(low):
        return "continuation"
    if extract_weather_followup_location_candidate(raw, low):
        return "value_answer"
    return "other"


__all__ = [
    "classify_followup_move",
    "compact_followup_text",
    "extract_retrieval_result_index",
    "extract_weather_followup_location_candidate",
    "looks_like_affirmative_followup",
    "looks_like_contextual_continuation",
    "looks_like_contextual_followup",
    "looks_like_explicit_location_declaration",
    "looks_like_retrieval_followup",
    "looks_like_retrieval_continuation",
    "looks_like_retrieval_meta_question",
    "looks_like_shared_location_reference",
    "mentions_location_phrase",
    "uses_prior_reference",
]
