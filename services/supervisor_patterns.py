from __future__ import annotations

import followup_move_classifier as followup_moves
import re


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def looks_like_reflective_retry(low: str) -> bool:
    if not low:
        return False
    cues = (
        "if you think for a bit",
        "think for a bit",
        "keep trying",
        "keep thinking",
        "think about it",
        "look at this session",
        "look at this conversation",
        "big clue",
        "almost there",
        "read what you're saying",
        "read what your saying",
        "are you sure because i just gave you",
    )
    return any(cue in low for cue in cues)


def looks_like_self_location(low: str) -> bool:
    if not low:
        return False
    triggers = (
        "where is nova",
        "where are you",
        "your location",
        "what is your location",
        "what is your current location",
        "what is your current physical location",
        "where are you located",
        "where is nova located",
    )
    return any(trigger in low for trigger in triggers)


def looks_like_profile_certainty_followup(low: str) -> bool:
    if not low:
        return False
    return any(
        phrase in low
        for phrase in (
            "are you sure that is all",
            "is that all the information",
            "is that all you know",
            "are you sure that's all",
            "are you sure that is all the information",
        )
    )


def looks_like_smalltalk(low: str) -> bool:
    if not low:
        return False
    greeting_regex = re.compile(r"^(hi|hello|hey|good morning|good afternoon|good evening)([\s!,\.]|$)")
    if greeting_regex.match(low):
        return True
    if low in {"thanks", "thx"} or "thank you" in low:
        return True
    if re.fullmatch(r"how\s+are\s+you(?:\s+doing)?(?:\s+today)?(?:\s*\?)?", low):
        return True
    return any(phrase in low for phrase in ("ready to get to work", "ready to work", "ready when you are"))


def looks_like_capability_query(low: str) -> bool:
    if not low:
        return False
    cues = (
        "what can you do",
        "what do you do",
        "what do you do nova",
        "your abilities",
        "your ability",
        "what do you help with",
        "what do you do here",
        "what are you capable",
        "know what your capable",
        "know what you're capable",
        "capabilities",
    )
    return any(cue in low for cue in cues)


def looks_like_policy_domain_query(low: str) -> bool:
    if not low:
        return False
    cues = (
        "domain access",
        "allowed domains",
        "what domains",
        "policy",
        "web access",
        "which domains",
    )
    return any(cue in low for cue in cues)


def looks_like_assistant_name_query(low: str) -> bool:
    if not low:
        return False
    normalized = re.sub(r"\byor\b", "your", low)
    if any(
        cue in normalized
        for cue in (
            "what is your name",
            "what's your name",
            "are you sure that is your name",
            "your name is not",
            "is your name",
        )
    ):
        return True
    return bool(re.search(r"\bare\s+\w*ou\s+sure\b.*\bname\b", normalized))


def looks_like_self_identity_web_challenge(low: str) -> bool:
    if not low or "web" not in low:
        return False
    identity_cues = ("your name", "who you are", "who are you")
    challenge_cues = ("why should i", "why would i", "why do i need", "why use the web", "try to use the web")
    return any(cue in low for cue in identity_cues) and any(cue in low for cue in challenge_cues)


def name_origin_query_kind(low: str) -> str:
    if not low:
        return ""
    if (
        "full story behind your name" in low
        or "tell me the full story behind your name" in low
        or ("full story" in low and "name" in low)
    ):
        return "full_story"
    if any(
        cue in low
        for cue in (
            "where your name comes from",
            "where does your name come from",
            "where your name came from",
            "story behind your name",
            "story behing your name",
            "do you now know where your name comes from",
            "do you know where your name comes from",
            "what does your name mean",
        )
    ):
        return "source_recall"
    if (
        (("why are you called" in low) and "nova" in low)
        or (("why is your name" in low) and "nova" in low)
        or bool(re.search(r"\bwhy\s+your\s+called\s+nova\b", low))
        or bool(re.search(r"\bwhy\s+.*\bcalled\s+nova\b", low))
        or "why nova" in low
    ):
        return "why_called"
    return ""


def looks_like_developer_full_name_query(low: str) -> bool:
    if not low or "full name" not in low:
        return False
    query_cues = ("what is", "what's", "tell me", "do you know", "can you tell me")
    if "?" not in low and not any(cue in low for cue in query_cues):
        return False
    return any(cue in low for cue in ("developer", "gus", "nickname", "nick name", "his full name", "creator"))


def looks_like_creator_query(low: str) -> bool:
    if not low:
        return False
    creator_cues = (
        "who is your creator",
        "who's your creator",
        "who made you",
        "who created you",
        "who is your developer",
        "who's your developer",
        "so gus is your creator",
        "is gus your creator",
        "is gustavo your creator",
    )
    return any(cue in low for cue in creator_cues)


def looks_like_developer_profile_query(low: str) -> bool:
    if not low:
        return False
    creator_cues = (
        "who is your developer",
        "who's your developer",
        "who is your creator",
        "who's your creator",
        "who created you",
        "your creator",
        "is gus your creator",
        "so gus is your creator",
        "is gustavo your creator",
        "is he your creator",
        "creator is gus",
        "creator is gustavo",
    )
    if any(cue in low for cue in creator_cues):
        return True
    if not any(token in low for token in ("developer", "gus", "gustavo")):
        return False
    cues = (
        "who is",
        "who's",
        "what do you know",
        "what else",
        "tell me about",
        "about your developer",
        "about gus",
        "about gustavo",
        "how did",
        "created you",
        "developed you",
        "built you",
    )
    return any(cue in low for cue in cues)


