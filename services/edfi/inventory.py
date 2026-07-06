from __future__ import annotations

from typing import Any

from services.edfi.client import EdFiClient
from services.edfi.config import (
    load_capability_profile,
    load_connection_config,
    save_capability_profile,
)
from services.edfi.discovery import _resource_names_from_dependencies
from services.edfi.district_scope import (
    district_filter_strategy,
    district_lea_filter_clause,
    merge_filter_params,
    uses_client_side_district_filter,
)
from services.edfi.resources import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    get_district_scoped_page,
    get_page,
)

MILESTONE_ID = "NOVA-EDFI-002"

EXPLORE_PRESETS: dict[str, list[str]] = {
    "schools": ["schools", "ed-fi/schools"],
    "students": ["students", "ed-fi/students"],
    "student_school_associations": [
        "studentSchoolAssociations",
        "ed-fi/studentSchoolAssociations",
    ],
}


def build_client(connection_id: str) -> EdFiClient:
    config = load_connection_config(connection_id)
    if config is None:
        raise ValueError("connection_credentials_required")
    return EdFiClient(config)


def profile_summary(connection_id: str) -> dict[str, Any]:
    profile = load_capability_profile(connection_id)
    if not profile:
        return {
            "ok": False,
            "connection_id": connection_id,
            "error_code": "edfi_profile_missing",
            "error": "No capability profile found. Run run_edfi_profile.py first.",
        }

    config = load_connection_config(connection_id)
    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    resources = _resource_names(discovery)
    resource_count = int(discovery.get("resource_count") or len(resources) or 0)
    return {
        "ok": True,
        "connection_id": connection_id,
        "district_lea_id": str(config.district_lea_id if config else ""),
        "district_scope_enabled": bool(config and config.district_lea_id),
        "base_url": str(profile.get("base_url") or ""),
        "health": str(profile.get("health") or "unknown"),
        "api_version": str(profile.get("api_version") or "unknown"),
        "data_model_version": str(profile.get("data_model_version") or "unknown"),
        "resource_count": resource_count,
        "catalog_count": len(resources),
        "catalog_truncated": resource_count > len(resources),
        "namespaces": list(discovery.get("namespaces") or []),
        "metadata_url": str(discovery.get("metadata_url") or ""),
        "discovered_at": int(profile.get("discovered_at") or 0),
        "auth_ok": bool((profile.get("auth") or {}).get("ok")),
    }


def refresh_resource_catalog(connection_id: str) -> dict[str, Any]:
    profile = load_capability_profile(connection_id)
    if not profile:
        return {
            "ok": False,
            "error_code": "edfi_profile_missing",
            "error": "No capability profile found.",
        }

    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    metadata_url = str(discovery.get("metadata_url") or "").strip()
    if not metadata_url:
        return {
            "ok": False,
            "error_code": "edfi_metadata_url_missing",
            "error": "Profile has no metadata URL to refresh.",
        }

    client = build_client(connection_id)
    response = client.get(metadata_url)
    if not response.ok:
        return {
            "ok": False,
            "error_code": response.error_code or "edfi_catalog_refresh_failed",
            "error": response.error or "Catalog refresh failed.",
            "status_code": int(response.status_code or 0),
        }

    resources = _resource_names_from_dependencies(response.body)
    if not resources:
        return {
            "ok": False,
            "error_code": "edfi_catalog_empty",
            "error": "Dependencies endpoint returned no resources.",
        }

    discovery = dict(discovery)
    discovery["resources"] = resources
    discovery["resource_count"] = len(resources)
    profile = dict(profile)
    profile["discovery"] = discovery
    save_capability_profile(connection_id, profile)
    return {
        "ok": True,
        "connection_id": connection_id,
        "resource_count": len(resources),
        "catalog_count": len(resources),
        "catalog_truncated": False,
    }


def list_resources(
    connection_id: str,
    *,
    query: str = "",
    namespace: str = "",
    limit: int = 50,
    offset: int = 0,
    refresh: bool = False,
) -> dict[str, Any]:
    profile = load_capability_profile(connection_id)
    if not profile:
        return {
            "ok": False,
            "error_code": "edfi_profile_missing",
            "error": "No capability profile found.",
        }

    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    resource_count = int(discovery.get("resource_count") or 0)
    catalog = _resource_names(discovery)
    if refresh or (resource_count > len(catalog)):
        refreshed = refresh_resource_catalog(connection_id)
        if refreshed.get("ok"):
            profile = load_capability_profile(connection_id) or profile
            discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
            catalog = _resource_names(discovery)
        elif refresh:
            return refreshed

    all_resources = _filter_resources(
        catalog,
        query=query,
        namespace=namespace,
    )
    effective_limit = min(max(1, int(limit or 50)), 200)
    start = max(0, int(offset or 0))
    page = all_resources[start : start + effective_limit]
    resource_count = int(discovery.get("resource_count") or len(all_resources) or 0)
    catalog_names = _resource_names(discovery)

    return {
        "ok": True,
        "connection_id": connection_id,
        "query": str(query or "").strip(),
        "namespace": str(namespace or "").strip(),
        "total_matches": len(all_resources),
        "resource_count": resource_count,
        "catalog_truncated": resource_count > len(catalog_names),
        "offset": start,
        "limit": effective_limit,
        "resources": page,
        "presets": sorted(EXPLORE_PRESETS.keys()),
    }


