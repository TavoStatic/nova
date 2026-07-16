from __future__ import annotations

import json
from typing import Any

from .base_tool import NovaTool, ToolContext, ToolInvocationError
from services.pipeline_privileged_bridge import run_governed_pipeline_query

PIPELINE_ID = "edfi_bisd"

_ACTION_TO_OPERATION: dict[str, str] = {
    "health": "connection_health",
    "status": "connection_health",
    "list_resources": "list_resources",
    "resources": "list_resources",
    "browse": "list_resources",
    "schools": "list_schools",
    "students": "list_students",
    "student_school_associations": "student_school_associations",
}


def _render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _governed_query(
    operation: str,
    *,
    params: dict[str, Any] | None = None,
    row_limit: int | None = None,
    requested_by: str = "edfi_explore",
) -> dict[str, Any]:
    return run_governed_pipeline_query(
        PIPELINE_ID,
        operation,
        params,
        row_limit=row_limit,
        requested_by=requested_by,
    )


class EdFiExploreTool(NovaTool):
    name = "edfi_explore"
    description = "Browse Ed-Fi inventory and read schools, students, or any discovered resource"
    category = "data"
    safe = True
    requires_admin = False
    locality = "network"
    mutating = False
    scope = "operator"

    def run(self, args: dict[str, Any], context: ToolContext) -> Any:
        action = str(args.get("action") or "health").strip().lower()
        operation = _ACTION_TO_OPERATION.get(action)
        if not operation:
            if action in {"get", "read"}:
                raise ToolInvocationError(
                    "edfi_governed_read_required:use pipeline preview/run for governed lane reads"
                )
            raise ToolInvocationError(f"unknown_edfi_action:{action}")

        params: dict[str, Any] = {}
        row_limit: int | None = None
        if operation == "list_resources":
            params = {
                "query": str(args.get("query") or args.get("q") or ""),
                "namespace": str(args.get("namespace") or args.get("ns") or ""),
                "offset": int(args.get("offset") or 0),
            }
            row_limit = int(args.get("limit") or 50)
        elif operation in {"list_schools", "list_students", "student_school_associations"}:
            params = {"offset": int(args.get("offset") or 0)}
            row_limit = int(args.get("limit") or 25)

        result = _governed_query(
            operation,
            params=params or None,
            row_limit=row_limit,
            requested_by="edfi_explore",
        )
        if not bool(result.get("ok")):
            raise ToolInvocationError(str(result.get("error") or "edfi_governed_query_failed"))
        return _render(result)