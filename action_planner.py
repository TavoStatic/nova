"""Simple action planner scaffold for Nova.

This module provides a lightweight, rule-based `ActionPlanner` used by Nova
to convert user utterances into an ordered list of candidate actions.

The implementation is intentionally small and deterministic so it can be
expanded later into a more sophisticated planner that reasons over tool
outputs and knowledge packs.
"""
from __future__ import annotations

import re
from typing import List, Dict, Optional


class ActionPlanner:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def plan(self, text: str) -> List[Dict]:
        """Return an ordered list of candidate actions based on `text`.

        Each action is a dict with at least a `type` key. Example types:
        - `ask_clarify` : ask a short clarifying question
        - `run_tool`    : run a specific tool (fields: `tool`, `args`)
        - `respond`     : produce a direct assistant reply
        """
        t = (text or "").strip()
        low = t.lower()

        # Disallow autonomous scanning actions; prefer clarification
        if any(x in low for x in ("nmap", "scan my", "scan the")):
            return [{"type": "ask_clarify", "question": "I can’t run network scans. What specific check would you like me to help with?"}]

        # If the user provided an http(s) url, propose a web_fetch tool action
        m = re.search(r"https?://[\w\-\.\/:?=&%]+", t)
        if m and ("gather" in low or "summarize" in low or "collect" in low):
            url = m.group(0)
            return [{"type": "run_tool", "tool": "web_gather", "args": [url]}]

        if m:
            url = m.group(0)
            return [{"type": "run_tool", "tool": "web_fetch", "args": [url]}]

        if low.startswith("web search ") or "search the web" in low or "web search" in low:
            q = t
            if low.startswith("web search "):
                q = t[11:].strip()
            return [{"type": "run_tool", "tool": "web_search", "args": [q]}]

        if low.startswith("web research ") or "all the information" in low or "research" in low:
            q = t
            if low.startswith("web research "):
                q = t[13:].strip()
            return [{"type": "run_tool", "tool": "web_research", "args": [q]}]

        # If the user asked to apply a patch or rollback, map to patch commands
        if "patch apply" in low or ("apply patch" in low and ".zip" in low):
            # naive extraction of path if present
            m2 = re.search(r"([A-Za-z]:\\[^\s]+\.zip|/[^\s]+\.zip|\S+\.zip)", t)
            path = m2.group(0) if m2 else None
            return [{"type": "run_tool", "tool": "patch_apply", "args": [path] if path else []}]

        if "patch rollback" in low or "rollback" in low:
            return [{"type": "run_tool", "tool": "patch_rollback", "args": []}]

        # If user asked for code help, plan a respond + suggest tests
        if any(x in low for x in ("fix my code", "debug", "bug in", "refactor")):
            return [{"type": "respond", "note": "I can help debug — paste the failing output or file path."}]

        # Default: respond and ask to clarify the goal if ambiguous
        return [{"type": "respond", "note": "Understood. Tell me what outcome you want and I’ll plan steps."}]


def decide_actions(text: str, config: Optional[dict] = None) -> List[Dict]:
    planner = ActionPlanner(config=config)
    return planner.plan(text)


if __name__ == "__main__":
    # simple interactive demo
    import sys
    ap = ActionPlanner()
    q = " ".join(sys.argv[1:]) or "fetch http://example.com"
    print(ap.plan(q))
