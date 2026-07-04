from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from services.edfi.client import EdFiClient, EdFiResponse
from services.edfi.config import (
    CAPABILITY_SCHEMA,
    ConnectionConfig,
    MILESTONE_ID,
    save_capability_profile,
)


@dataclass
class DiscoveryResult:
    ok: bool
    api_root: str = ""
    metadata_url: str = ""
    resource_count: int = 0
    resources: list[str] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    api_version: str = ""
    data_model_version: str = ""
    latency_ms: int = 0
    status_code: int = 0
    error: str = ""
    error_code: str = ""
    metadata_ok: bool = False
    sample_ok: bool = False
    metadata_response: EdFiResponse | None = None
    sample_response: EdFiResponse | None = None


def discover_metadata(client: EdFiClient) -> DiscoveryResult:
    config = client.config
    metadata = client.get(config.metadata_url())
    if not metadata.ok:
        return DiscoveryResult(
            ok=False,
            api_root=config.api_root,
            metadata_url=config.metadata_url(),
            latency_ms=metadata.latency_ms,
            status_code=metadata.status_code,
            error=metadata.error or "metadata_request_failed",
            error_code=metadata.error_code or "edfi_metadata_failed",
            metadata_ok=False,
            sample_ok=False,
            metadata_response=metadata,
        )

    resources, namespaces, api_version, data_model_version = _parse_metadata_body(metadata.body)
    sample = client.get(config.sample_resource, params={"limit": 1})
    return DiscoveryResult(
        ok=True,
        api_root=config.api_root,
        metadata_url=config.metadata_url(),
        resource_count=len(resources),
        resources=resources,
        namespaces=namespaces,
        api_version=api_version,
        data_model_version=data_model_version,
        latency_ms=metadata.latency_ms,
        status_code=metadata.status_code,
        metadata_ok=True,
        sample_ok=bool(sample.ok),
        metadata_response=metadata,
        sample_response=sample,
    )


def build_capability_profile(
    config: ConnectionConfig,
    discovery: DiscoveryResult,
    *,
    auth_summary: dict[str, Any],
    health: dict[str, Any],
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    sample = discovery.sample_response
    return {
        "schema": CAPABILITY_SCHEMA,
        "milestone": MILESTONE_ID,
        "connection_id": config.connection_id,
        "base_url": config.normalized_base_url(),
        "discovered_at": int(now_fn()),
        "api_root": config.api_root,
        "api_version": discovery.api_version or "unknown",
        "data_model_version": discovery.data_model_version or "unknown",
        "auth": auth_summary,
        "discovery": {
            "ok": discovery.ok,
            "metadata_url": discovery.metadata_url,
            "resource_count": discovery.resource_count,
            "resources": discovery.resources[:40],
            "namespaces": discovery.namespaces[:20],
            "sample_resource": config.sample_resource,
            "sample_ok": bool(sample.ok) if sample is not None else False,
            "sample_status_code": int(sample.status_code) if sample is not None else 0,
            "stages": _discovery_stages(discovery, config),
        },
        "latency_ms": dict(health.get("latency_ms") or {}),
        "health": str(health.get("status") or "unknown"),
        "issues": list(health.get("issues") or []),
    }


def discover_and_save_profile(
    client: EdFiClient,
    *,
    auth_summary: dict[str, Any],
    health: dict[str, Any],
    now_fn: Callable[[], float] = time.time,
) -> tuple[DiscoveryResult, dict[str, Any], str]:
    discovery = discover_metadata(client)
    profile = build_capability_profile(
        client.config,
        discovery,
        auth_summary=auth_summary,
        health=health,
        now_fn=now_fn,
    )
    path = save_capability_profile(client.config.connection_id, profile)
    return discovery, profile, str(path)


def _discovery_stages(discovery: DiscoveryResult, config: ConnectionConfig) -> dict[str, Any]:
    metadata = discovery.metadata_response
    sample = discovery.sample_response
    stages: dict[str, Any] = {
        "metadata": {
            "ok": bool(discovery.metadata_ok),
            "url": discovery.metadata_url,
            "status_code": int(metadata.status_code) if metadata is not None else int(discovery.status_code or 0),
            "latency_ms": int(metadata.latency_ms) if metadata is not None else int(discovery.latency_ms or 0),
            "error": metadata.error if metadata is not None else discovery.error,
            "error_code": metadata.error_code if metadata is not None else discovery.error_code,
        }
    }
    if discovery.metadata_ok:
        stages["sample_get"] = {
            "ok": bool(discovery.sample_ok),
            "resource": config.sample_resource,
            "url": config.sample_resource_url(),
            "status_code": int(sample.status_code) if sample is not None else 0,
            "latency_ms": int(sample.latency_ms) if sample is not None else 0,
            "error": sample.error if sample is not None else "",
            "error_code": sample.error_code if sample is not None else "",
        }
    return stages


def _parse_metadata_body(body: Any) -> tuple[list[str], list[str], str, str]:
    resources: list[str] = []
    namespaces: list[str] = []
    api_version = ""
    data_model_version = ""

    if isinstance(body, dict):
        api_version = str(body.get("apiVersion") or body.get("api_version") or "").strip()
        data_model_version = str(
            body.get("dataModelVersion") or body.get("data_model_version") or ""
        ).strip()
        raw_resources = body.get("resources") or body.get("resourceNames") or body.get("items")
        resources = _resource_names(raw_resources)
        raw_namespaces = body.get("namespaces") or body.get("namespace")
        namespaces = _namespace_names(raw_namespaces)
        return resources, namespaces, api_version, data_model_version

    if isinstance(body, list):
        resources = _resource_names(body)
        return resources, namespaces, api_version, data_model_version

    return resources, namespaces, api_version, data_model_version


def _resource_names(raw: Any) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    if isinstance(raw, list):
        for item in raw:
            name = ""
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("resource") or item.get("path") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def _namespace_names(raw: Any) -> list[str]:
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        out = []
        for item in raw:
            text = str(item or "").strip()
            if text:
                out.append(text)
        return out
    return []