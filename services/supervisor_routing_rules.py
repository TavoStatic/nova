from __future__ import annotations

import re
from typing import Any, Optional

import active_task_constraints as active_tasks
import followup_move_classifier as followup_moves
from services.supervisor_patterns import looks_like_self_location
from services.supervisor_patterns import normalize_text


_looks_like_affirmative_followup = followup_moves.looks_like_affirmative_followup
_looks_like_shared_location_reference = followup_moves.looks_like_shared_location_reference
_classify_followup_move = followup_moves.classify_followup_move


def looks_like_location_recall_query(low: str) -> bool:
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


def looks_like_location_name_query(low: str) -> bool:
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
    return "location" in low and "name" in low and followup_moves.uses_prior_reference(low)


def looks_like_saved_location_weather_query(low: str) -> bool:
    normalized = normalize_text(low)
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


def looks_like_saved_location_weather_confirmation(low: str) -> bool:
    normalized = normalize_text(low)
    if not normalized:
        return False
    if "saved location" not in normalized:
        return False
    return (
        _looks_like_affirmative_followup(normalized)
        or "use the saved location" in normalized
        or "using the saved location" in normalized
    )


def looks_like_weather_lookup_request(low: str) -> bool:
    if not low or low.startswith("web ") or "weather" not in low:
        return False
    if looks_like_saved_location_weather_query(low):
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


def looks_like_weather_meta_question(low: str) -> bool:
    normalized = normalize_text(low)
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


def extract_weather_request_location(user_text: str, low: str) -> str:
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
        if _looks_like_shared_location_reference(normalize_text(candidate)):
            return ""
        return candidate
    return ""


def extract_set_location_payload(user_text: str) -> dict[str, str]:
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


def extract_store_fact_payload(user_text: str, low: str) -> dict[str, str]:
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


def looks_like_deep_search_request(low: str) -> bool:
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


def looks_like_online_research_request(low: str) -> bool:
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


def explicit_general_web_prompt(user_text: str, request_kind: str) -> bool:
    if str(request_kind or "").strip().lower() != "research_prompt":
        return False
    low = normalize_text(user_text)
    if not low:
        return False
    cues = (
        "give me anything online about ",
        "search online for ",
        "look online for ",
        "find online ",
        "web research ",
        "search the web for ",
        "use the web",
        "just use the web",
    )
    return any(cue in low for cue in cues)


def web_research_query_from_text(user_text: str, low: str) -> str:
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


def looks_like_stackexchange_request(text: str) -> bool:
    low = normalize_text(text)
    if not low:
        return False
    cues = (
        "error",
        "exception",
        "traceback",
        "stack trace",
        "how do i fix",
        "how to fix",
        "not working",
        "fails",
        "failing",
        "bug",
        "warning",
        "debug",
        "oauth",
        "docker",
        "fastapi",
        "python",
        "javascript",
        "typescript",
        "react",
        "sql",
    )
    return any(cue in low for cue in cues)


def looks_like_repo_discovery_request(text: str) -> bool:
    low = normalize_text(text)
    if not low:
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
    return any(cue in low for cue in cues)


def looks_like_wikipedia_lookup_request(text: str) -> bool:
    low = normalize_text(text)
    if not low:
        return False
    if any(token in low for token in (
        "current",
        "latest",
        "today",
        "news",
        "weather",
        "forecast",
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
    return low.startswith(prompts)


def looks_like_proper_name_topic(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw or len(raw.split()) > 5:
        return False
    if len(raw.split()) == 1 and raw.isupper():
        return False
    return bool(re.fullmatch(r"[A-Z][A-Za-z0-9'\-]+(?:\s+[A-Z][A-Za-z0-9'\-]+){0,4}", raw))


def search_provider_tool_for_query(user_text: str, query: str, request_kind: str) -> str:
    if str(request_kind or "").strip().lower() == "deep_search":
        return "web_research"
    if explicit_general_web_prompt(user_text, request_kind):
        return "web_research"
    combined = f"{str(user_text or '').strip()} {str(query or '').strip()}".strip()
    if looks_like_repo_discovery_request(combined):
        return "web_research"
    if looks_like_stackexchange_request(combined):
        return "stackexchange_search"
    if looks_like_wikipedia_lookup_request(combined):
        return "wikipedia_lookup"
    if looks_like_proper_name_topic(query) and not any(token in normalize_text(query) for token in ("peims", "tsds", "api")):
        return "wikipedia_lookup"
    return "web_research"


def search_provider_candidates_for_query(user_text: str, query: str, request_kind: str) -> list[str]:
    if str(request_kind or "").strip().lower() == "deep_search":
        return ["general_web"]
    if explicit_general_web_prompt(user_text, request_kind):
        return ["general_web"]
    combined = f"{str(user_text or '').strip()} {str(query or '').strip()}".strip()
    if looks_like_repo_discovery_request(combined):
        return ["general_web"]
    if looks_like_stackexchange_request(combined):
        return ["stackexchange", "general_web"]
    if looks_like_wikipedia_lookup_request(combined) or looks_like_proper_name_topic(query):
        return ["wikipedia", "general_web"]
    return ["general_web"]


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
    payload = extract_store_fact_payload(user_text, low)
    if not payload:
        return {"handled": False}
    return {"handled": True, "intent": "store_fact", **payload}


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
        return {"handled": True, **pending_followup}

    if looks_like_saved_location_weather_confirmation(low):
        active_subject = active_tasks.manager_active_subject(manager)
        if "weather" in str(active_subject).lower():
            return {
                "handled": True,
                "intent": "weather_lookup",
                "weather_mode": "current_location",
                "ledger_stage": "weather_lookup",
                "grounded": True,
            }

    if looks_like_saved_location_weather_query(low):
        return {"handled": False}
    if not looks_like_weather_lookup_request(low):
        return {"handled": False}
    if looks_like_weather_meta_question(low):
        return {"handled": False}
    if _looks_like_shared_location_reference(low):
        return {
            "handled": True,
            "intent": "weather_lookup",
            "weather_mode": "current_location",
            "ledger_stage": "weather_lookup",
            "grounded": True,
        }

    location_value = extract_weather_request_location(user_text, low)
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
    if phase != "handle" or not looks_like_self_location(low):
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
    if looks_like_location_name_query(low):
        return {
            "handled": True,
            "action": "location_recall",
            "continuation": False,
            "next_state": {"kind": "location_recall"},
            "ledger_stage": "location_recall",
            "grounded": True,
        }
    if move in {"continuation", "reference_answer"} or looks_like_location_recall_query(low):
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
    return {"handled": True, **binding}


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
    if looks_like_deep_search_request(low):
        request_kind = "deep_search"
    elif looks_like_online_research_request(low):
        request_kind = "research_prompt"
    else:
        return {"handled": False}

    query = web_research_query_from_text(user_text, low)
    if not query:
        return {"handled": False}

    tool_name = search_provider_tool_for_query(user_text, query, request_kind)
    provider_candidates = search_provider_candidates_for_query(user_text, query, request_kind)
    return {
        "handled": True,
        "intent": "web_research_family",
        "web_request_kind": request_kind,
        "tool_name": tool_name,
        "provider_candidates": provider_candidates,
        "provider_family": provider_candidates[0] if provider_candidates else "general_web",
        "query": query,
        "ledger_stage": "web_research",
        "grounded": True,
    }


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
    payload = extract_set_location_payload(user_text)
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