from __future__ import annotations

import importlib.util
import json
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
        if password:
            text = text.replace(password, "***")
        text = re.sub(r"Pwd=[^;\"']*", "Pwd=***", text, flags=re.IGNORECASE)
        if "Login failed for user" in text:
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
        network_probe = (
            self._network_probe(host, port, timeout_sec)
            if configured
            else {"reachable": False, "reason": "local_config_incomplete"}
        )
        auth_probe = (
            self._auth_probe(config, driver_selected)
            if configured and network_probe.get("reachable")
            else {"authenticated": False, "reason": "network_unreachable"}
        )
        live_query_ready = bool(
            configured
            and self._client_module_available()
            and driver_selected
            and network_probe.get("reachable")
            and auth_probe.get("authenticated")
        )
        return {
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
            "auth_mode": self._auth_mode(config),
            "local_config_path": str(self.manifest.local_config_path) if self.manifest.local_config_path else None,
            "config_example_path": str(self.manifest.config_example_path) if self.manifest.config_example_path else None,
            "query_template_count": len(self.load_query_templates()),
            "entity_count": len(self.load_schema_manifest().get("entities") or []),
            "network_probe": network_probe,
            "auth_probe": auth_probe,
            "live_query_ready": live_query_ready,
            "execution_supported": True,
        }

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
                "next_step": "Fix driver/auth readiness before requesting live execution.",
            }

        payload = {
            "ok": True,
            **base_payload,
            "execution_mode": "dry_run",
            "next_step": (
                "Add local_config.json on the district network to enable connectivity checks."
                if not ready
                else "Live execution is ready; rerun this operation with dry_run=False to query the SIS test database."
            ),
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
