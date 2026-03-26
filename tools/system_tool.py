from __future__ import annotations

import subprocess
from pathlib import Path

from .base_tool import NovaTool, ToolContext, ToolInvocationError


def _format_generated_queue_status(queue: dict) -> str:
    payload = queue if isinstance(queue, dict) else {}
    count = int(payload.get("count", 0) or 0)
    open_count = int(payload.get("open_count", 0) or 0)
    green_count = int(payload.get("green_count", 0) or 0)
    drift_count = int(payload.get("drift_count", 0) or 0)
    warning_count = int(payload.get("warning_count", 0) or 0)
    never_run_count = int(payload.get("never_run_count", 0) or 0)
    next_item = payload.get("next_item") if isinstance(payload.get("next_item"), dict) else {}
    next_file = str(next_item.get("file") or "").strip()
    next_family = str(next_item.get("family_id") or "").strip()
    next_status = str(next_item.get("latest_status") or "unknown").strip() or "unknown"
    next_reason = str(next_item.get("opportunity_reason") or "unknown").strip() or "unknown"
    report_path = str(next_item.get("latest_report_path") or "").strip()

    lines = [
        "Standing work queue:",
        f"- open: {open_count} of {count}",
        f"- green: {green_count}",
        f"- drift: {drift_count}",
        f"- warning: {warning_count}",
        f"- never run: {never_run_count}",
    ]
    if next_file:
        lines.append(f"Next item: {next_file}")
        if next_family:
            lines.append(f"Family: {next_family}")
        lines.append(f"Status: {next_status} ({next_reason})")
        if report_path:
            lines.append(f"Latest report: {report_path}")
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    open_items = [item for item in items if isinstance(item, dict) and bool(item.get("open"))]
    if open_items:
        lines.append("Top open items:")
        for index, item in enumerate(open_items[:3], start=1):
            file_name = str(item.get("file") or "unknown").strip() or "unknown"
            status = str(item.get("latest_status") or "unknown").strip() or "unknown"
            reason = str(item.get("opportunity_reason") or "unknown").strip() or "unknown"
            highest = item.get("highest_priority") if isinstance(item.get("highest_priority"), dict) else {}
            signal = str(highest.get("signal") or "").strip()
            urgency = str(highest.get("urgency") or "").strip()
            seam = str(highest.get("seam") or "").strip()
            detail = f"status={status}; reason={reason}"
            if signal or urgency or seam:
                detail += f"; signal={signal or 'n/a'}; urgency={urgency or 'n/a'}; seam={seam or 'n/a'}"
            lines.append(f"{index}. {file_name} - {detail}")
    return "\n".join(lines)


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
        if action == "health_check":
            cmd = [python_exe, str((base_dir / "health.py").resolve()), "check"]
        elif action == "doctor":
            cmd = [python_exe, str((base_dir / "doctor.py").resolve()), "--quiet"]
        elif action == "diag":
            cmd = [python_exe, str((base_dir / "health.py").resolve()), "diag"]
        elif action == "queue_status":
            import nova_http

            return _format_generated_queue_status(nova_http._generated_work_queue(12))
        else:
            raise ToolInvocationError("unknown_system_action")
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        return out.strip()
