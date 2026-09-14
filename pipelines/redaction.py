from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

REDACTED = "[REDACTED]"

SENSITIVE_FIELDS = frozenset({
    "name",
    "full_name",
    "email",
    "phone",
    "addresses",
    "telephones",
})

ORGANIZATION_SENSITIVE_FIELDS = frozenset({
    "faxNumber",
    "website",
})

SUMMARY_ONLY_FIELDS = frozenset({
    "count",
    "row_count",
    "total_matches",
    "resource_count",
    "item_id",
    "display_name",
    "category",
    "preset",
    "resource",
    "educationOrganizationCategoryDescriptor",
})

METADATA_ONLY_FIELDS = frozenset({
    "ok",
    "connection_id",
    "resource",
    "offset",
    "limit",
    "count",
    "row_count",
    "execution_mode",
    "operation",
    "pipeline_id",
    "effective_row_limit",
    "requested_row_limit",
    "redaction_profile",
    "redaction_applied",
})

METADATA_OPERATIONS = frozenset({
    "connection_health",
    "list_resources",
    "sync_status",
})


def _normalize_backpack_resource(resource: Any) -> str:
    name = str(resource or "").strip().strip("/")
    if not name:
        return ""
    if "/" not in name:
        return f"backpack/{name}"
    return name


def profile_for_resource(resource: Any) -> str:
    normalized = _normalize_backpack_resource(resource)
    if normalized.startswith("backpack/"):
        return "sensitive_default"
    return "none"


def resolve_redaction_profile(
    *,
    operation: str = "",
    template_profile: Any = None,
    resource: Any = None,
) -> str:
    op = str(operation or "").strip()
    if op in METADATA_OPERATIONS:
        return "none"

    template = normalize_redaction_profile(template_profile) if template_profile else "none"
    resolved_resource = _normalize_backpack_resource(resource)
    if resolved_resource:
        resource_profile = profile_for_resource(resolved_resource)
        if resource_profile != "none":
            return resource_profile

    return template


def normalize_redaction_profile(value: Any) -> str:
    profile = str(value or "none").strip().lower() or "none"
    if profile not in {
        "none",
        "sensitive_default",
        "organization_default",
        "summary_only",
        "metadata_only",
    }:
        return "sensitive_default"
    return profile


def _redact_mapping(row: Mapping[str, Any], *, deny_fields: frozenset[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        name = str(key)
        if name in deny_fields:
            out[name] = REDACTED
            continue
        if isinstance(value, dict):
            nested = _redact_mapping(value, deny_fields=deny_fields)
            out[name] = nested
            continue
        if isinstance(value, list) and value and isinstance(value[0], dict):
            out[name] = [_redact_mapping(item, deny_fields=deny_fields) if isinstance(item, dict) else item for item in value]
            continue
        out[name] = value
    return out


def _keep_fields(row: Mapping[str, Any], *, allow_fields: frozenset[str]) -> dict[str, Any]:
    return {str(key): value for key, value in row.items() if str(key) in allow_fields}


def redact_row(row: Any, profile: str) -> Any:
    normalized = normalize_redaction_profile(profile)
    if normalized == "none" or not isinstance(row, dict):
        return row
    if normalized == "sensitive_default":
        return _redact_mapping(row, deny_fields=SENSITIVE_FIELDS)
    if normalized == "organization_default":
        return _redact_mapping(row, deny_fields=ORGANIZATION_SENSITIVE_FIELDS)
    if normalized == "summary_only":
        return _keep_fields(row, allow_fields=SUMMARY_ONLY_FIELDS)
    if normalized == "metadata_only":
        return {}
    return row


def redact_rows(rows: list[Any], profile: str) -> list[Any]:
    normalized = normalize_redaction_profile(profile)
    if normalized == "none":
        return list(rows)
    return [redact_row(item, normalized) for item in rows]


def _redact_record_collections(payload: dict[str, Any], profile: str) -> None:
    for key in ("rows", "items"):
        values = payload.get(key)
        if isinstance(values, list):
            payload[key] = redact_rows(values, profile)


def redaction_profile_protects_resource(profile: str, resource: Any) -> bool:
    normalized = normalize_redaction_profile(profile)
    if normalized == "none":
        return False
    resource_profile = profile_for_resource(resource)
    if resource_profile == "sensitive_default":
        return normalized == "sensitive_default"
    return normalized != "none"


def apply_redaction_to_payload(
    payload: Mapping[str, Any],
    profile: str,
    *,
    resource: Any = None,
) -> dict[str, Any]:
    normalized = resolve_redaction_profile(
        template_profile=profile,
        resource=resource or (payload.get("resource") if isinstance(payload, dict) else None),
    )
    result = deepcopy(dict(payload))
    result["redaction_profile"] = normalized
    effective_resource = resource or result.get("resource") or result.get("params", {}).get("resource")
    result["redaction_applied"] = redaction_profile_protects_resource(normalized, effective_resource)

    if normalized == "none":
        return result

    if normalized == "metadata_only":
        kept = {key: result[key] for key in METADATA_ONLY_FIELDS if key in result}
        kept["items"] = []
        kept["rows"] = []
        kept["redaction_profile"] = normalized
        kept["redaction_applied"] = True
        return kept

    _redact_record_collections(result, normalized)

    return result