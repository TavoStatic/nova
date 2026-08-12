"""Simulate live orchestrator decision with current code + runtime state."""
from __future__ import annotations

import json
from pathlib import Path

import autonomy_maintenance as am
from services.nova_mission import NovaMissionService


def main() -> None:
    state = am._load_state()
    kidney = dict(state.get("last_kidney_status") or {})
    work_tree_state = am.CONTROL_WORK_TREES_SERVICE.payload(
        list_visual_trees_fn=am.work_tree.list_visual_trees,
        limit=64,
    )
    generated_queue = am._generated_work_queue(limit=200)
    guard_health = am._guard_health_for_orchestrator()
    core_steward = am._core_steward_for_orchestrator(
        state, kidney, guard_health=guard_health
    )
    candidates = am._active_work_tree_candidates(am.ACTIVE_WORK_TREE_MAX_TREES)
    print("candidates", len(candidates))
    for c in candidates[:10]:
        print(
            {
                "title": str(c.get("title") or c.get("branch_title") or "")[:80],
                "tool": c.get("recommended_tool") or c.get("tool"),
                "tree": c.get("tree_id"),
                "branch": c.get("branch_id"),
                "task": c.get("task_id"),
                "executable": am._active_work_candidate_is_executable(c),
                "tool_status": c.get("tool_status"),
                "path": c.get("path") or (c.get("tool_args") or {}).get("path")
                if isinstance(c.get("tool_args"), dict)
                else c.get("path"),
            }
        )

    policy = am._policy_snapshot_for_orchestrator()
    envelope = am._autonomy_orchestrator_input_envelope(
        state=state,
        core_steward=core_steward,
        work_tree_state=work_tree_state,
        generated_queue=generated_queue,
        guard_health=guard_health,
        active_work_candidates=candidates,
        latest_report=am._latest_subconscious_report_for_triage(),
        kidney_summary=kidney,
        policy_snapshot=policy,
    )
    wt = envelope["work_tree_snapshot"]
    m = envelope["mission_snapshot"]
    print(
        "snapshot",
        {
            "active_candidate_count": wt.get("active_candidate_count"),
            "active_executable_count": wt.get("active_executable_count"),
            "open_count": wt.get("open_count"),
            "branches": len(wt.get("branches") or []),
        },
    )
    print(
        "mission",
        {
            k: m.get(k)
            for k in [
                "status",
                "action",
                "green_cycle",
                "regression_current",
                "truth_blockers",
                "active_work_evidence_current",
            ]
        },
    )
    print("pillars", NovaMissionService._base_evidence_pillars_current(m))
    for b in list(wt.get("branches") or [])[:8]:
        tool = b.get("recommended_tool") or ""
        blocked = NovaMissionService.hold_blocks_action(
            "active_work_tree_run_next",
            mission_snapshot=m,
            action_context=b,
        )
        print(
            "branch_hold",
            {
                "title": str(b.get("title") or "")[:70],
                "tool": tool,
                "executable": b.get("executable"),
                "blocks": blocked,
                "allow": NovaMissionService._hold_allows_active_work_tool(
                    m, str(tool), action_context=b
                )
                if tool
                else None,
            },
        )

    am.AUTONOMY_ORCHESTRATOR_SERVICE.set_mode(
        "execute" if policy.get("execute_enabled") else "advisory", policy
    )
    packet = am.AUTONOMY_ORCHESTRATOR_SERVICE.evaluate_next_action(envelope)
    print(
        "decision",
        {
            "decision_type": packet.get("decision_type"),
            "decision": packet.get("decision"),
            "reason": packet.get("reason") or packet.get("explain_text"),
            "rejection_reasons": packet.get("rejection_reasons"),
            "recommended_action": packet.get("recommended_action"),
            "confidence": packet.get("confidence"),
        },
    )
    # candidates considered from ledger if present
    ledger = packet.get("ledger") or {}
    row = ledger.get("row") or {}
    considered = packet.get("candidates_considered") or row.get("candidates_considered") or []
    print("considered_count", len(considered) if isinstance(considered, list) else type(considered))
    if isinstance(considered, list):
        for item in considered[:8]:
            action = (item or {}).get("action") or {}
            print(
                {
                    "action": action.get("action_type"),
                    "tool": action.get("recommended_tool"),
                    "reject": item.get("reject_reasons"),
                    "score": item.get("score"),
                    "status": item.get("status"),
                }
            )


if __name__ == "__main__":
    main()
