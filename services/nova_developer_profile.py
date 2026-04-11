from __future__ import annotations

import re
from typing import Callable, Optional


def extract_developer_color_preferences(session_turns: list[tuple[str, str]], *, known_colors: set[str]) -> list[str]:
    aliases = {"gus", "gustavo", "developer", "dev"}
    out: list[str] = []
    seen: set[str] = set()
    for role, text in session_turns:
        if role != "user":
            continue
        lowered = (text or "").lower().strip()
        if not any(alias in lowered for alias in aliases):
            continue
        if not any(keyword in lowered for keyword in ["color", "colors", "favourite", "favorite", "likes", "like", "bilingual", "english", "spanish"]):
            continue
        for word in re.findall(r"[a-z]{3,20}", lowered):
            if word in known_colors and word not in seen:
                seen.add(word)
                out.append(word)
    return out


def developer_fact_memory_probe(
    query: str,
    *,
    mem_enabled_fn: Callable[[], bool],
    mem_recall_fn: Callable[[str], str],
    get_active_user_fn: Callable[[], Optional[str]],
    default_local_user_id_fn: Callable[[], str],
    set_active_user_fn: Callable[[Optional[str]], None],
) -> str:
    if not mem_enabled_fn():
        return ""

    probe = mem_recall_fn(query)
    if probe:
        return probe

    active_user = (get_active_user_fn() or "").strip()
    fallback_user = default_local_user_id_fn()
    if not active_user or not fallback_user or active_user.lower() == fallback_user.lower():
        return ""

    set_active_user_fn(None)
    try:
        return mem_recall_fn(query)
    finally:
        set_active_user_fn(active_user)


def extract_developer_color_preferences_from_memory(
    *,
    mem_enabled_fn: Callable[[], bool],
    developer_fact_memory_probe_fn: Callable[[str], str],
    known_colors: set[str],
) -> list[str]:
    if not mem_enabled_fn():
        return []
    probe = developer_fact_memory_probe_fn("gustavo gus developer favorite colors color preference")
    if not probe:
        return []

    out: list[str] = []
    seen: set[str] = set()
    lines = [line.strip().lower() for line in probe.splitlines() if line.strip()]
    candidate_lines = [
        line for line in lines
        if any(alias in line for alias in ["gus", "gustavo", "developer"])
        and any(keyword in line for keyword in ["color", "colors", "favorite", "favourite", "likes", "like"])
    ]
    source = "\n".join(candidate_lines) if candidate_lines else probe
    for word in re.findall(r"[a-z]{3,20}", source.lower()):
        if word in known_colors and word not in seen:
            seen.add(word)
            out.append(word)
    return out


def is_developer_color_lookup_request(user_text: str) -> bool:
    lowered = (user_text or "").lower()
    if not any(keyword in lowered for keyword in ["color", "colors"]):
        return False
    return any(keyword in lowered for keyword in ["developer", "gus", "gustavo", "he", "his"])


def is_developer_bilingual_request(user_text: str) -> bool:
    lowered = (user_text or "").lower()
    if not any(keyword in lowered for keyword in ["developer", "gus", "gustavo", "he", "his"]):
        return False
    return any(keyword in lowered for keyword in ["bilingual", "english", "spanish", "languages", "language"])


def developer_is_bilingual(session_turns: list[tuple[str, str]]) -> Optional[bool]:
    aliases = ["developer", "gus", "gustavo"]
    for role, text in reversed(session_turns):
        if role != "user":
            continue
        lowered = (text or "").lower()
        if not any(alias in lowered for alias in aliases):
            continue
        if "bilingual" in lowered and ("english" in lowered or "spanish" in lowered):
            return True
        if "not bilingual" in lowered:
            return False
    return None


def developer_is_bilingual_from_memory(
    *,
    mem_enabled_fn: Callable[[], bool],
    developer_fact_memory_probe_fn: Callable[[str], str],
) -> Optional[bool]:
    if not mem_enabled_fn():
        return None
    probe = developer_fact_memory_probe_fn("is gustavo bilingual english spanish developer")
    lowered = (probe or "").lower()
    if not lowered:
        return None
    if ("gus" in lowered or "gustavo" in lowered or "developer" in lowered) and "bilingual" in lowered and ("english" in lowered or "spanish" in lowered):
        return True
    if "not bilingual" in lowered:
        return False
    return None


