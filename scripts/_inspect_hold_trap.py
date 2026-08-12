"""Diagnose quiet-hold + climbable freeze trap from live runtime state."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from services.nova_mission import NovaMissionService
from services.regression_evidence import regression_failure_is_lock_contention


def _find_mission(state: dict) -> dict:
    for key, value in state.items():
        if isinstance(value, dict) and "green_cycle" in value and "truth_blockers" in value:
            return value
    for nested_key in ("last_autonomy_orchestrator", "last_autonomy_execution"):
        nested = state.get(nested_key) or {}
        if isinstance(nested, dict):
            snap = nested.get("mission_snapshot")
            if isinstance(snap, dict) and "green_cycle" in snap:
                return snap
    return {}


def main() -> None:
    state_path = Path("runtime/autonomy_maintenance_state.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mission = _find_mission(state)
    orch = state.get("last_autonomy_orchestrator") or {}
    if not mission and isinstance(orch.get("mission_snapshot"), dict):
        mission = orch["mission_snapshot"]

    keys = [
        "enabled",
        "mode",
        "status",
        "action",
        "green_cycle",
        "truth_ready",
        "headline",
        "truth_blockers",
        "green_blockers",
        "validation_fresh",
        "regression_current",
        "regression_passed",
        "release_truth_current",
        "active_work_evidence_current",
        "generated_queue_untested_count",
        "ambient_gap_signal_count",
        "operator_hold_count",
        "blocked_count",
    ]
    print("mission", {k: mission.get(k) for k in keys})
    print("pillars", NovaMissionService._base_evidence_pillars_current(mission))
    print("aw_ev", NovaMissionService.active_work_evidence_current(mission))
    print("legacy_hold", NovaMissionService.hold_blocks_legacy_execution(mission))
    print(
        "orch",
        {
            k: orch.get(k)
            for k in [
                "ts",
                "decision_type",
                "reason",
                "rejection_reasons",
                "confidence",
            ]
        },
    )
    print(
        "state_reg",
        {
            k: state.get(k)
            for k in [
                "last_regression_status",
                "last_regression_tail",
                "last_regression_at",
                "last_regression_stale",
                "last_regression_returncode",
                "last_regression_failed_tests",
                "last_regression_failed_lane",
            ]
        },
    )
    reg_path = Path("runtime/regression_status.json")
    if reg_path.exists():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        print(
            "reg_file",
            {
                k: reg.get(k)
                for k in [
                    "status",
                    "last_status",
                    "failed_tests",
                    "failed_lane",
                    "updated_at",
                    "generated_at",
                    "tail",
                ]
            },
        )
        print("contention", regression_failure_is_lock_contention(reg))

    tools = [
        "read",
        "ls",
        "find",
        "release_rebuild_verify",
        "release_validation_run",
        "core_thinning",
        "run_tests",
        "inspect",
    ]
    print("hold_allow matrix:")
    for tool in tools:
        ctx = {
            "tool": tool,
            "recommended_tool": tool,
            "title": "Read release ledger validation outcome is missing",
            "path": "docs/RELEASE.md",
            "reason": "release validation outcome missing",
        }
        allow = NovaMissionService._hold_allows_active_work_tool(
            mission, tool, action_context=ctx
        )
        blocked = NovaMissionService.hold_blocks_action(
            "active_work_tree_run_next",
            mission_snapshot=mission,
            action_context=ctx,
        )
        rem = NovaMissionService._owner_remediation_allows_action(
            "active_work_tree_run_next",
            mission,
            action_context=ctx,
        )
        print(
            f"  tool={tool} allow={allow} rem={rem} blocks={blocked} "
            f"ctx_ok={NovaMissionService._release_ladder_hold_context_ok(ctx)}"
        )
    print(
        "blocks_no_ctx",
        NovaMissionService.hold_blocks_action(
            "active_work_tree_run_next", mission_snapshot=mission
        ),
    )

    # Work tree open/stuck
    db_path = Path("runtime/_internal/work_tree.db")
    if not db_path.exists():
        print("no work_tree.db")
        return
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    tables = [
        r[0]
        for r in con.execute(
            "select name from sqlite_master where type='table' order by name"
        ).fetchall()
    ]
    print("tables", tables)
    for table in tables:
        cols = [r[1] for r in con.execute(f"pragma table_info({table})").fetchall()]
        n = con.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"  {table}: {n} cols={cols}")

    # Heuristic: dump candidate tables with status-ish columns
    for table in tables:
        cols = {r[1] for r in con.execute(f"pragma table_info({table})").fetchall()}
        status_col = next((c for c in ("status", "state", "phase") if c in cols), None)
        if not status_col:
            continue
        rows = con.execute(
            f"select * from {table} where lower(coalesce({status_col},'')) "
            f"not in ('done','complete','completed','closed','archived','resolved','ok') "
            f"limit 40"
        ).fetchall()
        if not rows:
            continue
        print(f"openish_{table}", len(rows))
        for row in rows[:25]:
            d = dict(row)
            title = d.get("title") or d.get("name") or d.get("summary") or ""
            tool = d.get("tool") or d.get("recommended_tool") or ""
            payload = d.get("payload") or d.get("meta") or d.get("data") or ""
            climbable = ""
            if isinstance(payload, str) and payload.startswith("{"):
                try:
                    p = json.loads(payload)
                    climbable = p.get("climbable")
                    tool = tool or p.get("tool")
                except Exception:
                    pass
            print(
                f"  id={d.get('id') or d.get('task_id') or d.get('step_id')} "
                f"status={d.get(status_col)} tool={tool!r} climbable={climbable!r} "
                f"title={str(title)[:90]!r}"
            )


if __name__ == "__main__":
    main()
