from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from services.edfi.client import EdFiClient
from services.edfi.diagnostics import append_audit_event
from services.edfi.district_scope import (
    MAX_DISTRICT_SCAN_RECORDS,
    item_matches_district,
    normalize_district_lea_id,
)

MILESTONE_ID = "NOVA-EDFI-002"

DEFAULT_PAGE_SIZE: int = 25
MAX_PAGE_SIZE: int = 500  # single HTTP page size to TEA (not LEA match cap)
DEFAULT_LIMIT_CAP: int = 1_000
MAX_LIMIT_CAP: int = 5_000
# Soft safety for "all schools in this LEA" extracts — not a fixed district size.
# Stops only after ODS scan completes, or this many *matching* LEA rows.
MAX_LEA_MATCH_CAP: int = 2_000
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
    district_filter_strategy: str = ""
    records_scanned: int = 0
    scan_cap_hit: bool = False
    district_page_complete: bool = False


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


def get_district_scoped_page(
    client: EdFiClient,
    resource: str,
    *,
    district_lea_id: Any,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    backoff_sec: float = _DEFAULT_BACKOFF_SEC,
    audit: bool = False,
    max_scan_records: int = MAX_DISTRICT_SCAN_RECORDS,
    collect_all: bool = False,
    match_cap: int | None = None,
) -> PageResult:
    """Collect district-owned records from a statewide ODS.

    TEA IODS ignores OData district filters, so this scans statewide pages and
    keeps only rows that match the configured LEA id (or Texas id prefix).
    The ``offset`` is relative to district-matched rows, not statewide rows.

    collect_all:
      Dynamic LEA size — keep scanning until the statewide collection is
      exhausted (or safety caps). Match count grows with the district instead
      of stopping at a fixed 25/50 row limit.
    """
    lea = normalize_district_lea_id(district_lea_id)
    if lea is None:
        return PageResult(
            ok=False,
            resource=str(resource or "").strip(),
            error="district_lea_id_invalid",
            error_code="district_lea_id_invalid",
        )

    # Matching-row budget (LEA size), NOT the TEA HTTP page size.
    if collect_all:
        effective_limit = min(
            max(1, int(match_cap or MAX_LEA_MATCH_CAP)),
            MAX_LEA_MATCH_CAP,
        )
    else:
        effective_limit = min(
            max(1, int(limit or DEFAULT_PAGE_SIZE)),
            MAX_LEA_MATCH_CAP,
        )
    district_offset = max(0, int(offset or 0))
    scan_cap = max(effective_limit, int(max_scan_records or MAX_DISTRICT_SCAN_RECORDS))
    # HTTP page size to TEA — larger pages = fewer round-trips when collecting all.
    fetch_size = MAX_PAGE_SIZE if collect_all else min(MAX_PAGE_SIZE, max(effective_limit * 4, 100))

    collected: list[Any] = []
    skipped = 0
    statewide_offset = 0
    records_scanned = 0
    total_latency_ms = 0
    last_status = 0
    last_url = ""
    last_error = ""
    last_error_code = ""
    source_exhausted = False

    while len(collected) < effective_limit and records_scanned < scan_cap:
        page = get_page(
            client,
            resource,
            limit=fetch_size,
            offset=statewide_offset,
            backoff_sec=backoff_sec,
        )
        total_latency_ms += page.latency_ms
        last_status = int(page.status_code or 0)
        last_url = str(page.url or "")
        if not page.ok:
            last_error = page.error
            last_error_code = page.error_code
            break

        records_scanned += page.count
        for item in page.items:
            if not item_matches_district(item, lea):
                continue
            if skipped < district_offset:
                skipped += 1
                continue
            collected.append(item)
            if len(collected) >= effective_limit:
                break

        if page.count < fetch_size:
            source_exhausted = True
            break
        statewide_offset += page.count

    scan_cap_hit = records_scanned >= scan_cap and not source_exhausted
    # Complete only when the statewide stream is exhausted (true full-LEA size).
    district_page_complete = bool(source_exhausted and not last_error_code and not scan_cap_hit)
    ok = not last_error_code and (bool(collected) or records_scanned > 0)
    if scan_cap_hit and not collected:
        ok = False
    result = PageResult(
        ok=ok,
        resource=str(resource or "").strip(),
        url=last_url,
        offset=district_offset,
        limit=effective_limit,
        count=len(collected),
        items=collected,
        latency_ms=total_latency_ms,
        status_code=last_status,
        error=last_error,
        error_code=last_error_code,
        district_filter_strategy="client_side",
        records_scanned=records_scanned,
        scan_cap_hit=scan_cap_hit,
        district_page_complete=district_page_complete,
    )

    if audit:
        append_audit_event({
            "action": "resource_page_district",
            "milestone": MILESTONE_ID,
            "connection_id": str(client.config.connection_id),
            "resource": result.resource,
            "ok": result.ok,
            "district_lea_id": lea,
            "offset": result.offset,
            "limit": result.limit,
            "count": result.count,
            "records_scanned": result.records_scanned,
            "scan_cap_hit": result.scan_cap_hit,
            "district_page_complete": result.district_page_complete,
            "status_code": result.status_code,
            "error_code": result.error_code,
            "district_filter_strategy": result.district_filter_strategy,
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
