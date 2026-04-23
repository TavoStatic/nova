"""
Heuristic helper functions for turn classification.

These are pure-function signal detectors extracted from planner_decision.py.
They have no side effects and do not import from nova_core or nova_http.
"""
from __future__ import annotations

import re

from .turn_model import TurnUnderstanding
from .legacy_routes import looks_like_keyword_route, looks_like_command_route


# ---------------------------------------------------------------------------
# Web-research intent signals
# ---------------------------------------------------------------------------

def looks_like_explicit_web_research(low: str) -> bool:
    text = (low or "").strip()
    if not text:
        return False
    direct_phrases = (
        "just use the web",
        "use the web",
        "only need web",
        "all you need is the web",
        "all you need is web",
        "need is the web",
        "online about",
        "online for",
        "online on",
        "search online",
        "research online",
        "search the web",
        "anything online",
        "find online",
        "look online",
    )
    if any(phrase in text for phrase in direct_phrases):
        return True
    research_terms = ("research", "search", "lookup", "look up", "browse", "fetch")
    web_terms = ("web", "online", "internet", "website", "site", "tea.texas.gov", "txschools.gov")
    return any(term in text for term in research_terms) and any(term in text for term in web_terms)


def looks_like_wikipedia_lookup(low: str) -> bool:
    text = (low or "").strip()
    if not text:
        return False
    if any(token in text for token in (
        "current",
        "latest",
        "today",
        "news",
        "forecast",
        "weather",
        "right now",
        "doing",
        "feeling",
        "wearing",
        "holding",
        "smell",
        "hearing",
    )):
        return False
    prompts = (
        "who is ",
        "what is ",
        "where is ",
        "when was ",
        "tell me about ",
        "background on ",
        "overview of ",
        "history of ",
        "explain ",
    )
    return text.startswith(prompts)


def looks_like_repo_discovery(low: str) -> bool:
    text = (low or "").strip()
    if not text:
        return False
    cues = (
        "github",
        "repo",
        "repository",
        "source code",
        "implementation",
        "code example",
        "sample project",
        "public repo",
        "open source",
    )
    return any(cue in text for cue in cues)


def looks_like_stackexchange_search(low: str) -> bool:
    text = (low or "").strip()
    if not text:
        return False
    cues = (
        "stackexchange",
        "stack overflow",
        "traceback",
        "stack trace",
        "exception",
        "how do i fix",
        "how to fix",
        "not working",
        "fails",
        "failing",
    )
    return any(cue in text for cue in cues)


def assistant_offered_web_research(last_assistant: str) -> bool:
    low = (last_assistant or "").strip().lower()
    if not low:
        return False
    return (
        "i can try to find more" in low
        or "i can find more" in low
        or "i can try to look" in low
        or "i can look that up" in low
        or "i can try to gather more" in low
    )


# ---------------------------------------------------------------------------
# Follow-up / continuation signals
# ---------------------------------------------------------------------------

def looks_like_affirmative_followup(low: str) -> bool:
    compact = (low or "").strip()
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


def looks_like_accepting_web_offer(turn: TurnUnderstanding) -> bool:
    low = (turn.low or "").strip()
    if not low:
        return False
    if looks_like_explicit_web_research(low):
        return True
    if looks_like_affirmative_followup(low) and any(
        token in low for token in ("find", "more", "information", "look", "search", "try")
    ):
        return True
    return any(
        phrase in low
        for phrase in (
            "find more information",
            "find more",
            "look into that",
            "try to find more",
            "search for more",
            "tell me more about peims",
        )
    )


def looks_like_topic_research_followup(turn: TurnUnderstanding) -> bool:
    low = (turn.low or "").strip()
    if not low:
        return False
    if looks_like_explicit_web_research(low):
        return True
    phrases = (
        "find more information",
        "find more",
        "more information",
        "look into that",
        "try to find more",
        "search for more",
        "dig up",
        "find out more",
        "what else can you find",
    )
    return any(phrase in low for phrase in phrases)


# ---------------------------------------------------------------------------
# Domain / topic classifiers
# ---------------------------------------------------------------------------

def looks_like_identity_topic(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    return any(
        token in low
        for token in ("developer", "creator", "gus", "gustavo", "my name", "your name", "who are you")
    )


def looks_like_data_domain_query(low: str) -> bool:
    text = (low or "").strip()
    if not text:
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
        "data system",
        "reporting",
    )
    return any(term in text for term in data_terms)


# ---------------------------------------------------------------------------
# Command / structure detectors
# ---------------------------------------------------------------------------

def looks_like_find_command(text: str) -> bool:
    raw = str(text or "").strip()
    low = raw.lower()
    if not low.startswith("find "):
        return False
    if raw.endswith("?"):
        return False
    if any(mark in raw for mark in (",", ";", ":")):
        return False
    parts = raw.split()
    if len(parts) < 2 or len(parts) > 3:
        return False
    first_arg = str(parts[1] or "").strip().lower()
    if first_arg in {"a", "an", "the"}:
        return False
    return True


# ---------------------------------------------------------------------------
# Conversation history helpers
# ---------------------------------------------------------------------------

def last_assistant_turn(turns: object) -> str:
    if not isinstance(turns, list):
        return ""
    for item in reversed(turns):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        role = str(item[0] or "").strip().lower()
        text = str(item[1] or "").strip()
        if role == "assistant" and text:
            return text
    return ""


def last_user_question(turns: object, current_text: str = "") -> str:
    current_low = str(current_text or "").strip().lower()
    if not isinstance(turns, list):
        return ""
    for item in reversed(turns):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        role = str(item[0] or "").strip().lower()
        text = str(item[1] or "").strip()
        if role != "user" or not text:
            continue
        low = text.lower()
        if current_low and low == current_low:
            continue
        if "?" in text or low.startswith(("what", "how", "why", "who", "where", "when", "which")):
            return text
    return ""


# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------

def extract_followup_location_candidate(turn: TurnUnderstanding) -> str:
    text = (turn.text or "").strip().strip(" .,!?")
    low = turn.low
    if not text:
        return ""
    if turn.url or turn.mentions_weather or turn.mentions_shared_location:
        return ""
    if any(token in low for token in ("your location", "our location", "same location", "shared location")):
        return ""
    if looks_like_keyword_route(low) or looks_like_command_route(low):
        return ""
    if len(text) > 80:
        return ""
    if text.endswith("?"):
        return ""
    if re.match(r"^(yes|yeah|yea|sure|okay|ok|please|do that|go ahead)\b", low):
        return ""
    return text
