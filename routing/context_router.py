from __future__ import annotations

from typing import Optional

from .turn_model import RouteDecision, TurnUnderstanding


def classify_contextual_route(
    turn: TurnUnderstanding,
    *,
    config: Optional[dict] = None,
    base_route: RouteDecision,
) -> RouteDecision:
    del config, turn
    if base_route.kind != "none":
        return base_route
    return base_route
