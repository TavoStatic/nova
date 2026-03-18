from __future__ import annotations

from .base_tool import NovaTool, ToolContext, ToolInvocationError


class ResearchTool(NovaTool):
    name = "research"
    description = "Structured web fetch and research actions mediated by Nova policy"
    category = "research"
    safe = True
    requires_admin = False
    locality = "network"
    mutating = False
    scope = "user"

    def check_policy(self, args: dict, context: ToolContext) -> tuple[bool, str]:
        ok, reason = super().check_policy(args, context)
        if not ok:
            return ok, reason
        tools = (context.policy.get("tools_enabled") or {}) if isinstance(context.policy, dict) else {}
        web_cfg = (context.policy.get("web") or {}) if isinstance(context.policy, dict) else {}
        if not bool(tools.get("web", False)) or not bool(web_cfg.get("enabled", False)):
            return False, "web_tool_disabled"
        return True, ""

    def run(self, args: dict, context: ToolContext) -> str:
        action = str(args.get("action") or "").strip().lower()
        value = str(args.get("value") or "").strip()
        handlers = context.extra.get("research_handlers") if isinstance(context.extra.get("research_handlers"), dict) else {}
        handler = handlers.get(action)
        if callable(handler):
            return str(handler(value))
        chat_callable = context.extra.get("chat_callable")
        if not callable(chat_callable):
            raise ToolInvocationError("chat_callable_missing")
        if action == "web_fetch":
            return str(chat_callable(f"web {value}"))
        if action == "web_search":
            return str(chat_callable(f"web search {value}"))
        if action == "web_research":
            return str(chat_callable(f"web research {value}"))
        if action == "web_gather":
            return str(chat_callable(f"web gather {value}"))
        raise ToolInvocationError("unknown_research_action")