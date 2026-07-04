#!/usr/bin/env python3
"""Capture P0 Leah promotion baseline (core gate, gaps, layer maturity)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.capabilities_gap_detector import detect_capability_gaps
from services.layer_maturity_policy import enrich_status_with_layer_maturity
from services.nova_runtime_context import RUNTIME_DIR


def _load_policy() -> dict:
    try:
        return json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _local_status_payload() -> dict:
    try:
        import autonomy_maintenance as maintenance

        return maintenance._local_dependency_payload_for_signal_ingestion({})
    except Exception as exc:
        return {"ok": False, "error": str(exc), "signal_ingestion_status_source": "baseline_script_fallback"}


def _work_tree_open_summary() -> dict:
    try:
        import work_tree as work_tree_module

        trees = work_tree_module.list_trees(limit=5)
        open_tasks = work_tree_module.list_open_tasks(limit=50)
        blocked = [task for task in open_tasks if str(getattr(task, "status", "") or "").strip().lower() == "blocked"]
        return {
            "tree_count": len(trees or []),
            "open_task_count": len(open_tasks or []),
            "blocked_task_count": len(blocked),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def capture_baseline(*, output: Path | None = None) -> dict:
    policy = _load_policy()
    gaps, gap_summary = detect_capability_gaps(ROOT)
    status = _local_status_payload()
    status["capability_gaps"] = gaps
    enriched = enrich_status_with_layer_maturity(status, policy=policy)
    maturity = enriched.get("layer_maturity") if isinstance(enriched.get("layer_maturity"), dict) else {}
    payload = {
        "schema": "nova.leah_promotion_baseline.v1",
        "captured_at": int(time.time()),
        "milestone": "P0",
        "core_gate": maturity.get("core_gate") or {},
        "next_leah_capability": enriched.get("next_leah_capability") or "",
        "capability_gaps": gaps,
        "capability_gaps_actionable": list(enriched.get("capability_gaps_actionable") or []),
        "capability_gaps_observed": list(enriched.get("capability_gaps_observed") or []),
        "layer_policy": maturity.get("layers") or {},
        "gap_summary": gap_summary,
        "work_tree": _work_tree_open_summary(),
        "status_source": str(status.get("signal_ingestion_status_source") or "unknown"),
    }
    target = Path(output or (RUNTIME_DIR / "leah_promotion_baseline.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    payload["output_path"] = str(target)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Leah promotion P0 baseline")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")
    parser.add_argument("--output", default="", help="Override output path")
    args = parser.parse_args()
    payload = capture_baseline(output=Path(args.output) if args.output else None)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        core = payload.get("core_gate") if isinstance(payload.get("core_gate"), dict) else {}
        print("Leah promotion baseline captured")
        print(f"  output: {payload.get('output_path')}")
        print(f"  core_gate.ok: {core.get('ok')}")
        print(f"  core_gate.drift_blocked: {core.get('drift_blocked')}")
        print(f"  missing_roots: {core.get('missing_roots')}")
        print(f"  next_leah_capability: {payload.get('next_leah_capability')}")
        print(f"  actionable_gaps: {payload.get('capability_gaps_actionable')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())