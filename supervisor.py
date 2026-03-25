from __future__ import annotations

from collections import Counter
import active_task_constraints as active_tasks
import followup_move_classifier as followup_moves
import re
from typing import Any, Callable, Optional


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _status_line(name: str, status: str, message: str) -> str:
    label = str(status or "green").upper()
    clean = str(message or "").strip()
    return f"{label}: {name}" if not clean else f"{label}: {name} - {clean}"


_manager_active_subject = active_tasks.manager_active_subject
_manager_pending_action = active_tasks.manager_pending_action
_manager_retrieval_state = active_tasks.manager_retrieval_state


def _looks_like_reflective_retry(low: str) -> bool:
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


def _looks_like_self_location(low: str) -> bool:
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


def _looks_like_profile_certainty_followup(low: str) -> bool:
    if not low:
        return False
    return any(phrase in low for phrase in (
        "are you sure that is all",
        "is that all the information",
        "is that all you know",
        "are you sure that's all",
        "are you sure that is all the information",
    ))


def _looks_like_smalltalk(low: str) -> bool:
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


def _looks_like_capability_query(low: str) -> bool:
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


def _looks_like_policy_domain_query(low: str) -> bool:
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


def _looks_like_assistant_name_query(low: str) -> bool:
    if not low:
        return False
    normalized = re.sub(r"\byor\b", "your", low)
    if any(cue in normalized for cue in (
        "what is your name",
        "what's your name",
        "are you sure that is your name",
        "your name is not",
        "is your name",
    )):
        return True
    return bool(re.search(r"\bare\s+\w*ou\s+sure\b.*\bname\b", normalized))


def _looks_like_self_identity_web_challenge(low: str) -> bool:
    if not low or "web" not in low:
        return False
    identity_cues = ("your name", "who you are", "who are you")
    challenge_cues = ("why should i", "why would i", "why do i need", "why use the web", "try to use the web")
    return any(cue in low for cue in identity_cues) and any(cue in low for cue in challenge_cues)


