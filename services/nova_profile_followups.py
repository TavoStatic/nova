from __future__ import annotations

from typing import Callable, Optional


def developer_color_reply(
    turns: list[tuple[str, str]],
    *,
    extract_developer_color_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_developer_color_preferences_from_memory_fn: Callable[[], list[str]],
    prefix_from_earlier_memory_fn: Callable[[str], str],
) -> str:
    prefs = extract_developer_color_preferences_fn(turns)
    from_memory = False
    if not prefs:
        prefs = extract_developer_color_preferences_from_memory_fn()
        from_memory = bool(prefs)
    if not prefs:
        return "I don't have Gus's color preferences yet."
    if len(prefs) == 1:
        reply = f"From what you've told me, Gus likes {prefs[0]}."
    else:
        reply = "From what you've told me, Gus likes these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."
    return prefix_from_earlier_memory_fn(reply) if from_memory else reply


def developer_bilingual_reply(
    turns: list[tuple[str, str]],
    *,
    developer_is_bilingual_fn: Callable[[list[tuple[str, str]]], Optional[bool]],
    developer_is_bilingual_from_memory_fn: Callable[[], Optional[bool]],
    prefix_from_earlier_memory_fn: Callable[[str], str],
) -> str:
    known = developer_is_bilingual_fn(turns)
    from_memory = False
    if known is None:
        known = developer_is_bilingual_from_memory_fn()
        from_memory = known is not None
    if known is True:
        reply = "Yes. From what you've told me, Gus is bilingual in English and Spanish."
        return prefix_from_earlier_memory_fn(reply) if from_memory else reply
    if known is False:
        reply = "From what I have, Gus is not bilingual."
        return prefix_from_earlier_memory_fn(reply) if from_memory else reply
    return "I don't have confirmed language details for Gus yet."


def color_reply(
    turns: list[tuple[str, str]],
    *,
    extract_color_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_color_preferences_from_memory_fn: Callable[[], list[str]],
    prefix_from_earlier_memory_fn: Callable[[str], str],
) -> str:
    prefs = extract_color_preferences_fn(turns)
    from_memory = False
    if not prefs:
        prefs = extract_color_preferences_from_memory_fn()
        from_memory = bool(prefs)
    if not prefs:
        return "You haven't told me a color preference in this current chat yet."
    if len(prefs) == 1:
        reply = f"You told me you like the color {prefs[0]}."
    else:
        reply = "You told me you like these colors: " + ", ".join(prefs[:-1]) + f", and {prefs[-1]}."
    return prefix_from_earlier_memory_fn(reply) if from_memory else reply


def animal_reply(
    turns: list[tuple[str, str]],
    *,
    extract_animal_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_animal_preferences_from_memory_fn: Callable[[], list[str]],
    prefix_from_earlier_memory_fn: Callable[[str], str],
) -> str:
    animals = extract_animal_preferences_fn(turns)
    from_memory = False
    if not animals:
        animals = extract_animal_preferences_from_memory_fn()
        from_memory = bool(animals)
    if not animals:
        return "You haven't told me animal preferences yet in this chat, and I can't find them in saved memory."
    if len(animals) == 1:
        reply = f"You told me you like {animals[0]}."
    else:
        reply = "You told me you like: " + ", ".join(animals[:-1]) + f", and {animals[-1]}."
    return prefix_from_earlier_memory_fn(reply) if from_memory else reply


