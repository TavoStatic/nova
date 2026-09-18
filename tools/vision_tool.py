from __future__ import annotations

import subprocess
from pathlib import Path

from services.nova_vision_runtime import describe_image_file

from .base_tool import NovaTool, ToolContext, ToolInvocationError


def _completed_text(process) -> str:
    return ((process.stdout or "") + (("\n" + process.stderr) if process.stderr else "")).strip()


class VisionTool(NovaTool):
    name = "vision"
    description = "Screenshot and camera helper tools"
    category = "vision"
    safe = True
    requires_admin = False
    locality = "local"
    mutating = False
    scope = "user"

    def check_policy(self, args: dict, context: ToolContext) -> tuple[bool, str]:
        ok, reason = super().check_policy(args, context)
        if not ok:
            return ok, reason
        tools = (context.policy.get("tools_enabled") or {}) if isinstance(context.policy, dict) else {}
        action = str(args.get("action") or "").strip().lower()
        if action == "screen" and not bool(tools.get("screen", False)):
            return False, "screen_tool_disabled"
        if action == "camera" and not bool(tools.get("camera", False)):
            return False, "camera_tool_disabled"
        return True, ""

    def run(self, args: dict, context: ToolContext) -> str:
        base_dir = Path(__file__).resolve().parent.parent
        venv_windows = base_dir / ".venv" / "Scripts" / "python.exe"
        venv_posix = base_dir / ".venv" / "bin" / "python"
        if venv_windows.exists():
            python_exe = str(venv_windows.resolve())
        elif venv_posix.exists():
            python_exe = str(venv_posix.resolve())
        else:
            import sys

            python_exe = str(Path(sys.executable).resolve())
        action = str(args.get("action") or "").strip().lower()
        if action == "screen":
            cmd = [python_exe, str((base_dir / "look_crop.py").resolve())]
        elif action == "camera":
            prompt = str(args.get("prompt") or "Describe what you see.").strip() or "Describe what you see."
            cmd = [python_exe, str((base_dir / "camera.py").resolve()), prompt]
        elif action == "describe_file":
            path = str(args.get("path") or "").strip()
            if not path:
                raise ToolInvocationError("missing_image_path")
            prompt = str(args.get("prompt") or "Describe what you see in this image.").strip()
            policy = context.policy if isinstance(getattr(context, "policy", None), dict) else {}
            return describe_image_file(path, prompt, policy=policy)
        else:
            raise ToolInvocationError("unknown_vision_action")
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = _completed_text(p)
        returncode = int(getattr(p, "returncode", 0) or 0)
        if returncode != 0:
            detail = out[:500] if out else f"exit:{returncode}"
            raise ToolInvocationError(f"vision_helper_failed:exit:{returncode}:{detail}")
        return out