def _name_origin_query_kind(low: str) -> str:
    if not low:
        return ""
    if (
        "full story behind your name" in low
        or "tell me the full story behind your name" in low
        or ("full story" in low and "name" in low)
    ):
        return "full_story"
    if any(
        cue in low for cue in (
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


def _looks_like_developer_full_name_query(low: str) -> bool:
    if not low or "full name" not in low:
        return False
    query_cues = ("what is", "what's", "tell me", "do you know", "can you tell me")
    if "?" not in low and not any(cue in low for cue in query_cues):
        return False
    return any(cue in low for cue in ("developer", "gus", "nickname", "nick name", "his full name", "creator"))


def _looks_like_creator_query(low: str) -> bool:
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


def _looks_like_developer_profile_query(low: str) -> bool:
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


def _looks_like_identity_history_prompt(low: str) -> bool:
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


def _open_probe_kind(low: str) -> str:
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


def _looks_like_last_question_recall(low: str) -> bool:
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


def _looks_like_rules_query(low: str) -> bool:
    if not low:
        return False
    cues = (
        "do you have any rules",
        "what rules do you follow",
    )
    return any(cue in low for cue in cues)


def _identity_history_kind(user_text: str, low: str, *, active_subject: str = "") -> str:
    if not low:
        return ""
    move = _classify_followup_move(user_text, low)
    if _name_origin_query_kind(low) or ("name" in low and any(token in low for token in ("tell me more", "more about", "go on", "continue"))):
        return "name_origin"
    if _looks_like_creator_query(low):
        return "creator_question"
    developer_thread = active_subject.startswith("identity_profile:developer") or active_subject.startswith("developer_identity")
    self_thread = active_subject.startswith("identity_profile:self")
    if _looks_like_identity_history_prompt(low):
        return "history_recall"
    if developer_thread and move == "continuation":
        return "history_recall"
    if self_thread and (
        move == "continuation"
        or ("name" in low and any(token in low for token in ("tell me more", "more about", "go on", "continue")))
    ):
        return "name_origin" if "name" in low else "history_recall"
    return ""


_mentions_location_phrase = followup_moves.mentions_location_phrase
_uses_prior_reference = followup_moves.uses_prior_reference
_compact_followup_text = followup_moves.compact_followup_text
_looks_like_contextual_continuation = followup_moves.looks_like_contextual_continuation
_looks_like_contextual_followup = followup_moves.looks_like_contextual_followup
_extract_retrieval_result_index = followup_moves.extract_retrieval_result_index
_looks_like_retrieval_followup = followup_moves.looks_like_retrieval_followup
_looks_like_retrieval_continuation = followup_moves.looks_like_retrieval_continuation
_looks_like_shared_location_reference = followup_moves.looks_like_shared_location_reference
_classify_followup_move = followup_moves.classify_followup_move
_looks_like_retrieval_meta_question = followup_moves.looks_like_retrieval_meta_question


def _last_assistant_turn(turns: list[tuple[str, str]]) -> str:
    for role, text in reversed(list(turns or [])):
        if str(role or "").strip().lower() == "assistant":
            return _normalize_text(text)
    return ""


def _looks_like_location_recall_query(low: str) -> bool:
    if not low:
        return False
    cues = (
        "where am i",
        "where am i located",
        "what's my location",
        "what is my location",
        "where is my location",
        "recall my location",
        "remember my location",
        "do you know my location",
        "can you recall my location",
        "can you remember my location",
    )
    return any(cue in low for cue in cues)


def _looks_like_location_name_query(low: str) -> bool:
    if not low:
        return False
    cues = (
        "give me the name to that location",
        "give me the name of that location",
        "whats the name of that location",
        "what's the name of that location",
        "what is the name of that location",
        "what location is that",
        "which location is that",
        "what city is that zip",
        "what city is that location",
        "name of that location",
        "name to that location",
    )
    if any(cue in low for cue in cues):
        return True
    return "location" in low and "name" in low and _uses_prior_reference(low)


def _looks_like_saved_location_weather_query(low: str) -> bool:
    normalized = _normalize_text(low)
    if not normalized:
        return False
    return normalized in {
        "weather",
        "weather now",
        "weather current",
        "weather today",
        "current weather",
        "what's the weather",
        "what is the weather",
        "what is the weather now",
        "what's the weather now",
    }


_looks_like_affirmative_followup = followup_moves.looks_like_affirmative_followup


def _looks_like_weather_lookup_request(low: str) -> bool:
    if not low or low.startswith("web ") or "weather" not in low:
        return False
    if _looks_like_saved_location_weather_query(low):
        return True
    return (
        "?" in low
        or any(
            phrase in low
            for phrase in (
                "give me",
                "get",
                "check",
                "show",
                "tell me",
                "what is",
                "what's",
                "today",
                "now",
                "current",
                "forecast",
                "temperature",
                "outside",
                "notice",
                "changes in the weather",
            )
        )
    )


def _looks_like_weather_meta_question(low: str) -> bool:
    normalized = _normalize_text(low)
    if not normalized or "weather" not in normalized:
        return False
    cues = (
        "how did you get the weather",
        "how did you get weather",
        "how are you getting the weather",
        "where did you get the weather",
        "weather information",
        "weather tool",
    )
    return any(cue in normalized for cue in cues)


def _extract_weather_request_location(user_text: str, low: str) -> str:
    raw = str(user_text or "").strip()
    if not raw or "weather" not in str(low or ""):
        return ""
    patterns = (
        r"\b(?:weather|forecast)\s+(?:for|in|at)\s+(.+?)\s*[.!?]*$",
        r"\b(?:what(?:'s|\s+is)\s+the\s+weather|check\s+the\s+weather|give\s+me\s+the\s+weather|show\s+me\s+the\s+weather)\s+(?:for|in|at)\s+(.+?)\s*[.!?]*$",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.I)
        if not match:
            continue
        candidate = str(match.group(1) or "").strip(" .,!?")
        if not candidate:
            continue
        if _looks_like_shared_location_reference(_normalize_text(candidate)):
            return ""
        return candidate
    return ""


_extract_weather_followup_location_candidate = followup_moves.extract_weather_followup_location_candidate
_looks_like_explicit_location_declaration = followup_moves.looks_like_explicit_location_declaration


def _extract_set_location_payload(user_text: str) -> dict[str, str]:
    raw = str(user_text or "").strip()
    if not raw or "?" in raw:
        return {}

    patterns = (
        ("set_location_explicit", r"^\s*the\s+(\d{5})\s+is\s+the\s+zip\s+code\s+for\s+your\s+current\s+physical\s+location\s*[.!?]*$"),
        ("set_location_explicit", r"^\s*my\s+zip\s+is\s+(.+?)\s*[.!?]*$"),
        ("set_location_explicit", r"^\s*set\s+location\s+to\s+(.+?)\s*[.!?]*$"),
        ("set_location_explicit", r"^\s*the\s+location\s+is\s+(.+?)\s*[.!?]*$"),
        ("set_location_explicit", r"^\s*(?:my|your|the)(?:\s+(?:current|physical))?\s+location\s+is\s+(.+?)\s*[.!?]*$"),
        ("set_location_explicit", r"^\s*i\s*(?:am|m)\s+in\s+(.+?)\s*[.!?]*$"),
        ("set_location_explicit", r"^\s*i\s+am\s+located\s+in\s+(.+?)\s*[.!?]*$"),
        ("set_location_explicit", r"^\s*you\s+are\s+located\s+in\s+(.+?)\s*[.!?]*$"),
        ("set_location_explicit", r"^\s*(?:living|based)\s+in\s+(.+?)\s*[.!?]*$"),
    )
    for matched_rule_name, pattern in patterns:
        match = re.match(pattern, raw, flags=re.I)
        if not match:
            continue
        location_value = str(match.group(1) or "").strip()
        if not location_value:
            return {}
        location_kind = "zip" if re.fullmatch(r"\d{5}", location_value) else "place"
        return {
            "matched_rule_name": matched_rule_name,
            "location_value": location_value,
            "location_kind": location_kind,
            "location_ack_kind": "fact_only" if location_kind == "zip" else "confirmed_location",
        }
    return {}


def _extract_store_fact_payload(user_text: str, low: str) -> dict[str, str]:
    raw = str(user_text or "").strip()
    normalized = str(low or "").strip()
    if not raw or not normalized:
        return {}

    patterns = (
        r"^(remember this|remember that|learn this|save this|store this)(?:\s*[:,-]\s*|\s+)(.+?)\s*$",
    )
    for pattern in patterns:
        match = re.match(pattern, raw, flags=re.I)
        if not match:
            continue
        fact_text = str(match.group(2) or "").strip(" .!?")
        if not fact_text:
            return {}
        return {
            "fact_text": fact_text,
            "store_fact_kind": "explicit_store",
            "user_commitment": "explicit",
            "memory_kind": "user_fact",
        }
    return {}


def store_fact_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "intent",
    entry_point: str = "",
) -> dict[str, Any]:
    del manager, turn, turns, entry_point
    if phase != "intent":
        return {"handled": False}
    payload = _extract_store_fact_payload(user_text, low)
    if not payload:
        return {"handled": False}
    return {
        "handled": True,
        "intent": "store_fact",
        **payload,
    }


def weather_lookup_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "intent",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, turns, entry_point
    if phase != "intent":
        return {"handled": False}

    context = active_tasks.resolve_active_task_context(manager)
    move = _classify_followup_move(user_text, low)
    pending_followup = active_tasks.bind_pending_weather_followup(context, user_text, low, move=move)
    if pending_followup:
        return {
            "handled": True,
            **pending_followup,
        }

    if _looks_like_saved_location_weather_query(low):
        return {"handled": False}

    if not _looks_like_weather_lookup_request(low):
        return {"handled": False}

    if _looks_like_weather_meta_question(low):
        return {"handled": False}

    if _looks_like_shared_location_reference(low):
        return {
            "handled": True,
            "intent": "weather_lookup",
            "weather_mode": "current_location",
            "ledger_stage": "weather_lookup",
            "grounded": True,
        }

    location_value = _extract_weather_request_location(user_text, low)
    if location_value:
        return {
            "handled": True,
            "intent": "weather_lookup",
            "weather_mode": "explicit_location",
            "location_value": location_value,
            "ledger_stage": "weather_lookup",
            "grounded": True,
        }

    return {
        "handled": True,
        "intent": "weather_lookup",
        "weather_mode": "clarify",
        "ledger_stage": "weather_lookup",
        "grounded": False,
    }


def _extract_last_user_question(turns: list[tuple[str, str]], current_text: str) -> str:
    target = _normalize_text(current_text)
    for role, text in reversed(list(turns or [])[:-1]):
        if str(role or "").strip().lower() != "user":
            continue
        candidate = str(text or "").strip()
        if not candidate:
            continue
        normalized = _normalize_text(candidate)
        if normalized == target:
            continue
        if "?" in candidate or normalized.startswith((
            "what ", "who ", "why ", "how ", "when ", "where ", "which ",
            "do ", "does ", "did ", "can ", "could ", "would ", "will ", "are ", "is ",
        )):
            return candidate
    return ""


def reflective_retry_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, entry_point
    if not _looks_like_reflective_retry(low):
        return {"handled": False}

    active_subject = _manager_active_subject(manager)
    if phase == "handle":
        if (
            active_subject in {"identity_profile:developer", "developer_identity:developer"}
            and _mentions_location_phrase(low)
            and any(token in low for token in ("gus", "gustavo", "his", "developer", "creator"))
        ):
            return {
                "handled": True,
                "action": "developer_location",
                "continuation": True,
                "ledger_stage": "developer_location",
                "intent": "developer_location",
                "grounded": True,
            }
        return {"handled": False}

    if _mentions_location_phrase(low) and any(token in low for token in ("gus", "gustavo", "his", "developer", "creator")):
        return {
            "handled": False,
            "rewrite_text": str(user_text or "").strip(),
            "analysis_reason": "reflective_retry_location_hint",
        }

    prior_question = _extract_last_user_question(list(turns or []), user_text)
    if prior_question:
        return {
            "handled": False,
            "rewrite_text": prior_question,
            "analysis_reason": "reflective_retry_prior_question",
        }
    return {"handled": False}


def self_location_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "handle" or not _looks_like_self_location(low):
        return {"handled": False}
    return {
        "handled": True,
        "action": "self_location",
        "next_state": {"kind": "location_recall"},
        "ledger_stage": "location_recall",
        "grounded": True,
    }


def location_recall_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}

    context = active_tasks.resolve_active_task_context(manager)
    if not context.is_location_recall():
        return {"handled": False}

    move = _classify_followup_move(user_text, low)
    if move == "clarification":
        return {"handled": False}
    if _looks_like_location_name_query(low):
        return {
            "handled": True,
            "action": "location_recall",
            "continuation": False,
            "next_state": {"kind": "location_recall"},
            "ledger_stage": "location_recall",
            "grounded": True,
        }
    if move in {"continuation", "reference_answer"} or _looks_like_location_recall_query(low):
        return {
            "handled": True,
            "action": "location_recall",
            "continuation": move == "continuation",
            "next_state": {"kind": "location_recall"},
            "ledger_stage": "location_recall",
            "grounded": True,
        }
    return {"handled": False}


