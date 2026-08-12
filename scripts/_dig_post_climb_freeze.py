"""Why climb stopped after release ladder + quiet hold defer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from services.nova_mission import NovaMissionService
import autonomy_maintenance as am

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    st = json.loads((ROOT / "runtime/autonomy_maintenance_state.json").read_text(encoding="utf-8"))
    mission = dict(st.get("last_nova_mission") or {})
    print("mission status/action/green", mission.get("status"), mission.get("action"), mission.get("green_cycle"))
    print("owner_blockers", mission.get("owner_blockers"))
    print("truth_blockers", mission.get("truth_blockers"))

    # Hold matrix for release tools + active work
    tools = [
        "read",
        "release_rebuild_verify",
        "release_validation_run",
        "release_record_validation_outcome",
        "release_promotion_judgment",
        "core_thinning",
    ]
    print("\n=== hold_blocks active_work_tree_run_next ===")
    for tool in tools:
        ctx = {
            "tool": tool,
            "recommended_tool": tool,
            "title": "Release package is stale behind live source",
            "path": "runtime/exports/release_packages/release_ledger.jsonl",
        }
        blocked = NovaMissionService.hold_blocks_action(
            "active_work_tree_run_next",
            mission_snapshot=mission,
            action_context=ctx,
        )
        allow = NovaMissionService._hold_allows_active_work_tool(
            mission, tool, action_context=ctx
        )
        print(f"  {tool}: blocks={blocked} allow={allow}")

    print(
        "\nblocks no context",
        NovaMissionService.hold_blocks_action(
            "active_work_tree_run_next", mission_snapshot=mission
        ),
    )
    print("pillars", NovaMissionService._base_evidence_pillars_current(mission))
    print("aw_ev", NovaMissionService.active_work_evidence_current(mission))

    # Active work candidates
    cands = am._active_work_tree_candidates(am.ACTIVE_WORK_TREE_MAX_TREES)
    print("\n=== active_work_candidates", len(cands), "===")
    for c in cands[:12]:
        ns = c.get("next_step") if isinstance(c.get("next_step"), dict) else {}
        exe = am._active_work_candidate_is_executable(c)
        print(
            {
                "tree": c.get("tree_id"),
                "title": str(c.get("title") or "")[:50],
                "tool": ns.get("recommended_tool"),
                "branch": ns.get("branch_id"),
                "task": ns.get("task_id"),
                "task_title": str(ns.get("task_title") or "")[:50],
                "executable": exe,
                "tool_status": am._active_work_candidate_next_tool_status(c),
            }
        )

    # Work tree open release tasks
    con = sqlite3.connect(str(ROOT / "runtime/_internal/work_tree.db"))
    con.row_factory = sqlite3.Row
    print("\n=== open/blocked tasks ===")
    rows = con.execute(
        "select task_id, branch_id, title, status, updated_at from work_tree_tasks "
        "where lower(status) in ('open','ready','in_progress','blocked') "
        "order by updated_at desc limit 30"
    ).fetchall()
    for r in rows:
        print(r["status"], r["task_id"], r["branch_id"], (r["title"] or "")[:70], r["updated_at"])

    # Release-ish branches
    print("\n=== ready/open release branches ===")
    br = con.execute(
        "select branch_id, title, status, preferred_tool, open_stem_count, updated_at, "
        "work_class, actionability, resolution_state "
        "from work_tree_branches "
        "where lower(status) not in ('done','complete','completed','closed','archived') "
        "order by updated_at desc limit 20"
    ).fetchall()
    for r in br:
        print(
            r["status"],
            r["branch_id"],
            (r["title"] or "")[:60],
            "tool=",
            r["preferred_tool"],
            "stems=",
            r["open_stem_count"],
            r["work_class"],
            r["updated_at"],
        )

    # Full envelope sim
    print("\n=== live orchestrator evaluate ===")
    kidney = dict(st.get("last_kidney_status") or {})
    work_tree_state = am.CONTROL_WORK_TREES_SERVICE.payload(
        list_visual_trees_fn=am.work_tree.list_visual_trees,
        limit=64,
    )
    generated_queue = am._generated_work_queue(limit=200)
    guard_health = am._guard_health_for_orchestrator()
    core_steward = am._core_steward_for_orchestrator(st, kidney, guard_health=guard_health)
    policy = am._policy_snapshot_for_orchestrator()
    envelope = am._autonomy_orchestrator_input_envelope(
        state=st,
        core_steward=core_steward,
        work_tree_state=work_tree_state,
        generated_queue=generated_queue,
        guard_health=guard_health,
        active_work_candidates=cands,
        latest_report=am._latest_subconscious_report_for_triage(),
        kidney_summary=kidney,
        policy_snapshot=policy,
    )
    wt = envelope["work_tree_snapshot"]
    print(
        "snapshot",
        {
            "active_candidate_count": wt.get("active_candidate_count"),
            "active_executable_count": wt.get("active_executable_count"),
            "open_count": wt.get("open_count"),
            "operator_hold": wt.get("operator_hold_count"),
            "branches": len(wt.get("branches") or []),
        },
    )
    for b in list(wt.get("branches") or [])[:8]:
        tool = b.get("recommended_tool") or ""
        blocked = NovaMissionService.hold_blocks_action(
            "active_work_tree_run_next",
            mission_snapshot=envelope["mission_snapshot"],
            action_context=b,
        )
        print(
            " branch",
            str(b.get("title") or "")[:50],
            "tool",
            tool,
            "exec",
            b.get("executable"),
            "blocks",
            blocked,
            "climb",
            b.get("climbable"),
            "motion",
            b.get("progress_motion"),
        )

    am.AUTONOMY_ORCHESTRATOR_SERVICE.set_mode(
        "execute" if policy.get("execute_enabled") else "advisory", policy
    )
    packet = am.AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_next_action(envelope)
    print(
        "\ndecision",
        packet.get("decision_type"),
        packet.get("reason") or packet.get("explain_text"),
    )
    print("rejection", packet.get("rejection_reasons"))
    print("recommended", packet.get("recommended_action"))
    considered = packet.get("candidates_considered") or []
    if not considered:
        ledger = packet.get("ledger") or {}
        row = ledger.get("row") or {}
        considered = row.get("candidates_considered") or []
    print("considered", len(considered) if isinstance(considered, list) else type(considered))
    if isinstance(considered, list):
        for item in considered[:10]:
            a = (item or {}).get("action") or {}
            print(
                {
                    "action": a.get("action_type"),
                    "tool": a.get("recommended_tool"),
                    "reject": item.get("reject_reasons"),
                    "score": item.get("score"),
                    "status": item.get("status"),
                }
            )


if __name__ == "__main__":
    main()
