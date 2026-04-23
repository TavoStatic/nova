from __future__ import annotations

import json
from typing import Callable


DEFAULT_DIRECT_TOOLS = [
    "camera",
    "find",
    "health",
    "ls",
    "patch_apply",
    "patch_rollback",
    "phase2_audit",
    "pulse",
    "queue_status",
    "read",
    "screen",
    "system_check",
    "update_now",
    "update_now_cancel",
    "update_now_confirm",
    "weather_current_location",
    "weather_location",
    "web_fetch",
    "web_gather",
    "web_research",
    "web_search",
]


class ToolConsoleService:
    """Shared planner-to-tool console orchestration for CLI entrypoints."""

    def __init__(
        self,
        *,
        decide_turn_fn: Callable[[str], list],
        execute_planned_action_fn: Callable[[str, list], object],
        handle_commands_fn: Callable[[str], object],
        describe_tools_fn: Callable[[], str],
        direct_tools: list[str] | None = None,
    ) -> None:
        self._decide_turn = decide_turn_fn
        self._execute_planned_action = execute_planned_action_fn
        self._handle_commands = handle_commands_fn
        self._describe_tools = describe_tools_fn
        self._direct_tools = list(direct_tools or DEFAULT_DIRECT_TOOLS)

    @staticmethod
    def coerce_output(value) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=True, indent=2).strip()
        return str(value or "").strip()

    def list_tools_text(self) -> str:
        registry_desc = str(self._describe_tools() or "").strip()
        lines = [
            "run_tools direct routes:",
            *[f"- {name}" for name in self._direct_tools],
        ]
        if registry_desc:
            lines.extend(["", "Registered tools:", registry_desc])
        return "\n".join(lines)

    def handle_tools(self, user_text: str, *, emit_status: Callable[[str], None] | None = None):
        text = str(user_text or "").strip()
        if not text:
            return None

        steps = self._decide_turn(text)
        if not steps:
            return None

        step = steps[0] if isinstance(steps[0], dict) else {}
        action_type = str(step.get("type") or "").strip().lower()
        if action_type == "run_tool":
            tool_name = str(step.get("tool") or "").strip()
            tool_args = list(step.get("args") or [])
            if callable(emit_status):
                emit_status(f"Nova: tool -> {tool_name}")
            return self.coerce_output(self._execute_planned_action(tool_name, tool_args))
        if action_type == "ask_clarify":
            return str(step.get("question") or "").strip()
        if action_type == "respond":
            return str(step.get("note") or "").strip()
        if action_type in {"route_command", "route_keyword"}:
            return self.coerce_output(self._handle_commands(text))
        return None