def location_name_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, low, manager, turn, turns, phase, entry_point
    return {"handled": False}


def location_weather_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, low, manager, turn, turns, phase, entry_point
    return {"handled": False}


def retrieval_followup_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}

    context = active_tasks.resolve_active_task_context(manager)
    move = _classify_followup_move(user_text, low)
    binding = active_tasks.bind_retrieval_followup(context, move=move)
    if not binding:
        return {"handled": False}
    return {
        "handled": True,
        **binding,
    }


def _looks_like_deep_search_request(low: str) -> bool:
    if not low:
        return False
    cues = (
        "deep search",
        "dig up",
        "search deeper",
        "search more online",
        "look online for more",
    )
    return any(cue in low for cue in cues)


def _looks_like_online_research_request(low: str) -> bool:
    if not low:
        return False
    cues = (
        "research ",
        "online about ",
        "search online",
        "look online",
        "find online",
        "web research",
        "search the web",
    )
    return any(cue in low for cue in cues)


def _web_research_query_from_text(user_text: str, low: str) -> str:
    raw = str(user_text or "").strip()
    if not raw:
        return ""

    patterns = (
        r"^research\s+(.+?)\s+online\s*[.!?]*$",
        r"^research\s+(.+?)\s*[.!?]*$",
        r"^give me anything online about\s+(.+?)\s*[.!?]*$",
        r"^search online for\s+(.+?)\s*[.!?]*$",
        r"^look online for\s+(.+?)\s*[.!?]*$",
        r"^find online\s+(.+?)\s*[.!?]*$",
        r"^web research\s+(.+?)\s*[.!?]*$",
        r"^search the web for\s+(.+?)\s*[.!?]*$",
    )
    for pattern in patterns:
        match = re.match(pattern, raw, flags=re.I)
        if match:
            return str(match.group(1) or "").strip()

    if "online about " in low:
        idx = low.find("online about ") + len("online about ")
        return raw[idx:].strip(" .!?")
    return ""


