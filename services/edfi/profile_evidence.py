from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from services.edfi.change_tracking import load_sync_state
from services.edfi.config import CAPABILITY_SCHEMA, load_capability_profile, load_connection_config, profile_path
from services.evidence_validity import evidence_result_valid

DEFAULT_CONNECTION_ID = "district-main"
PROFILE_EVIDENCE_MILESTONE = "NOVA-EDFI-001"
DEFAULT_PROFILE_EVIDENCE_PATH = "runtime/edfi/profiles/district-main.json"
EXPECTED_BISD_LEA_ID = "31901"
EXPECTED_BISD_RESOURCE_COUNT = 445


def _relative_profile_path(connection_id: str) -> str:
    safe_id = str(connection_id or DEFAULT_CONNECTION_ID).strip() or DEFAULT_CONNECTION_ID
    return f"runtime/edfi/profiles/{safe_id}.json"


def _relative_change_cursor_path(connection_id: str) -> str:
    safe_id = str(connection_id or DEFAULT_CONNECTION_ID).strip() or DEFAULT_CONNECTION_ID
    return f"runtime/edfi/change_cursors/{safe_id}.json"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _summarize_saved_sync_state(state: dict[str, Any], *, connection_id: str) -> dict[str, Any] | None:
    """Build optional sync/cursor evidence from saved change-cursor state only."""
    payload = dict(state or {})
    resources = payload.get("resources") if isinstance(payload.get("resources"), dict) else {}
    resource_cursors: dict[str, dict[str, Any]] = {}
    for resource, entry in resources.items():
        resource_name = str(resource or "").strip()
        if not resource_name or not isinstance(entry, dict):
            continue
        resource_cursors[resource_name] = {
            "last_change_version": _safe_int(entry.get("last_change_version")),
            "last_sync_at": _safe_int(entry.get("last_sync_at")),
            "last_pull_mechanism": str(entry.get("last_pull_mechanism") or "").strip(),
            "last_item_count": _safe_int(entry.get("last_item_count")),
        }

    updated_at = _safe_int(payload.get("updated_at"))
    if not resource_cursors and updated_at <= 0:
        return None

    return {
        "present": True,
        "connection_id": str(payload.get("connection_id") or connection_id or "").strip() or connection_id,
        "evidence_source": "saved_change_cursors",
        "cursor_evidence_path": _relative_change_cursor_path(connection_id),
        "updated_at": updated_at,
        "resource_cursor_count": len(resource_cursors),
        "resource_cursors": resource_cursors,
    }


def _normalize_evidence_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").rstrip("/").lower()


def _parse_tool_args_json(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item or "").strip() for item in raw if str(item or "").strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return [text] if text else []
    if isinstance(parsed, list):
        return [str(item or "").strip() for item in parsed if str(item or "").strip()]
    return [text]


def extract_profile_from_read_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        for key in ("content", "text", "body", "result"):
            nested = result.get(key)
            if isinstance(nested, dict):
                return dict(nested)
            if isinstance(nested, str) and nested.strip().startswith("{"):
                try:
                    payload = json.loads(nested)
                    return dict(payload) if isinstance(payload, dict) else {}
                except Exception:
                    continue
        if str(result.get("schema") or "").strip():
            return dict(result)
    text = str(result or "").strip()
    if not text.startswith("{"):
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def capability_profile_payload_valid(
    payload: dict[str, Any],
    *,
    require_auth_ok: bool = True,
    min_resource_count: int = 1,
) -> tuple[bool, str]:
    profile = dict(payload or {})
    schema = str(profile.get("schema") or "").strip()
    if schema and schema != CAPABILITY_SCHEMA:
        return False, "profile_schema_mismatch"
    auth = profile.get("auth") if isinstance(profile.get("auth"), dict) else {}
    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    if require_auth_ok and not bool(auth.get("ok")):
        return False, "profile_auth_not_ok"
    resource_count = int(discovery.get("resource_count") or len(list(discovery.get("resources") or [])) or 0)
    if resource_count < int(min_resource_count or 0):
        return False, "profile_resources_insufficient"
    discovered_at = int(profile.get("discovered_at") or 0)
    if discovered_at <= 0:
        return False, "profile_discovered_at_missing"
    if not str(profile.get("connection_id") or profile.get("milestone") or schema).strip():
        return False, "profile_source_metadata_missing"
    return True, ""


def profile_read_evidence_valid(
    row: dict[str, Any],
    *,
    expected_path: str = DEFAULT_PROFILE_EVIDENCE_PATH,
) -> bool:
    if not isinstance(row, dict):
        return False
    tool_name = str(row.get("tool_name") or "").strip().lower()
    if tool_name != "read":
        return False
    if not evidence_result_valid(row):
        return False
    args = _parse_tool_args_json(row.get("tool_args"))
    if not args:
        return False
    expected = _normalize_evidence_path(expected_path)
    if not any(_normalize_evidence_path(arg) == expected for arg in args):
        return False
    profile = extract_profile_from_read_result(row.get("result_text"))
    ok, _reason = capability_profile_payload_valid(profile)
    return ok


