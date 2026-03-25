from __future__ import annotations

from .base_tool import NovaTool, ToolContext, ToolInvocationError


class PatchTool(NovaTool):
    name = "patch"
    description = "Admin-gated patch preview, approval, apply, and rollback actions"
    category = "patch"
    safe = False
    requires_admin = True
    locality = "local"
    mutating = True
    scope = "system"

    def check_policy(self, args: dict, context: ToolContext) -> tuple[bool, str]:
        ok, reason = super().check_policy(args, context)
        if not ok:
            return ok, reason
        patch_cfg = (context.policy.get("patch") or {}) if isinstance(context.policy, dict) else {}
        if not bool(patch_cfg.get("enabled", True)):
            return False, "patch_tool_disabled"
        action = str(args.get("action") or "").strip().lower()
        allow_force = bool(patch_cfg.get("allow_force", False))
        if action == "apply" and bool(args.get("force")) and not allow_force:
            return False, "patch_force_disabled"
        return True, ""

    def run(self, args: dict, context: ToolContext) -> str:
        action = str(args.get("action") or "").strip().lower()
        value = str(args.get("value") or "").strip()
        handlers = context.extra.get("patch_handlers") if isinstance(context.extra.get("patch_handlers"), dict) else {}
        handler = handlers.get(action)
        if not callable(handler):
            raise ToolInvocationError("unknown_patch_action")
        if action == "apply":
            return str(handler(value, force=bool(args.get("force", False))))
        return str(handler(value))
