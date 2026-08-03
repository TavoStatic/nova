from __future__ import annotations

"""
Ed-Fi explore tool — live path uses the Ed-Fi backpack (pipeline_id=edfi).

Legacy data_sources/edfi_bisd remains on disk for migration; new calls go through
services.backpack_host (in-process safe_query + operations.json grants).
"""

import json
from typing import Any

from .base_tool import NovaTool, ToolContext, ToolInvocationError
from services.backpack_host.ops_map import resolve_shell_role
from services.backpack_host.query import run_backpack_query

PIPELINE_ID = "edfi"

_ACTION_TO_OPERATION: dict[str, str] = {
    "health": "connection_health",
    "status": "connection_health",
    "list_resources": "list_resources",
    "resources": "list_resources",
    "browse": "list_resources",
    "schools": "list_schools",
    "students": "list_students",
    "student_school_associations": "student_school_associations",
    "associations": "student_school_associations",
    "sync_status": "sync_status",
    "changes": "changes_since",
    "changes_since": "changes_since",
}


def _render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _governed_query(
    operation: str,
    *,
    params: dict[str, Any] | None = None,
    row_limit: int | None = None,
    role: str = "standard_user",
) -> dict[str, Any]:
    return run_backpack_query(
        PIPELINE_ID,
        operation,
        params,
        row_limit=row_limit,
        role=role,
    )