def developer_profile_reply(
    turns: Optional[list[tuple[str, str]]] = None,
    user_text: str = "",
    *,
    get_learned_fact_fn: Callable[[str, str], str],
    extract_developer_roles_from_memory_fn: Callable[[], list[str]],
    extract_developer_color_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_developer_color_preferences_from_memory_fn: Callable[[], list[str]],
    developer_is_bilingual_fn: Callable[[list[tuple[str, str]]], Optional[bool]],
    developer_is_bilingual_from_memory_fn: Callable[[], Optional[bool]],
    prefix_from_earlier_memory_fn: Callable[[str], str],
    format_fact_series_fn: Callable[[list[str]], str],
) -> str:
    low = (user_text or "").lower()
    session_turns = turns if isinstance(turns, list) else []

    developer_name = get_learned_fact_fn("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus").strip()
    roles = extract_developer_roles_from_memory_fn()
    colors = extract_developer_color_preferences_fn(session_turns)
    if not colors:
        colors = extract_developer_color_preferences_from_memory_fn()
    bilingual = developer_is_bilingual_fn(session_turns)
    if bilingual is None:
        bilingual = developer_is_bilingual_from_memory_fn()

    if developer_nickname and developer_nickname.lower() != developer_name.lower():
        base_fact = f"His full name is {developer_name}, and he also goes by {developer_nickname}."
    else:
        base_fact = f"His full name is {developer_name}."

    if "how did" in low or "developed you" in low or "built you" in low:
        return prefix_from_earlier_memory_fn(f"{base_fact} He created me. I do not have detailed build-history notes in memory yet.")

    if "who is" in low or "who's" in low or "creator" in low:
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            return prefix_from_earlier_memory_fn(f"My developer is {developer_name}. {developer_nickname} is his nickname. He created me.")
        return prefix_from_earlier_memory_fn(f"My developer is {developer_name}. He created me.")

    extra_facts: list[str] = []
    if roles:
        extra_facts.append(f"Known work roles: {format_fact_series_fn(roles)}.")
    if colors:
        if len(colors) == 1:
            extra_facts.append(f"Known favorite color: {colors[0]}.")
        else:
            extra_facts.append(f"Known favorite colors: {format_fact_series_fn(colors)}.")
    if bilingual is True:
        extra_facts.append("He is bilingual in English and Spanish.")
    elif bilingual is False:
        extra_facts.append("Known bilingual note: not bilingual.")

    lead = "Here are the verified facts I have about my developer, Gus."
    if extra_facts:
        return prefix_from_earlier_memory_fn(" ".join([lead, base_fact] + extra_facts))
    return prefix_from_earlier_memory_fn(f"{lead} {base_fact} I don't have any additional verified information about him beyond that yet.")


def is_developer_location_request(
    user_text: str,
    *,
    state: Optional[dict] = None,
    turns: Optional[list[tuple[str, str]]] = None,
    recent_turn_mentions_fn: Callable[[list[tuple[str, str]], list[str]], bool],
) -> bool:
    low = (user_text or "").strip().lower()
    if not low:
        return False

    explicit_cues = [
        "where is gus",
        "where is gustavo",
        "where is your developer",
        "developer current location",
        "developer's current location",
        "gus current location",
        "gustavo current location",
    ]
    if any(cue in low for cue in explicit_cues):
        return True

    developer_context = False
    if isinstance(state, dict) and str(state.get("subject") or "") == "developer":
        developer_context = True
    elif turns:
        developer_context = recent_turn_mentions_fn(turns, ["gus", "gustavo", "developer", "creator"])

    pronoun_cues = ["his current location", "his location", "current whereabouts", "where is he"]
    return developer_context and any(cue in low for cue in pronoun_cues)


def developer_location_reply(
    *,
    get_learned_fact_fn: Callable[[str, str], str],
    get_saved_location_text_fn: Callable[[], str],
    prefix_from_earlier_memory_fn: Callable[[str], str],
) -> str:
    relation = get_learned_fact_fn("developer_location_relation", "").strip().lower()
    if relation == "same_as_assistant":
        preview = get_saved_location_text_fn()
        if preview:
            return prefix_from_earlier_memory_fn(f"Based on the verified relation you gave me, Gus's location is {preview}.")
        return "You told me Gus shares my location, but I do not have my own stored location yet. You can tell me: 'My location is ...'"
    return "I'm uncertain about Gus's current location. I do not have verified current whereabouts for him."


def developer_location_turn(
    text: str,
    *,
    state: Optional[dict] = None,
    turns: Optional[list[tuple[str, str]]] = None,
    is_developer_location_request_fn: Callable[..., bool],
    infer_profile_conversation_state_fn: Callable[[str], Optional[dict]],
    make_conversation_state_fn: Callable[..., dict],
    developer_location_reply_fn: Callable[[], str],
) -> tuple[str, Optional[dict]]:
    if not is_developer_location_request_fn(text, state=state, turns=turns):
        return "", None
    next_state = infer_profile_conversation_state_fn(text) or make_conversation_state_fn("identity_profile", subject="developer")
    return developer_location_reply_fn(), next_state


