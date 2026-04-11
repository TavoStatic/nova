from __future__ import annotations

import re
from typing import Callable, Optional


def deterministic_identity_answer(
    user_text: str,
    *,
    assistant_name: str,
    developer_name: str,
    developer_nickname: str,
    active_user_raw: str,
    speaker_matches_developer_fn: Callable[[], bool],
    get_name_origin_story_fn: Callable[[], str],
    prefix_from_earlier_memory_fn: Callable[[str], str],
    extract_developer_color_preferences_from_memory_fn: Callable[[], list[str]],
    mem_get_recent_learned_fn: Callable[[int], list[str]],
) -> Optional[str]:
    t = (user_text or "").strip().lower()
    t = re.sub(r"\byor\b", "your", t)
    active_user = str(active_user_raw or "").strip().lower()

    if (
        re.search(r"\b(what\s+is|what'?s)\s+your\s+name\b", t)
        or re.search(r"\bwho\s+are\s+you\b", t)
        or re.search(r"\bare\s+\w*ou\s+sure\b.*\bname\b", t)
    ):
        return f"My name is {assistant_name}."

    if any(q in t for q in ["do you remember me", "do you know me"]):
        if speaker_matches_developer_fn():
            if developer_nickname and developer_nickname.lower() != developer_name.lower():
                return f"Yes. I remember you as {developer_name}, and you also go by {developer_nickname}."
            return f"Yes. I remember you as {developer_name}."
        if active_user_raw:
            return f"I remember your current session identity as {active_user_raw}. I do not have more verified personal facts yet."
        return "Uncertain. I do not have a verified user identity bound for this session yet."

    if re.search(r"\b(what\s+is|what'?s)\s+my\s+name\b", t) or "do you know my name" in t:
        if speaker_matches_developer_fn():
            return f"Your name is {developer_name}."
        if active_user_raw:
            return f"The only verified name I have for you in this session is {active_user_raw}."
        return "Uncertain. I do not have a verified name for you yet."

    why_name_query = (
        (("why are you called" in t) and "nova" in t)
        or (("why is your name" in t) and "nova" in t)
        or bool(re.search(r"\bwhy\s+your\s+called\s+nova\b", t))
        or bool(re.search(r"\bwhy\s+.*\bcalled\s+nova\b", t))
    )
    if why_name_query:
        story = get_name_origin_story_fn().strip()
        if story:
            low_story = story.lower()
            if "was given its name" in low_story and "creator" in low_story:
                return story
            return f"{assistant_name} was given its name by its creator, {developer_nickname}. {story}"
        return "I do not have a saved name-origin story yet. You can teach me with: remember this ..."

    full_story_query = (
        "full story behind your name" in t
        or "tell me the full story behind your name" in t
        or ("full story" in t and "name" in t)
    )
    if full_story_query:
        story = get_name_origin_story_fn().strip()
        if story:
            return story
        return "I do not have a saved full name-origin story yet. You can teach me with: remember this ..."

    if (
        "if you could name yourself" in t
        or "what name would you give yourself" in t
        or "if you had to rename yourself" in t
    ):
        return f"I would keep the name {assistant_name}."

    if "would you like to know the story behind your name" in t:
        return "Yes. Please share it, and I will remember it."

    if "where your name comes from" in t or "where your name came from" in t:
        story = get_name_origin_story_fn().strip()
        if story:
            return story
        return "I do not have a saved name-origin story yet. You can teach me with: remember this ..."

    if "who gave you that name" in t or "who gave you your name" in t:
        return prefix_from_earlier_memory_fn(f"My name was given by my developer, {developer_name} ({developer_nickname}).")

    creator_query = (
        bool(re.search(r"\bwho\s+is\s+your\s+creator\b", t))
        or bool(re.search(r"\bwho\s+made\s+you\b", t))
        or bool(re.search(r"\bwho\s+created\s+you\b", t))
        or bool(re.search(r"\bso\s+gus\s+is\s+your\s+creator\b", t))
        or bool(re.search(r"\bis\s+(?:gus|gustavo)\s+your\s+creator\b", t))
    )
    if creator_query:
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            return prefix_from_earlier_memory_fn(f"My creator is {developer_name}. He created me. {developer_nickname} is his nickname.")
        return prefix_from_earlier_memory_fn(f"My creator is {developer_name}. He created me.")

    if any(q in t for q in ["what do you know about me", "what else do you know about me", "what do you remember about me"]):
        facts = []
        if speaker_matches_developer_fn():
            facts.append(f"You are {developer_name}.")
            if developer_nickname and developer_nickname.lower() != developer_name.lower():
                facts.append(f"You also go by {developer_nickname}.")
            colors = extract_developer_color_preferences_from_memory_fn()
            if colors:
                if len(colors) == 1:
                    facts.append(f"Your known favorite color is {colors[0]}.")
                else:
                    facts.append("Your known favorite colors are " + ", ".join(colors[:-1]) + f", and {colors[-1]}.")
            story = get_name_origin_story_fn().strip()
            if story:
                facts.append("You gave me the name Nova.")
            if facts:
                return " ".join(facts)
        if active_user_raw:
            return f"I have one verified personal fact for this session: your name is {active_user_raw}. I do not have enough other structured personal facts yet."
        return "Uncertain. I do not have enough structured personal facts yet."

    if (
        "just knowing my name" in t
        or ("find out more" in t and "my name" in t)
        or ("know more about me" in t and "my name" in t)
    ):
        if speaker_matches_developer_fn():
            return (
                f"No. Knowing your name alone does not justify inventing more personal facts about you. "
                f"I should only state verified facts I actually learned, such as that you are {developer_name}."
            )
        if active_user_raw:
            return (
                f"No. Knowing the name {active_user_raw} alone is not enough for me to claim more personal facts. "
                "I should only use verified facts you explicitly gave me."
            )
        return "No. A name alone is not enough for me to claim personal facts. I should only use verified facts you explicitly gave me."

    my_full_name_query = (
        "my full name" in t
        or bool(re.search(r"\bif i am\s+gus\b.*\bfull name\b", t))
    )
    if my_full_name_query:
        developer_name_low = developer_name.lower()
        developer_nickname_low = developer_nickname.lower()
        if developer_name and (
            "i am gus" in t
            or (active_user and active_user in {developer_nickname_low, developer_name_low})
            or (developer_nickname_low and developer_nickname_low in t)
        ):
            return f"Your full name is {developer_name}."

    if "full name" in t and any(k in t for k in ["developer", "creator", "his", "gus", "nickname"]):
        if developer_nickname and developer_nickname.lower() != developer_name.lower():
            return prefix_from_earlier_memory_fn(f"My developer's full name is {developer_name}. {developer_nickname} is his nickname.")
        return prefix_from_earlier_memory_fn(f"My developer's full name is {developer_name}.")

    if t in {
        "what have you learned from me",
        "what have you learned from me?",
        "what did you learn from me",
        "what did you learn from me?",
        "show me what you've learned",
        "show me what you have learned",
    }:
        learned_items = mem_get_recent_learned_fn(5)
        if not learned_items:
            return "I haven't learned anything specific from you recently."
        return "Here's what I've learned from you recently:\n- " + "\n- ".join(learned_items)

    return None


