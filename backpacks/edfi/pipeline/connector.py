from __future__ import annotations

"""
Ed-Fi Backpack — Governed Pipeline Connector

District-agnostic version of the Ed-Fi governed read lane.
Connection ID and LEA ID come from settings (set by account_admin at install),
not from hardcoded values.

Replaces: data_sources/edfi_bisd/connector.py (BISD-specific)
Uses:     services/edfi/* (shared Ed-Fi protocol library)
"""

import json
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from pipelines.audit import PipelineAuditLogger
from pipelines.base import BaseDataPipeline, PipelineManifest
from pipelines.query_guard import PipelineQueryGuard, QueryGuardError
from pipelines.redaction import apply_redaction_to_payload, resolve_redaction_profile
from services.edfi.config import load_capability_profile, load_connection_config
from services.edfi.change_tracking import load_sync_state, pull_changes_since, sync_status
from services.edfi.inventory import list_resources, profile_summary, read_preset, read_resource


_DEFAULT_CONNECTION_ID = "district-main"
# connection_health is disk-profile only but was spammed every ~30s by UI/tools.
_HEALTH_AUDIT_MIN_INTERVAL_SEC = 300.0
_LAST_HEALTH_AUDIT_EPOCH: float = 0.0


def _load_settings(path: Path | None) -> dict[str, Any]:
    """Load backpack settings from the local config file (written by account_admin at install)."""
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _truthy_param(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "full", "all"}


def _effective_query_resource(
    operation: str,
    params: Mapping[str, Any],
    raw: Mapping[str, Any] | None = None,
) -> str | None:
    resource = params.get("resource")
    if resource not in (None, ""):
        return str(resource)
    if isinstance(raw, Mapping):
        raw_resource = raw.get("resource")
        if raw_resource not in (None, ""):
            return str(raw_resource)
    _defaults = {
        "changes_since": "ed-fi/schools",
        "list_students": "ed-fi/students",
        "student_school_associations": "ed-fi/studentSchoolAssociations",
        "list_schools": "ed-fi/schools",
    }
    return _defaults.get(operation)


def _shape_rows(items: list[Any]) -> dict[str, Any]:
    rows = [item for item in items if isinstance(item, dict)]
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows[:5]:
        for key in row.keys():
            name = str(key)
            if name not in seen:
                seen.add(name)
                columns.append(name)
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "items": rows,
    }


