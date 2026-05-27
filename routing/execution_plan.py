from __future__ import annotations

from typing import Dict, List

from .turn_model import RouteDecision


def choose_execution(route: RouteDecision) -> List[Dict]:
    if route.kind == "direct_tool":
        return [{"type": "run_tool", "tool": route.tool, "args": list(route.args)}]
    if route.kind == "respond":
        return [{"type": "respond", "note": route.message}]
    if route.kind == "clarify":
        return [{"type": "ask_clarify", "question": route.message}]
    return []