def read_resource(
    connection_id: str,
    resource: str,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    filter_params: dict[str, Any] | None = None,
    apply_district_scope: bool = True,
) -> dict[str, Any]:
    name = str(resource or "").strip()
    if not name:
        return {
            "ok": False,
            "error_code": "edfi_resource_required",
            "error": "Resource name is required.",
        }

    effective_limit = min(max(1, int(limit or DEFAULT_PAGE_SIZE)), MAX_PAGE_SIZE)
    config = load_connection_config(connection_id)
    if config is None:
        return {
            "ok": False,
            "error_code": "connection_credentials_required",
            "error": "Connection config not found.",
        }
    client = EdFiClient(config)
    resolved = _resolve_resource_name(name)
    params = dict(filter_params or {})
    district_lea_id = ""
    strategy = ""
    if apply_district_scope and config.district_lea_id:
        district_lea_id = str(config.district_lea_id).strip()
        strategy = district_filter_strategy(config.normalized_base_url())
        if strategy == "client_side":
            page = get_district_scoped_page(
                client,
                resolved,
                district_lea_id=district_lea_id,
                limit=effective_limit,
                offset=max(0, int(offset or 0)),
                audit=True,
            )
        else:
            clause = district_lea_filter_clause(resolved, district_lea_id)
            params = merge_filter_params(params, clause)
            page = get_page(
                client,
                resolved,
                limit=effective_limit,
                offset=max(0, int(offset or 0)),
                filter_params=params or None,
                audit=True,
            )
    else:
        page = get_page(
            client,
            resolved,
            limit=effective_limit,
            offset=max(0, int(offset or 0)),
            filter_params=params or None,
            audit=True,
        )
    return {
        "ok": page.ok,
        "connection_id": connection_id,
        "district_lea_id": district_lea_id,
        "district_scope_applied": bool(district_lea_id),
        "district_filter_strategy": strategy or page.district_filter_strategy,
        "records_scanned": _safe_int(getattr(page, "records_scanned", 0)),
        "odata_filter_honored": not uses_client_side_district_filter(config.normalized_base_url()),
        "filter": str(params.get("$filter") or ""),
        "resource": resolved,
        "url": page.url,
        "offset": page.offset,
        "limit": page.limit,
        "count": page.count,
        "items": page.items,
        "latency_ms": page.latency_ms,
        "status_code": page.status_code,
        "error": page.error,
        "error_code": page.error_code,
        "rate_limited": page.rate_limited,
    }


def read_preset(
    connection_id: str,
    preset: str,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    apply_district_scope: bool = True,
) -> dict[str, Any]:
    key = str(preset or "").strip().lower()
    candidates = EXPLORE_PRESETS.get(key)
    if not candidates:
        return {
            "ok": False,
            "error_code": "edfi_preset_unknown",
            "error": f"Unknown preset '{preset}'.",
            "presets": sorted(EXPLORE_PRESETS.keys()),
        }

    last_result: dict[str, Any] | None = None
    for candidate in candidates:
        result = read_resource(
            connection_id,
            candidate,
            limit=limit,
            offset=offset,
            apply_district_scope=apply_district_scope,
        )
        last_result = result
        if result.get("ok"):
            result["preset"] = key
            return result

    if last_result is not None:
        last_result["preset"] = key
        last_result["candidates_tried"] = candidates
    return last_result or {
        "ok": False,
        "error_code": "edfi_preset_failed",
        "error": f"Preset '{preset}' could not be read.",
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _resolve_resource_name(resource: str) -> str:
    text = str(resource or "").strip().strip("/")
    if not text:
        return ""
    preset = EXPLORE_PRESETS.get(text.lower())
    if preset:
        return preset[0]
    return text


def _resource_names(discovery: dict[str, Any]) -> list[str]:
    raw = discovery.get("resources")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item or "").strip().strip("/")
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _filter_resources(
    resources: list[str],
    *,
    query: str,
    namespace: str,
) -> list[str]:
    q = str(query or "").strip().lower()
    ns = str(namespace or "").strip().lower()
    out: list[str] = []
    for resource in resources:
        lowered = resource.lower()
        if ns and not lowered.startswith(f"{ns}/") and lowered != ns:
            continue
        if q and q not in lowered:
            continue
        out.append(resource)
    return out