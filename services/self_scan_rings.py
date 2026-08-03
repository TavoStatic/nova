"""Self-scan rings: map (1), contract (2), climb (3) — weave, not a second engine.

See docs/SELF_SCAN_RINGS_DESIGN.md.
"""
from __future__ import annotations

from typing import Any, Iterable

from services.nova_root_inventory import build_source_root_inventory_payload
from services.nova_wiring_inventory import (
    build_root_closure_inventory_payload,
    build_source_wiring_probe_payload,
    build_wiring_inventory_payload,
)

PROBE_LIVE = "live_status"
PROBE_OFFLINE = "offline"
PROBE_PARTIAL = "partial"

_LIVE_STATUS_MARKERS = (
    "guard",
    "core",
    "webui",
    "health_score",
    "operator_outbox",
    "work_tree_truth_status",
    "ollama_health",
    "autonomy_maintenance",
    "release_status",
    "runtime_summary",
)


def resolve_probe_context(
    status_payload: dict[str, Any] | None = None,
    *,
    explicit: str | None = None,
) -> str:
    """Ring 2 probe context — required before trusting status-key gaps."""
    clean = str(explicit or "").strip().lower()
    if clean in {PROBE_LIVE, PROBE_OFFLINE, PROBE_PARTIAL}:
        return clean
    status = status_payload if isinstance(status_payload, dict) else {}
    if not status:
        return PROBE_OFFLINE
    if any(key in status for key in _LIVE_STATUS_MARKERS):
        return PROBE_LIVE
    if len(status) < 8:
        return PROBE_PARTIAL
    return PROBE_LIVE


def run_ring1_map_integrity(*, root=None) -> dict[str, Any]:
    """Ring 1: source paths vs SOURCE_ROOTS / coverage (existing scanner)."""
    inventory = build_source_root_inventory_payload(root=root)
    return {
        "ring": 1,
        "name": "map_integrity",
        "ok": bool(inventory.get("ok")),
        "gap_count": int(inventory.get("gap_count", 0) or 0),
        "findings": {
            "unwired_roots": list(inventory.get("unwired_roots") or []),
            "missing_evidence_roots": list(inventory.get("missing_evidence_roots") or []),
            "unclassified_source_files": list(inventory.get("unclassified_source_files") or []),
        },
        "inventory": inventory,
    }


