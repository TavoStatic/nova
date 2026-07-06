from __future__ import annotations

from typing import Any


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