def web_research_family_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "intent",
    entry_point: str = "",
) -> dict[str, Any]:
    del manager, turn, turns, entry_point
    if phase != "intent":
        return {"handled": False}

    request_kind = ""
    if _looks_like_deep_search_request(low):
        request_kind = "deep_search"
    elif _looks_like_online_research_request(low):
        request_kind = "research_prompt"
    else:
        return {"handled": False}

    query = _web_research_query_from_text(user_text, low)
    if not query:
        return {"handled": False}

    return {
        "handled": True,
        "intent": "web_research_family",
        "web_request_kind": request_kind,
        "tool_name": "web_research",
        "query": query,
        "ledger_stage": "web_research",
        "grounded": True,
    }


def name_origin_store_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del manager, turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}

    raw = str(user_text or "").strip()
    trigger = (
        "remember this nova" in low
        or "story behind your name" in low
        or "story behing your name" in low
        or "gus gave you your name" in low
        or "gus named you" in low
    )
    if not trigger:
        return {"handled": False}

    store_text = raw
    if "gus gave you your name" in low and "remember this" not in low:
        store_text = "Gus gave me the name Nova."
    elif "gus named you" in low and "remember this" not in low:
        store_text = raw if len(raw) >= 30 else "Gus named me Nova."

    return {
        "handled": True,
        "action": "name_origin_store",
        "store_text": store_text,
        "ledger_stage": "name_origin",
        "intent": "name_origin_store",
        "grounded": True,
    }


def profile_certainty_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, turn, turns, entry_point
    if phase != "handle" or not _looks_like_profile_certainty_followup(low):
        return {"handled": False}

    context = active_tasks.resolve_active_task_context(manager)
    if context.is_developer_identity_thread():
        return {
            "handled": True,
            "action": "developer_identity_followup",
            "continuation": True,
            "name_focus": False,
            "ledger_stage": "profile_followup",
            "intent": "conversation_followup",
            "grounded": True,
        }
    if context.is_identity_profile_thread():
        subject = context.identity_profile_subject() or "self"
        return {
            "handled": True,
            "action": "identity_profile_followup",
            "continuation": True,
            "subject": subject or "self",
            "ledger_stage": "profile_followup",
            "intent": "conversation_followup",
            "grounded": True,
        }
    return {"handled": False}


def identity_history_family_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}
    if any(trigger in low for trigger in ("remember this", "learn this", "save this", "store")):
        return {"handled": False}

    context = active_tasks.resolve_active_task_context(manager)
    active_subject = context.active_subject
    outcome_kind = _identity_history_kind(user_text, low, active_subject=active_subject)
    if not outcome_kind:
        return {"handled": False}

    subject = "developer"
    if active_subject.startswith("identity_profile:"):
        subject = active_subject.split(":", 1)[1] if ":" in active_subject else "self"
    elif active_subject.startswith("developer_identity"):
        subject = "developer"
    elif outcome_kind == "name_origin":
        subject = "self"

    return {
        "handled": True,
        "action": "identity_history_family",
        "identity_history_kind": outcome_kind,
        "name_origin_query_kind": _name_origin_query_kind(low) or "source_recall",
        "subject": subject or "developer",
        "continuation": active_subject.startswith("identity_profile") or active_subject.startswith("developer_identity"),
        "ledger_stage": "identity_history",
        "intent": "identity_history_family",
        "grounded": True,
    }


def open_probe_family_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}
    probe_kind = _open_probe_kind(low)
    if not probe_kind:
        return {"handled": False}
    return {
        "handled": True,
        "action": "open_probe_family",
        "open_probe_kind": probe_kind,
        "ledger_stage": "open_probe",
        "intent": "open_probe_family",
        "grounded": False,
    }


def last_question_recall_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, entry_point
    if phase != "handle" or not _looks_like_last_question_recall(low):
        return {"handled": False}
    if not _extract_last_user_question(list(turns or []), low):
        return {
            "handled": True,
            "action": "last_question_recall",
            "ledger_stage": "session_history",
            "intent": "last_question_recall",
            "grounded": True,
            "last_question_available": False,
        }
    return {
        "handled": True,
        "action": "last_question_recall",
        "ledger_stage": "session_history",
        "intent": "last_question_recall",
        "grounded": True,
        "last_question_available": True,
    }


def rules_list_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "handle" or not _looks_like_rules_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "action": "rules_list",
        "ledger_stage": "policy_rules",
        "intent": "rules_list",
        "grounded": True,
    }


def developer_profile_state_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del user_text, manager, turn, turns, entry_point
    if phase != "state" or not _looks_like_developer_profile_query(low):
        return {"handled": False}
    return {
        "handled": False,
        "state_update": {"kind": "identity_profile", "subject": "developer"},
    }


def apply_correction_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del turn, turns, entry_point
    if phase != "handle":
        return {"handled": False}
    context = active_tasks.resolve_active_task_context(manager)
    raw = str(user_text or "").strip()
    identity_correction_patterns = (
        r"\byour\s+name\s+is\s+[a-z]",
        r"\b(?:his|the\s+developer(?:'s)?)\s+full\s+name\s+is\s+[a-z]",
        r"\bdeveloper(?:'s)?\s+name\s+is\s+[a-z]",
        r"\bcreator(?:'s)?\s+full\s+name\s+is\s+[a-z]",
    )
    if context.is_correction_pending() and raw and "?" not in raw:
        return {
            "handled": True,
            "action": "apply_correction",
            "user_correction_text": user_text,
            "continuation": True,
            "ledger_stage": "correction_feedback",
            "intent": "apply_correction",
            "grounded": True,
        }
    triggers = [
        "wrong", "no,", "actually", "that's not", "not true", "incorrect",
        "mistake", "you lied", "that's wrong", "no it's not", "correction:",
        "you gave me garbage", "garbage back",
    ]
    if any(trigger in low for trigger in triggers) or (
        "?" not in raw and any(re.search(pattern, low) for pattern in identity_correction_patterns)
    ):
        return {
            "handled": True,
            "action": "apply_correction",
            "user_correction_text": user_text,
            "ledger_stage": "correction_feedback",
            "intent": "apply_correction",
            "grounded": True,
        }
    return {"handled": False}


