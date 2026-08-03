from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from services.edfi.profile_evidence import (
    DEFAULT_CONNECTION_ID,
    build_capability_profile_evidence,
    get_district_layer_facts,
)
from services.nova_wiring_inventory import build_source_wiring_probe_payload, wiring_surface_ids

CORE_READINESS_MILESTONE = "NOVA-EDFI-010"
# Metadata rediscovery cadence (advisory). Not a hard block — live TEA re-profile
# every week was creating permanent governance pressure once the profile aged.
PROFILE_FRESHNESS_TTL_SEC = 7 * 24 * 3600
_EDFI_CAPABILITY_SURFACE_ID = "edfi_capability_profile"


def _work_tree_signal_ingestion_source() -> str:
    path = Path(__file__).resolve().parents[2] / "services" / "work_tree_signal_ingestion.py"
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _inventory_declared() -> bool:
    return _EDFI_CAPABILITY_SURFACE_ID in wiring_surface_ids()


def _evidence_loop_ready() -> bool:
    probe = build_source_wiring_probe_payload()
    signal_sources = set(probe.get("signal_sources") or [])
    if _EDFI_CAPABILITY_SURFACE_ID not in signal_sources:
        return False
    source = _work_tree_signal_ingestion_source()
    return (
        '"source": "edfi_capability_profile"' in source
        and "def resolve_edfi_capability_profile_branches" in source
        and "profile_read_evidence_valid" in source
        and "profile_evidence_closure_required" in source
    )


def _issue_messages(issues: list[Any]) -> list[str]:
    messages: list[str] = []
    for item in list(issues or []):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if code and detail:
            messages.append(f"{code}: {detail}")
        elif code:
            messages.append(code)
        elif detail:
            messages.append(detail)
    return messages[:8]


def _next_recommended_slice(
    *,
    profile_ok: bool,
    profile_fresh: bool,
    inventory_declared: bool,
    evidence_loop_ready: bool,
    district_facts_ok: bool,
    backpack_operational: bool = False,
) -> str:
    if not profile_ok:
        return "edfi-profile-refresh"
    if not inventory_declared:
        return "edfi-wiring-inventory"
    if not evidence_loop_ready:
        return "edfi-profile-evidence-loop"
    if not district_facts_ok:
        return "edfi-connection-config"
    # Stale profile is advisory when the backpack extract path is operational.
    if not profile_fresh and not backpack_operational:
        return "edfi-profile-refresh"
    if backpack_operational:
        return "backpack-local-extract-ready"
    return "domain-layer-first-consumer"


def _backpack_operational_snapshot(connection_id: str) -> dict[str, Any]:
    """
    True when the Ed-Fi backpack can serve reports without a live metadata re-probe.

    This is the pressure relief valve: a saved schools extract + known LEA means
    Nova should not keep opening work-tree pressure for 'core not ready'.
    """
    out: dict[str, Any] = {
        "ok": False,
        "has_schools_extract": False,
        "schools_row_count": 0,
        "extract_synced_at": "",
        "connection_id": str(connection_id or "").strip() or DEFAULT_CONNECTION_ID,
    }
    try:
        from services.edfi.extract_store import list_extracts

        rows = list_extracts("edfi")
        best: dict[str, Any] | None = None
        for item in rows:
            if str(item.get("intent") or "") != "schools":
                continue
            count = int(item.get("row_count") or 0)
            if count <= 0:
                continue
            if best is None or count > int(best.get("row_count") or 0):
                best = item
        if best is not None:
            out["has_schools_extract"] = True
            out["schools_row_count"] = int(best.get("row_count") or 0)
            out["extract_synced_at"] = str(best.get("synced_at") or "")
            out["ok"] = True
    except Exception:
        pass
    return out


def _profile_freshness(
    evidence: dict[str, Any],
    *,
    now_fn: Callable[[], float] = time.time,
    ttl_sec: int = PROFILE_FRESHNESS_TTL_SEC,
) -> dict[str, Any]:
    discovered_at = int(evidence.get("discovered_at") or 0)
    now_epoch = int(now_fn())
    age_sec = max(0, now_epoch - discovered_at) if discovered_at > 0 else None
    fresh = age_sec is not None and age_sec <= max(60, int(ttl_sec))
    return {
        "discovered_at": discovered_at,
        "profile_age_sec": age_sec,
        "profile_fresh": fresh,
        "profile_freshness_ttl_sec": max(60, int(ttl_sec)),
    }


