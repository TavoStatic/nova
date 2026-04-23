from __future__ import annotations

from typing import Dict, List, Optional

from routing import (
    RouteDecision,
    TurnUnderstanding,
    choose_execution,
    classify_contextual_route,
    classify_direct_tool_route,
    understand_turn,
    looks_like_keyword_route,
    looks_like_command_route,
    looks_like_explicit_web_research,
    looks_like_wikipedia_lookup,
    looks_like_repo_discovery,
    looks_like_stackexchange_search,
    assistant_offered_web_research,
    looks_like_affirmative_followup,
    looks_like_accepting_web_offer,
    looks_like_topic_research_followup,
    looks_like_identity_topic,
    looks_like_data_domain_query,
    looks_like_find_command,
    last_assistant_turn,
    last_user_question,
    extract_followup_location_candidate,
)


def classify_route(turn: TurnUnderstanding) -> RouteDecision:
    low = turn.low
    route = classify_direct_tool_route(turn, looks_like_find_command=looks_like_find_command)
    if route.kind != "none":
        return route

    if looks_like_keyword_route(low):
        return RouteDecision(kind="legacy_keyword")

    if looks_like_command_route(low):
        return RouteDecision(kind="legacy_command")

    return RouteDecision(kind="none")


def classify_route_with_context(turn: TurnUnderstanding, config: Optional[dict] = None) -> RouteDecision:
    route = classify_route(turn)
    return classify_contextual_route(
        turn,
        config=config,
        base_route=route,
        looks_like_explicit_web_research=looks_like_explicit_web_research,
        looks_like_wikipedia_lookup=looks_like_wikipedia_lookup,
        looks_like_repo_discovery=looks_like_repo_discovery,
        looks_like_stackexchange_search=looks_like_stackexchange_search,
        looks_like_data_domain_query=looks_like_data_domain_query,
        last_assistant_turn=last_assistant_turn,
        assistant_offered_web_research=assistant_offered_web_research,
        looks_like_accepting_web_offer=looks_like_accepting_web_offer,
        last_user_question=last_user_question,
        looks_like_topic_research_followup=looks_like_topic_research_followup,
        looks_like_identity_topic=looks_like_identity_topic,
        looks_like_affirmative_followup=looks_like_affirmative_followup,
        extract_followup_location_candidate=extract_followup_location_candidate,
    )


def decide_turn(text: str, config: Optional[dict] = None) -> List[Dict]:
    understanding = understand_turn(text)
    route = classify_route_with_context(understanding, config=config)
    return choose_execution(route)