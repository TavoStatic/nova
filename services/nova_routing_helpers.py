from __future__ import annotations

import re
from typing import Callable


def strip_invocation_prefix(text: str) -> str:
    """Normalize inputs like 'nova, ...' so routing sees the actual request."""
    raw = (text or "").strip()
    if not raw:
        return raw

    match = re.match(r"^nova\b[\s,:\-]*(.*)$", raw, flags=re.I)
    if not match:
        return raw

    rest = (match.group(1) or "").strip()
    if not rest:
        return ""

    starter = (rest.split(maxsplit=1)[0] or "").lower()
    invoke_starters = {
        "what", "which", "who", "where", "when", "why", "how",
        "can", "could", "would", "do", "does", "did", "is", "are",
        "say", "tell", "show", "find", "search", "read", "list", "give",
        "web", "screen", "camera", "health", "inspect", "capabilities",
        "patch", "kb", "mem", "teach",
    }
    if starter in invoke_starters:
        return rest
    return raw


def resolve_research_provider(
    candidates: list[str],
    *,
    default_tool: str = "web_research",
    get_search_provider_priority_fn: Callable[[], list[str]],
    provider_name_from_tool_fn: Callable[[str], str],
) -> dict[str, str]:
    normalized_candidates: list[str] = []
    seen: set[str] = set()
    for item in list(candidates or []):
        token = str(item or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized_candidates.append(token)
    if not normalized_candidates:
        provider = provider_name_from_tool_fn(default_tool) or "general_web"
        return {"provider": provider, "tool_name": default_tool}

    chosen = next(
        (item for item in get_search_provider_priority_fn() if item in normalized_candidates),
        normalized_candidates[0],
    )
    tool_map = {
        "wikipedia": "wikipedia_lookup",
        "stackexchange": "stackexchange_search",
        "general_web": "web_research",
    }
    return {"provider": chosen, "tool_name": tool_map.get(chosen, default_tool)}