def audit_runtime_profile_contract(
    connection_id: str = DEFAULT_CONNECTION_ID,
    *,
    expected_lea_id: str = EXPECTED_BISD_LEA_ID,
    expected_resource_count: int = EXPECTED_BISD_RESOURCE_COUNT,
    runtime_root: Any | None = None,
) -> dict[str, Any]:
    """Validate the on-disk profile and connection config without live API calls."""
    resolved_id = str(connection_id or DEFAULT_CONNECTION_ID).strip() or DEFAULT_CONNECTION_ID
    if runtime_root is not None:
        root = Path(runtime_root)
        path = root / "edfi" / "profiles" / f"{resolved_id}.json"
        config_path = root / "edfi" / "connections" / resolved_id / "local_config.json"
        try:
            profile = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            profile = {}
        if not isinstance(profile, dict):
            profile = {}
        conn = None
        if config_path.exists():
            try:
                from services.edfi.config import connection_config_from_dict

                config_data = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(config_data, dict):
                    conn = connection_config_from_dict(config_data, connection_id=resolved_id)
            except Exception:
                conn = None
        evidence = build_capability_profile_evidence(
            resolved_id,
            profile_override=profile,
            path_override=path,
        )
    else:
        path = profile_path(resolved_id)
        profile = load_capability_profile(resolved_id)
        conn = load_connection_config(resolved_id)
        evidence = build_capability_profile_evidence(resolved_id)

    checks: dict[str, bool] = {
        "profile_file_exists": path.exists(),
        "profile_present": bool(evidence.get("present")),
        "profile_auth_ok": bool(evidence.get("auth_ok")),
        "profile_resource_count_ok": int(evidence.get("resource_count") or 0) == int(expected_resource_count),
        "profile_discovered_at_present": int(evidence.get("discovered_at") or 0) > 0,
        "profile_schema_present": str(evidence.get("schema") or "") == CAPABILITY_SCHEMA,
        "profile_evidence_source_present": str(evidence.get("evidence_source") or "") == "saved_capability_profile",
        "connection_config_present": conn is not None,
        "district_lea_id_ok": str(getattr(conn, "district_lea_id", "") or "").strip() == str(expected_lea_id).strip(),
    }
    issues = [
        {"code": code, "detail": detail}
        for code, detail, ok in (
            ("edfi_profile_missing", f"Missing profile at {_relative_profile_path(resolved_id)}.", checks["profile_file_exists"]),
            ("edfi_profile_auth_not_ok", "Saved profile auth is not ok.", checks["profile_auth_ok"]),
            (
                "edfi_profile_resource_count_mismatch",
                f"Expected {expected_resource_count} resources; found {int(evidence.get('resource_count') or 0)}.",
                checks["profile_resource_count_ok"],
            ),
            ("edfi_profile_discovered_at_missing", "Profile discovered_at is missing.", checks["profile_discovered_at_present"]),
            ("edfi_profile_schema_missing", "Profile schema is not nova.edfi_capability.v1.", checks["profile_schema_present"]),
            (
                "edfi_profile_evidence_source_missing",
                "Profile evidence_source is not saved_capability_profile.",
                checks["profile_evidence_source_present"],
            ),
            ("edfi_connection_config_missing", "Connection local_config.json is missing.", checks["connection_config_present"]),
            (
                "edfi_district_lea_id_mismatch",
                f"Expected district LEA {expected_lea_id}; found {str(getattr(conn, 'district_lea_id', '') or '').strip() or 'missing'}.",
                checks["district_lea_id_ok"],
            ),
        )
        if not ok
    ]
    ok = all(checks.values()) and bool(evidence.get("ok"))
    return {
        "ok": ok,
        "connection_id": resolved_id,
        "profile_path": str(path),
        "profile_evidence_path": _relative_profile_path(resolved_id),
        "district_lea_id": str(getattr(conn, "district_lea_id", "") or "").strip(),
        "resource_count": int(evidence.get("resource_count") or 0),
        "discovered_at": int(evidence.get("discovered_at") or 0),
        "evidence_source": str(evidence.get("evidence_source") or ""),
        "checks": checks,
        "issues": issues,
        "profile": dict(profile or {}),
        "live_api_required": False,
    }


