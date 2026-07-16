from __future__ import annotations

import json
import time
from typing import Any, Callable, Mapping

from services.edfi.client import EdFiClient
from services.edfi.config import (
    change_cursor_path,
    ensure_runtime_dirs,
    load_connection_config,
)
from services.edfi.diagnostics import append_audit_event
from services.edfi.district_scope import item_matches_district, normalize_district_lea_id
from services.edfi.inventory import build_client

MILESTONE_ID = "NOVA-EDFI-005"

DEFAULT_TRACKED_RESOURCES: dict[str, str] = {
    "schools": "ed-fi/schools",
    "students": "ed-fi/students",
    "student_school_associations": "ed-fi/studentSchoolAssociations",
}

CHANGE_SYNC_MAINTENANCE_TTL_SEC = 3600


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_resource(resource: str) -> str:
    name = str(resource or "").strip().strip("/")
    if not name:
        return DEFAULT_TRACKED_RESOURCES["schools"]
    for path in DEFAULT_TRACKED_RESOURCES.values():
        if name == path or name.endswith(path.split("/")[-1]):
            return path
    if "/" not in name:
        return f"ed-fi/{name}"
    return name


def _load_json_dict(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _root_manifest(client: EdFiClient) -> dict[str, Any]:
    response = client.get(client.config.normalized_base_url())
    body = response.body if isinstance(response.body, dict) else {}
    return body


def resolve_change_queries_base(client: EdFiClient) -> tuple[str, str]:
    manifest = _root_manifest(client)
    urls = manifest.get("urls") if isinstance(manifest.get("urls"), dict) else {}
    base = str((urls or {}).get("changeQueries") or "").strip().rstrip("/")
    if base:
        return base, "root_manifest"
    return "", "unavailable"


def resolve_data_management_api(client: EdFiClient) -> str:
    manifest = _root_manifest(client)
    urls = manifest.get("urls") if isinstance(manifest.get("urls"), dict) else {}
    return str((urls or {}).get("dataManagementApi") or "").strip().rstrip("/")


def fetch_available_change_versions(client: EdFiClient) -> dict[str, Any]:
    base, source = resolve_change_queries_base(client)
    if not base:
        return {
            "ok": False,
            "error_code": "edfi_change_queries_unavailable",
            "error": "ODS root manifest did not expose changeQueries URL.",
            "source": source,
        }

    url = f"{base}/availableChangeVersions"
    response = client.get(url)
    if not response.ok:
        return {
            "ok": False,
            "error_code": response.error_code or "edfi_change_versions_failed",
            "error": response.error or "availableChangeVersions request failed.",
            "source": source,
            "url": url,
            "status_code": response.status_code,
        }

    body = response.body if isinstance(response.body, dict) else {}
    oldest = _safe_int(body.get("oldestChangeVersion"))
    newest = _safe_int(body.get("newestChangeVersion"))
    return {
        "ok": True,
        "source": source,
        "url": url,
        "oldest_change_version": oldest,
        "newest_change_version": newest,
        "latency_ms": response.latency_ms,
        "status_code": response.status_code,
    }


def load_sync_state(connection_id: str) -> dict[str, Any]:
    return _load_json_dict(change_cursor_path(connection_id))


def save_sync_state(
    connection_id: str,
    state: Mapping[str, Any] | None = None,
    *,
    now_fn: Callable[[], float] = time.time,
) -> str:
    ensure_runtime_dirs()
    payload = dict(state or {})
    payload["connection_id"] = str(connection_id or "").strip()
    payload["updated_at"] = int(now_fn())
    target = change_cursor_path(connection_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return str(target)


def _resource_state(state: dict[str, Any], resource: str) -> dict[str, Any]:
    resources = state.get("resources") if isinstance(state.get("resources"), dict) else {}
    entry = resources.get(resource)
    return dict(entry) if isinstance(entry, dict) else {}


def _max_item_change_version(items: list[Any]) -> int:
    best = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        version = _safe_int(item.get("changeVersion"))
        if version > best:
            best = version
    return best


def sync_status(connection_id: str) -> dict[str, Any]:
    config = load_connection_config(connection_id)
    if config is None:
        return {
            "ok": False,
            "connection_id": connection_id,
            "error_code": "edfi_connection_config_missing",
            "error": "Connection config is missing.",
        }

    client = build_client(connection_id)
    versions = fetch_available_change_versions(client)
    change_base, mechanism = resolve_change_queries_base(client)
    state = load_sync_state(connection_id)
    resource_status: dict[str, Any] = {}
    for key, resource in DEFAULT_TRACKED_RESOURCES.items():
        entry = _resource_state(state, resource)
        resource_status[resource] = {
            "label": key,
            "last_change_version": _safe_int(entry.get("last_change_version")),
            "last_sync_at": _safe_int(entry.get("last_sync_at")),
            "last_pull_mechanism": str(entry.get("last_pull_mechanism") or ""),
            "last_item_count": _safe_int(entry.get("last_item_count")),
        }

    return {
        "ok": bool(versions.get("ok")),
        "connection_id": connection_id,
        "district_lea_id": str(config.district_lea_id or ""),
        "change_queries_base": change_base,
        "delta_mechanism": mechanism,
        "available_change_versions": versions,
        "tracked_resources": list(DEFAULT_TRACKED_RESOURCES.values()),
        "resource_cursors": resource_status,
        "cursor_path": str(change_cursor_path(connection_id)),
        "milestone": MILESTONE_ID,
    }


def _attempt_change_query_pull(
    client: EdFiClient,
    *,
    change_base: str,
    resource: str,
    min_change_version: int,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    url = f"{change_base.rstrip('/')}/{resource.strip('/')}/changes"
    response = client.get(
        url,
        params={
            "minChangeVersion": max(0, int(min_change_version)),
            "limit": max(1, int(limit)),
            "offset": max(0, int(offset)),
        },
    )
    items = response.body if isinstance(response.body, list) else []
    return {
        "ok": bool(response.ok),
        "mechanism": "change_query_resource",
        "url": url,
        "status_code": response.status_code,
        "error": response.error,
        "error_code": response.error_code,
        "items": items,
        "latency_ms": response.latency_ms,
    }


def _attempt_data_api_pull(
    client: EdFiClient,
    *,
    data_api: str,
    resource: str,
    min_change_version: int,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    if data_api:
        url = f"{data_api.rstrip('/')}/{resource.strip('/')}"
    else:
        url = resource
    response = client.get(
        url,
        params={
            "minChangeVersion": max(0, int(min_change_version)),
            "limit": max(1, int(limit)),
            "offset": max(0, int(offset)),
        },
    )
    items = response.body if isinstance(response.body, list) else []
    return {
        "ok": bool(response.ok),
        "mechanism": "data_api_min_change_version",
        "url": response.url or url,
        "status_code": response.status_code,
        "error": response.error,
        "error_code": response.error_code,
        "items": items,
        "latency_ms": response.latency_ms,
    }


def _district_filter_items(
    items: list[Any],
    *,
    district_lea_id: str,
) -> tuple[list[dict[str, Any]], int]:
    lea = normalize_district_lea_id(district_lea_id)
    if not lea:
        rows = [item for item in items if isinstance(item, dict)]
        return rows, 0
    kept: list[dict[str, Any]] = []
    scanned = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        scanned += 1
        if item_matches_district(item, lea):
            kept.append(item)
    return kept, scanned


def maybe_advance_tracked_cursors(
    connection_id: str,
    *,
    maintenance_ttl_sec: int = CHANGE_SYNC_MAINTENANCE_TTL_SEC,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Advance saved change-version cursors when maintenance is due."""
    resolved_id = str(connection_id or "").strip()
    if not resolved_id:
        return {
            "ok": False,
            "connection_id": connection_id,
            "error_code": "edfi_connection_id_missing",
            "error": "Connection id is required.",
            "advanced": False,
        }

    state = load_sync_state(resolved_id)
    last_maintenance_at = _safe_int(state.get("last_maintenance_at"))
    now_epoch = int(now_fn())
    due = last_maintenance_at <= 0 or (now_epoch - last_maintenance_at) >= max(60, int(maintenance_ttl_sec))
    if not due:
        return {
            "ok": True,
            "connection_id": resolved_id,
            "advanced": False,
            "reason": "maintenance_not_due",
            "last_maintenance_at": last_maintenance_at,
            "next_due_at": last_maintenance_at + max(60, int(maintenance_ttl_sec)),
        }

    results: list[dict[str, Any]] = []
    for resource in DEFAULT_TRACKED_RESOURCES.values():
        results.append(
            pull_changes_since(
                resolved_id,
                resource=resource,
                limit=1,
                offset=0,
                advance_cursor=True,
                now_fn=now_fn,
            )
        )

    ok = all(bool(item.get("ok")) for item in results) if results else False
    state = load_sync_state(resolved_id)
    last_maintenance_at = int(state.get("last_maintenance_at") or 0)
    if ok:
        state["last_maintenance_at"] = now_epoch
        save_sync_state(resolved_id, state, now_fn=now_fn)
        last_maintenance_at = now_epoch
    return {
        "ok": ok,
        "connection_id": resolved_id,
        "advanced": True,
        "last_maintenance_at": last_maintenance_at,
        "resource_results": results,
        "tracked_resources": list(DEFAULT_TRACKED_RESOURCES.values()),
    }


def pull_changes_since(
    connection_id: str,
    *,
    resource: str = "ed-fi/schools",
    min_change_version: int | None = None,
    limit: int = 25,
    offset: int = 0,
    advance_cursor: bool = False,
    now_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    config = load_connection_config(connection_id)
    if config is None:
        return {
            "ok": False,
            "connection_id": connection_id,
            "error_code": "edfi_connection_config_missing",
            "error": "Connection config is missing.",
        }

    client = build_client(connection_id)
    resource_path = _normalize_resource(resource)
    versions = fetch_available_change_versions(client)
    if not versions.get("ok"):
        return {
            "ok": False,
            "connection_id": connection_id,
            "resource": resource_path,
            "error_code": str(versions.get("error_code") or "edfi_change_versions_failed"),
            "error": str(versions.get("error") or "Could not read available change versions."),
            "available_change_versions": versions,
        }

    state = load_sync_state(connection_id)
    cursor_entry = _resource_state(state, resource_path)
    effective_min = (
        _safe_int(min_change_version)
        if min_change_version is not None
        else _safe_int(cursor_entry.get("last_change_version"))
    )
    change_base, _ = resolve_change_queries_base(client)
    data_api = resolve_data_management_api(client)

    attempts: list[dict[str, Any]] = []
    chosen: dict[str, Any] | None = None
    if change_base:
        attempt = _attempt_change_query_pull(
            client,
            change_base=change_base,
            resource=resource_path,
            min_change_version=effective_min,
            limit=limit,
            offset=offset,
        )
        attempts.append(attempt)
        if attempt.get("ok"):
            chosen = attempt

    if chosen is None:
        attempt = _attempt_data_api_pull(
            client,
            data_api=data_api,
            resource=resource_path,
            min_change_version=effective_min,
            limit=limit,
            offset=offset,
        )
        attempts.append(attempt)
        if attempt.get("ok"):
            chosen = attempt

    if chosen is None:
        last = attempts[-1] if attempts else {}
        append_audit_event(
            {
                "action": "pull_changes_since",
                "milestone": MILESTONE_ID,
                "connection_id": connection_id,
                "resource": resource_path,
                "status": "error",
                "ok": False,
                "min_change_version": effective_min,
                "error_code": str(last.get("error_code") or "edfi_delta_pull_failed"),
            }
        )
        return {
            "ok": False,
            "connection_id": connection_id,
            "resource": resource_path,
            "min_change_version": effective_min,
            "attempts": attempts,
            "error_code": str(last.get("error_code") or "edfi_delta_pull_failed"),
            "error": str(last.get("error") or "Delta pull failed for all supported mechanisms."),
            "available_change_versions": versions,
        }

    raw_items = list(chosen.get("items") or [])
    filtered_items, scanned = _district_filter_items(raw_items, district_lea_id=config.district_lea_id)
    max_version = _max_item_change_version(filtered_items or raw_items)
    newest = _safe_int(versions.get("newest_change_version"))
    next_cursor = max_version or (newest if advance_cursor else _safe_int(cursor_entry.get("last_change_version")))

    if advance_cursor and next_cursor >= effective_min:
        resources = state.get("resources") if isinstance(state.get("resources"), dict) else {}
        resources[resource_path] = {
            "last_change_version": next_cursor,
            "last_sync_at": int(now_fn()),
            "last_pull_mechanism": str(chosen.get("mechanism") or ""),
            "last_item_count": len(filtered_items),
        }
        state["resources"] = resources
        state["available"] = {
            "oldest_change_version": _safe_int(versions.get("oldest_change_version")),
            "newest_change_version": newest,
            "fetched_at": int(now_fn()),
        }
        state["change_queries_base"] = change_base
        save_sync_state(connection_id, state, now_fn=now_fn)

    note = ""
    if chosen.get("mechanism") == "data_api_min_change_version" and not filtered_items:
        note = (
            "TEA IODS exposes change versions but may return empty minChangeVersion pages; "
            "use full district-scoped reads when incremental delta is unavailable."
        )

    append_audit_event(
        {
            "action": "pull_changes_since",
            "milestone": MILESTONE_ID,
            "connection_id": connection_id,
            "resource": resource_path,
            "status": "ok",
            "ok": True,
            "min_change_version": effective_min,
            "item_count": len(filtered_items),
            "mechanism": chosen.get("mechanism"),
            "advance_cursor": bool(advance_cursor),
        }
    )
    return {
        "ok": True,
        "connection_id": connection_id,
        "resource": resource_path,
        "min_change_version": effective_min,
        "next_change_version": next_cursor,
        "mechanism": chosen.get("mechanism"),
        "items": filtered_items,
        "item_count": len(filtered_items),
        "records_scanned": scanned,
        "district_filter_strategy": "client_side" if config.district_lea_id else "none",
        "available_change_versions": versions,
        "attempts": attempts,
        "advance_cursor": bool(advance_cursor),
        "note": note,
    }