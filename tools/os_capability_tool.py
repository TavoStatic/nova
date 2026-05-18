from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base_tool import NovaTool, ToolContext, ToolInvocationError
from services.nova_runtime_context import BASE_DIR, OPERATOR_OUTBOX_FILE, OS_CAPABILITY_LEDGER_FILE, OS_CAPABILITY_REGISTRY_FILE
from services.os_capability_operator_outbox import publish_os_capability_notice
from services.os_script_controller import OS_SCRIPT_CONTROLLER_SERVICE
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _parse_request(args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    capability = str(args.get("capability") or args.get("name") or "").strip()
    capability_args = args.get("args") if isinstance(args.get("args"), dict) else {}
    request = args.get("request")
    if isinstance(request, dict):
        capability = str(request.get("capability") or request.get("name") or capability).strip()
        capability_args = request.get("args") if isinstance(request.get("args"), dict) else capability_args
    elif isinstance(request, str) and request.strip().startswith("{"):
        try:
            parsed = json.loads(request)
        except Exception as exc:
            raise ToolInvocationError(f"invalid_os_capability_request:{exc}") from exc
        if isinstance(parsed, dict):
            capability = str(parsed.get("capability") or parsed.get("name") or capability).strip()
            capability_args = parsed.get("args") if isinstance(parsed.get("args"), dict) else capability_args
    elif isinstance(request, str) and request.strip():
        capability = request.strip()
    if not capability:
        raise ToolInvocationError("capability_required")
    return capability, dict(capability_args or {})


class OsCapabilityTool(NovaTool):
    name = "os_capability"
    description = "Execute registered OS capabilities through verified script contracts"
    category = "system"
    safe = False
    requires_admin = False
    locality = "local"
    mutating = False
    scope = "system"

    def check_policy(self, args: dict[str, Any], context: ToolContext) -> tuple[bool, str]:
        ok, reason = super().check_policy(args, context)
        if not ok:
            return ok, reason
        policy = context.policy if isinstance(context.policy, dict) else {}
        tools = policy.get("tools_enabled") if isinstance(policy.get("tools_enabled"), dict) else {}
        if "os_capability" in tools and not bool(tools.get("os_capability")):
            return False, "os_capability_tool_disabled"
        return True, ""

    def run(self, args: dict[str, Any], context: ToolContext) -> str:
        capability, capability_args = _parse_request(args or {})
        extra = context.extra if isinstance(context.extra, dict) else {}
        controller = extra.get("os_script_controller") or OS_SCRIPT_CONTROLLER_SERVICE
        registry_path = Path(str(extra.get("os_capability_registry_path") or OS_CAPABILITY_REGISTRY_FILE))
        ledger_path = Path(str(extra.get("os_capability_ledger_path") or OS_CAPABILITY_LEDGER_FILE))
        base_dir = Path(str(extra.get("base_dir") or BASE_DIR))
        result = controller.execute_capability(
            capability,
            capability_args,
            registry_path=registry_path,
            ledger_path=ledger_path,
            base_dir=base_dir,
            authority_context={
                "is_admin": bool(context.is_admin),
                "allowed_authority_levels": extra.get("allowed_authority_levels"),
                "allow_mutating": bool(extra.get("allow_mutating")),
                "allow_evidence_write": bool(extra.get("allow_evidence_write")),
            },
        )
        if isinstance(result, dict) and result.get("operator_outbox"):
            result = dict(result)
            result["operator_notice"] = publish_os_capability_notice(
                result,
                outbox_path=Path(str(extra.get("operator_outbox_path"))) if extra.get("operator_outbox_path") else None,
                context=_safe_dict(extra.get("work_tree_target") or extra.get("work_tree")),
            )
        elif isinstance(result, dict) and bool(result.get("ok")) and str(result.get("status") or "") == "success":
            result = dict(result)
            result["operator_reconcile"] = OPERATOR_OUTBOX_SERVICE.reconcile_os_capability_notices(
                Path(str(extra.get("operator_outbox_path") or OPERATOR_OUTBOX_FILE)),
                capability=capability,
                cleared_reasons={"contract_stale", "capability_evidence_not_ok"},
            )
        return json.dumps(result, ensure_ascii=True, sort_keys=True)