def deterministic_truth_answer(
    user_text: str,
    *,
    is_self_identity_web_challenge_fn: Callable[[str], bool],
    self_identity_web_challenge_reply_fn: Callable[[], str],
    describe_capabilities_fn: Callable[[], str],
) -> Optional[str]:
    t = (user_text or "").strip().lower()
    t = re.sub(r"\byor\b", "your", t)

    if is_self_identity_web_challenge_fn(t):
        return self_identity_web_challenge_reply_fn()

    if bool(re.fullmatch(r"how\s+are\s+you\??", t)):
        return "I'm doing well, thanks for asking."

    if any(k in t for k in ["what are your abilities", "what are you capable", "know what your capable", "know what you're capable", "what can you do"]):
        return describe_capabilities_fn()

    if t in {"can you code", "can you code?", "do you code", "do you code?"}:
        return (
            "Yes. I can write code, debug it, and explain it. "
            "I just can’t scan your machine or execute system actions unless you trigger an explicit tool command."
        )

    if "scan my machine" in t or "scan my computer" in t or "run a scan" in t or "nmap" in t:
        return (
            "No. I can’t scan your machine or run tools like nmap by myself. "
            "Tell me what you want checked and I’ll give you safe commands to run, then paste the output and I’ll interpret it."
        )

    return None