def recent_turn_mentions(turns: list[tuple[str, str]], keywords: list[str], limit: int = 6) -> bool:
    keys = [str(keyword or "").strip().lower() for keyword in keywords if str(keyword or "").strip()]
    if not keys:
        return False
    for role, text in reversed(turns[-max(1, int(limit)):]):
        lowered = (text or "").strip().lower()
        if not lowered:
            continue
        if any(keyword in lowered for keyword in keys):
            return True
    return False


def strip_confirmation_prefix(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    patterns = [
        r"^(?:yes|yeah|yep|correct|exactly|true|right)\b[\s,!.:-]*",
        r"^(?:you(?:'| a)?re\s+right|your\s+correct|that(?:'| i)?s\s+right)\b[\s,!.:-]*",
        r"^(?:yes\s+)?nova\b[\s,!.:-]*",
    ]
    changed = True
    while cleaned and changed:
        changed = False
        for pattern in patterns:
            newer = re.sub(pattern, "", cleaned, flags=re.I).strip()
            if newer != cleaned:
                cleaned = newer
                changed = True
    return cleaned


def extract_work_role_parts(raw: str, *, strip_confirmation_prefix_fn: Callable[[str], str]) -> list[str]:
    text = strip_confirmation_prefix_fn(raw)
    lowered = text.lower()
    role_parts: list[str] = []

    if "full stack developer" in lowered:
        role_parts.append("full stack developer")

    work_match = re.search(r"\bworks?\s+as\s+(.+)$", text, flags=re.I)
    if work_match:
        work_text = work_match.group(1)
        work_text = re.sub(r"^[^A-Za-z0-9]+", "", work_text).strip(" .,!?:;")
        if work_text:
            role_parts.append(work_text)

    normalized_roles: list[str] = []
    seen_roles: set[str] = set()
    for role in role_parts:
        cleaned = re.sub(r"\s+", " ", str(role or "").strip())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen_roles:
            continue
        seen_roles.add(key)
        normalized_roles.append(cleaned)
    return normalized_roles


def store_developer_role_facts(
    roles: list[str],
    *,
    input_source: str = "typed",
    mem_enabled_fn: Callable[[], bool],
    mem_add_fn: Callable[[str, str, str], object],
) -> tuple[bool, str]:
    if not roles or not mem_enabled_fn():
        return False, ""
    if len(roles) == 1:
        role_sentence = f"Gus works as a {roles[0]}."
    else:
        role_sentence = f"Gus works as a {roles[0]} and {roles[1]}."
    mem_add_fn("identity", input_source, role_sentence)
    return True, role_sentence.rstrip(".")


def extract_developer_roles_from_memory(
    *,
    mem_enabled_fn: Callable[[], bool],
    developer_fact_memory_probe_fn: Callable[[str], str],
) -> list[str]:
    if not mem_enabled_fn():
        return []
    probe = developer_fact_memory_probe_fn("gus gustavo developer works as role job title")
    if not probe:
        return []
    roles: list[str] = []
    seen: set[str] = set()
    for line in probe.splitlines():
        match = re.search(r"\bworks?\s+as\s+(.+?)(?:[.!?]|$)", line, flags=re.I)
        if not match:
            continue
        role_text = re.sub(r"^(?:a|an)\s+", "", match.group(1).strip(), flags=re.I)
        parts = re.split(r"\s+(?:and|&)\s+|\s*,\s*", role_text)
        for part in parts:
            cleaned = re.sub(r"\s+", " ", part).strip(" .,!?:;")
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            roles.append(cleaned)
    return roles


def format_fact_series(items: list[str]) -> str:
    values = [str(item or "").strip() for item in items if str(item or "").strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def is_developer_profile_request(user_text: str) -> bool:
    lowered = (user_text or "").strip().lower()
    if not lowered:
        return False

    creator_cues = [
        "who is your developer", "who's your developer", "who is your creator", "who's your creator",
        "who created you", "your creator", "is gus your creator", "so gus is your creator",
        "is gustavo your creator", "is he your creator", "creator is gus", "creator is gustavo",
    ]
    if any(cue in lowered for cue in creator_cues):
        return True
    if any(cue in lowered for cue in ["how did he develop you", "how did he developed you", "how did he build you", "how was he able to develop you", "what else does he"]):
        return True
    if not any(keyword in lowered for keyword in ["developer", "gus", "gustavo"]):
        return False
    cues = [
        "who is", "who's", "what do you know", "what else", "tell me about",
        "about your developer", "about gus", "about gustavo", "how did", "created you",
        "developed you", "built you",
    ]
    return any(cue in lowered for cue in cues)


def is_developer_work_guess_query(text: str, *, normalize_turn_text_fn: Callable[[str], str]) -> bool:
    lowered = normalize_turn_text_fn(text)
    if not lowered or "?" not in str(text or ""):
        return False
    targets_developer = any(token in lowered for token in ("gus", "gustavo", "developer", "creator", "he do"))
    work_intent = any(token in lowered for token in ("type of work", "kind of work", "what does", "job", "occupation", "work does"))
    return targets_developer and work_intent


def developer_work_guess_reply(text: str, *, is_developer_work_guess_query_fn: Callable[[str], bool]) -> str:
    if not is_developer_work_guess_query_fn(text):
        return ""
    return (
        "Based on the context so far, my grounded guess is that Gus works in software or technical data systems. "
        "If you confirm or correct that, I will store the verified role."
    )


def developer_work_guess_turn(
    text: str,
    *,
    developer_work_guess_reply_fn: Callable[[str], str],
    make_conversation_state_fn: Callable[..., dict],
) -> tuple[str, Optional[dict]]:
    reply = developer_work_guess_reply_fn(text)
    if not reply:
        return "", None
    return reply, make_conversation_state_fn("developer_role_guess", subject="Gus")


def learn_contextual_developer_facts(
    turns: list[tuple[str, str]],
    text: str,
    *,
    input_source: str = "typed",
    normalize_turn_text_fn: Callable[[str], str],
    recent_turn_mentions_fn: Callable[[list[tuple[str, str]], list[str]], bool],
    mem_enabled_fn: Callable[[], bool],
    mem_add_fn: Callable[[str, str, str], object],
    extract_color_preferences_from_text_fn: Callable[[str], list[str]],
    extract_work_role_parts_fn: Callable[[str], list[str]],
    store_developer_role_facts_fn: Callable[..., tuple[bool, str]],
    load_learned_facts_fn: Callable[[], dict],
    save_learned_facts_fn: Callable[[dict], None],
    timestamp_fn: Callable[[], str],
) -> tuple[bool, str]:
    raw = (text or "").strip()
    lowered = normalize_turn_text_fn(raw)
    if not raw:
        return False, ""

    relevant_context = recent_turn_mentions_fn(turns, ["gus", "gustavo", "developer", "creator"])
    if not relevant_context and not any(keyword in lowered for keyword in ["gus", "gustavo", "developer", "creator"]):
        return False, ""

    learned: list[str] = []

    color_match = re.search(r"\b(?:favorite|favourite)\s+colors?\s+are\s+(.+)$", raw, flags=re.I)
    if color_match and mem_enabled_fn():
        colors_text = re.sub(r"\s+and\s+he(?:'s|\s+is)\b.*$", "", color_match.group(1), flags=re.I).strip(" .,:;")
        colors = extract_color_preferences_from_text_fn(colors_text)
        if colors:
            pretty = ", ".join(colors[:-1]) + (f", and {colors[-1]}" if len(colors) > 1 else colors[0])
            mem_add_fn("identity", input_source, f"Gus favorite colors are {pretty}.")
            learned.append(f"Gus favorite colors are {pretty}")

    if "bilingual" in lowered and "english" in lowered and "spanish" in lowered and mem_enabled_fn():
        mem_add_fn("identity", input_source, "Gus is bilingual in English and Spanish.")
        learned.append("Gus is bilingual in English and Spanish")

    role_parts = extract_work_role_parts_fn(raw)
    learned_role, learned_role_text = store_developer_role_facts_fn(role_parts, input_source=input_source)
    if learned_role:
        learned.append(learned_role_text)

    same_location_cues = (
        "same as yours",
        "same as your location",
        "same location as yours",
        "same location as you",
    )
    references_developer_location = "location" in lowered and (
        relevant_context or any(keyword in lowered for keyword in ["gus", "gustavo", "developer", "creator"])
    )
    if references_developer_location and any(cue in lowered for cue in same_location_cues):
        facts = load_learned_facts_fn()
        if str(facts.get("developer_location_relation") or "").strip().lower() != "same_as_assistant":
            facts["developer_location_relation"] = "same_as_assistant"
            facts["updated_at"] = timestamp_fn()
            save_learned_facts_fn(facts)
            if mem_enabled_fn():
                mem_add_fn("identity", input_source, "Gus location is the same as Nova's location.")
            learned.append("Gus shares my location")

    if not learned:
        return False, ""
    return True, "Understood. I learned: " + "; ".join(learned) + "."