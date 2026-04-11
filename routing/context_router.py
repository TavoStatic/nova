from __future__ import annotations

from typing import Optional

from .turn_model import RouteDecision, TurnUnderstanding


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

    if looks_like_topic_research_followup(turn):
        prior_topic = last_user_question(cfg.get("session_turns"), turn.text)
        if prior_topic and not looks_like_identity_topic(prior_topic):
            return RouteDecision(kind="direct_tool", tool="web_research", args=(prior_topic,))

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