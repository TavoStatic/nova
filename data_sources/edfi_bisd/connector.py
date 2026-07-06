from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from pipelines.audit import PipelineAuditLogger
from pipelines.base import BaseDataPipeline, PipelineManifest
from pipelines.query_guard import PipelineQueryGuard, QueryGuardError
from services.edfi.config import load_capability_profile, load_connection_config
from services.edfi.inventory import list_resources, profile_summary, read_preset, read_resource


def _load_local_config(path: Optional[Path]) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _shape_rows(items: list[Any]) -> dict[str, Any]:
    rows = [item for item in items if isinstance(item, dict)]
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows[:5]:
        for key in row.keys():
            name = str(key)
            if name in seen:
                continue
            seen.add(name)
            columns.append(name)
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "items": rows,
    }


class EdFiBisdPipeline(BaseDataPipeline):
    """Governed read-only lane: BISD Ed-Fi via Nova Ed-Fi Core."""

    def __init__(self, manifest: PipelineManifest):
        super().__init__(manifest)
        self.guard = PipelineQueryGuard(max_rows_default=25, max_rows_hard_cap=50)
        audit_path = manifest.audit_log_path or (manifest.pipeline_dir / "edfi_bisd_audit.jsonl")
        self.audit = PipelineAuditLogger(audit_path)

    def _connection_id(self) -> str:
        config = _load_local_config(self.manifest.local_config_path)
        return str(config.get("connection_id") or "district-main").strip() or "district-main"

    def _readiness(self) -> dict[str, Any]:
        connection_id = self._connection_id()
        conn = load_connection_config(connection_id)
        profile = load_capability_profile(connection_id)
        profile_ok = bool(profile)
        auth_ok = bool((profile.get("auth") or {}).get("ok")) if profile_ok else False
        district_lea_id = str(conn.district_lea_id if conn else "")
        blockers: list[str] = []
        if conn is None:
            blockers.append("edfi_connection_config_missing")
        if not profile_ok:
            blockers.append("edfi_capability_profile_missing")
        if profile_ok and not auth_ok:
            blockers.append("edfi_profile_auth_not_ok")
        if conn is not None and not district_lea_id:
            blockers.append("district_lea_id_missing")
        ready = not blockers
        return {
            "connection_id": connection_id,
            "configured": conn is not None,
            "profile_ok": profile_ok,
            "auth_ok": auth_ok,
            "district_lea_id": district_lea_id,
            "ready": ready,
            "blockers": blockers,
        }

    def status(self) -> dict[str, Any]:
        readiness = self._readiness()
        profile = profile_summary(readiness["connection_id"]) if readiness["profile_ok"] else {}
        return {
            "pipeline_id": self.manifest.pipeline_id,
            "display_name": self.manifest.display_name,
            "kind": self.manifest.kind,
            "read_only": self.manifest.read_only,
            "network_scope": self.manifest.network_scope,
            "connection_id": readiness["connection_id"],
            "configured": readiness["configured"],
            "profile_ok": readiness["profile_ok"],
            "auth_ok": readiness["auth_ok"],
            "district_lea_id": readiness["district_lea_id"],
            "profile_health": str(profile.get("health") or "unknown"),
            "resource_count": int(profile.get("resource_count") or 0),
            "query_template_count": len(self.load_query_templates()),
            "entity_count": len(self.load_schema_manifest().get("entities") or []),
            "live_query_ready": readiness["ready"],
            "execution_supported": True,
            "readiness": {
                "state": "ready" if readiness["ready"] else "blocked",
                "blockers": readiness["blockers"],
                "next_step": self._next_step(readiness),
            },
            "readiness_blockers": readiness["blockers"],
            "next_step": self._next_step(readiness),
        }

    def _next_step(self, readiness: Mapping[str, Any]) -> str:
        if readiness.get("ready"):
            return "Live execution is ready; rerun with dry_run=False via pipeline preview or tool_pipeline."
        blockers = list(readiness.get("blockers") or [])
        if "edfi_connection_config_missing" in blockers:
            return "Run scripts/run_edfi_profile.py to save runtime/edfi/connections/district-main/local_config.json."
        if "edfi_capability_profile_missing" in blockers:
            return "Run scripts/run_edfi_profile.py to create runtime/edfi/profiles/district-main.json."
        if "district_lea_id_missing" in blockers:
            return "Set district_lea_id (31901) in runtime/edfi/connections/district-main/local_config.json."
        return "Resolve Ed-Fi readiness blockers before live execution."

    def _execute_operation(
        self,
        operation: str,
        params: Mapping[str, Any],
        row_limit: int,
    ) -> dict[str, Any]:
        connection_id = self._connection_id()
        offset = max(0, int(params.get("offset") or 0))

        if operation == "connection_health":
            return profile_summary(connection_id)

        if operation == "list_schools":
            return read_preset(connection_id, "schools", limit=row_limit, offset=offset)

        if operation == "list_students":
            return read_preset(connection_id, "students", limit=row_limit, offset=offset)

        if operation == "student_school_associations":
            return read_preset(
                connection_id,
                "student_school_associations",
                limit=row_limit,
                offset=offset,
            )

        if operation == "list_resources":
            return list_resources(
                connection_id,
                query=str(params.get("query") or ""),
                namespace=str(params.get("namespace") or ""),
                limit=row_limit,
                offset=offset,
            )

        raise QueryGuardError(f"Live query builder not implemented for operation: {operation}")

    def safe_query(
        self,
        operation: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        row_limit: Optional[int] = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        try:
            validated = self.guard.validate(
                self.load_query_templates(),
                operation,
                params,
                row_limit=row_limit,
            )
        except QueryGuardError as exc:
            self.audit.append(
                pipeline_id=self.manifest.pipeline_id,
                action=operation,
                status="denied",
                detail=str(exc),
                data={"params": dict(params or {})},
            )
            return {
                "ok": False,
                "pipeline_id": self.manifest.pipeline_id,
                "operation": operation,
                "error": str(exc),
            }

        template = validated["template"]
        status = self.status()
        ready = bool(status.get("live_query_ready"))
        resources = list(template.get("resources") or [])
        base_payload = {
            "pipeline_id": self.manifest.pipeline_id,
            "operation": validated["operation"],
            "description": template.get("description") or "",
            "resources": resources,
            "params": validated["params"],
            "requested_row_limit": validated["requested_row_limit"],
            "effective_row_limit": validated["effective_row_limit"],
            "row_limit_clamped": validated["row_limit_clamped"],
            "read_only": self.manifest.read_only,
            "live_query_ready": ready,
            "execution_supported": True,
            "connection_id": status.get("connection_id"),
            "district_lea_id": status.get("district_lea_id"),
        }

        if not dry_run and ready:
            try:
                raw = self._execute_operation(
                    validated["operation"],
                    validated["params"],
                    validated["effective_row_limit"],
                )
            except Exception as exc:
                self.audit.append(
                    pipeline_id=self.manifest.pipeline_id,
                    action=validated["operation"],
                    status="error",
                    detail="pipeline_live_query_error",
                    data={"error": str(exc)},
                )
                return {
                    "ok": False,
                    **base_payload,
                    "execution_mode": "live",
                    "error": str(exc),
                }

            if not raw.get("ok"):
                self.audit.append(
                    pipeline_id=self.manifest.pipeline_id,
                    action=validated["operation"],
                    status="error",
                    detail=str(raw.get("error_code") or "edfi_query_failed"),
                    data={"error": str(raw.get("error") or "")},
                )
                return {
                    "ok": False,
                    **base_payload,
                    "execution_mode": "live",
                    "error": str(raw.get("error") or raw.get("error_code") or "edfi_query_failed"),
                    "edfi": raw,
                }

            if validated["operation"] == "list_resources":
                shaped = {
                    "columns": ["resource"],
                    "rows": [{"resource": name} for name in raw.get("resources") or []],
                    "row_count": len(raw.get("resources") or []),
                    "items": raw.get("resources") or [],
                }
            elif validated["operation"] == "connection_health":
                shaped = {
                    "columns": sorted(raw.keys()),
                    "rows": [raw],
                    "row_count": 1,
                    "items": [raw],
                }
            else:
                shaped = _shape_rows(list(raw.get("items") or []))

            self.audit.append(
                pipeline_id=self.manifest.pipeline_id,
                action=validated["operation"],
                status="ok",
                detail="pipeline_live_query_ok",
                data={
                    "row_count": shaped["row_count"],
                    "records_scanned": int(raw.get("records_scanned") or 0),
                },
            )
            return {
                "ok": True,
                **base_payload,
                "execution_mode": "live",
                **shaped,
                "edfi": {
                    "resource": raw.get("resource"),
                    "district_filter_strategy": raw.get("district_filter_strategy"),
                    "records_scanned": raw.get("records_scanned"),
                    "filter": raw.get("filter"),
                },
            }

        if not dry_run and not ready:
            reason = str(status.get("next_step") or "pipeline_not_ready")
            self.audit.append(
                pipeline_id=self.manifest.pipeline_id,
                action=validated["operation"],
                status="denied",
                detail="pipeline_live_query_blocked",
                data={"reason": reason},
            )
            return {
                "ok": False,
                **base_payload,
                "execution_mode": "blocked",
                "error": reason,
                "next_step": reason,
            }

        payload = {
            "ok": True,
            **base_payload,
            "execution_mode": "dry_run",
            "next_step": status.get("next_step"),
        }
        self.audit.append(
            pipeline_id=self.manifest.pipeline_id,
            action=validated["operation"],
            status="ok",
            detail="pipeline_safe_query_preview",
            data={
                "resources": resources,
                "effective_row_limit": payload["effective_row_limit"],
                "execution_mode": payload["execution_mode"],
            },
        )
        return payload