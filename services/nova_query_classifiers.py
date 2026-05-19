from __future__ import annotations

import re


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _intent_fragments(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    normalized = _normalize(raw)
    fragments: list[str] = []
    if len(normalized) <= 260 and "\n" not in raw and "\r" not in raw:
        fragments.append(normalized)

    split_parts = [
        part.strip()
        for part in re.split(r"[\r\n]+|(?<=[.!?])\s+", raw)
        if part.strip()
    ]
    if split_parts:
        for part in (split_parts[0], split_parts[-1]):
            normalized_part = _normalize(part)
            if normalized_part and normalized_part not in fragments:
                fragments.append(normalized_part)
    return fragments


def _any_intent_fragment_contains(text: str, cues) -> bool:
    return any(cue in fragment for fragment in _intent_fragments(text) for cue in cues)


def _fragment_has_direct_cue(fragment: str, cue: str) -> bool:
    candidate = str(fragment or "").strip()
    if not candidate or cue not in candidate:
        return False
    if candidate.startswith(cue) or candidate.startswith(f"nova {cue}"):
        return True
    cue_index = candidate.find(cue)
    if cue_index > 90:
        return False
    before = candidate[:cue_index].strip(" '\"")
    if "answer to" in before or "question" in before:
        return False
    starters = (
        "actually",
        "so",
        "ok",
        "okay",
        "well",
        "nova",
        "can you",
        "could you",
        "would you",
        "do you",
        "does nova",
        "are you",
        "is your",
        "what",
        "who",
        "why",
        "where",
        "tell me",
        "show me",
        "give me",
        "prove",
        "proof",
        "allowed",
        "domain",
        "policy",
        "rules",
        "requirements",
        "developer",
        "creator",
        "gus",
        "gustavo",
    )
    return candidate.startswith(starters)


def _any_direct_intent_fragment_contains(text: str, cues) -> bool:
    return any(_fragment_has_direct_cue(fragment, cue) for fragment in _intent_fragments(text) for cue in cues)


def is_factual_identity_or_policy_query(text: str) -> bool:
    if not str(text or "").strip():
        return False
    cues = [
        "what is", "why is", "who is", "full name", "rules", "policy", "requirements",
        "attendance", "peims", "tsds", "tea",
    ]
    return _any_direct_intent_fragment_contains(text, cues)


def is_capability_query(text: str) -> bool:
    if not str(text or "").strip():
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
        "what are your capabilities",
        "what are your abilities",
        "prove all your abilities",
        "proof all your abilities",
        "show your abilities",
        "know what your capable",
        "know what you're capable",
        "capabilities",
    ]
    return _any_direct_intent_fragment_contains(text, cues)


def is_runtime_identity_query(text: str) -> bool:
    fragments = _intent_fragments(text)
    if not fragments:
        return False
    if any(term in fragment for fragment in fragments for term in ("capability", "capabilities", "ability", "abilities", "capable")):
        return False
    cues = (
        "who are you",
        "what are you",
        "are you just a chatbot",
        "are you just a chat bot",
        "just a chatbot",
        "just a chat bot",
        "more than a chatbot",
        "more then a chatbot",
        "more than a conversational ai",
        "more then a conversational ai",
    )
    return any(_fragment_has_direct_cue(fragment, cue) for fragment in fragments for cue in cues)


def is_policy_domain_query(text: str) -> bool:
    if not str(text or "").strip():
        return False
    cues = [
        "domain access",
        "allowed domains",
        "what domains",
        "policy",
        "web access",
        "which domains",
    ]
    return _any_direct_intent_fragment_contains(text, cues)


def is_action_history_query(text: str) -> bool:
    if not str(text or "").strip():
        return False
    fragments = _intent_fragments(text)
    for fragment in fragments:
        if not fragment.startswith(("why ", "nova why ")):
            continue
        if " you " not in f" {fragment} ":
            continue
        if any(action in fragment for action in ("answer", "respond", "say", "said", "give", "gave", "provide", "provided")):
            return True
    cues = [
        "what did you just do",
        "what did you do",
        "last action",
        "last tool",
        "what did you just run",
    ]
    return _any_direct_intent_fragment_contains(text, cues)


def is_student_data_attendance_rules_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    if not candidate:
        return False
    return "peims" in candidate and "attendance" in candidate and any(
        token in candidate for token in ("rule", "rules", "reporting", "report")
    )


def is_web_preferred_data_query(text: str) -> bool:
    candidate = (text or "").strip().lower()
    if not candidate:
        return False
    data_terms = (
        "peims",
        "tsds",
        "attendance",
        "ada",
        "submission",
        "submissions",
        "student data",
        "records",
        "reporting",
        "data system",
    )
    if not any(term in candidate for term in data_terms):
        return False
    broad_cues = (
        "anything about",
        "what do you know about",
        "tell me about",
        "explain",
        "overview",
        "summary",
        "information",
        "anything",
    )
    return any(cue in candidate for cue in broad_cues)


def is_conversational_clarification(text: str) -> bool:
    if not str(text or "").strip():
        return False
    cues = (
        "what are you talking about",
        "what are you talking",
        "are you sure about that information",
        "are you sure about that",
        "why i am not asking you",
        "why am i not asking you",
        "you will not find that information",
        "do you need help",
        "what ?",
        "what?",
    )
    return _any_direct_intent_fragment_contains(text, cues)


def is_identity_or_developer_query(text: str) -> bool:
    normalized_text = re.sub(r"\byor\b", "your", str(text or "").strip().lower())
    if not normalized_text:
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
    return _any_direct_intent_fragment_contains(normalized_text, cues)


def is_name_origin_question(text: str) -> bool:
    if not str(text or "").strip():
        return False
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
    return _any_direct_intent_fragment_contains(text, cues)


def is_assistant_name_query(text: str) -> bool:
    candidate = re.sub(r"\byor\b", "your", str(text or "").strip().lower())
    fragments = _intent_fragments(candidate)
    cues = [
        "what is your name",
        "what is your real name",
        "what's your name",
        "what's your real name",
        "are you sure that is your name",
        "your name is not",
        "is your name",
    ]
    if any(_fragment_has_direct_cue(fragment, cue) for fragment in fragments for cue in cues):
        return True
    return any(bool(re.search(r"\bare\s+\w*ou\s+sure\b.*\bname\b", fragment)) for fragment in fragments)


def is_self_identity_web_challenge(text: str) -> bool:
    candidate = str(text or "").strip().lower()
    candidate = re.sub(r"\byor\b", "your", candidate)
    fragments = _intent_fragments(candidate)
    if not any("web" in fragment for fragment in fragments):
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
    return any(
        any(cue in fragment for cue in identity_cues)
        and any(cue in fragment for cue in challenge_cues)
        for fragment in fragments
    )


def is_developer_full_name_query(text: str) -> bool:
    fragments = _intent_fragments(text)
    if not any("full name" in fragment for fragment in fragments):
        return False
    query_cues = ["what is", "what's", "tell me", "do you know", "can you tell me"]
    if "?" not in text and not any(cue in fragment for fragment in fragments for cue in query_cues):
        return False
    cues = ["developer", "gus", "nickname", "nick name", "his full name"]
    return any(cue in fragment for fragment in fragments for cue in cues)
