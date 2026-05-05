from __future__ import annotations

import re
from typing import Optional

from .turn_model import RouteDecision, TurnUnderstanding


def _location_context_active(session_turns) -> bool:
    recent = session_turns[-6:] if isinstance(session_turns, list) else []
    for role, content in reversed(recent):
        if str(role or "").strip().lower() != "assistant":
            continue
        low = str(content or "").strip().lower()
        if not low:
            continue
        if (
            "device location" in low
            or "saved location" in low
            or "location fix" in low
            or low.startswith("my location is")
            or low.startswith("your location is")
        ):
            return True
    return False


def _location_label_intent(low: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9']+", str(low or "").lower()))
    asks_identity = bool(tokens & {"name", "called", "which", "what"})
    asks_location_label = bool(tokens & {"city", "place", "town", "area", "county", "zip", "zipcode"})
    has_external_topic = bool(tokens & {"song", "book", "movie", "album", "person", "company", "band", "definition", "history"})
    return asks_identity and asks_location_label and not has_external_topic


def classify_contextual_route(
    turn: TurnUnderstanding,
    *,
    config: Optional[dict] = None,
    base_route: RouteDecision,
    looks_like_explicit_web_research,
    looks_like_wikipedia_lookup,
    looks_like_repo_discovery,
    looks_like_stackexchange_search,
    looks_like_data_domain_query,
    last_assistant_turn,
    assistant_offered_web_research,
    looks_like_accepting_web_offer,
    last_user_question,
    looks_like_topic_research_followup,
    looks_like_identity_topic,
    looks_like_affirmative_followup,
    extract_followup_location_candidate,
) -> RouteDecision:
    if base_route.kind != "none":
        return base_route

    cfg = config if isinstance(config, dict) else {}
    if looks_like_repo_discovery(turn.low):
        return RouteDecision(kind="direct_tool", tool="web_research", args=(turn.text,))

    if looks_like_stackexchange_search(turn.low) and looks_like_explicit_web_research(turn.low):
        return RouteDecision(kind="direct_tool", tool="stackexchange_search", args=(turn.text,))

    session_turns = cfg.get("session_turns")
    if _location_label_intent(turn.low):
        if _location_context_active(session_turns):
            return RouteDecision(kind="none")
        return RouteDecision(
            kind="clarify",
            message="Which location do you mean: your current device location, your saved location, or another place?",
        )

    if looks_like_wikipedia_lookup(turn.low):
        return RouteDecision(kind="direct_tool", tool="wikipedia_lookup", args=(turn.text,))

    if looks_like_explicit_web_research(turn.low):
        return RouteDecision(kind="direct_tool", tool="web_research", args=(turn.text,))

    if bool(cfg.get("prefer_web_for_data_queries")) and looks_like_data_domain_query(turn.low):
        return RouteDecision(kind="direct_tool", tool="web_research", args=(turn.text,))

    pending_action = cfg.get("pending_action") if isinstance(cfg.get("pending_action"), dict) else {}
    last_assistant = last_assistant_turn(cfg.get("session_turns"))
    last_low = last_assistant.lower()

    if assistant_offered_web_research(last_assistant) and looks_like_accepting_web_offer(turn):
        prior_topic = last_user_question(cfg.get("session_turns"), turn.text)
        query = prior_topic or turn.text
        return RouteDecision(kind="direct_tool", tool="web_research", args=(query,))

    if pending_action.get("kind") == "weather_lookup" and pending_action.get("status") == "awaiting_location":
        if turn.mentions_shared_location or turn.low in {"our location", "our location nova", "same location", "shared location"}:
            return RouteDecision(kind="direct_tool", tool="weather_current_location")
        if ("your" in turn.low and turn.mentions_location) or "that location" in turn.low or "there" in turn.low:
            return RouteDecision(kind="direct_tool", tool="weather_current_location")
        if pending_action.get("saved_location_available") and looks_like_affirmative_followup(turn.low):
            return RouteDecision(kind="direct_tool", tool="weather_current_location")
        explicit_location = extract_followup_location_candidate(turn)
        if explicit_location:
            return RouteDecision(kind="direct_tool", tool="weather_location", args=(explicit_location,))

    if "what location should i use for the weather lookup" in last_low:
        if turn.mentions_shared_location or turn.low in {"our location", "our location nova", "same location", "shared location"}:
            return RouteDecision(kind="direct_tool", tool="weather_current_location")

    return base_route
