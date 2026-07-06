from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from services.edfi.client import EdFiClient
from services.edfi.diagnostics import append_audit_event

MILESTONE_ID = "NOVA-EDFI-002"

DEFAULT_PAGE_SIZE: int = 25
MAX_PAGE_SIZE: int = 500
DEFAULT_LIMIT_CAP: int = 1_000
MAX_LIMIT_CAP: int = 5_000
_DEFAULT_BACKOFF_SEC: float = 2.0


@dataclass
class PageResult:
    ok: bool
    resource: str = ""
    url: str = ""
    offset: int = 0
    limit: int = 0
    count: int = 0
    items: list[Any] = field(default_factory=list)
    latency_ms: int = 0
    status_code: int = 0
    error: str = ""
    error_code: str = ""
    rate_limited: bool = False


@dataclass
class ResourceReadResult:
    ok: bool
    resource: str = ""
    total_fetched: int = 0
    pages: int = 0
    items: list[Any] = field(default_factory=list)
    truncated: bool = False
    latency_ms: int = 0
    error: str = ""
    error_code: str = ""
    limit_cap: int = 0


def get_page(
    client: EdFiClient,
    resource: str,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    filter_params: dict[str, Any] | None = None,
    backoff_sec: float = _DEFAULT_BACKOFF_SEC,
    audit: bool = False,
) -> PageResult:
    """Fetch one page from an Ed-Fi resource collection.

    Handles 429 with a single sleep+retry.  All other error codes surface
    immediately.  URL resolution follows EdFiClient._resolve_url — pass a
    relative path like ``ed-fi/schools`` or a full https:// URL.
    """
    effective_limit = min(max(1, int(limit or DEFAULT_PAGE_SIZE)), MAX_PAGE_SIZE)
    params: dict[str, Any] = {
        "limit": effective_limit,
        "offset": max(0, int(offset or 0)),
    }
    if filter_params:
        for k, v in filter_params.items():
            params[k] = v

    started = time.perf_counter()
    response = client.get(resource, params=params)

    if response.status_code == 429:
        time.sleep(max(0.0, float(backoff_sec)))
        response = client.get(resource, params=params)

    latency_ms = int((time.perf_counter() - started) * 1000)
    items = _extract_items(response.body)
    ok = response.ok and isinstance(response.body, list)

    result = PageResult(
        ok=ok,
        resource=str(resource or "").strip(),
        url=str(response.url or ""),
        offset=int(offset or 0),
        limit=effective_limit,
        count=len(items),
        items=items,
        latency_ms=latency_ms,
        status_code=int(response.status_code or 0),
        error="" if ok else (response.error or "unexpected_response_shape"),
        error_code="" if ok else (response.error_code or "edfi_page_failed"),
        rate_limited=int(response.status_code or 0) == 429,
    )

    if audit:
        append_audit_event({
            "action": "resource_page",
            "milestone": MILESTONE_ID,
            "connection_id": str(client.config.connection_id),
            "resource": result.resource,
            "ok": result.ok,
            "offset": result.offset,
            "limit": result.limit,
            "count": result.count,
            "status_code": result.status_code,
            "error_code": result.error_code,
        })

    return result


def get_all(
    client: EdFiClient,
    resource: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    limit_cap: int = DEFAULT_LIMIT_CAP,
    filter_params: dict[str, Any] | None = None,
    backoff_sec: float = _DEFAULT_BACKOFF_SEC,
) -> ResourceReadResult:
    """Page through an Ed-Fi resource collection up to limit_cap records.

    Stops when:
    - a page returns fewer items than requested (collection exhausted), or
    - total fetched reaches limit_cap (truncated=True), or
    - any page returns an error.

    Always writes one audit entry on completion.
    """
    effective_page_size = min(max(1, int(page_size or DEFAULT_PAGE_SIZE)), MAX_PAGE_SIZE)
    effective_cap = min(max(1, int(limit_cap or DEFAULT_LIMIT_CAP)), MAX_LIMIT_CAP)

    all_items: list[Any] = []
    total_latency_ms = 0
    page_num = 0
    offset = 0
    truncated = False
    last_error = ""
    last_error_code = ""

    while True:
        remaining = effective_cap - len(all_items)
        if remaining <= 0:
            truncated = True
            break

        fetch_limit = min(effective_page_size, remaining)
        page = get_page(
            client,
            resource,
            limit=fetch_limit,
            offset=offset,
            filter_params=filter_params,
            backoff_sec=backoff_sec,
        )
        total_latency_ms += page.latency_ms
        page_num += 1

        if not page.ok:
            last_error = page.error
            last_error_code = page.error_code
            break

        all_items.extend(page.items)

        if page.count < fetch_limit:
            # Fewer items than requested — collection exhausted.
            break

        offset += page.count

    ok = page_num > 0 and not last_error_code
    append_audit_event({
        "action": "resource_read",
        "milestone": MILESTONE_ID,
        "connection_id": str(client.config.connection_id),
        "resource": str(resource or "").strip(),
        "ok": ok,
        "total_fetched": len(all_items),
        "pages": page_num,
        "truncated": truncated,
        "limit_cap": effective_cap,
        "latency_ms": total_latency_ms,
        "error_code": last_error_code,
    })

    return ResourceReadResult(
        ok=ok,
        resource=str(resource or "").strip(),
        total_fetched=len(all_items),
        pages=page_num,
        items=all_items,
        truncated=truncated,
        latency_ms=total_latency_ms,
        error=last_error,
        error_code=last_error_code,
        limit_cap=effective_cap,
    )


def _extract_items(body: Any) -> list[Any]:
    if isinstance(body, list):
        return list(body)
    return []