def identity_profile_followup_reply(
    subject: str,
    turns: Optional[list[tuple[str, str]]] = None,
    *,
    get_active_user_fn: Callable[[], str],
    get_learned_fact_fn: Callable[[str, str], str],
    speaker_matches_developer_fn: Callable[[], bool],
    extract_developer_roles_from_memory_fn: Callable[[], list[str]],
    extract_developer_color_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_developer_color_preferences_from_memory_fn: Callable[[], list[str]],
    developer_is_bilingual_fn: Callable[[list[tuple[str, str]]], Optional[bool]],
    developer_is_bilingual_from_memory_fn: Callable[[], Optional[bool]],
    get_name_origin_story_fn: Callable[[], str],
    extract_color_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_color_preferences_from_memory_fn: Callable[[], list[str]],
    extract_animal_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_animal_preferences_from_memory_fn: Callable[[], list[str]],
    format_fact_series_fn: Callable[[list[str]], str],
) -> str:
    active_user_raw = str(get_active_user_fn() or "").strip()
    developer_name = get_learned_fact_fn("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus").strip()
    session_turns = turns if isinstance(turns, list) else []

    if subject == "developer" or (subject == "self" and speaker_matches_developer_fn()):
        facts: list[str] = []
        roles = extract_developer_roles_from_memory_fn()
        colors = extract_developer_color_preferences_fn(session_turns)
        if not colors:
            colors = extract_developer_color_preferences_from_memory_fn()
        bilingual = developer_is_bilingual_fn(session_turns)
        if bilingual is None:
            bilingual = developer_is_bilingual_from_memory_fn()
        story = get_name_origin_story_fn().strip()

        if developer_name:
            facts.append(f"Developer full name: {developer_name}.")
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            facts.append(f"Developer nickname: {developer_nickname}.")
        if roles:
            facts.append(f"Known work roles: {format_fact_series_fn(roles)}.")
        if colors:
            facts.append(f"Known favorite colors: {format_fact_series_fn(colors)}.")
        if bilingual is True:
            facts.append("Known languages: English and Spanish.")
        elif bilingual is False:
            facts.append("Known language note: not bilingual.")
        if story:
            facts.append("Verified history: you gave me the name Nova.")

        if facts:
            lead = "Here are the other verified facts I have about you." if subject == "self" else "Here are the other verified facts I have about Gus."
            return lead + " " + " ".join(facts)
        return "I do not have more verified developer facts beyond the basics yet."

    facts = []
    colors = extract_color_preferences_fn(session_turns)
    if not colors:
        colors = extract_color_preferences_from_memory_fn()
    animals = extract_animal_preferences_fn(session_turns)
    if not animals:
        animals = extract_animal_preferences_from_memory_fn()

    if active_user_raw:
        facts.append(f"Verified name: {active_user_raw}.")
    if colors:
        facts.append(f"Known color preferences: {format_fact_series_fn(colors)}.")
    if animals:
        facts.append(f"Known animal preferences: {format_fact_series_fn(animals)}.")

    if facts:
        return "Here are the other verified personal facts I have. " + " ".join(facts)
    if active_user_raw:
        return f"Beyond your session identity as {active_user_raw}, I do not have other verified personal facts yet."
    return "I do not have more verified personal facts for this thread yet."


def identity_name_followup_reply(
    subject: str,
    *,
    get_active_user_fn: Callable[[], str],
    get_learned_fact_fn: Callable[[str, str], str],
    get_name_origin_story_fn: Callable[[], str],
    speaker_matches_developer_fn: Callable[[], bool],
) -> str:
    active_user_raw = str(get_active_user_fn() or "").strip()
    developer_name = get_learned_fact_fn("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus").strip()
    assistant_name = get_learned_fact_fn("assistant_name", "Nova").strip()
    story = get_name_origin_story_fn().strip()

    if subject == "developer" or (subject == "self" and speaker_matches_developer_fn()):
        parts = []
        if developer_name:
            parts.append(f"Your verified full name is {developer_name}.")
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            parts.append(f"You also go by {developer_nickname}.")
        if story:
            parts.append(f"You gave me the name {assistant_name}.")
        if parts:
            return " ".join(parts)

    if active_user_raw:
        return f"The verified name I have for you in this session is {active_user_raw}."

    return "I do not have a more detailed verified name record for this thread yet."


