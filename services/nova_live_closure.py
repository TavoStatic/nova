from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from services.nova_wiring_inventory import build_self_repair_closure_inventory_payload
from services.regression_evidence import (
    regression_evidence_stale,
    regression_failure_active,
    regression_outcome_label,
)

LiveClosureCheck = Callable[[dict[str, Any], Path], list[str]]

_SEMANTIC_ROOT_IDS = frozenset(
    {
        "core_steward_reflection",
        "memory_identity",
        "conversation_routing",
        "release",
        "runtime_core",
    }
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _owner_verdicts(status: dict[str, Any]) -> list[dict[str, Any]]:
    raw = status.get("nova_mission_owner_verdicts")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _regression_status_payload(status: dict[str, Any]) -> dict[str, Any]:
    payload = status.get("regression_status")
    if isinstance(payload, dict):
        return dict(payload)
    label = regression_outcome_label(str(status.get("regression_status_label") or status.get("last_regression_status") or ""))
    if not label:
        return {}
    return {
        "status": label,
        "date": str(status.get("last_regression_date") or ""),
        "detail": str(status.get("last_regression_detail") or ""),
        "failed_lane": str(status.get("last_regression_failed_lane") or ""),
        "failed_tests": list(status.get("last_regression_failed_tests") or []),
    }


def _core_thinning_pressure_metrics(status: dict[str, Any]) -> tuple[int, int, bool]:
    """Return order_count, executable_count, and whether a thinning witness was found."""
    for verdict in _owner_verdicts(status):
        if str(verdict.get("owner") or "").strip() != "core_thinning":
            continue
        evidence = dict(verdict.get("evidence") or {}) if isinstance(verdict.get("evidence"), dict) else {}
        return (
            int(evidence.get("order_count", 0) or 0),
            int(evidence.get("executable_count", 0) or 0),
            True,
        )

    sync = dict(status.get("core_thinning_sync") or {}) if isinstance(status.get("core_thinning_sync"), dict) else {}
    nested_verdict = (
        dict(sync.get("owner_verdict") or {})
        if isinstance(sync.get("owner_verdict"), dict)
        else {}
    )
    nested_evidence = (
        dict(nested_verdict.get("evidence") or {})
        if isinstance(nested_verdict.get("evidence"), dict)
        else {}
    )
    if nested_evidence:
        return (
            int(nested_evidence.get("order_count", sync.get("order_count", 0) or 0) or 0),
            int(nested_evidence.get("executable_count", 0) or 0),
            True,
        )

    order_count = int(status.get("core_thinning_order_count", sync.get("order_count", 0) or 0) or 0)
    executable_count = int(sync.get("executable_count", 0) or 0)
    return order_count, executable_count, bool(order_count or sync)


def _check_core_steward_reflection(status: dict[str, Any], repo_root: Path) -> list[str]:
    del repo_root
    order_count, executable_count, witnessed = _core_thinning_pressure_metrics(status)
    if witnessed and order_count > 0 and executable_count <= 0:
        return ["feedback_loop_gap:thinning_pressure_without_executable_work"]
    if witnessed:
        return []
    if order_count > 0 and executable_count <= 0:
        return ["feedback_loop_gap:thinning_pressure_without_executable_work"]
    return []


def _check_memory_identity(status: dict[str, Any], repo_root: Path) -> list[str]:
    del status
    gaps: list[str] = []
    reply_seq = _read_text(repo_root / "services" / "nova_reply_sequence.py")
    nova_core = _read_text(repo_root / "nova_core.py")
    if "apply_user_memory_learning" not in reply_seq:
        gaps.append("production_wiring_gap:reply_sequence_missing_learning_hook")
    if "build_memory_recall_plan" not in nova_core:
        gaps.append("production_wiring_gap:mem_recall_missing_routing_plan")
    if "build_memory_read_plan" not in nova_core:
        gaps.append("production_wiring_gap:recent_learning_missing_routing_plan")
    return gaps


def _check_conversation_routing(status: dict[str, Any], repo_root: Path) -> list[str]:
    del status
    policy_text = _read_text(repo_root / "policy.json")
    if re.search(r'"fast_chat_skip_spine"\s*:\s*true', policy_text, flags=re.IGNORECASE):
        return ["front_door_divergence:fast_chat_skip_spine_enabled_in_policy"]
    reply_seq = _read_text(repo_root / "services" / "nova_reply_sequence.py")
    if "skipped_planner" in reply_seq and re.search(
        r'input_source\s*==\s*["\']http["\']',
        reply_seq,
    ):
        return ["front_door_divergence:http_fast_chat_skips_planner_spine"]
    return []


def _check_release(status: dict[str, Any], repo_root: Path) -> list[str]:
    del repo_root
    payload = _regression_status_payload(status)
    label = regression_outcome_label(str(payload.get("status") or ""))
    if not label:
        return []
    stale = regression_evidence_stale(
        status_label=label,
        regression_date=str(payload.get("date") or ""),
    )
    if regression_failure_active(status_label=label, stale=stale):
        return ["feedback_loop_gap:active_regression_failure"]
    return []


def _check_runtime_core(status: dict[str, Any], repo_root: Path) -> list[str]:
    del status
    gaps: list[str] = []
    adapter_checks = (
        ("nova_http.py", "render_nova_pulse", "nova_core.py", "def render_nova_pulse"),
    )
    for consumer_file, symbol, provider_file, provider_marker in adapter_checks:
        consumer_text = _read_text(repo_root / consumer_file)
        if symbol not in consumer_text:
            continue
        provider_text = _read_text(repo_root / provider_file)
        if provider_marker not in provider_text:
            gaps.append(f"cross_module_gap:missing_adapter_{symbol}")
    return gaps


LIVE_CLOSURE_CHECKS: dict[str, LiveClosureCheck] = {
    "core_steward_reflection": _check_core_steward_reflection,
    "memory_identity": _check_memory_identity,
    "conversation_routing": _check_conversation_routing,
    "release": _check_release,
    "runtime_core": _check_runtime_core,
}


def build_live_closure_inventory_payload(
    status_payload: dict[str, Any] | None = None,
    *,
    root: str | Path | None = None,
    self_repair_seed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate semantic live closure for roots with behavioral validators.

    This inventory is distinct from source-contract closure: it checks whether
    known feedback loops can diagnose, act, produce evidence, and close work.
    """
    status = status_payload if isinstance(status_payload, dict) else {}
    repo_root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    seed = (
        self_repair_seed
        if isinstance(self_repair_seed, dict)
        else build_self_repair_closure_inventory_payload(status, root=repo_root)
    )

    roots: list[dict[str, Any]] = []
    gap_roots: list[str] = []
    verified_roots: list[str] = []
    unverified_roots: list[str] = []
    depth_counts: dict[str, int] = {}

    for base_row in list(seed.get("roots") or []):
        if not isinstance(base_row, dict):
            continue
        row = dict(base_row)
        root_id = str(row.get("root_id") or "").strip()
        if not root_id:
            continue

        live_gaps = list(LIVE_CLOSURE_CHECKS.get(root_id, lambda _s, _r: [])(status, repo_root))
        source_ok = bool(row.get("ok", False))
        has_semantic_check = root_id in LIVE_CLOSURE_CHECKS

        if live_gaps:
            live_depth = "live_gap"
        elif not source_ok:
            live_depth = "source_contract_gap"
        elif has_semantic_check:
            live_depth = "live_verified"
        else:
            live_depth = "source_contract_only"

        row["live_gaps"] = live_gaps
        row["live_closure_depth"] = live_depth
        row["semantic_check_available"] = has_semantic_check
        row["source_contract_ok"] = source_ok
        row["ok"] = source_ok and not live_gaps

        depth_counts[live_depth] = depth_counts.get(live_depth, 0) + 1
        if has_semantic_check and not live_gaps:
            verified_roots.append(root_id)
        elif not has_semantic_check:
            unverified_roots.append(root_id)
        if not row["ok"]:
            gap_roots.append(root_id)
        roots.append(row)

    return {
        "ok": not gap_roots,
        "proof_scope": "live_closure",
        "root_count": len(roots),
        "gap_count": len(gap_roots),
        "gap_roots": gap_roots,
        "verified_root_count": len(verified_roots),
        "unverified_root_count": len(unverified_roots),
        "semantic_root_ids": sorted(LIVE_CLOSURE_CHECKS.keys()),
        "verified_roots": verified_roots,
        "unverified_roots": unverified_roots,
        "depth_counts": depth_counts,
        "coverage_note": (
            "Semantic live closure is enforced for declared validator roots; "
            "remaining roots remain source-contract only until validators are added."
        ),
        "source_contract_seed": {
            "proof_scope": str(seed.get("proof_scope") or "source_contract"),
            "ok": bool(seed.get("ok", False)),
            "gap_count": int(seed.get("gap_count", 0) or 0),
        },
        "roots": roots,
    }