def run_ring2_contract_integrity(
    status_payload: dict[str, Any] | None = None,
    *,
    probe_context: str | None = None,
    signal_sources: Iterable[str] | None = None,
    planned_tools: Iterable[str] | None = None,
    advisory_actions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Ring 2: declared surfaces/roots vs reality, with honest probe context."""
    context = resolve_probe_context(status_payload, explicit=probe_context)
    status = status_payload if isinstance(status_payload, dict) else {}
    wiring = build_wiring_inventory_payload(
        status,
        signal_sources=signal_sources,
        planned_tools=planned_tools,
        advisory_actions=advisory_actions,
        probe_context=context,
    )
    closure = build_root_closure_inventory_payload(
        status,
        signal_sources=signal_sources,
        planned_tools=planned_tools,
        advisory_actions=advisory_actions,
        probe_context=context,
    )
    probe = build_source_wiring_probe_payload()
    gap_count = int(wiring.get("gap_count", 0) or 0) + int(closure.get("gap_count", 0) or 0)
    # Source probe is structural (paths/tools), always counts.
    gap_count += int(probe.get("gap_count", 0) or 0)
    return {
        "ring": 2,
        "name": "contract_integrity",
        "probe_context": context,
        "ok": gap_count == 0 and bool(wiring.get("ok")) and bool(closure.get("ok")) and bool(probe.get("ok")),
        "gap_count": gap_count,
        "findings": {
            "wiring_gap_count": int(wiring.get("gap_count", 0) or 0),
            "closure_gap_count": int(closure.get("gap_count", 0) or 0),
            "probe_gap_count": int(probe.get("gap_count", 0) or 0),
            "missing_status_surfaces": list(wiring.get("missing_status_surfaces") or []),
            "closure_gap_roots": list(closure.get("gap_roots") or []),
            "status_gaps_scored": context == PROBE_LIVE,
        },
        "wiring_inventory": wiring,
        "root_closure_inventory": closure,
        "source_wiring_probe": probe,
    }


def assess_stem_climbability(
    *,
    tool_name: str = "",
    tool_status: str = "",
    tool_args_resolvable: bool | None = None,
    tool_in_safe_execute: bool | None = None,
    operator_hold: bool = False,
    blocked_reason: str = "",
) -> dict[str, Any]:
    """Ring 3 unit: is this named stem climbable? (findings queue only)."""
    tool = str(tool_name or "").strip()
    status = str(tool_status or "").strip().lower()
    reason = ""
    climbable = True
    if operator_hold or str(blocked_reason or "").strip():
        climbable = False
        reason = str(blocked_reason or "operator_hold").strip() or "operator_hold"
    elif tool and tool_in_safe_execute is False:
        climbable = False
        reason = "tool_not_in_safe_execute"
    elif tool in {"read", "ls", "find"} and tool_args_resolvable is False:
        climbable = False
        reason = "unresolvable_tool_args"
    elif status == "failed":
        climbable = False
        reason = "tool_failed"
    elif not tool and not operator_hold:
        # No tool and not an explicit hold — unclimbable for autonomy execute.
        climbable = False
        reason = "no_tool_selected"
    return {
        "climbable": climbable,
        "reason": reason or ("climbable" if climbable else "unclimbable"),
        "tool": tool,
        "tool_status": status,
    }


def run_ring3_climb_integrity(
    findings_queue: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ring 3: climbability of the findings queue only (not a repo scan)."""
    queue = [dict(row) for row in list(findings_queue or []) if isinstance(row, dict)]
    assessed: list[dict[str, Any]] = []
    climbable_n = 0
    unclimbable_n = 0
    for row in queue:
        result = assess_stem_climbability(
            tool_name=str(row.get("recommended_tool") or row.get("tool") or ""),
            tool_status=str(row.get("tool_status") or ""),
            tool_args_resolvable=row.get("tool_args_resolvable"),
            tool_in_safe_execute=row.get("tool_in_safe_execute"),
            operator_hold=bool(row.get("operator_hold")),
            blocked_reason=str(row.get("blocked_reason") or ""),
        )
        entry = {
            **{k: row.get(k) for k in ("tree_id", "branch_id", "task_id", "task_title", "title") if k in row},
            **result,
        }
        assessed.append(entry)
        if result["climbable"]:
            climbable_n += 1
        else:
            unclimbable_n += 1
    return {
        "ring": 3,
        "name": "climb_integrity",
        "ok": unclimbable_n == 0 or climbable_n > 0,  # ok if queue empty or has climbable work
        "queue_count": len(queue),
        "climbable_count": climbable_n,
        "unclimbable_count": unclimbable_n,
        "findings": assessed,
    }


def run_self_scan_rings(
    status_payload: dict[str, Any] | None = None,
    *,
    findings_queue: list[dict[str, Any]] | None = None,
    probe_context: str | None = None,
    root=None,
) -> dict[str, Any]:
    """Run rings 1 → 2 → 3 in order. Ring 3 only sees the findings queue."""
    ring1 = run_ring1_map_integrity(root=root)
    ring2 = run_ring2_contract_integrity(
        status_payload,
        probe_context=probe_context,
    )
    ring3 = run_ring3_climb_integrity(findings_queue)
    return {
        "ok": bool(ring1.get("ok")) and bool(ring2.get("ok")) and bool(ring3.get("ok")),
        "rings": {
            "1_map_integrity": ring1,
            "2_contract_integrity": ring2,
            "3_climb_integrity": ring3,
        },
        "probe_context": ring2.get("probe_context"),
        "summary": {
            "ring1_gap_count": ring1.get("gap_count"),
            "ring2_gap_count": ring2.get("gap_count"),
            "ring3_unclimbable_count": ring3.get("unclimbable_count"),
            "ring3_climbable_count": ring3.get("climbable_count"),
        },
    }
