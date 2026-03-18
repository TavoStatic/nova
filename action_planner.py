"""Thin planner adapter over Nova's decision module."""
from __future__ import annotations

from typing import List, Dict, Optional

from planner_decision import decide_turn


class ActionPlanner:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def plan(self, text: str) -> List[Dict]:
        return decide_turn(text, config=self.config)


def decide_actions(text: str, config: Optional[dict] = None) -> List[Dict]:
    planner = ActionPlanner(config=config)
    return planner.plan(text)


if __name__ == "__main__":
    # simple interactive demo
    import sys
    ap = ActionPlanner()
    q = " ".join(sys.argv[1:]) or "fetch http://example.com"
    print(ap.plan(q))
