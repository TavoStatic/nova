from __future__ import annotations

from typing import Callable, Optional


def classify_web_research_outcome(
    intent_result: dict,
    user_text: str = "",
    *,
    turns: Optional[list[tuple[str, str]]] = None,
    infer_research_query_from_turns_fn: Callable[[list[tuple[str, str]]], str],
    resolve_research_provider_fn: Callable[..., dict[str, str]],
    provider_name_from_tool_fn: Callable[[str], str],
) -> dict[str, object]:
    payload = intent_result if isinstance(intent_result, dict) else {}
    request_kind = str(payload.get("web_request_kind") or "research_prompt").strip().lower() or "research_prompt"
    tool_name = str(payload.get("tool_name") or "web_research").strip().lower() or "web_research"
    provider_candidates = payload.get("provider_candidates") if isinstance(payload.get("provider_candidates"), list) else []
    provider_family = str(payload.get("provider_family") or "general_web").strip().lower() or "general_web"
    query = str(payload.get("query") or "").strip()
    if request_kind == "deep_search" and not query:
        query = infer_research_query_from_turns_fn(list(turns or []))
    if not query:
        query = str(user_text or "").strip()
    resolved = resolve_research_provider_fn(provider_candidates, default_tool=tool_name)
    tool_name = str(resolved.get("tool_name") or tool_name).strip().lower() or tool_name
    provider_used = str(resolved.get("provider") or provider_name_from_tool_fn(tool_name)).strip().lower() or provider_name_from_tool_fn(tool_name)
    return {
        "intent": "web_research_family",
        "kind": request_kind,
        "reply_contract": f"web_research_family.{request_kind}",
        "tool_name": tool_name,
        "provider_candidates": list(provider_candidates or []),
        "provider_family": provider_family,
        "provider_used": provider_used,
        "query": query,
        "requires_tool": True,
        "state_delta": {},
    }