class EdFiPipeline(BaseDataPipeline):
    """
    Governed read-only Ed-Fi pipeline.

    District-agnostic: connection_id and district_lea_id are read from
    the settings file written by account_admin at install time.
    """

    def __init__(self, manifest: PipelineManifest) -> None:
        super().__init__(manifest)
        # Schools for a full LEA often exceed 25–50 campuses. Hard cap is high for
        # LEA-scoped extracts; per-operation max_rows in query_templates.json is the
        # real throttle (students stay lower because of PII volume).
        # Hard cap is a safety ceiling for full-LEA extracts (dynamic match count).
        # Per-op max_rows in query_templates still governs casual page reads.
        self.guard = PipelineQueryGuard(max_rows_default=50, max_rows_hard_cap=2000)
        audit_path = manifest.audit_log_path or (manifest.pipeline_dir / "edfi_audit.jsonl")
        self.audit = PipelineAuditLogger(audit_path)

    # ── Settings ───────────────────────────────────────────────────────────

    def _settings(self) -> dict[str, Any]:
        return _load_settings(self.manifest.local_config_path)

    def _connection_id(self) -> str:
        return str(
            self._settings().get("connection_id") or _DEFAULT_CONNECTION_ID
        ).strip() or _DEFAULT_CONNECTION_ID

    def _district_lea_id(self) -> str:
        from services.backpack_host.scope_settings import primary_lea_from_settings

        settings = self._settings()
        lea = primary_lea_from_settings(settings)
        if not lea:
            conn = load_connection_config(self._connection_id())
            if conn:
                lea = str(conn.district_lea_id or "").strip()
        return lea

    def _scope_snapshot(self) -> dict[str, Any]:
        from services.backpack_host.scope_settings import (
            allowed_leas_from_settings,
            normalize_access_tier,
            normalize_scope_mode,
        )

        settings = self._settings()
        mode = normalize_scope_mode(settings.get("scope_mode"))
        return {
            "scope_mode": mode,
            "district_lea_id": self._district_lea_id(),
            "allowed_lea_ids": allowed_leas_from_settings(settings),
            "credential_access_tier": normalize_access_tier(
                settings.get("credential_access_tier")
            ),
        }

    def _resolve_lea_for_query(self, params: Mapping[str, Any]) -> tuple[str, str | None]:
        from services.backpack_host.scope_settings import resolve_query_lea

        # Merge connection-config LEA when backpack settings.json is not yet filled
        # (common on dev boxes that only have runtime/edfi/connections/*/local_config.json).
        settings = dict(self._settings() or {})
        if not str(settings.get("district_lea_id") or "").strip():
            primary = self._district_lea_id()
            if primary:
                settings["district_lea_id"] = primary
        if not str(settings.get("scope_mode") or "").strip():
            settings["scope_mode"] = "single_lea"
        request_lea = str(
            params.get("district_lea_id") or params.get("lea_id") or ""
        ).strip()
        return resolve_query_lea(settings, request_lea or None)

    # ── Readiness ──────────────────────────────────────────────────────────

    def _readiness(self) -> dict[str, Any]:
        from services.backpack_host.scope_settings import (
            SCOPE_MULTI,
            allowed_leas_from_settings,
            normalize_scope_mode,
        )

        connection_id = self._connection_id()
        conn = load_connection_config(connection_id)
        profile = load_capability_profile(connection_id)
        profile_ok = bool(profile)
        auth_ok = bool((profile.get("auth") or {}).get("ok")) if profile_ok else False
        scope = self._scope_snapshot()
        district_lea_id = str(scope.get("district_lea_id") or "")
        change_state = load_sync_state(connection_id) if profile_ok and auth_ok else {}
        mode = normalize_scope_mode(scope.get("scope_mode"))
        allowed = list(scope.get("allowed_lea_ids") or allowed_leas_from_settings(self._settings()))

        blockers: list[str] = []
        if conn is None:
            blockers.append("edfi_connection_config_missing")
        if not profile_ok:
            blockers.append("edfi_capability_profile_missing")
        if profile_ok and not auth_ok:
            blockers.append("edfi_profile_auth_not_ok")
        if conn is not None and mode == SCOPE_MULTI and not allowed:
            blockers.append("allowed_lea_ids_missing")
        elif conn is not None and not district_lea_id:
            blockers.append("district_lea_id_missing")

        return {
            "connection_id": connection_id,
            "configured": conn is not None,
            "profile_ok": profile_ok,
            "auth_ok": auth_ok,
            "district_lea_id": district_lea_id,
            "scope_mode": mode,
            "allowed_lea_ids": allowed,
            "credential_access_tier": scope.get("credential_access_tier"),
            "change_sync_ok": bool(change_state),
            "change_sync": change_state,
            "ready": not blockers,
            "blockers": blockers,
        }

    def _next_step(self, readiness: Mapping[str, Any]) -> str:
        if readiness.get("ready"):
            return (
                "Ed-Fi connection is ready. Use the control panel or "
                "Nova tool for governed reads."
            )
        blockers = list(readiness.get("blockers") or [])
        if "edfi_connection_config_missing" in blockers:
            return (
                "Connection config missing. account_admin must complete "
                "backpack install settings."
            )
        if "edfi_capability_profile_missing" in blockers:
            return (
                "Capability profile missing. Run the 'install' operation "
                "to authenticate and discover ODS resources."
            )
        if "edfi_profile_auth_not_ok" in blockers:
            return (
                "Authentication failed on last profile run. "
                "Check ODS credentials in backpack settings."
            )
        if "district_lea_id_missing" in blockers:
            return (
                "District LEA ID is not set. account_admin must set "
                "district_lea_id in backpack settings (single_lea mode)."
            )
        if "allowed_lea_ids_missing" in blockers:
            return (
                "Region mode requires allowed_lea_ids (list of LEA ids). "
                "account_admin must set them in backpack settings."
            )
        return "Resolve Ed-Fi readiness blockers before running queries."

    # ── Status ─────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        readiness = self._readiness()
        connection_id = readiness["connection_id"]
        profile = profile_summary(connection_id) if readiness["profile_ok"] else {}
        return {
            "backpack_id": "edfi",
            "pipeline_id": self.manifest.pipeline_id,
            "display_name": self.manifest.display_name,
            "kind": self.manifest.kind,
            "read_only": self.manifest.read_only,
            "network_scope": self.manifest.network_scope,
            "connection_id": connection_id,
            "configured": readiness["configured"],
            "profile_ok": readiness["profile_ok"],
            "auth_ok": readiness["auth_ok"],
            "district_lea_id": readiness["district_lea_id"],
            "scope_mode": readiness.get("scope_mode"),
            "allowed_lea_ids": readiness.get("allowed_lea_ids") or [],
            "credential_access_tier": readiness.get("credential_access_tier"),
            "profile_health": str(profile.get("health") or "unknown"),
            "resource_count": int(profile.get("resource_count") or 0),
            "change_sync_ok": bool(readiness.get("change_sync_ok")),
            "newest_change_version": int(
                ((readiness.get("change_sync") or {}).get("available") or {}).get(
                    "newest_change_version"
                ) or 0
            ),
            "change_sync": readiness.get("change_sync") or {},
            "query_template_count": len(self.load_query_templates()),
            "entity_count": len(self.load_schema_manifest().get("entities") or []),
            "live_query_ready": readiness["ready"],
            "execution_supported": True,
            "readiness": {
                "state": "ready" if readiness["ready"] else "blocked",
                "blockers": readiness["blockers"],
                "next_step": self._next_step(readiness),
            },
        }

    # ── Operations ─────────────────────────────────────────────────────────

    def _execute_operation(
        self,
        operation: str,
        params: Mapping[str, Any],
        row_limit: int,
    ) -> dict[str, Any]:
        connection_id = self._connection_id()
        offset = max(0, int(params.get("offset") or 0))

        if operation == "connection_health":
            summary = profile_summary(connection_id)
            if isinstance(summary, dict):
                summary = {**summary, **self._scope_snapshot()}
            return summary

        # Data ops: resolve LEA (district one-id, or region pick from allowed list)
        lea_id = ""
        if operation in {
            "list_schools",
            "list_students",
            "student_school_associations",
            "changes_since",
        }:
            lea_id, lea_err = self._resolve_lea_for_query(params)
            if lea_err:
                raise QueryGuardError(lea_err)

        if operation == "list_schools":
            full_lea = _truthy_param(params.get("full_lea")) or _truthy_param(
                params.get("collect_all")
            )
            return read_preset(
                connection_id,
                "schools",
                # full_lea: match budget is dynamic (all LEA schools); soft safety 2000
                limit=2000 if full_lea else row_limit,
                offset=offset,
                district_lea_id_override=lea_id or None,
                collect_all=full_lea,
            )

        if operation == "list_students":
            return read_preset(
                connection_id,
                "students",
                limit=row_limit,
                offset=offset,
                district_lea_id_override=lea_id or None,
            )

        if operation == "student_school_associations":
            return read_preset(
                connection_id,
                "student_school_associations",
                limit=row_limit,
                offset=offset,
                district_lea_id_override=lea_id or None,
            )

        if operation == "list_resources":
            return list_resources(
                connection_id,
                query=str(params.get("query") or ""),
                namespace=str(params.get("namespace") or ""),
                limit=row_limit,
                offset=offset,
            )

        if operation == "sync_status":
            return sync_status(connection_id)

        if operation == "changes_since":
            min_raw = params.get("min_change_version")
            min_change_version = int(min_raw) if min_raw not in (None, "") else None
            # Change pull still uses connection primary LEA in core services;
            # override is applied when inventory paths are used above.
            return pull_changes_since(
                connection_id,
                resource=str(params.get("resource") or "ed-fi/schools"),
                min_change_version=min_change_version,
                limit=row_limit,
                offset=offset,
                advance_cursor=bool(params.get("advance_cursor")),
            )

        raise QueryGuardError(f"Unknown operation: {operation}")

    # ── Governed query ─────────────────────────────────────────────────────

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
            "backpack_id": "edfi",
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

            effective_resource = _effective_query_resource(
                validated["operation"], validated["params"], raw
            )
            redaction_profile = resolve_redaction_profile(
                operation=validated["operation"],
                template_profile=validated.get("redaction_profile")
                or template.get("redaction_profile"),
                resource=effective_resource,
            )

            if not raw.get("ok"):
                self.audit.append(
                    pipeline_id=self.manifest.pipeline_id,
                    action=validated["operation"],
                    status="error",
                    detail=str(raw.get("error_code") or "edfi_query_failed"),
                    data={"error": str(raw.get("error") or "")},
                )
                return apply_redaction_to_payload(
                    {
                        "ok": False,
                        **base_payload,
                        "execution_mode": "live",
                        "error": str(
                            raw.get("error") or raw.get("error_code") or "edfi_query_failed"
                        ),
                        "edfi": raw,
                    },
                    redaction_profile,
                    resource=effective_resource,
                )

            # Report presentation: stable columns + summary for Nova dashboards.
            # Raw ODS items stay under edfi.raw_items (capped) for debugging only.
            from services.edfi.present import present_operation_result

            presented = present_operation_result(validated["operation"], raw)
            shaped = {
                "columns": list(presented.get("columns") or []),
                "rows": list(presented.get("rows") or []),
                "row_count": int(presented.get("row_count") or 0),
                "items": list(presented.get("rows") or []),
                "summary": str(presented.get("summary") or ""),
                "report_intent": str(presented.get("report_intent") or validated["operation"]),
                "reader_friendly": True,
            }

            op_name = str(validated["operation"] or "")
            is_health = op_name == "connection_health"
            # Health is local profile data — do not mark as live TEA traffic.
            execution_mode = "local_profile" if is_health else "live"

            should_audit = True
            if is_health:
                global _LAST_HEALTH_AUDIT_EPOCH
                now = time.time()
                if now - _LAST_HEALTH_AUDIT_EPOCH < _HEALTH_AUDIT_MIN_INTERVAL_SEC:
                    should_audit = False
                else:
                    _LAST_HEALTH_AUDIT_EPOCH = now

            if should_audit:
                self.audit.append(
                    pipeline_id=self.manifest.pipeline_id,
                    action=op_name,
                    status="ok",
                    detail="pipeline_live_query_ok" if not is_health else "pipeline_local_health_ok",
                    data={
                        "row_count": shaped["row_count"],
                        "records_scanned": int(raw.get("records_scanned") or 0),
                        "report_intent": shaped["report_intent"],
                        "execution_mode": execution_mode,
                    },
                )

            # Holding cell: save schools/students extracts after any successful live pull.
            if op_name in {"list_schools", "list_students"} and shaped["rows"]:
                try:
                    from services.edfi.extract_store import save_extract

                    lea_raw = str(
                        validated["params"].get("district_lea_id")
                        or status.get("district_lea_id")
                        or ""
                    )
                    try:
                        from services.backpack_host.scope_settings import format_lea_id

                        lea_for_extract = format_lea_id(lea_raw) if lea_raw else ""
                    except Exception:
                        lea_for_extract = lea_raw
                    save_extract(
                        backpack_id=self.manifest.pipeline_id,
                        intent="schools" if op_name == "list_schools" else "students",
                        lea=lea_for_extract,
                        connection_id=str(status.get("connection_id") or ""),
                        columns=list(shaped["columns"]),
                        rows=list(shaped["rows"]),
                        summary=str(shaped["summary"] or ""),
                        meta={
                            "source": "backpack_connector",
                            "records_scanned": int(raw.get("records_scanned") or 0),
                        },
                    )
                    shaped["summary"] = (
                        str(shaped["summary"] or "") + " [saved as local extract]"
                    ).strip()
                    shaped["extract_saved"] = True
                except Exception as exc:
                    shaped["extract_saved"] = False
                    shaped["extract_save_error"] = str(exc)[:160]

            raw_items = list(raw.get("items") or [])
            response = apply_redaction_to_payload(
                {
                    "ok": True,
                    **base_payload,
                    "execution_mode": execution_mode,
                    **shaped,
                    "edfi": {
                        "resource": raw.get("resource"),
                        "district_filter_strategy": raw.get("district_filter_strategy"),
                        "records_scanned": raw.get("records_scanned"),
                        "scan_cap_hit": raw.get("scan_cap_hit"),
                        "district_page_complete": raw.get("district_page_complete"),
                        "filter": raw.get("filter"),
                        # Cap raw dump so chat/UI stay readable; full raw is for debug only.
                        "raw_item_count": len(raw_items),
                        "raw_items_sample": raw_items[:3],
                    },
                },
                redaction_profile,
                resource=effective_resource,
            )
            if validated["operation"] == "changes_since":
                response.update({
                    "mechanism": raw.get("mechanism"),
                    "min_change_version": raw.get("min_change_version"),
                    "next_change_version": raw.get("next_change_version"),
                    "note": raw.get("note"),
                })
            return response

        if not dry_run and not ready:
            reason = str(status.get("readiness", {}).get("next_step") or "pipeline_not_ready")
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

        # dry_run preview
        preview_resource = _effective_query_resource(validated["operation"], validated["params"])
        preview_profile = resolve_redaction_profile(
            operation=validated["operation"],
            template_profile=validated.get("redaction_profile")
            or template.get("redaction_profile"),
            resource=preview_resource,
        )
        payload = apply_redaction_to_payload(
            {
                "ok": True,
                **base_payload,
                "execution_mode": "dry_run",
                "next_step": status.get("readiness", {}).get("next_step"),
            },
            preview_profile,
            resource=preview_resource,
        )
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
