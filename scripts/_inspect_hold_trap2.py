"""Continue hold-trap dig: hold allow + work tree open steps."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from services.nova_mission import NovaMissionService


def main() -> None:
    st = json.loads(Path("runtime/autonomy_maintenance_state.json").read_text(encoding="utf-8"))
    m = None
    for k, v in st.items():
        if isinstance(v, dict) and "green_cycle" in v and "truth_blockers" in v:
            m = v
            print("mission_key", k)
            break
    if m is None:
        m = st["last_autonomy_orchestrator"]["mission_snapshot"]

    print(
        "flags",
        {
            "green_cycle": m.get("green_cycle"),
            "regression_current": m.get("regression_current"),
            "regression_passed": m.get("regression_passed"),
            "aw_ev": m.get("active_work_evidence_current"),
            "pillars": NovaMissionService._base_evidence_pillars_current(m),
            "truth_blockers": m.get("truth_blockers"),
            "owner_blockers": m.get("owner_blockers"),
        },
    )
    for tool, title in [
        ("read", "Read release ledger validation outcome is missing"),
        ("release_rebuild_verify", "release rebuild verify"),
        ("core_thinning", "core thinning"),
        ("ls", "List release package paths"),
    ]:
        ctx = {
            "tool": tool,
            "recommended_tool": tool,
            "title": title,
            "path": "docs/RELEASE.md",
            "reason": "release validation",
        }
        print(
            tool,
            {
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

    con = sqlite3.connect("runtime/_internal/work_tree.db")
    con.row_factory = sqlite3.Row
    tables = [
        r[0]
        for r in con.execute(
            "select name from sqlite_master where type='table' order by name"
        )
    ]
    print("tables", tables)
    for table in tables:
        cols = [r[1] for r in con.execute(f"pragma table_info({table})")]
        n = con.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"  {table}: {n} {cols}")

    # Prefer steps/tasks tables
    for table in tables:
        cols = {r[1] for r in con.execute(f"pragma table_info({table})")}
        if not ({"status", "title"} & cols):
            continue
        status_col = "status" if "status" in cols else None
        if not status_col:
            continue
        q = (
            f"select * from {table} where lower(coalesce({status_col},'')) "
            f"not in ('done','complete','completed','closed','archived','resolved','ok','cancelled') "
            f"order by rowid desc limit 50"
        )
        rows = con.execute(q).fetchall()
        print(f"openish {table}: {len(rows)}")
        for row in rows[:30]:
            d = dict(row)
            payload_raw = d.get("payload") or d.get("meta") or d.get("data") or ""
            p = {}
            if isinstance(payload_raw, str) and payload_raw.startswith("{"):
                try:
                    p = json.loads(payload_raw)
                except Exception:
                    p = {}
            print(
                {
                    "id": d.get("id") or d.get("task_id") or d.get("step_id"),
                    "status": d.get(status_col),
                    "tool": d.get("tool") or p.get("tool"),
                    "climbable": p.get("climbable"),
                    "title": str(d.get("title") or "")[:100],
                    "tree": d.get("tree_id") or d.get("work_tree_id") or p.get("work_tree_id"),
                }
            )

    # Last active work cycle
    print("last_active_work", st.get("last_active_work_tree_cycle"))
    print("last_work_tree", st.get("last_work_tree_cycle"))


if __name__ == "__main__":
    main()