def smalltalk_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, turn, kwargs
    context = active_tasks.resolve_active_task_context(manager)
    if context.is_correction_pending():
        return {"handled": False}
    if not _looks_like_smalltalk(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "smalltalk",
        "confidence": 0.95,
    }


def capability_query_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not _looks_like_capability_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "capability_query",
        "confidence": 0.95,
    }


def policy_domain_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not _looks_like_policy_domain_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "policy_domain_query",
        "confidence": 0.95,
    }


def assistant_name_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not _looks_like_assistant_name_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "assistant_name",
        "confidence": 0.95,
    }


def self_identity_web_challenge_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not _looks_like_self_identity_web_challenge(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "self_identity_web_challenge",
        "confidence": 0.95,
    }


def name_origin_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if (
        "remember this nova" in low
        or "gus gave you your name" in low
        or "gus named you" in low
    ):
        return {"handled": False}
    query_kind = _name_origin_query_kind(low)
    if not query_kind:
        return {"handled": False}
    return {
        "handled": True,
        "intent": "name_origin",
        "name_origin_query_kind": query_kind,
        "confidence": 0.94,
    }


def developer_full_name_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if not _looks_like_developer_full_name_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "developer_full_name",
        "confidence": 0.95,
    }


def developer_profile_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    if _looks_like_creator_query(low):
        return {
            "handled": True,
            "intent": "creator_identity",
            "confidence": 0.94,
        }
    if not _looks_like_developer_profile_query(low):
        return {"handled": False}
    return {
        "handled": True,
        "intent": "developer_profile",
        "confidence": 0.92,
    }


def session_summary_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    **kwargs,
) -> dict[str, Any]:
    del user_text, manager, turn, kwargs
    triggers = [
        "what happened", "recap", "summarize", "digest", "review chat",
        "what did we talk about", "session summary", "what's going on",
    ]
    if any(trigger in low for trigger in triggers):
        return {
            "handled": True,
            "intent": "session_summary",
            "target": "current_session_only",
            "confidence": 0.95,
        }
    return {"handled": False}


def set_location_rule(
    user_text: str,
    low: str,
    manager: Any,
    turn: int,
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    phase: str = "handle",
    entry_point: str = "",
) -> dict[str, Any]:
    del low, manager, turn, turns, entry_point
    if phase != "intent":
        return {"handled": False}
    payload = _extract_set_location_payload(user_text)
    if not payload:
        return {"handled": False}
    return {
        "handled": True,
        "intent": "set_location",
        "rule_name": str(payload.get("matched_rule_name") or "set_location_explicit"),
        "location_value": str(payload.get("location_value") or "").strip(),
        "location_kind": str(payload.get("location_kind") or "place").strip(),
        "location_ack_kind": str(payload.get("location_ack_kind") or "confirmed_location").strip(),
    }


_EXPLICIT_INTENT_OWNERSHIP_RULES = frozenset({
    "store_fact",
    "web_research_family",
    "weather_lookup",
    "set_location",
    "capability_query",
    "policy_domain_query",
    "assistant_name",
    "self_identity_web_challenge",
})


_EXPLICIT_HANDLE_OWNERSHIP_RULES = frozenset({
    "reflective_retry",
    "profile_certainty",
    "identity_history_family",
    "open_probe_family",
    "self_location",
    "location_recall",
    "retrieval_followup",
    "name_origin_store",
    "apply_correction",
    "rules_list",
    "last_question_recall",
})


def _result_is_explicitly_owned(rule_name: str, result: dict[str, Any], *, phase: str) -> bool:
    if not bool(result.get("handled")):
        return False
    if bool(result.get("required_safety_intercept")) or bool(result.get("required_policy_intercept")):
        return True
    if str(result.get("ownership") or "").strip().lower() == "explicit":
        return True

    normalized_rule_name = str(rule_name or "").strip()
    normalized_phase = str(phase or "handle").strip().lower()
    if normalized_phase == "intent":
        return normalized_rule_name in _EXPLICIT_INTENT_OWNERSHIP_RULES
    if normalized_phase == "handle":
        return normalized_rule_name in _EXPLICIT_HANDLE_OWNERSHIP_RULES
    return False