class EdFiExploreTool(NovaTool):
    name = "edfi_explore"
    description = (
        "Ed-Fi backpack fusion tool. Prefer action=capabilities or health first. "
        "Schools default to local hold (warehouse/extract). Live ODS only when "
        "action=schools_refresh (rate-limit risk). Do not invent facts outside "
        "available_capability_ids. Pipeline phase: not a full dashboard product."
    )
    category = "data"
    safe = True
    requires_admin = False
    locality = "network"
    mutating = False
    scope = "operator"

    def run(self, args: dict[str, Any], context: ToolContext) -> Any:
        action = str(args.get("action") or "health").strip().lower()

        # Nervous-system probe: what Nova may claim right now
        if action in {"capabilities", "fusion", "what_i_have", "inventory"}:
            from services.backpack_host.capability_surface import get_fusion_status

            force = bool(args.get("force") or args.get("rescan"))
            scan = get_fusion_status(max_age_sec=30.0, force=force)
            return _render(
                {
                    "ok": bool(scan.get("ok")),
                    "action": "capabilities",
                    "backpack_id": scan.get("backpack_id"),
                    "available_capability_ids": scan.get("available_capability_ids") or [],
                    "declared_capabilities": scan.get("declared_capabilities") or [],
                    "nova_must_know": scan.get("nova_must_know") or {},
                    "teach_rules": scan.get("teach_rules") or [],
                    "local_hold": scan.get("local_hold") or {},
                    "probes": scan.get("probes") or [],
                    "probe_fail_count": scan.get("probe_fail_count"),
                    "summary": (
                        f"Ed-Fi fusion ok={scan.get('ok')} "
                        f"capabilities={len(scan.get('available_capability_ids') or [])} "
                        f"local_schools={((scan.get('local_hold') or {}).get('row_count') or 0)}"
                    ),
                }
            )

        # Schools: prefer local report path (no live TEA)
        if action in {"schools", "list_schools", "schools_local"}:
            from services.backpack_host.reports import run_backpack_report

            role = resolve_shell_role(
                role=str(args.get("role") or args.get("shell_role") or ""),
                is_admin=bool(context.is_admin),
                context_extra=dict(context.extra or {}),
                policy=dict(context.policy or {}),
            )
            limit = int(args.get("limit") or 25)
            lea = str(args.get("lea") or args.get("district_lea_id") or "").strip()
            report = run_backpack_report(
                "schools",
                role=role,
                lea=lea,
                limit=limit,
                prefer_local=True,
                force_refresh=False,
            )
            if not report.get("ok"):
                raise ToolInvocationError(str(report.get("error") or "edfi_schools_local_failed"))
            return _render(
                {
                    "ok": True,
                    "action": "schools",
                    "summary": report.get("summary") or "",
                    "columns": report.get("columns") or [],
                    "rows": report.get("rows") or [],
                    "row_count": report.get("row_count"),
                    "from_extract": report.get("from_extract"),
                    "from_warehouse": report.get("from_warehouse"),
                    "live_pull": False,
                    "connection_id": report.get("connection_id"),
                    "district_lea_id": report.get("district_lea_id"),
                    "synced_at": report.get("synced_at") or "",
                    "governed_route": report.get("governed_route") or "local_hold",
                    "teach": "Prefer this local dated list; do not invent campuses.",
                }
            )

        if action in {"schools_refresh", "refresh_schools", "schools_live"}:
            from services.backpack_host.reports import run_backpack_report

            role = resolve_shell_role(
                role=str(args.get("role") or args.get("shell_role") or ""),
                is_admin=bool(context.is_admin),
                context_extra=dict(context.extra or {}),
                policy=dict(context.policy or {}),
            )
            lea = str(args.get("lea") or args.get("district_lea_id") or "").strip()
            report = run_backpack_report(
                "schools",
                role=role,
                lea=lea,
                limit=int(args.get("limit") or 50),
                prefer_local=False,
                force_refresh=True,
            )
            # Rescan fusion after deliberate sync
            try:
                from services.backpack_host.capability_surface import scan_backpack_fusion

                scan_backpack_fusion("edfi", persist=True)
            except Exception:
                pass
            if not report.get("ok"):
                raise ToolInvocationError(str(report.get("error") or "edfi_schools_refresh_failed"))
            return _render(
                {
                    "ok": True,
                    "action": "schools_refresh",
                    "summary": report.get("summary") or "",
                    "row_count": report.get("row_count"),
                    "rate_limited": report.get("rate_limited"),
                    "from_warehouse": report.get("from_warehouse"),
                    "note": "Live/warehouse sync — do not immediately re-run.",
                }
            )

        operation = _ACTION_TO_OPERATION.get(action)
        if not operation:
            if action in {"get", "read"}:
                raise ToolInvocationError(
                    "edfi_governed_read_required:use action=capabilities|health|schools first"
                )
            raise ToolInvocationError(f"unknown_edfi_action:{action}")

        role = resolve_shell_role(
            role=str(args.get("role") or args.get("shell_role") or ""),
            is_admin=bool(context.is_admin),
            context_extra=dict(context.extra or {}),
            policy=dict(context.policy or {}),
        )

        params: dict[str, Any] = {}
        row_limit: int | None = None
        if operation == "list_resources":
            params = {
                "query": str(args.get("query") or args.get("q") or ""),
                "namespace": str(args.get("namespace") or args.get("ns") or ""),
                "offset": int(args.get("offset") or 0),
            }
            row_limit = int(args.get("limit") or 50)
        elif operation in {"list_students", "student_school_associations"}:
            params = {"offset": int(args.get("offset") or 0)}
            row_limit = int(args.get("limit") or 25)
        elif operation == "changes_since":
            params = {
                "resource": str(args.get("resource") or "ed-fi/schools"),
                "offset": int(args.get("offset") or 0),
                "advance_cursor": bool(args.get("advance_cursor")),
            }
            min_cv = args.get("min_change_version")
            if min_cv not in (None, ""):
                params["min_change_version"] = int(min_cv)
            row_limit = int(args.get("limit") or 25)

        result = _governed_query(
            operation,
            params=params or None,
            row_limit=row_limit,
            role=role,
        )
        if operation == "connection_health":
            # Attach fusion snapshot so Nova always sees what it has
            try:
                from services.backpack_host.capability_surface import get_fusion_status

                fusion = get_fusion_status(max_age_sec=120.0, force=False)
            except Exception:
                fusion = {}
            friendly = {
                "ok": bool(result.get("ok") is not False),
                "action": "health",
                "summary": result.get("summary")
                or f"connection health={result.get('health')} lea={result.get('district_lea_id')}",
                "health": result.get("health"),
                "connection_id": result.get("connection_id"),
                "district_lea_id": result.get("district_lea_id"),
                "resource_count": result.get("resource_count"),
                "available_capability_ids": (fusion or {}).get("available_capability_ids") or [],
                "nova_must_know": (fusion or {}).get("nova_must_know") or {},
                "teach_rules": (fusion or {}).get("teach_rules") or [],
                "local_hold": (fusion or {}).get("local_hold") or {},
                "governed_route": "backpack_host",
                "live_pull": False,
            }
            return _render(friendly)

        if not bool(result.get("ok")):
            raise ToolInvocationError(str(result.get("error") or "edfi_governed_query_failed"))
        friendly = {
            "ok": True,
            "summary": result.get("summary") or "",
            "report_intent": result.get("report_intent") or operation,
            "columns": result.get("columns") or [],
            "rows": result.get("rows") or [],
            "row_count": result.get("row_count"),
            "connection_id": result.get("connection_id"),
            "district_lea_id": result.get("district_lea_id"),
            "pipeline_id": result.get("pipeline_id") or PIPELINE_ID,
            "governed_route": result.get("governed_route") or "backpack_host",
        }
        return _render(friendly)
