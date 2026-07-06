from __future__ import annotations

import json
from typing import Any

from .base_tool import NovaTool, ToolContext, ToolInvocationError
from services.edfi.inventory import (
    list_resources,
    profile_summary,
    read_preset,
    read_resource,
)


def _render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2)


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
        connection_id = str(args.get("connection_id") or "district-main").strip() or "district-main"

        if action in {"health", "status"}:
            return _render(profile_summary(connection_id))

        if action in {"list_resources", "resources", "browse"}:
            return _render(
                list_resources(
                    connection_id,
                    query=str(args.get("query") or args.get("q") or ""),
                    namespace=str(args.get("namespace") or args.get("ns") or ""),
                    limit=int(args.get("limit") or 50),
                    offset=int(args.get("offset") or 0),
                )
            )

        if action in {"schools", "students", "student_school_associations"}:
            return _render(
                read_preset(
                    connection_id,
                    action,
                    limit=int(args.get("limit") or 25),
                    offset=int(args.get("offset") or 0),
                )
            )

        if action in {"get", "read"}:
            resource = str(args.get("resource") or args.get("name") or "").strip()
            if not resource:
                raise ToolInvocationError("edfi_resource_required")
            limit = int(args.get("limit") or 25)
            if limit <= 0:
                raise ToolInvocationError("edfi_limit_required")
            return _render(
                read_resource(
                    connection_id,
                    resource,
                    limit=limit,
                    offset=int(args.get("offset") or 0),
                )
            )

        raise ToolInvocationError(f"unknown_edfi_action:{action}")