class Supervisor:
    def __init__(self) -> None:
        self.probes: dict[str, Callable[[dict], tuple[str, str]]] = {
            "entrypoint_parity": self.probe_entrypoint_parity,
            "continuation_drop": self.probe_continuation_drop,
            "pending_action_leak": self.probe_pending_action_leak,
            "override_consistency": self.probe_override_consistency,
            "thin_answer_frequency": self.probe_thin_answer_frequency,
            "identity_location_route": self.probe_identity_location_route,
            "rule_coverage": self.probe_rule_coverage,
        }
        self.rules: list[dict[str, Any]] = []
        self.register_rule("reflective_retry", reflective_retry_rule, priority=30, phases=("rewrite", "handle"))
        self.register_rule("profile_certainty", profile_certainty_rule, priority=35, phases=("handle",))
        self.register_rule("identity_history_family", identity_history_family_rule, priority=36, phases=("handle",))
        self.register_rule("open_probe_family", open_probe_family_rule, priority=37, phases=("handle",))
        self.register_rule("last_question_recall", last_question_recall_rule, priority=39, phases=("handle",))
        self.register_rule("rules_list", rules_list_rule, priority=41, phases=("handle",))
        self.register_rule("developer_profile_state", developer_profile_state_rule, priority=38, phases=("state",))
        self.register_rule("self_location", self_location_rule, priority=40, phases=("handle",))
        self.register_rule("location_recall", location_recall_rule, priority=42, phases=("handle",))
        self.register_rule("location_name", location_name_rule, priority=44, phases=("handle",))
        self.register_rule("location_weather", location_weather_rule, priority=46, phases=("handle",))
        self.register_rule("retrieval_followup", retrieval_followup_rule, priority=47, phases=("handle",))
        self.register_rule("name_origin_store", name_origin_store_rule, priority=50, phases=("handle",))
        self.register_rule("apply_correction", apply_correction_rule, priority=60, phases=("handle",))
        self.register_rule("store_fact", store_fact_rule, priority=62, phases=("intent",))
        self.register_rule("web_research_family", web_research_family_rule, priority=62, phases=("intent",))
        self.register_rule("weather_lookup", weather_lookup_rule, priority=62, phases=("intent",))
        self.register_rule("set_location", set_location_rule, priority=62, phases=("intent",))
        self.register_rule("smalltalk", smalltalk_rule, priority=61, phases=("intent",))
        self.register_rule("capability_query", capability_query_rule, priority=63, phases=("intent",))
        self.register_rule("policy_domain_query", policy_domain_rule, priority=64, phases=("intent",))
        self.register_rule("assistant_name", assistant_name_rule, priority=66, phases=("intent",))
        self.register_rule("self_identity_web_challenge", self_identity_web_challenge_rule, priority=67, phases=("intent",))
        self.register_rule("name_origin", name_origin_rule, priority=68, phases=("intent",))
        self.register_rule("developer_full_name", developer_full_name_rule, priority=69, phases=("intent",))
        self.register_rule("developer_profile", developer_profile_rule, priority=70, phases=("intent",))
        self.register_rule("session_summary", session_summary_rule, priority=71, phases=("intent",))
        self.reset()

    def register_rule(
        self,
        name: str,
        rule: Callable[..., dict[str, Any]],
        *,
        priority: int = 100,
        phases: tuple[str, ...] = ("handle",),
    ) -> None:
        self.rules = [item for item in self.rules if str(item.get("name") or "") != str(name or "")]
        self.rules.append({
            "name": str(name or "").strip(),
            "rule": rule,
            "priority": int(priority),
            "phases": tuple(str(phase or "handle").strip().lower() for phase in phases if str(phase or "").strip()),
        })
        self.rules.sort(key=lambda item: (int(item.get("priority", 100)), str(item.get("name") or "")))

    def evaluate_rules(
        self,
        user_text: str,
        *,
        manager: Any = None,
        turns: Optional[list[tuple[str, str]]] = None,
        phase: str = "handle",
        entry_point: str = "",
    ) -> dict[str, Any]:
        normalized_user_text = str(user_text or "")
        normalized_manager = {} if manager is None else manager
        normalized_turns = list(turns or [])
        normalized_phase = str(phase or "handle").strip().lower() or "handle"
        normalized_entry_point = str(entry_point or "").strip().lower()
        low = _normalize_text(normalized_user_text)
        turn = len(normalized_turns)
        candidates: list[dict[str, Any]] = []
        for item in self.rules:
            phases = tuple(item.get("phases") or ())
            if normalized_phase not in phases:
                continue
            rule_name = str(item.get("name") or "")
            try:
                result = item["rule"](
                    normalized_user_text,
                    low,
                    normalized_manager,
                    turn,
                    turns=list(normalized_turns),
                    phase=normalized_phase,
                    entry_point=normalized_entry_point,
                )
            except Exception as exc:
                result = {"handled": False, "rule_error": str(exc)}
            if not isinstance(result, dict):
                continue
            explicitly_owned = _result_is_explicitly_owned(rule_name, result, phase=normalized_phase)
            candidate = {
                "rule_name": rule_name,
                "priority": int(item.get("priority", 100)),
                "handled": bool(result.get("handled")) and explicitly_owned,
            }
            action = str(result.get("action") or "").strip()
            if action:
                candidate["action"] = action
            intent = str(result.get("intent") or "").strip()
            if intent:
                candidate["intent"] = intent
            if bool(result.get("handled")) and not explicitly_owned:
                candidate["ownership_declined"] = True
            if str(result.get("rewrite_text") or "").strip():
                candidate["rewrite"] = True
            if isinstance(result.get("state_update"), dict):
                candidate["state_update"] = True
            rule_error = str(result.get("rule_error") or "").strip()
            if rule_error:
                candidate["rule_error"] = rule_error[:160]
            candidates.append(candidate)
            if (
                explicitly_owned
                or str(result.get("rewrite_text") or "").strip()
                or isinstance(result.get("state_update"), dict)
            ):
                payload = dict(result)
                payload["phase"] = normalized_phase
                payload["candidates"] = list(candidates)
                if str(payload.get("rule_name") or "").strip():
                    payload["matched_rule_name"] = str(payload.get("rule_name") or "").strip()
                payload["rule_name"] = rule_name
                payload["priority"] = int(item.get("priority", 100))
                if not explicitly_owned:
                    payload["handled"] = False
                return payload
        return {"handled": False, "phase": normalized_phase, "candidates": candidates}

    def reset(self) -> None:
        self.last_decision: dict[str, dict] = {}
        self.last_decision_by_session: dict[str, dict] = {}
        self.override_state_by_session: dict[str, dict[str, tuple[str, ...]]] = {}

    def process_turn(
        self,
        *,
        entry_point: str,
        session_id: str,
        session_summary: Optional[dict],
        current_decision: Optional[dict],
        recent_records: Optional[list[dict]] = None,
        recent_reflections: Optional[list[dict]] = None,
    ) -> dict:
        summary = dict(session_summary or {})
        decision = self._normalize_decision(entry_point, session_id, summary, current_decision or {})
        context = {
            "entry_point": decision["entry_point"],
            "session_id": decision["session_id"],
            "session_summary": summary,
            "decision": decision,
            "recent_records": list(recent_records or []),
            "recent_reflections": list(recent_reflections or []),
            "previous_input_decision": self.last_decision.get(decision["parity_key"]),
            "previous_session_decision": self.last_decision_by_session.get(decision["session_id"]),
            "other_entry_overrides": dict(self.override_state_by_session.get(decision["session_id"], {})),
        }
        findings: list[dict] = []
        for name, probe in self.probes.items():
            try:
                status, message = probe(context)
            except Exception as exc:
                status, message = "yellow", f"Probe error: {exc}"
            clean_status = str(status or "green").strip().lower()
            if clean_status == "green":
                continue
            findings.append({
                "name": name,
                "status": clean_status,
                "message": str(message or "").strip(),
            })

        suggestions = self._build_suggestions(context, findings)

        self._remember(decision)
        issue_count = len(findings)
        summary_text = "All green" if issue_count == 0 else f"{issue_count} issue{'s' if issue_count != 1 else ''} detected"
        return {
            "entry_point": decision["entry_point"],
            "session_id": decision["session_id"],
            "probe_summary": summary_text,
            "reply_contract": str(decision.get("reply_contract") or ""),
            "reply_outcome_kind": str(decision.get("reply_outcome_kind") or ""),
            "turn_acts": list(decision.get("turn_acts") or []),
            "probe_results": [_status_line(item["name"], item["status"], item["message"]) for item in findings],
            "probe_findings": findings,
            "probe_status_counts": {
                "green": max(0, len(self.probes) - issue_count),
                "yellow": sum(1 for item in findings if item["status"] == "yellow"),
                "red": sum(1 for item in findings if item["status"] == "red"),
            },
            "suggestions": suggestions,
            "headline": f"Probe summary: {summary_text}",
        }

    def _normalize_decision(self, entry_point: str, session_id: str, session_summary: dict, current_decision: dict) -> dict:
        overrides = current_decision.get("overrides_active")
        if not isinstance(overrides, list):
            overrides = session_summary.get("overrides_active") if isinstance(session_summary.get("overrides_active"), list) else []
        pending_action = current_decision.get("pending_action") if isinstance(current_decision.get("pending_action"), dict) else None
        tool_result = str(current_decision.get("tool_result") or "")
        final_answer = str(current_decision.get("final_answer") or current_decision.get("reply_text") or "")
        user_input = str(current_decision.get("user_input") or "")
        turn_acts = current_decision.get("turn_acts")
        if not isinstance(turn_acts, list):
            turn_acts = (current_decision.get("routing_decision") or {}).get("turn_acts") if isinstance(current_decision.get("routing_decision"), dict) else []
        return {
            "entry_point": str(entry_point or "unknown").strip().lower() or "unknown",
            "session_id": str(session_id or "").strip() or "default",
            "user_input": user_input,
            "parity_key": _normalize_text(user_input),
            "active_subject": str(current_decision.get("active_subject") or session_summary.get("active_subject") or "").strip(),
            "continuation_used": bool(current_decision.get("continuation_used", session_summary.get("continuation_used", False))),
            "planner_decision": str(current_decision.get("planner_decision") or "deterministic").strip() or "deterministic",
            "tool": str(current_decision.get("tool") or "").strip(),
            "tool_result": tool_result,
            "final_answer": final_answer,
            "reply_contract": str(current_decision.get("reply_contract") or "").strip(),
            "reply_outcome_kind": str((current_decision.get("reply_outcome") or {}).get("kind") or "").strip(),
            "turn_acts": [str(item).strip() for item in turn_acts if str(item).strip()] if isinstance(turn_acts, list) else [],
            "pending_action": pending_action,
            "overrides_active": sorted(str(item).strip() for item in overrides if str(item).strip()),
            "grounded": bool(current_decision.get("grounded")) if isinstance(current_decision.get("grounded"), bool) else bool(tool_result.strip()),
            "route_summary": str(current_decision.get("route_summary") or "").strip(),
        }

    def _remember(self, decision: dict) -> None:
        parity_key = str(decision.get("parity_key") or "")
        if parity_key:
            self.last_decision[parity_key] = dict(decision)
        session_id = str(decision.get("session_id") or "default")
        self.last_decision_by_session[session_id] = dict(decision)
        entry_point = str(decision.get("entry_point") or "unknown")
        self.override_state_by_session.setdefault(session_id, {})[entry_point] = tuple(decision.get("overrides_active") or [])

    def _recent_issue_names(self, recent_reflections: list[dict]) -> list[str]:
        names: list[str] = []
        for reflection in recent_reflections[-5:]:
            findings = reflection.get("probe_findings") if isinstance(reflection, dict) else None
            if isinstance(findings, list):
                for item in findings:
                    if not isinstance(item, dict):
                        continue
                    status = str(item.get("status") or "").strip().lower()
                    if status not in {"yellow", "red"}:
                        continue
                    name = str(item.get("name") or "").strip()
                    if name:
                        names.append(name)
                continue
            for line in list(reflection.get("probe_results") or []):
                text = str(line or "").strip()
                match = re.match(r"^(?:YELLOW|RED):\s+([a-z_]+)", text, flags=re.I)
                if match:
                    names.append(match.group(1))
        return names

    def _build_suggestions(self, context: dict, findings: list[dict]) -> list[str]:
        repeated = Counter(self._recent_issue_names(list(context.get("recent_reflections") or [])))
        for item in findings:
            status = str(item.get("status") or "").strip().lower()
            name = str(item.get("name") or "").strip()
            if status in {"yellow", "red"} and name:
                repeated[name] += 1
        suggestions: list[str] = []
        for issue, count in repeated.items():
            if count < 3:
                continue
            suggestions.append(f"Repeated {issue} ({count}x) - consider hardening rule: {self.suggest_hardening(issue)}")
        return suggestions[:3]

    def suggest_hardening(self, issue: str) -> str:
        name = str(issue or "").strip().lower()
        if name == "pending_action_leak":
            return "auto-clear pending_action after tool success"
        if name == "continuation_drop":
            return "broaden continuation triggers or add a still-on-subject prompt"
        if name == "entrypoint_parity":
            return "compare CLI and HTTP ordering around the last matching input"
        if name == "identity_location_route":
            return "guard identity and location turns from local knowledge retrieval routes"
        if name == "rule_coverage":
            return "add a deterministic handler or tighten fallback gating for factual/tool turns"
        return "review probe details"

    def _looks_like_identity_location_turn(self, current: dict) -> bool:
        low = str(current.get("user_input") or "").strip().lower()
        if not low:
            return False
        return any(token in low for token in (
            "what is your location",
            "your current location",
            "your current physical location",
            "where are you",
            "where is nova",
            "his location",
            "where is he",
            "where is gus",
            "gus current location",
        ))

    def _looks_like_suspicious_fallback(self, current: dict) -> bool:
        low = str(current.get("user_input") or "").strip().lower()
        if not low:
            return False
        suspicious_terms = (
            "weather",
            "peims",
            "tsds",
            "attendance",
            "domain",
            "policy",
            "fetch",
            "search",
            "research",
            "tool",
            "location",
            "who is",
            "what is",
            "where is",
            "current location",
        )
        return any(term in low for term in suspicious_terms)

    def probe_entrypoint_parity(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        previous = context.get("previous_input_decision") or {}
        if not previous:
            return "green", ""
        if str(previous.get("entry_point") or "") == str(current.get("entry_point") or ""):
            return "green", ""
        prev_subject = str(previous.get("active_subject") or "")
        current_subject = str(current.get("active_subject") or "")
        if prev_subject != current_subject:
            return "red", f"Drift: {previous.get('entry_point')} -> {prev_subject or 'none'} vs {current.get('entry_point')} -> {current_subject or 'none'}"
        if bool(previous.get("continuation_used", False)) != bool(current.get("continuation_used", False)):
            return "yellow", f"Continuation mismatch on similar input: {previous.get('entry_point')} -> {bool(previous.get('continuation_used', False))} vs {current.get('entry_point')} -> {bool(current.get('continuation_used', False))}"
        return "green", ""

    def probe_continuation_drop(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        previous = context.get("previous_session_decision") or {}
        if not previous:
            return "green", ""
        if not bool(previous.get("continuation_used", False)) or bool(current.get("continuation_used", False)):
            return "green", ""
        previous_subject = str(previous.get("active_subject") or "")
        current_subject = str(current.get("active_subject") or "")
        if previous_subject and previous_subject != current_subject:
            return "yellow", f"Previous turn continued on {previous_subject}, current turn dropped to {current_subject or 'none'}"
        return "green", ""

    def probe_pending_action_leak(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        pending = current.get("pending_action")
        if not isinstance(pending, dict) or not pending:
            return "green", ""
        planner_decision = str(current.get("planner_decision") or "")
        tool_result = str(current.get("tool_result") or "").strip()
        if planner_decision in {"run_tool", "command"} and (bool(current.get("grounded", False)) or bool(tool_result)):
            return "red", f"Pending action still set after successful {planner_decision}"
        return "green", ""

    def probe_override_consistency(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        current_entry = str(current.get("entry_point") or "")
        current_overrides = tuple(current.get("overrides_active") or [])
        other_entries = context.get("other_entry_overrides") or {}
        for other_entry, other_overrides in other_entries.items():
            if str(other_entry or "") == current_entry:
                continue
            if tuple(other_overrides or ()) != current_overrides:
                return "yellow", f"Override mismatch: {other_entry} -> {list(other_overrides or [])} vs {current_entry} -> {list(current_overrides)}"
        return "green", ""

    def probe_thin_answer_frequency(self, context: dict) -> tuple[str, str]:
        recent = context.get("recent_records") or []
        if not isinstance(recent, list):
            return "green", ""
        count = 0
        for record in recent[-10:]:
            if not isinstance(record, dict):
                continue
            low = str(record.get("final_answer") or "").strip().lower()
            if not low:
                continue
            if any(token in low for token in (
                "i don't have",
                "i do not have",
                "uncertain",
                "not sure",
                "don't yet know",
                "do not yet know",
            )):
                count += 1
        if count > 2:
            return "yellow", f"Thin answers appearing {count} times in the last 10 turns"
        return "green", ""

    def probe_identity_location_route(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        if not self._looks_like_identity_location_turn(current):
            return "green", ""
        rendered = " ".join(
            str(current.get(field) or "")
            for field in ("final_answer", "tool_result", "route_summary")
        ).lower()
        if "local knowledge files" in rendered or "[source: knowledge/" in rendered:
            return "red", "Location or identity turn routed to local knowledge retrieval"
        return "green", ""

    def probe_rule_coverage(self, context: dict) -> tuple[str, str]:
        current = context.get("decision") or {}
        if str(current.get("planner_decision") or "") == "llm_fallback":
            if self._looks_like_suspicious_fallback(current):
                return "red", "Suspicious fallback on a factual or tool-directed turn"
            return "green", ""
        return "green", ""