from __future__ import annotations

import time
from typing import Any, Callable

from services.edfi.auth import AuthResult, EdFiAuthService
from services.edfi.client import EdFiClient
from services.edfi.config import (
    CAPABILITY_SCHEMA,
    ConnectionConfig,
    MILESTONE_ID,
    connection_config_from_dict,
    ensure_runtime_dirs,
    load_connection_config,
    profile_path,
    runtime_roots,
    save_connection_config,
)
from services.edfi.diagnostics import append_audit_event, build_health_payload
from services.edfi.config import save_capability_profile
from services.edfi.discovery import build_capability_profile, discover_metadata

__all__ = [
    "CAPABILITY_SCHEMA",
    "MILESTONE_ID",
    "ConnectionConfig",
    "EdFiAuthService",
    "EdFiClient",
    "connection_config_from_dict",
    "discover_metadata",
    "load_connection_config",
    "profile_path",
    "run_self_profile",
    "runtime_roots",
    "save_connection_config",
]


def run_self_profile(
    *,
    connection_id: str,
    base_url: str = "",
    client_id: str = "",
    client_secret: str = "",
    save_config: bool = True,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """
    NOVA-EDFI-001: authenticate, discover metadata, save profile, return health.

    No PEIMS, TSDS, Texas, attendance, SPED, or vendor-specific logic.
    """
    ensure_runtime_dirs()

    config = _resolve_config(
        connection_id=connection_id,
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
    )
    if save_config:
        save_connection_config(config)

    client = EdFiClient(config)
    auth = client.authenticate()
    discovery = discover_metadata(client)

    auth_summary = {
        "type": "oauth2_client_credentials",
        "ok": bool(auth.ok),
        "token_endpoint": auth.token_endpoint or config.token_url(),
        "scope": auth.scope,
        "error": auth.error,
    }
    provisional_health = build_health_payload(
        config,
        auth=auth,
        discovery=discovery,
        profile_path="",
        now_fn=now_fn,
    )
    profile = build_capability_profile(
        config,
        discovery,
        auth_summary=auth_summary,
        health=provisional_health,
        now_fn=now_fn,
    )
    saved_profile_path = str(save_capability_profile(config.connection_id, profile))
    health = build_health_payload(
        config,
        auth=auth,
        discovery=discovery,
        profile_path=saved_profile_path,
        now_fn=now_fn,
    )
    profile["health"] = health["status"]
    profile["issues"] = health["issues"]

    append_audit_event(
        {
            "action": "self_profile",
            "milestone": MILESTONE_ID,
            "connection_id": config.connection_id,
            "status": health["status"],
            "ok": health["ok"],
            "resource_count": discovery.resource_count,
            "profile_path": saved_profile_path,
        }
    )

    return {
        "ok": bool(health["ok"]),
        "milestone": MILESTONE_ID,
        "connection_id": config.connection_id,
        "profile": profile,
        "profile_path": saved_profile_path,
        "health": health,
        "discovery": {
            "resource_count": discovery.resource_count,
            "resources": discovery.resources[:20],
            "api_version": discovery.api_version,
            "data_model_version": discovery.data_model_version,
        },
    }


def _resolve_config(
    *,
    connection_id: str,
    base_url: str,
    client_id: str,
    client_secret: str,
) -> ConnectionConfig:
    if base_url and client_id and client_secret:
        return connection_config_from_dict(
            {
                "connection_id": connection_id,
                "base_url": base_url,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            connection_id=connection_id,
        )
    loaded = load_connection_config(connection_id)
    if loaded is not None:
        return loaded
    raise ValueError("connection_credentials_required")