def read_edfi_core_readiness(
    connection_id: str = DEFAULT_CONNECTION_ID,
    *,
    now_fn: Callable[[], float] = time.time,
    profile_freshness_ttl_sec: int = PROFILE_FRESHNESS_TTL_SEC,
) -> dict[str, Any]:
    """Summarize Ed-Fi Core operational readiness without live probes or branch mutation."""
    resolved_id = str(connection_id or DEFAULT_CONNECTION_ID).strip() or DEFAULT_CONNECTION_ID
    evidence = build_capability_profile_evidence(resolved_id)
    facts = get_district_layer_facts(resolved_id)
    freshness = _profile_freshness(
        evidence,
        now_fn=now_fn,
        ttl_sec=profile_freshness_ttl_sec,
    )

    profile_ok = bool(evidence.get("ok"))
    profile_fresh = bool(freshness.get("profile_fresh"))
    inventory_declared = _inventory_declared()
    evidence_loop_ready = _evidence_loop_ready()
    district_facts_ok = bool(facts.get("ok")) and bool(str(facts.get("lea_id") or "").strip())
    sync_status = facts.get("sync_status")
    sync_status_present = isinstance(sync_status, dict) and bool(sync_status.get("present"))
    backpack = _backpack_operational_snapshot(resolved_id)
    backpack_operational = bool(backpack.get("ok"))

    blocking_issues: list[str] = []
    watch_issues: list[str] = []
    if not profile_ok:
        blocking_issues.extend(_issue_messages(list(evidence.get("issues") or [])))
        if not blocking_issues:
            blocking_issues.append("edfi_profile_not_ok")
    if not inventory_declared:
        blocking_issues.append("edfi_capability_profile wiring surface is not declared")
    if not evidence_loop_ready:
        blocking_issues.append("edfi profile evidence closure loop is not wired")
    if not district_facts_ok:
        if not bool(facts.get("ok")):
            blocking_issues.extend(_issue_messages(list(facts.get("issues") or [])))
        if not str(facts.get("lea_id") or "").strip():
            blocking_issues.append("edfi_district_lea_id_missing")
    # Stale metadata is a watch item, not a hard block — re-profile is optional and
    # expensive on TEA. Local extracts keep the backpack operational.
    if profile_ok and not profile_fresh:
        watch_issues.append("edfi_profile_stale")
    if not backpack_operational and profile_ok and district_facts_ok:
        watch_issues.append("edfi_schools_extract_missing")

    # Ready = can operate as a bridge without forcing live TEA metadata refresh.
    ready = (
        profile_ok
        and inventory_declared
        and evidence_loop_ready
        and district_facts_ok
    )
    if ready:
        blocking_issues = []

    return {
        "ready": ready,
        "profile_ok": profile_ok,
        "profile_fresh": profile_fresh,
        "profile_age_sec": freshness.get("profile_age_sec"),
        "profile_freshness_ttl_sec": freshness.get("profile_freshness_ttl_sec"),
        "inventory_declared": inventory_declared,
        "evidence_loop_ready": evidence_loop_ready,
        "district_facts_ok": district_facts_ok,
        "backpack_operational": backpack_operational,
        "backpack": backpack,
        "sync_status_present": sync_status_present,
        "blocking_issues": blocking_issues[:8],
        "watch_issues": watch_issues[:8],
        "next_recommended_slice": _next_recommended_slice(
            profile_ok=profile_ok,
            profile_fresh=profile_fresh,
            inventory_declared=inventory_declared,
            evidence_loop_ready=evidence_loop_ready,
            district_facts_ok=district_facts_ok,
            backpack_operational=backpack_operational,
        ),
        "milestone": CORE_READINESS_MILESTONE,
        "connection_id": resolved_id,
    }