"""Inspect open release-ladder branch tool context for hold allow."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from services.nova_mission import NovaMissionService


def main() -> None:
    st = json.loads(Path("runtime/autonomy_maintenance_state.json").read_text(encoding="utf-8"))
    m = st.get("last_nova_mission") or {}
    con = sqlite3.connect("runtime/_internal/work_tree.db")
    con.row_factory = sqlite3.Row
    branches = con.execute(
        "select * from work_tree_branches where lower(status) not in "
        "('done','complete','completed','closed','archived','resolved') limit 20"
    ).fetchall()
    for b in branches:
        d = dict(b)
        print("BRANCH", {k: d.get(k) for k in [
            "branch_id", "tree_id", "title", "status", "preferred_tool",
            "work_class", "actionability", "open_stem_count", "bucket",
        ]})
        print("  allowed", d.get("allowed_tools_json"))
        print("  required", d.get("required_tools_json"))
        print("  tool_state", (d.get("tool_state_json") or "")[:300])
        print("  source", (d.get("source_payload_json") or "")[:400])
        tasks = con.execute(
            "select task_id, title, status, meta_json from work_tree_tasks "
            "where branch_id=? and lower(status) in ('open','ready','in_progress','blocked')",
            (d.get("branch_id"),),
        ).fetchall()
        for t in tasks:
            td = dict(t)
            meta = {}
            raw = td.get("meta_json") or ""
            if isinstance(raw, str) and raw.startswith("{"):
                try:
                    meta = json.loads(raw)
                except Exception:
                    meta = {}
            print("  TASK", {
                "id": td.get("task_id"),
                "title": td.get("title"),
                "status": td.get("status"),
                "tool": meta.get("tool") or meta.get("recommended_tool"),
                "path": meta.get("path"),
                "climbable": meta.get("climbable"),
                "meta_keys": list(meta.keys())[:20],
            })
            ctx = {
                **meta,
                "title": td.get("title") or d.get("title"),
                "recommended_tool": meta.get("tool") or meta.get("recommended_tool") or d.get("preferred_tool"),
                "tool": meta.get("tool") or d.get("preferred_tool"),
                "branch_id": d.get("branch_id"),
            }
            tool = str(ctx.get("recommended_tool") or "")
            if tool:
                print(
                    "    hold",
                    {
                        "tool": tool,
                        "allow": NovaMissionService._hold_allows_active_work_tool(
                            m, tool, action_context=ctx
                        ),
                        "blocks": NovaMissionService.hold_blocks_action(
                            "active_work_tree_run_next",
                            mission_snapshot=m,
                            action_context=ctx,
                        ),
                        "ctx_ok": NovaMissionService._release_ladder_hold_context_ok(ctx),
                    },
                )


if __name__ == "__main__":
    main()
