from __future__ import annotations

from typing import Dict, List, Optional

from routing import RouteDecision, TurnUnderstanding


def classify_route(turn: TurnUnderstanding) -> RouteDecision:
    del turn
    return RouteDecision(kind="none")


def classify_route_with_context(turn: TurnUnderstanding, config: Optional[dict] = None) -> RouteDecision:
    del config
    return classify_route(turn)


def decide_turn(text: str, config: Optional[dict] = None) -> List[Dict]:
    del text, config
    return []