def looks_like_identity_history_prompt(low: str) -> bool:
    if not low:
        return False
    cues = (
        "how did he develop you",
        "how did he developed you",
        "how did he build you",
        "how was he able to develop you",
        "what else does he",
        "tell me more about my name",
        "more about my name",
        "more about your name",
    )
    return any(cue in low for cue in cues)


def open_probe_kind(low: str) -> str:
    if not low:
        return ""
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
    if any(cue in low for cue in clarification_cues):
        return "clarification"
    normalized = re.sub(r"[^a-z0-9 ]+", " ", low)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in {
        "random question",
        "random question for ledger",
        "can you help me a little here",
        "can you help me here",
        "what do you think then",
        "what now",
        "what next",
        "okay so what next",
        "where does that leave us",
    }:
        return "safe_fallback"
    return ""


def looks_like_last_question_recall(low: str) -> bool:
    if not low:
        return False
    cues = (
        "what was my last question",
        "what was my previous question",
        "what did i just ask",
        "repeat my last question",
        "last thing i said",
    )
    return any(cue in low for cue in cues)


def session_fact_recall_target(low: str) -> str:
    if not low:
        return ""
    if "codeword" in low and any(cue in low for cue in ("what codeword", "which codeword")):
        return "codeword"
    if any(cue in low for cue in ("what topic", "were tracking", "we were tracking", "tracked topic")):
        return "topic"
    if "review" in low and "blocked" in low and any(cue in low for cue in ("what review", "which review")):
        return "review"
    if any(cue in low for cue in ("what is blocking it", "what's blocking it", "what is blocking that", "what's blocking that", "what blocked it")):
        return "blocker"
    if any(cue in low for cue in ("who owns", "who owned", "owner of")):
        return "owner"
    return ""


def extract_session_fact_bundle(text: str) -> dict[str, str]:
    raw = str(text or "").strip()
    if not raw:
        return {}

    paired = re.search(
        r"\bremember(?:\s+that|\s+for\s+this\s+session)?\b.*?\bcodeword\s+(?P<codeword>.+?)\s+and\s+(?:the\s+)?topic\s+(?P<topic>.+?)(?:[.!?]|$)",
        raw,
        flags=re.I,
    )
    if paired:
        return {
            "codeword": str(paired.group("codeword") or "").strip(" \t\r\n\"'.,!?"),
            "topic": str(paired.group("topic") or "").strip(" \t\r\n\"'.,!?"),
        }

    review = re.search(
        r"\bremember\s+that\s+the\s+(?P<review>.+?)\s+is\s+blocked\s+by\s+(?P<blocker>.+?)\s+and\s+owned\s+by\s+(?P<owner>.+?)(?:[.!?]|$)",
        raw,
        flags=re.I,
    )
    if review:
        return {
            "review": str(review.group("review") or "").strip(" \t\r\n\"'.,!?"),
            "blocker": str(review.group("blocker") or "").strip(" \t\r\n\"'.,!?"),
            "owner": str(review.group("owner") or "").strip(" \t\r\n\"'.,!?"),
        }

    return {}


def extract_session_fact_value(turns: list[tuple[str, str]], user_text: str, target: str) -> str:
    if not target:
        return ""
    current = normalize_text(user_text)
    skipped_current = False
    for role, text in reversed(list(turns or [])):
        if str(role or "").strip().lower() != "user":
            continue
        normalized = normalize_text(text)
        if not skipped_current and normalized == current:
            skipped_current = True
            continue
        bundle = extract_session_fact_bundle(str(text or ""))
        value = str(bundle.get(target) or "").strip()
        if value:
            return value
    return ""


def looks_like_session_fact_recall(
    low: str,
    *,
    turns: list[tuple[str, str]] | None = None,
    user_text: str = "",
) -> tuple[str, str]:
    target = session_fact_recall_target(low)
    if not target:
        return "", ""
    value = extract_session_fact_value(list(turns or []), user_text, target)
    return target, value


def looks_like_rules_query(low: str) -> bool:
    if not low:
        return False
    cues = (
        "do you have any rules",
        "what rules do you follow",
    )
    return any(cue in low for cue in cues)


def identity_history_kind(user_text: str, low: str, *, active_subject: str = "") -> str:
    if not low:
        return ""
    move = followup_moves.classify_followup_move(user_text, low)
    if name_origin_query_kind(low) or ("name" in low and any(token in low for token in ("tell me more", "more about", "go on", "continue"))):
        return "name_origin"
    if looks_like_creator_query(low):
        return "creator_question"
    developer_thread = active_subject.startswith("identity_profile:developer") or active_subject.startswith("developer_identity")
    self_thread = active_subject.startswith("identity_profile:self")
    if looks_like_identity_history_prompt(low):
        return "history_recall"
    if developer_thread and move == "continuation":
        return "history_recall"
    if self_thread and (
        move == "continuation"
        or ("name" in low and any(token in low for token in ("tell me more", "more about", "go on", "continue")))
    ):
        return "name_origin" if "name" in low else "history_recall"
    return ""


def extract_last_user_question(turns: list[tuple[str, str]], current_text: str) -> str:
    target = normalize_text(current_text)
    for role, text in reversed(list(turns or [])[:-1]):
        if str(role or "").strip().lower() != "user":
            continue
        candidate = str(text or "").strip()
        if not candidate:
            continue
        normalized = normalize_text(candidate)
        if normalized == target:
            continue
        if "?" in candidate or normalized.startswith((
            "what ", "who ", "why ", "how ", "when ", "where ", "which ",
            "do ", "does ", "did ", "can ", "could ", "would ", "will ", "are ", "is ",
        )):
            return candidate
    return ""