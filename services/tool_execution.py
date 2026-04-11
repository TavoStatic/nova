from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from tools import ToolContext, ToolInvocationError


class ToolExecutionService:
    """Build tool context and execute tools through the registry service."""

    def __init__(
        self,
        *,
        policy_loader: Callable[[], dict],
        active_user_getter: Callable[[], Optional[str]],
        base_dir: Path,
        registry_service: Any,
    ) -> None:
        self._policy_loader = policy_loader
        self._active_user_getter = active_user_getter
        self._base_dir = Path(base_dir)
        self._registry_service = registry_service

    def build_tool_context(self, *, is_admin: bool = False, extra: Optional[dict] = None) -> ToolContext:
        policy = self._policy_loader() or {}
        extras = dict(extra or {})
        allowed_root_raw = policy.get("allowed_root") if isinstance(policy, dict) else None
        allowed_root = str(Path(allowed_root_raw or str(self._base_dir)).resolve())
        return ToolContext(
            user_id=self._active_user_getter() or "",
            session_id="",
            policy=policy,
            allowed_root=allowed_root,
            is_admin=bool(is_admin),
            extra=extras,
        )

    @staticmethod
    def tool_error_message(tool_name: str, reason: str) -> str:
        r = str(reason or "tool_failed").strip()
        mapping = {
            "screen_tool_disabled": "Screen tool disabled by policy.",
            "camera_tool_disabled": "Camera tool disabled by policy.",
            "files_tool_disabled": "File tools disabled by policy.",
            "health_tool_disabled": "Health tool disabled by policy.",
            "patch_tool_disabled": "Patch tool disabled by policy.",
            "patch_force_disabled": "Forced patch apply is disabled by policy.",
            "admin_required": f"{tool_name} is restricted to admin-approved execution.",
        }
        return mapping.get(r, r)

    def execute_registered_tool(
        self,
        tool_name: str,
        args: dict,
        *,
        is_admin: bool = False,
        extra: Optional[dict] = None,
    ) -> str:
        ctx = self.build_tool_context(is_admin=is_admin, extra=extra)
        try:
            result = self._registry_service.run_tool(tool_name, args or {}, ctx)
        except ToolInvocationError as e:
            return self.tool_error_message(tool_name, str(e))
        except Exception as e:
            return f"{tool_name} tool failed: {e}"
        return str(result or "").strip()
