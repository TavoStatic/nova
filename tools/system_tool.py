from __future__ import annotations

import subprocess
from pathlib import Path

from .base_tool import NovaTool, ToolContext, ToolInvocationError


class SystemTool(NovaTool):
    name = "system"
    description = "Operator-facing local system and diagnostics actions"
    category = "system"
    safe = False
    requires_admin = False
    locality = "local"
    mutating = False
    scope = "system"

    def check_policy(self, args: dict, context: ToolContext) -> tuple[bool, str]:
        ok, reason = super().check_policy(args, context)
        if not ok:
            return ok, reason
        action = str(args.get("action") or "").strip().lower()
        tools = (context.policy.get("tools_enabled") or {}) if isinstance(context.policy, dict) else {}
        if action == "health_check" and not bool(tools.get("health", False)):
            return False, "health_tool_disabled"
        if action in {"doctor", "diag"} and not bool(context.is_admin):
            return False, "admin_required"
        return True, ""

    def run(self, args: dict, context: ToolContext) -> str:
        base_dir = Path(__file__).resolve().parent.parent
        python_exe = str((base_dir / ".venv" / "Scripts" / "python.exe").resolve())
        action = str(args.get("action") or "").strip().lower()
        if action == "health_check":
            cmd = [python_exe, str((base_dir / "health.py").resolve()), "check"]
        elif action == "doctor":
            cmd = [python_exe, str((base_dir / "doctor.py").resolve()), "--quiet"]
        elif action == "diag":
            cmd = [python_exe, str((base_dir / "health.py").resolve()), "diag"]
        else:
            raise ToolInvocationError("unknown_system_action")
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        return out.strip()