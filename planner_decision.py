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
    looks_like_find_command,
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
    )


def decide_turn(text: str, config: Optional[dict] = None) -> List[Dict]:
    understanding = understand_turn(text)
    route = classify_route_with_context(understanding, config=config)
    return choose_execution(route)
