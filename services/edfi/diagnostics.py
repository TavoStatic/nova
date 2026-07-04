from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from services.edfi.auth import AuthResult
from services.edfi.config import ConnectionConfig, EDFI_AUDIT_LOG, MILESTONE_ID, ensure_runtime_dirs
from services.edfi.discovery import DiscoveryResult
from services.edfi.errors import config_validation_issues, empty_health_shell, issue_from_error


def build_health_payload(
    config: ConnectionConfig,
    *,
    auth: AuthResult,
    discovery: DiscoveryResult,
    profile_path: str = "",
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    latency_ms = {
        "token": int(auth.latency_ms or 0),
        "metadata": int(discovery.latency_ms or 0),
    }
    sample = discovery.sample_response
    if sample is not None:
        latency_ms["sample_get"] = int(sample.latency_ms or 0)

    if not auth.ok:
        issues.append(
            issue_from_error(
                severity="failure",
                code=auth.error_code or "edfi_auth_failed",
                detail=auth.error or "authentication_failed",
            )
        )
    if auth.ok and not discovery.ok:
        issues.append(
            issue_from_error(
                severity="failure",
                code=discovery.error_code or "edfi_discovery_failed",
                detail=discovery.error or "metadata_request_failed",
            )
        )
    if discovery.ok and sample is not None and not sample.ok:
        issues.append(
            issue_from_error(
                severity="warning",
                code=sample.error_code or "edfi_sample_get_failed",
                detail=sample.error or f"sample resource returned {sample.status_code}",
            )
        )
    if discovery.ok and discovery.resource_count <= 0:
        issues.append(
            issue_from_error(
                severity="warning",
                code="edfi_resources_empty",
                detail="Metadata returned no resource names.",
            )
        )

    status = "ok"
    if any(item["severity"] == "failure" for item in issues):
        status = "failure"
    elif issues:
        status = "watch"

    ok = status == "ok" and auth.ok and discovery.ok
    return {
        "ok": ok,
        "status": status,
        "milestone": MILESTONE_ID,
        "generated_at": int(now_fn()),
        "connection_id": config.connection_id,
        "base_url": config.normalized_base_url(),
        "profile_path": profile_path,
        "auth": {
            "ok": bool(auth.ok),
            "type": "oauth2_client_credentials",
            "token_endpoint": auth.token_endpoint or config.token_url(),
            "status_code": int(auth.status_code or 0),
            "scope": auth.scope,
            "error": auth.error,
            "error_code": auth.error_code,
        },
        "discovery": {
            "ok": bool(discovery.ok),
            "metadata_ok": bool(discovery.metadata_ok),
            "sample_ok": bool(discovery.sample_ok),
            "metadata_url": discovery.metadata_url,
            "resource_count": int(discovery.resource_count),
            "api_version": discovery.api_version or "unknown",
            "data_model_version": discovery.data_model_version or "unknown",
            "resources_sample": discovery.resources[:12],
            "error": discovery.error,
            "error_code": discovery.error_code,
        },
        "latency_ms": latency_ms,
        "issue_count": len(issues),
        "issues": issues[:8],
    }


def build_config_error_health(
    *,
    connection_id: str,
    error_code: str,
    detail: str = "",
    validation_errors: list[dict[str, str]] | None = None,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    issues = config_validation_issues(validation_errors or [{"code": error_code, "detail": detail or error_code}])
    health = empty_health_shell(connection_id=connection_id)
    health.update(
        {
            "milestone": MILESTONE_ID,
            "generated_at": int(now_fn()),
            "status": "failure",
            "ok": False,
            "issue_count": len(issues),
            "issues": issues[:8],
            "error_code": error_code,
        }
    )
    return health


def append_audit_event(event: dict[str, Any], *, audit_log_path: Path | None = None) -> None:
    ensure_runtime_dirs()
    target = Path(audit_log_path or EDFI_AUDIT_LOG)
    payload = dict(event or {})
    payload.setdefault("ts", int(time.time()))
    payload.setdefault("component", "edfi_core")
    try:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
    except Exception:
        pass