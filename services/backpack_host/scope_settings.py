from __future__ import annotations

"""
Shared helpers for backpack scope settings (district vs region).

Texas TEA ODS credentials are typically statewide: the client id/secret can reach
many districts. Nova still scopes every install by LEA list (policy), not by
assuming the key is single-district.

LEA forms like PEIMS 031901 and Ed-Fi 31901 are the same integer identity.
"""

import re
from typing import Any


SCOPE_SINGLE = "single_lea"
SCOPE_MULTI = "multi_lea"
VALID_SCOPE_MODES = {SCOPE_SINGLE, SCOPE_MULTI, "district", "region", "multi"}

# Declared by the installer (what they believe the key allows). Profile can refine later.
ACCESS_READ = "read"
ACCESS_LIMITED = "limited"
ACCESS_FULL = "full"
VALID_ACCESS_TIERS = {ACCESS_READ, ACCESS_LIMITED, ACCESS_FULL}


def normalize_scope_mode(value: Any) -> str:
    mode = str(value or SCOPE_SINGLE).strip().lower().replace("-", "_")
    if mode in {"region", "multi", "multi_lea", "multi_district"}:
        return SCOPE_MULTI
    if mode in {"district", "single", "single_lea", "lea"}:
        return SCOPE_SINGLE
    return SCOPE_SINGLE


def normalize_access_tier(value: Any) -> str:
    tier = str(value or ACCESS_READ).strip().lower()
    if tier in {"readonly", "read_only", "ro"}:
        return ACCESS_READ
    if tier in {"limited", "ext", "restricted"}:
        return ACCESS_LIMITED
    if tier in {"full", "admin", "unrestricted"}:
        return ACCESS_FULL
    if tier in VALID_ACCESS_TIERS:
        return tier
    return ACCESS_READ


def lea_identity_key(value: Any) -> int | None:
    """
    Canonical LEA identity for comparisons.

    PEIMS-style 031901 and Ed-Fi-style 31901 both map to 31901.
    """
    text = str(value or "").strip()
    if not text:
        return None
    # Prefer shared Ed-Fi helper when available
    try:
        from services.edfi.district_scope import normalize_district_lea_id

        return normalize_district_lea_id(text)
    except Exception:
        pass
    if text.isdigit():
        return int(text)
    return None


def format_lea_id(value: Any) -> str:
    """Stable string form for storage/display (no leading zeros)."""
    key = lea_identity_key(value)
    if key is None:
        return str(value or "").strip()
    return str(key)


def lea_in_list(candidate: Any, allowed: list[Any]) -> bool:
    want = lea_identity_key(candidate)
    if want is None:
        return False
    for item in allowed:
        if lea_identity_key(item) == want:
            return True
    return False


def parse_lea_list(value: Any) -> list[str]:
    """Accept a list or comma/whitespace-separated string of LEA ids (deduped by identity)."""
    raw: list[str] = []
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = str(item or "").strip()
            if text:
                raw.append(text)
    else:
        text = str(value).strip()
        if text:
            raw.extend(p.strip() for p in re.split(r"[\s,;]+", text) if p.strip())

    out: list[str] = []
    seen: set[int] = set()
    for item in raw:
        key = lea_identity_key(item)
        if key is None:
            if item not in out:
                out.append(item)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(format_lea_id(item))
    return out


def allowed_leas_from_settings(settings: dict[str, Any]) -> list[str]:
    mode = normalize_scope_mode(settings.get("scope_mode"))
    if mode == SCOPE_MULTI:
        leas = parse_lea_list(settings.get("allowed_lea_ids"))
        primary = str(settings.get("district_lea_id") or "").strip()
        if primary and not lea_in_list(primary, leas):
            leas = [format_lea_id(primary), *leas]
        return leas
    primary = str(settings.get("district_lea_id") or "").strip()
    return [format_lea_id(primary)] if primary else []


def primary_lea_from_settings(settings: dict[str, Any]) -> str:
    """LEA written into ConnectionConfig for Ed-Fi core services."""
    primary = str(settings.get("district_lea_id") or "").strip()
    if primary:
        return format_lea_id(primary)
    allowed = allowed_leas_from_settings(settings)
    return allowed[0] if allowed else ""


def resolve_query_lea(
    settings: dict[str, Any],
    request_lea: str | None = None,
) -> tuple[str, str | None]:
    """
    Resolve which LEA a data query should use.

    Returns (lea_id, error_code_or_none).
    LEA matching is identity-based (031901 == 31901).
    """
    mode = normalize_scope_mode(settings.get("scope_mode"))
    allowed = allowed_leas_from_settings(settings)
    requested = str(request_lea or "").strip()

    if mode == SCOPE_SINGLE:
        if not allowed:
            return "", "district_lea_id_missing"
        if requested and not lea_in_list(requested, allowed):
            return "", "lea_not_in_scope"
        return allowed[0], None

    # multi_lea — policy list on a typically statewide key
    if not allowed:
        return "", "allowed_lea_ids_missing"
    if requested:
        if not lea_in_list(requested, allowed):
            return "", "lea_not_in_allowed_list"
        return format_lea_id(requested), None
    # Default to primary/first so existing tools keep working
    return allowed[0], None


def validate_scope_values(values: dict[str, Any]) -> list[dict[str, str]]:
    """Extra validation beyond per-field schema checks."""
    errors: list[dict[str, str]] = []
    mode = normalize_scope_mode(values.get("scope_mode"))
    if str(values.get("scope_mode") or "").strip():
        raw = str(values.get("scope_mode")).strip().lower().replace("-", "_")
        if raw not in VALID_SCOPE_MODES and normalize_scope_mode(raw) not in {
            SCOPE_SINGLE,
            SCOPE_MULTI,
        }:
            errors.append(
                {
                    "code": "scope_mode_invalid",
                    "field": "scope_mode",
                    "detail": "scope_mode must be single_lea (district) or multi_lea (region).",
                }
            )

    if mode == SCOPE_SINGLE:
        if not str(values.get("district_lea_id") or "").strip():
            errors.append(
                {
                    "code": "district_lea_id_required",
                    "field": "district_lea_id",
                    "detail": "District mode requires district_lea_id (e.g. 031901 or 31901).",
                }
            )
        elif lea_identity_key(values.get("district_lea_id")) is None:
            errors.append(
                {
                    "code": "district_lea_id_invalid",
                    "field": "district_lea_id",
                    "detail": "district_lea_id must be numeric (PEIMS or Ed-Fi LEA form).",
                }
            )
    else:
        allowed = parse_lea_list(values.get("allowed_lea_ids"))
        primary = str(values.get("district_lea_id") or "").strip()
        if not allowed and not primary:
            errors.append(
                {
                    "code": "allowed_lea_ids_required",
                    "field": "allowed_lea_ids",
                    "detail": (
                        "Region mode requires allowed_lea_ids. TEA keys are usually statewide; "
                        "this list is which districts THIS Nova install may query."
                    ),
                }
            )

    tier_raw = str(values.get("credential_access_tier") or "").strip()
    if tier_raw and normalize_access_tier(tier_raw) not in VALID_ACCESS_TIERS:
        errors.append(
            {
                "code": "credential_access_tier_invalid",
                "field": "credential_access_tier",
                "detail": "credential_access_tier must be read, limited, or full.",
            }
        )
    return errors