def developer_identity_followup_reply(
    turns: Optional[list[tuple[str, str]]] = None,
    *,
    name_focus: bool = False,
    get_learned_fact_fn: Callable[[str, str], str],
    get_name_origin_story_fn: Callable[[], str],
    extract_developer_roles_from_memory_fn: Callable[[], list[str]],
    extract_developer_color_preferences_fn: Callable[[list[tuple[str, str]]], list[str]],
    extract_developer_color_preferences_from_memory_fn: Callable[[], list[str]],
    developer_is_bilingual_fn: Callable[[list[tuple[str, str]]], Optional[bool]],
    developer_is_bilingual_from_memory_fn: Callable[[], Optional[bool]],
    format_fact_series_fn: Callable[[list[str]], str],
) -> str:
    developer_name = get_learned_fact_fn("developer_name", "Gustavo Uribe").strip()
    developer_nickname = get_learned_fact_fn("developer_nickname", "Gus").strip()
    assistant_name = get_learned_fact_fn("assistant_name", "Nova").strip()
    story = get_name_origin_story_fn().strip()
    session_turns = turns if isinstance(turns, list) else []
    roles = extract_developer_roles_from_memory_fn()
    colors = extract_developer_color_preferences_fn(session_turns)
    if not colors:
        colors = extract_developer_color_preferences_from_memory_fn()
    bilingual = developer_is_bilingual_fn(session_turns)
    if bilingual is None:
        bilingual = developer_is_bilingual_from_memory_fn()

    parts: list[str] = []
    if developer_name:
        parts.append(f"Your verified full name is {developer_name}.")
    if developer_nickname and developer_nickname.lower() != developer_name.lower():
        parts.append(f"You also go by {developer_nickname}.")
    if story:
        parts.append(f"You are the creator who gave me the name {assistant_name}. {story}")
    elif assistant_name:
        parts.append(f"You are confirmed as the creator tied to the name {assistant_name}.")

    if not name_focus:
        if roles:
            parts.append(f"Known work roles: {format_fact_series_fn(roles)}.")
        if colors:
            parts.append(f"Known favorite colors: {format_fact_series_fn(colors)}.")
        if bilingual is True:
            parts.append("Known languages: English and Spanish.")
        elif bilingual is False:
            parts.append("Known language note: not bilingual.")

    if parts:
        if name_focus:
            return "About your name and identity: " + " ".join(parts)
        return "Here are the richer verified developer facts I have about you. " + " ".join(parts)

    return "I have your name and creator role confirmed, but no deeper verified details yet."


def infer_profile_conversation_state(
    text: str,
    *,
    normalize_turn_text_fn: Callable[[str], str],
    evaluate_rule_state_fn: Callable[[str], dict],
    speaker_matches_developer_fn: Callable[[], bool],
    is_developer_color_lookup_request_fn: Callable[[str], bool],
    is_developer_bilingual_request_fn: Callable[[str], bool],
    is_color_lookup_request_fn: Callable[[str], bool],
    make_conversation_state_fn: Callable[..., dict],
) -> Optional[dict]:
    low = normalize_turn_text_fn(text)
    if not low:
        return None
    rule_result = evaluate_rule_state_fn(text)
    state_update = rule_result.get("state_update") if isinstance(rule_result, dict) else None
    if isinstance(state_update, dict):
        return state_update
    developer_confirmed = speaker_matches_developer_fn()
    developer_cues = (
        is_developer_color_lookup_request_fn(text)
        or is_developer_bilingual_request_fn(text)
        or "what do you know about gus" in low
        or "what else do you know about gus" in low
        or "who is your creator" in low
        or "who made you" in low
        or "creator" in low
    )
    self_cues = (
        is_color_lookup_request_fn(text)
        or "what animals do i like" in low
        or "which animals do i like" in low
        or "what do you know about me" in low
        or "what else do you know about me" in low
        or "what do you remember about me" in low
        or "do you remember me" in low
        or "what is my name" in low
        or "do you know my name" in low
    )
    if developer_confirmed and (developer_cues or self_cues):
        return make_conversation_state_fn("developer_identity", subject="developer")
    if developer_cues:
        return make_conversation_state_fn("identity_profile", subject="developer")
    if self_cues:
        return make_conversation_state_fn("identity_profile", subject="self")
    return None