def build_capability_profile_evidence(
    connection_id: str = DEFAULT_CONNECTION_ID,
    *,
    now_fn: Callable[[], float] = time.time,
    profile_override: dict[str, Any] | None = None,
    path_override: Path | str | None = None,
    sync_state_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build work-tree/status evidence from a saved profile only (no live API calls)."""
    resolved_id = str(connection_id or DEFAULT_CONNECTION_ID).strip() or DEFAULT_CONNECTION_ID
    path = Path(path_override) if path_override is not None else profile_path(resolved_id)
    profile = dict(profile_override or load_capability_profile(resolved_id))
    present = path.exists() and bool(profile)

    discovery = profile.get("discovery") if isinstance(profile.get("discovery"), dict) else {}
    auth = profile.get("auth") if isinstance(profile.get("auth"), dict) else {}
    resources = [
        str(item).strip()
        for item in list(discovery.get("resources") or [])
        if str(item or "").strip()
    ]
    namespaces = [
        str(item).strip()
        for item in list(discovery.get("namespaces") or [])
        if str(item or "").strip()
    ]

    resource_count = int(discovery.get("resource_count") or len(resources) or 0)
    discovered_at = int(profile.get("discovered_at") or 0)
    auth_ok = bool(auth.get("ok")) if present else False
    discovery_ok = bool(discovery.get("ok", True)) if discovery else False
    health = str(profile.get("health") or "").strip().lower()

    issues: list[dict[str, str]] = []
    if not present:
        issues.append({
            "code": "edfi_profile_missing",
            "severity": "failure",
            "detail": f"No saved capability profile at {_relative_profile_path(resolved_id)}.",
        })
    if present and not auth_ok:
        issues.append({
            "code": "edfi_profile_auth_not_ok",
            "severity": "failure",
            "detail": "Saved profile reports authentication is not ok.",
        })
    if present and not discovery_ok:
        issues.append({
            "code": "edfi_profile_discovery_not_ok",
            "severity": "failure",
            "detail": "Saved profile reports metadata discovery is not ok.",
        })
    if present and resource_count <= 0:
        issues.append({
            "code": "edfi_profile_resources_empty",
            "severity": "failure",
            "detail": "Saved profile has no discovered resources.",
        })
    if present and health and health not in {"ok", "unknown"}:
        issues.append({
            "code": "edfi_profile_health_watch",
            "severity": "watch" if health == "watch" else "failure",
            "detail": f"Saved profile health is {health}.",
        })

    if not present:
        status = "missing"
    elif any(item.get("severity") == "failure" for item in issues):
        status = "failure"
    elif issues:
        status = "watch"
    else:
        status = health or "ok"

    ok = present and auth_ok and discovery_ok and resource_count > 0 and status == "ok"
    age_sec = max(0, int(now_fn()) - discovered_at) if discovered_at else None
    sync_state = (
        dict(sync_state_override)
        if isinstance(sync_state_override, dict)
        else load_sync_state(resolved_id)
    )
    sync_status = _summarize_saved_sync_state(sync_state, connection_id=resolved_id)

    payload = {
        "ok": ok,
        "status": status,
        "present": present,
        "milestone": str(profile.get("milestone") or PROFILE_EVIDENCE_MILESTONE),
        "schema": str(profile.get("schema") or ""),
        "connection_id": resolved_id,
        "base_url": str(profile.get("base_url") or ""),
        "profile_path": str(path),
        "profile_evidence_path": _relative_profile_path(resolved_id),
        "auth_ok": auth_ok,
        "discovery_ok": discovery_ok,
        "health": health or status,
        "resource_count": resource_count,
        "discovered_at": discovered_at,
        "profile_age_sec": age_sec,
        "api_version": str(profile.get("api_version") or ""),
        "data_model_version": str(profile.get("data_model_version") or ""),
        "namespaces": namespaces[:12],
        "sample_resources": resources[:24],
        "issue_count": len(issues),
        "issues": issues[:8],
        "evidence_source": "saved_capability_profile",
        "live_api_required": False,
    }
    if sync_status is not None:
        payload["sync_status"] = sync_status
    return payload


def get_district_layer_facts(connection_id: str = DEFAULT_CONNECTION_ID) -> dict[str, Any]:
    """Read-only district facts from saved profile and connection config (no live API)."""
    resolved_id = str(connection_id or DEFAULT_CONNECTION_ID).strip() or DEFAULT_CONNECTION_ID
    evidence = build_capability_profile_evidence(resolved_id)
    conn = load_connection_config(resolved_id)
    lea_id = str(getattr(conn, "district_lea_id", "") or "").strip()

    facts: dict[str, Any] = {
        "ok": bool(evidence.get("ok")),
        "connection_id": resolved_id,
        "lea_id": lea_id,
        "resource_count": int(evidence.get("resource_count") or 0),
        "auth_ok": bool(evidence.get("auth_ok")),
        "profile_path": str(evidence.get("profile_evidence_path") or _relative_profile_path(resolved_id)),
        "discovered_at": int(evidence.get("discovered_at") or 0),
        "schema": str(evidence.get("schema") or ""),
        "evidence_source": str(evidence.get("evidence_source") or ""),
        "issues": list(evidence.get("issues") or [])[:8],
    }
    sync_status = evidence.get("sync_status")
    if isinstance(sync_status, dict) and sync_status:
        facts["sync_status"] = dict(sync_status)
    return facts