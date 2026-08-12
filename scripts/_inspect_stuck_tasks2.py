from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "runtime" / "_internal" / "work_tree.db"


def main() -> None:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    print("=== task status counts (active tree branches) ===")
    # join tasks to branches on active trees
    rows = con.execute(
        """
        SELECT t.status AS tstatus, b.status AS bstatus, COUNT(*) AS n
        FROM work_tree_tasks t
        JOIN work_tree_branches b ON b.branch_id = t.branch_id
        JOIN work_trees tr ON tr.tree_id = b.tree_id
        WHERE tr.status = 'active'
        GROUP BY t.status, b.status
        ORDER BY n DESC
        """
    ).fetchall()
    for r in rows:
        print(dict(r))

    print("\n=== OPEN/BLOCKED tasks on active trees ===")
    tasks = con.execute(
        """
        SELECT t.task_id, t.title, t.status, t.updated_at, t.meta_json,
               b.branch_id, b.title AS branch_title, b.status AS branch_status,
               tr.tree_id, tr.title AS tree_title
        FROM work_tree_tasks t
        JOIN work_tree_branches b ON b.branch_id = t.branch_id
        JOIN work_trees tr ON tr.tree_id = b.tree_id
        WHERE tr.status = 'active'
          AND t.status IN ('open', 'blocked', 'ready', 'in_progress', 'held')
        ORDER BY t.updated_at DESC
        LIMIT 40
        """
    ).fetchall()
    for t in tasks:
        meta = {}
        try:
            meta = json.loads(t["meta_json"] or "{}")
        except Exception:
            meta = {}
        print("---")
        print("task:", t["task_id"], t["status"])
        print("title:", t["title"])
        print("branch:", t["branch_status"], t["branch_title"])
        print("tree:", t["tree_title"])
        print("updated:", t["updated_at"])
        interesting = {
            k: meta.get(k)
            for k in (
                "hold_reason",
                "blocked_reason",
                "reason",
                "source",
                "allowed_tools",
                "preferred_tool",
                "next_task",
                "signal_class",
                "error",
                "symbol",
            )
            if meta.get(k) not in (None, "", [], {})
        }
        if interesting:
            print("meta:", json.dumps(interesting, default=str)[:500])

    print("\n=== READY branches with open tasks ===")
    ready = con.execute(
        """
        SELECT b.branch_id, b.title, b.status, COUNT(t.task_id) AS open_tasks
        FROM work_tree_branches b
        JOIN work_trees tr ON tr.tree_id = b.tree_id
        LEFT JOIN work_tree_tasks t
          ON t.branch_id = b.branch_id AND t.status IN ('open','blocked','ready','in_progress')
        WHERE tr.status='active' AND b.status IN ('ready','active','blocked','open')
        GROUP BY b.branch_id
        HAVING open_tasks > 0
        ORDER BY open_tasks DESC
        """
    ).fetchall()
    for r in ready:
        print(dict(r))

    # operator outbox last lines
    outbox = ROOT / "runtime" / "operator_outbox.jsonl"
    if outbox.is_file():
        print("\n=== operator outbox last open-ish ===")
        lines = outbox.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-15:]:
            try:
                o = json.loads(line)
            except Exception:
                continue
            if str(o.get("status") or "").lower() in {"open", "pending", "waiting", ""} or o.get(
                "audience"
            ):
                print(
                    json.dumps(
                        {
                            "status": o.get("status"),
                            "message": str(o.get("message") or "")[:160],
                            "dedupe_key": str(o.get("dedupe_key") or "")[:80],
                            "id": o.get("id"),
                        },
                        default=str,
                    )
                )

    auto = ROOT / "runtime" / "autonomy_maintenance_state.json"
    if auto.is_file():
        a = json.loads(auto.read_text(encoding="utf-8"))
        print("\n=== last_autonomy_orchestrator ===")
        print(json.dumps(a.get("last_autonomy_orchestrator"), indent=2, default=str)[:2500])
        print("\n=== last_active_work_tree_cycle ===")
        print(json.dumps(a.get("last_active_work_tree_cycle"), indent=2, default=str)[:1500])
        print("\n=== last_error ===")
        print(json.dumps(a.get("last_error"), indent=2, default=str)[:800])
        print("\n=== last_autonomy_execution_gate ===")
        print(json.dumps(a.get("last_autonomy_execution_gate"), indent=2, default=str)[:1500])


if __name__ == "__main__":
    main()
