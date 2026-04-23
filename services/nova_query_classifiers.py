from __future__ import annotations

import re


def is_factual_identity_or_policy_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    if not candidate:
        return False
    cues = [
        "what is", "why is", "who is", "full name", "rules", "policy", "requirements",
        "attendance", "peims", "tsds", "tea",
    ]
    return any(cue in candidate for cue in cues)


def is_capability_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    if not candidate:
        return False
    cues = [
        "what can you do",
        "what do you do",
        "what do you do nova",
        "what do you do?",
        "your abilities",
        "your ability",
        "what do you help with",
        "what do you do here",
        "what are you capable",
        "know what your capable",
        "know what you're capable",
        "capabilities",
    ]
    return any(cue in candidate for cue in cues)


def is_policy_domain_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    if not candidate:
        return False
    cues = [
        "domain access",
        "allowed domains",
        "what domains",
        "policy",
        "web access",
        "which domains",
    ]
    return any(cue in candidate for cue in cues)


def is_action_history_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    if not candidate:
        return False
    cues = [
        "what did you just do",
        "what did you do",
        "last action",
        "last tool",
        "what did you just run",
    ]
    return any(cue in candidate for cue in cues)


def is_identity_or_developer_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    candidate = re.sub(r"\byor\b", "your", candidate)
    if not candidate:
        return False
    cues = [
        "your name",
        "who are you",
        "developer",
        "creator",
        "full name",
        "name origin",
        "why are you called",
        "why is your name",
        "did you learn about your name",
        "do you remember me",
        "do you know me",
        "what is my name",
        "what's my name",
        "know my name",
        "just knowing my name",
        "what do you know about me",
        "what else do you know about me",
        "what do you remember about me",
    ]
    return any(cue in candidate for cue in cues)


def is_name_origin_question(text: str) -> bool:
    candidate = (text or "").strip().lower()
    cues = [
        "where your name comes from",
        "where does your name come from",
        "story behind your name",
        "story behing your name",
        "why are you called nova",
        "why nova",
        "do you know where your name comes from",
        "what does your name mean",
    ]
    return any(cue in candidate for cue in cues)


def is_assistant_name_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    candidate = re.sub(r"\byor\b", "your", candidate)
    cues = [
        "what is your name",
        "what's your name",
        "are you sure that is your name",
        "your name is not",
        "is your name",
    ]
    if any(cue in candidate for cue in cues):
        return True
    return bool(re.search(r"\bare\s+\w*ou\s+sure\b.*\bname\b", candidate))


def is_self_identity_web_challenge(text: str) -> bool:
    candidate = (text or "").strip().lower()
    candidate = re.sub(r"\byor\b", "your", candidate)
    if "web" not in candidate:
        return False
    identity_cues = (
        "your name",
        "who you are",
        "who are you",
    )
    challenge_cues = (
        "why should i",
        "why would i",
        "why do i need",
        "why use the web",
        "try to use the web",
    )
    return any(cue in candidate for cue in identity_cues) and any(cue in candidate for cue in challenge_cues)


def is_developer_full_name_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    if "full name" not in candidate:
        return False
    query_cues = ["what is", "what's", "tell me", "do you know", "can you tell me"]
    if "?" not in text and not any(cue in candidate for cue in query_cues):
        return False
    cues = ["developer", "gus", "nickname", "nick name", "his full name"]
    return any(cue in candidate for cue in cues)