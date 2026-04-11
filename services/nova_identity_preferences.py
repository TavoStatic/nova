from __future__ import annotations

import re
from typing import Callable


def extract_color_preferences(session_turns: list[tuple[str, str]], *, known_colors: set[str]) -> list[str]:
    colors: list[str] = []
    seen: set[str] = set()
    for role, text in session_turns:
        if role != "user":
            continue
        lowered = (text or "").lower().strip()
        has_preference_signal = any(signal in lowered for signal in [
            "i like", "i love", "i prefer", "favorite color", "favourite color", "like the color",
        ]) or bool(re.search(r"\bi\s+(?:\w+\s+){0,3}like\b", lowered))
        if not has_preference_signal:
            continue

        tokens = re.findall(r"[a-z]{3,20}", lowered)
        found = [word for word in tokens if word in known_colors]
        if not found:
            continue

        for color in found:
            if color in seen:
                continue
            seen.add(color)
            colors.append(color)
    return colors


def extract_color_preferences_from_text(text: str, *, known_colors: set[str]) -> list[str]:
    tokens = re.findall(r"[a-z]{3,20}", (text or "").lower())
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in known_colors and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def extract_color_preferences_from_memory(
    *,
    mem_enabled_fn: Callable[[], bool],
    mem_recall_fn: Callable[[str], str],
    extract_color_preferences_from_text_fn: Callable[[str], list[str]],
) -> list[str]:
    if not mem_enabled_fn():
        return []
    probe = mem_recall_fn("what colors does the user like favorite color preference")
    return extract_color_preferences_from_text_fn(probe)


def extract_last_user_question(
    turns: list[tuple[str, str]],
    current_text: str,
    *,
    is_identity_or_developer_query_fn: Callable[[str], bool],
    is_color_lookup_request_fn: Callable[[str], bool],
    is_developer_color_lookup_request_fn: Callable[[str], bool],
    is_developer_bilingual_request_fn: Callable[[str], bool],
) -> str:
    target = (current_text or "").strip().lower()
    for role, text in reversed(turns[:-1]):
        if role != "user":
            continue
        candidate = (text or "").strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered == target:
            continue
        if (
            "?" in candidate
            or lowered.startswith(("what ", "who ", "why ", "how ", "when ", "where ", "which ", "do ", "does ", "did ", "can ", "could ", "would ", "will ", "are ", "is "))
            or is_identity_or_developer_query_fn(candidate)
            or is_color_lookup_request_fn(candidate)
            or is_developer_color_lookup_request_fn(candidate)
            or is_developer_bilingual_request_fn(candidate)
        ):
            return candidate
    return ""


def extract_animal_preferences(session_turns: list[tuple[str, str]], *, known_animals: set[str]) -> list[str]:
    animals: list[str] = []
    seen: set[str] = set()
    for role, text in session_turns:
        if role != "user":
            continue
        lowered = (text or "").lower().strip()
        has_signal = any(signal in lowered for signal in ["i like", "i love", "i prefer", "favorite animal", "favourite animal"]) or bool(re.search(r"\bi\s+(?:\w+\s+){0,3}like\b", lowered))
        if not has_signal:
            continue
        tokens = re.findall(r"[a-z]{3,20}", lowered)
        for word in tokens:
            if word not in known_animals:
                continue
            normalized = "birds" if word in {"bird", "birds"} else ("dogs" if word in {"dog", "dogs"} else word)
            if normalized in seen:
                continue
            seen.add(normalized)
            animals.append(normalized)
    return animals


def extract_animal_preferences_from_text(text: str, *, known_animals: set[str]) -> list[str]:
    tokens = re.findall(r"[a-z]{3,20}", (text or "").lower())
    out: list[str] = []
    seen: set[str] = set()
    for word in tokens:
        if word not in known_animals:
            continue
        normalized = "birds" if word in {"bird", "birds"} else ("dogs" if word in {"dog", "dogs"} else word)
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def extract_animal_preferences_from_memory(
    *,
    mem_enabled_fn: Callable[[], bool],
    mem_recall_fn: Callable[[str], str],
    extract_animal_preferences_from_text_fn: Callable[[str], list[str]],
) -> list[str]:
    if not mem_enabled_fn():
        return []
    probe = mem_recall_fn("what animals does the user like favorite animal preference")
    return extract_animal_preferences_from_text_fn(probe)


def is_color_animal_match_question(user_text: str) -> bool:
    lowered = (user_text or "").lower()
    return ("what color" in lowered or "which color" in lowered) and ("animal" in lowered or "animals" in lowered) and any(
        token in lowered for token in ["match", "best", "goes", "fit", "fits"]
    )


def pick_color_for_animals(colors: list[str], animals: list[str]) -> str:
    if not colors:
        return ""
    if len(colors) == 1:
        return colors[0]

    score = {color: 0 for color in colors}
    for color in colors:
        color_lower = color.lower()
        for animal in animals:
            animal_lower = animal.lower()
            if animal_lower in {"birds", "parrots", "eagles", "hawks"} and color_lower in {"red", "blue", "green", "yellow", "orange"}:
                score[color] += 2
            if animal_lower in {"dogs", "cats", "horses"} and color_lower in {"brown", "black", "white", "gray", "grey", "silver", "gold"}:
                score[color] += 1
    best = sorted(colors, key=lambda color: score.get(color, 0), reverse=True)
    return best[0]


def is_color_lookup_request(user_text: str) -> bool:
    lowered = (user_text or "").lower()
    direct = [
        "what color do i like",
        "what colors do i like",
        "which color do i like",
        "which colors do i like",
        "color i like",
        "colors i like",
    ]
    if any(fragment in lowered for fragment in direct):
        return True
    if "go back" in lowered and "color" in lowered:
        return True
    if "past chat" in lowered and "color" in lowered:
        return True
    return False