from __future__ import annotations

import importlib.util
import json
import os
import re
import socket
from pathlib import Path
from typing import Any, Mapping, Optional
import winreg

from pipelines.audit import PipelineAuditLogger
from pipelines.base import BaseDataPipeline
from pipelines.base import PipelineManifest
from pipelines.query_guard import PipelineQueryGuard
from pipelines.query_guard import QueryGuardError


def _load_local_config(path: Optional[Path]) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _like_pattern(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _validate_like_pattern(name: str, value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\[\]%.]+", value):
        raise QueryGuardError(f"Invalid {name}; use only letters, numbers, underscore, brackets, percent, and dot.")
    return value


def _current_windows_identity() -> str:
    domain = str(os.environ.get("USERDOMAIN") or "").strip()
    user = str(os.environ.get("USERNAME") or "").strip()
    if domain and user:
        return f"{domain}\\{user}"
    return user


class SisTestPipeline(BaseDataPipeline):
    """Read-only SIS test pipeline scaffold for district-network execution."""

    def __init__(self, manifest: PipelineManifest):
        super().__init__(manifest)
        self.guard = PipelineQueryGuard(max_rows_default=100)
        audit_path = manifest.audit_log_path or (manifest.pipeline_dir / "sis_test_audit.jsonl")
        self.audit = PipelineAuditLogger(audit_path)

    def _client_module_available(self) -> bool:
        return importlib.util.find_spec("adodbapi") is not None

    def _installed_odbc_drivers(self) -> list[str]:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers",
            )
        except OSError:
            return []
        drivers: list[str] = []
        index = 0
        while True:
            try:
                name, value, _value_type = winreg.EnumValue(key, index)
            except OSError:
                break
            if str(value).strip().lower() == "installed":
                drivers.append(str(name))
            index += 1
        return drivers

    def _resolve_driver_name(self, preferred: str) -> Optional[str]:
        available = self._installed_odbc_drivers()
        candidates = [preferred, "ODBC Driver 17 for SQL Server", "SQL Server"]
        for driver in candidates:
            candidate = str(driver or "").strip()
            if candidate and candidate in available:
                return candidate
        return None

    def _connection_timeout_sec(self, config: Mapping[str, Any]) -> int:
        return max(1, int(config.get("connection_timeout_sec") or 5))

    def _port(self, config: Mapping[str, Any]) -> int:
        return max(1, int(config.get("port") or 1433))

    def _auth_mode(self, config: Mapping[str, Any]) -> str:
        return str(config.get("auth_mode") or "sqlserver").strip().lower()

    def _intended_windows_identity(self, config: Mapping[str, Any]) -> str:
        explicit = str(config.get("intended_windows_identity") or "").strip()
        if explicit:
            return explicit.replace("/", "\\")
        username = str(config.get("username") or "").strip()
        if not username:
            return ""
        return username.replace("/", "\\")

    def _build_connection_string(self, config: Mapping[str, Any], driver_name: str) -> str:
        host = str(config.get("host") or "").strip()
        database = str(config.get("database") or "").strip()
        port = self._port(config)
        trust = "Yes" if bool(config.get("trust_server_certificate", True)) else "No"
        auth_mode = self._auth_mode(config)
        base = (
            "Provider=MSDASQL;"
            f"Driver={{{driver_name}}};"
            f"Server={host},{port};"
            f"Database={database};"
            f"TrustServerCertificate={trust};"
        )
        if auth_mode in {"trusted", "windows", "integrated"}:
            return base + "Trusted_Connection=Yes;"
        user = str(config.get("username") or "").strip()
        password = str(config.get("password") or "")
        return base + f"Uid={user};Pwd={password};"

    def _sanitize_error_text(self, exc: Exception | str, config: Mapping[str, Any]) -> str:
        text = str(exc)
        password = str(config.get("password") or "")
        username = str(config.get("username") or "").strip()
        auth_mode = self._auth_mode(config)
        if password:
            text = text.replace(password, "***")
        text = re.sub(r"Pwd=[^;\"']*", "Pwd=***", text, flags=re.IGNORECASE)
        if "Login failed for user" in text:
            if auth_mode in {"trusted", "windows", "integrated"}:
                match = re.search(r"Login failed for user ['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
                identity = match.group(1) if match else ""
                if identity:
                    return f"Login failed for Windows integrated SIS identity ({identity})."
                return "Login failed for Windows integrated SIS identity."
            if username:
                return f"Login failed for configured SIS read-only user ({username})."
            return "Login failed for configured SIS read-only user."
        return text

    def _open_connection(self, config: Mapping[str, Any], driver_name: str):
        import adodbapi

        conn_str = self._build_connection_string(config, driver_name)
        return adodbapi.connect(conn_str, timeout=self._connection_timeout_sec(config))

    def _network_probe(self, host: str, port: int, timeout_sec: float) -> dict[str, Any]:
        if not host:
            return {"reachable": False, "reason": "missing_host"}
        try:
            with socket.create_connection((host, port), timeout=timeout_sec):
                return {"reachable": True, "reason": "connected"}
        except OSError as exc:
            return {"reachable": False, "reason": str(exc)}

    def _auth_probe(self, config: Mapping[str, Any], driver_name: Optional[str]) -> dict[str, Any]:
        if not driver_name:
            return {"authenticated": False, "reason": "missing_driver"}
        if not self._client_module_available():
            return {"authenticated": False, "reason": "missing_client_module"}
        try:
            connection = self._open_connection(config, driver_name)
            cursor = connection.cursor()
            cursor.execute("SELECT 1 AS ok")
            _ = cursor.fetchone()
            cursor.close()
            connection.close()
            return {"authenticated": True, "reason": "connected"}
        except Exception as exc:
            return {"authenticated": False, "reason": self._sanitize_error_text(exc, config)}

    def _readiness_blockers(self, status: Mapping[str, Any]) -> list[str]:
        blockers: list[str] = []
        if not bool(status.get("configured")):
            blockers.append("local_config_incomplete")
        if not bool(status.get("client_module_available")):
            blockers.append("missing_client_module")
        if not bool(status.get("driver_available")):
            blockers.append("missing_odbc_driver")
        network = status.get("network_probe") if isinstance(status.get("network_probe"), Mapping) else {}
        if bool(status.get("configured")) and not bool(network.get("reachable")):
            blockers.append("network_unreachable")
        if bool(status.get("windows_identity_mismatch")):
            blockers.append("windows_identity_mismatch")
        auth = status.get("auth_probe") if isinstance(status.get("auth_probe"), Mapping) else {}
        if (
            bool(status.get("configured"))
            and bool(network.get("reachable"))
            and not bool(status.get("windows_identity_mismatch"))
            and not bool(auth.get("authenticated"))
        ):
            blockers.append("auth_not_ready")
        return blockers

    def _build_live_query(
        self,
        operation: str,
        params: Mapping[str, Any],
        row_limit: int,
    ) -> tuple[str, list[Any]]:
        if operation == "student_lookup":
            sql = (
                f"SELECT TOP {row_limit} "
                "r.STUDENT_ID, r.LAST_NAME, r.FIRST_NAME, r.MIDDLE_NAME, "
                "r.GRADE, r.CURRENT_STATUS, r.BUILDING AS CAMPUS_ID, "
                "b.NAME AS CAMPUS_NAME "
                "FROM dbo.REG r "
                "LEFT JOIN dbo.REG_BUILDING b ON b.BUILDING = r.BUILDING "
                "WHERE 1=1"
            )
            args: list[Any] = []
            if params.get("student_id"):
                sql += " AND r.STUDENT_ID = ?"
                args.append(params["student_id"])
            if params.get("campus_id"):
                sql += " AND r.BUILDING = ?"
                args.append(params["campus_id"])
            if params.get("current_status"):
                sql += " AND r.CURRENT_STATUS = ?"
                args.append(params["current_status"])
            sql += " ORDER BY r.LAST_NAME, r.FIRST_NAME, r.STUDENT_ID"
            return sql, args

        if operation == "campus_enrollment_summary":
            sql = (
                f"SELECT TOP {row_limit} "
                "r.BUILDING AS CAMPUS_ID, b.NAME AS CAMPUS_NAME, "
                "r.GRADE, r.CURRENT_STATUS, COUNT(*) AS STUDENT_COUNT "
                "FROM dbo.REG r "
                "LEFT JOIN dbo.REG_BUILDING b ON b.BUILDING = r.BUILDING "
                "WHERE 1=1"
            )
            args = []
            if params.get("campus_id"):
                sql += " AND r.BUILDING = ?"
                args.append(params["campus_id"])
            if params.get("grade_level"):
                sql += " AND r.GRADE = ?"
                args.append(params["grade_level"])
            if params.get("current_status"):
                sql += " AND r.CURRENT_STATUS = ?"
                args.append(params["current_status"])
            sql += (
                " GROUP BY r.BUILDING, b.NAME, r.GRADE, r.CURRENT_STATUS "
                "ORDER BY r.GRADE, r.CURRENT_STATUS"
            )
            return sql, args

        if operation == "program_membership_lookup":
            sql = (
                f"SELECT TOP {row_limit} "
                "r.STUDENT_ID, r.LAST_NAME, r.FIRST_NAME, r.GRADE, "
                "r.BUILDING AS CAMPUS_ID, b.NAME AS CAMPUS_NAME, "
                "p.PROGRAM_ID, p.PROGRAM_VALUE, p.START_DATE, p.END_DATE "
                "FROM dbo.REG_PROGRAMS p "
                "INNER JOIN dbo.REG r ON p.STUDENT_ID = r.STUDENT_ID "
                "LEFT JOIN dbo.REG_BUILDING b ON b.BUILDING = r.BUILDING "
                "WHERE 1=1"
            )
            args = []
            if params.get("student_id"):
                sql += " AND r.STUDENT_ID = ?"
                args.append(params["student_id"])
            if params.get("campus_id"):
                sql += " AND r.BUILDING = ?"
                args.append(params["campus_id"])
            if params.get("program_id"):
                sql += " AND p.PROGRAM_ID = ?"
                args.append(params["program_id"])
            if params.get("program_value"):
                sql += " AND p.PROGRAM_VALUE = ?"
                args.append(params["program_value"])
            active_only = str(params.get("active_only") or "").strip().lower()
            if active_only in {"1", "true", "yes", "y", "active"}:
                sql += " AND p.END_DATE IS NULL"
            sql += " ORDER BY r.LAST_NAME, r.FIRST_NAME, p.PROGRAM_ID"
            return sql, args

        if operation == "schema_inventory":
            schema_like = _validate_like_pattern("schema_like", _like_pattern(params.get("schema_like"), "dbo"))
            table_like = _validate_like_pattern("table_like", _like_pattern(params.get("table_like"), "%"))
            sql = (
                f"SELECT TOP {row_limit} "
                "s.name AS SchemaName, "
                "t.name AS TableName, "
                "c.column_id AS OrdinalPosition, "
                "c.name AS ColumnName, "
                "ty.name AS DataType, "
                "CASE "
                "WHEN ty.name IN ('varchar','char','nvarchar','nchar') THEN c.max_length "
                "ELSE NULL "
                "END AS MaxLength, "
                "c.precision, "
                "c.scale, "
                "c.is_nullable AS IsNullable, "
                "c.is_identity AS IsIdentity, "
                "dc.definition AS DefaultValue, "
                "CASE WHEN pk.column_id IS NOT NULL THEN 1 ELSE 0 END AS IsPrimaryKey "
                "FROM sys.tables t "
                "JOIN sys.schemas s ON s.schema_id = t.schema_id "
                "JOIN sys.columns c ON c.object_id = t.object_id "
                "JOIN sys.types ty ON c.user_type_id = ty.user_type_id "
                "LEFT JOIN sys.default_constraints dc "
                "ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id "
                "LEFT JOIN ("
                "SELECT ic.object_id, ic.column_id "
                "FROM sys.indexes i "
                "JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id "
                "WHERE i.is_primary_key = 1"
                ") pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id "
                "WHERE s.name LIKE ? AND t.name LIKE ? "
                "ORDER BY s.name, t.name, c.column_id"
            )
            return sql, [schema_like, table_like]

        raise QueryGuardError(f"Live query builder not implemented for operation: {operation}")

    def _execute_live_query(
        self,
        config: Mapping[str, Any],
        driver_name: str,
        operation: str,
        params: Mapping[str, Any],
        row_limit: int,
    ) -> dict[str, Any]:
        sql, args = self._build_live_query(operation, params, row_limit)
        connection = self._open_connection(config, driver_name)
        try:
            cursor = connection.cursor()
            cursor.execute(sql, args)
            columns = [str(column[0]) for column in (cursor.description or [])]
            rows = cursor.fetchall()
            cursor.close()
        finally:
            connection.close()
        normalized_rows = [dict(zip(columns, row)) for row in rows]
        return {
            "columns": columns,
            "rows": normalized_rows,
            "row_count": len(normalized_rows),
        }

    def status(self) -> dict[str, Any]:
        config = _load_local_config(self.manifest.local_config_path)
        host = str(config.get("host") or "").strip()
        database = str(config.get("database") or "").strip()
        port = self._port(config)
        timeout_sec = float(self._connection_timeout_sec(config))
        configured = bool(host and database)
        driver_requested = str(config.get("driver") or "").strip() or None
        driver_selected = self._resolve_driver_name(driver_requested or "")
        auth_mode = self._auth_mode(config)
        current_windows_identity = _current_windows_identity()
        intended_windows_identity = (
            self._intended_windows_identity(config)
            if auth_mode in {"trusted", "windows", "integrated"}
            else ""
        )
        identity_mismatch = bool(
            intended_windows_identity
            and current_windows_identity
            and intended_windows_identity.lower() != current_windows_identity.lower()
        )
        network_probe = (
            self._network_probe(host, port, timeout_sec)
            if configured
            else {"reachable": False, "reason": "local_config_incomplete"}
        )
        if configured and network_probe.get("reachable") and identity_mismatch:
            auth_probe = {"authenticated": False, "reason": "windows_identity_mismatch"}
        elif configured and network_probe.get("reachable"):
            auth_probe = self._auth_probe(config, driver_selected)
        else:
            auth_probe = {"authenticated": False, "reason": "network_unreachable"}
        live_query_ready = bool(
            configured
            and self._client_module_available()
            and driver_selected
            and network_probe.get("reachable")
            and not identity_mismatch
            and auth_probe.get("authenticated")
        )
        payload = {
            "pipeline_id": self.manifest.pipeline_id,
            "display_name": self.manifest.display_name,
            "kind": self.manifest.kind,
            "read_only": self.manifest.read_only,
            "network_scope": self.manifest.network_scope,
            "configured": configured,
            "client_module": "adodbapi" if self._client_module_available() else None,
            "client_module_available": self._client_module_available(),
            "driver_requested": driver_requested,
            "driver_selected": driver_selected,
            "driver_available": bool(driver_selected),
            "installed_odbc_drivers": self._installed_odbc_drivers(),
            "host": host or None,
            "database": database or None,
            "port": port,
            "auth_mode": auth_mode,
            "current_windows_identity": current_windows_identity if auth_mode in {"trusted", "windows", "integrated"} else "",
            "intended_windows_identity": intended_windows_identity,
            "windows_identity_mismatch": identity_mismatch,
            "local_config_path": str(self.manifest.local_config_path) if self.manifest.local_config_path else None,
            "config_example_path": str(self.manifest.config_example_path) if self.manifest.config_example_path else None,
            "query_template_count": len(self.load_query_templates()),
            "entity_count": len(self.load_schema_manifest().get("entities") or []),
            "network_probe": network_probe,
            "auth_probe": auth_probe,
            "live_query_ready": live_query_ready,
            "execution_supported": True,
        }
        blockers = self._readiness_blockers(payload)
        next_step = self._safe_query_next_step(payload, live_query_ready)
        payload["readiness"] = {
            "state": "ready" if live_query_ready else "blocked",
            "blockers": blockers,
            "next_step": next_step,
        }
        payload["readiness_blockers"] = blockers
        payload["next_step"] = next_step
        return payload

    def schema_probe(self) -> dict[str, Any]:
        payload = super().schema_probe()
        payload["status"] = self.status()
        return payload

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
        config = _load_local_config(self.manifest.local_config_path)
        status = self.status()
        ready = bool(status.get("live_query_ready"))
        base_payload = {
            "pipeline_id": self.manifest.pipeline_id,
            "operation": validated["operation"],
            "description": template.get("description") or "",
            "tables": list(template.get("tables") or []),
            "params": validated["params"],
            "requested_row_limit": validated["requested_row_limit"],
            "effective_row_limit": validated["effective_row_limit"],
            "row_limit_clamped": validated["row_limit_clamped"],
            "read_only": self.manifest.read_only,
            "live_query_ready": ready,
            "execution_supported": True,
        }
        if not dry_run and ready:
            driver_name = str(status.get("driver_selected") or "")
            try:
                result = self._execute_live_query(
                    config,
                    driver_name,
                    validated["operation"],
                    validated["params"],
                    validated["effective_row_limit"],
                )
            except Exception as exc:
                sanitized = self._sanitize_error_text(exc, config)
                self.audit.append(
                    pipeline_id=self.manifest.pipeline_id,
                    action=validated["operation"],
                    status="error",
                    detail="pipeline_live_query_error",
                    data={"error": sanitized},
                )
                return {
                    "ok": False,
                    **base_payload,
                    "execution_mode": "live",
                    "error": sanitized,
                }
            self.audit.append(
                pipeline_id=self.manifest.pipeline_id,
                action=validated["operation"],
                status="ok",
                detail="pipeline_live_query_ok",
                data={"row_count": result["row_count"]},
            )
            return {
                "ok": True,
                **base_payload,
                "execution_mode": "live",
                **result,
            }

        if not dry_run and not ready:
            reason = ((status.get("auth_probe") or {}).get("reason") or "pipeline_not_ready")
            next_step = str(status.get("next_step") or self._safe_query_next_step(status, ready))
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
                "next_step": next_step,
            }

        payload = {
            "ok": True,
            **base_payload,
            "execution_mode": "dry_run",
            "next_step": self._safe_query_next_step(status, ready),
        }
        self.audit.append(
            pipeline_id=self.manifest.pipeline_id,
            action=validated["operation"],
            status="ok",
            detail="pipeline_safe_query_preview",
            data={
                "tables": payload["tables"],
                "effective_row_limit": payload["effective_row_limit"],
                "execution_mode": payload["execution_mode"],
            },
        )
        return payload

    def _safe_query_next_step(self, status: Mapping[str, Any], ready: bool) -> str:
        if ready:
            return "Live execution is ready; rerun this operation with dry_run=False to query the SIS test database."
        if not bool(status.get("configured")):
            return "Add local_config.json on the district network to enable connectivity checks."
        network = status.get("network_probe") if isinstance(status.get("network_probe"), Mapping) else {}
        if not bool(network.get("reachable")):
            reason = str(network.get("reason") or "network_unreachable")
            return f"Fix SIS network reachability before live execution: {reason}"
        if bool(status.get("windows_identity_mismatch")):
            reason = str(((status.get("auth_probe") or {}).get("reason") or "windows_identity_mismatch"))
            return (
                "Run the SIS pipeline under the intended Windows identity "
                f"{status.get('intended_windows_identity')} instead of "
                f"{status.get('current_windows_identity')}; trusted auth uses the process identity. "
                f"Current auth result: {reason}"
            )
        if not bool(status.get("driver_available")):
            return "Install or configure an available SIS ODBC driver before live execution."
        if not bool(status.get("client_module_available")):
            return "Install the SIS database client module before live execution."
        auth = status.get("auth_probe") if isinstance(status.get("auth_probe"), Mapping) else {}
        if not bool(auth.get("authenticated")):
            reason = str(auth.get("reason") or "auth_not_ready")
            return f"Fix SIS read-only authentication before live execution: {reason}"
        return "Fix pipeline readiness before live execution."
