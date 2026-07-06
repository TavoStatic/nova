from __future__ import annotations

from typing import Any

MAX_DISTRICT_SCAN_RECORDS: int = 20_000


def normalize_district_lea_id(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text or not text.isdigit():
        return None
    return int(text)


def district_lea_filter_clause(resource: str, lea_id: Any) -> str | None:
    """Build an OData $filter clause to scope reads to one Texas district LEA."""
    lea = normalize_district_lea_id(lea_id)
    if lea is None:
        return None

    tail = str(resource or "").strip().strip("/").split("/")[-1].lower()
    if tail == "localeducationagencies":
        return f"localEducationAgencyId eq {lea}"
    return f"localEducationAgencyReference/localEducationAgencyId eq {lea}"


def merge_filter_params(
    filter_params: dict[str, Any] | None,
    clause: str | None,
) -> dict[str, Any]:
    if not clause:
        return dict(filter_params or {})
    params = dict(filter_params or {})
    existing = str(params.get("$filter") or "").strip()
    params["$filter"] = f"({existing}) and ({clause})" if existing else clause
    return params


def uses_client_side_district_filter(base_url: str) -> bool:
    """TEA statewide IODS ignores OData $filter on collection reads."""
    return "tea.texas.gov" in str(base_url or "").lower()


def item_matches_district(item: Any, lea_id: Any) -> bool:
    lea = normalize_district_lea_id(lea_id)
    if lea is None or not isinstance(item, dict):
        return False

    ref = item.get("localEducationAgencyReference")
    if isinstance(ref, dict):
        ref_lea = ref.get("localEducationAgencyId")
        if ref_lea is not None:
            try:
                if int(ref_lea) == lea:
                    return True
            except (TypeError, ValueError):
                pass

    direct_lea = item.get("localEducationAgencyId")
    if direct_lea is not None:
        try:
            if int(direct_lea) == lea:
                return True
        except (TypeError, ValueError):
            pass

    prefix = str(lea)
    for field in ("schoolId", "studentUniqueId", "educationOrganizationId"):
        value = item.get(field)
        if value is not None and str(value).startswith(prefix):
            return True
    return False


def district_filter_strategy(base_url: str) -> str:
    return "client_side" if uses_client_side_district_filter(base_url) else "odata"