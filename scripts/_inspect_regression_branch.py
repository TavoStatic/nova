"""Inspect Resolve regression/test failures branch state."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import work_tree as wt

DB = Path(__file__).resolve().parents[1] / "runtime" / "_internal" / "work_tree.db"


def main() -> None:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    print("=== DB: branches matching regression / source-root ===")
    rows = conn.execute(
        """
        SELECT branch_id, title, status, resolution_state, open_stem_count,
               preferred_tool, tool_state_json, notes, source_key, updated_at
        FROM work_tree_branches
        WHERE title LIKE '%regression%'
           OR title LIKE '%source-root%'
           OR source_key LIKE '%regression%'
        ORDER BY updated_at DESC
        LIMIT 20
        """
    ).fetchall()
    for r in rows:
        print("-" * 60)
        print(dict(r)["branch_id"], dict(r)["status"], dict(r)["resolution_state"], dict(r)["title"])
        print("  open_stem", r["open_stem_count"], "preferred", r["preferred_tool"], "updated", r["updated_at"])
        print("  source_key", r["source_key"])
        print("  notes", (r["notes"] or "")[:300])
        tasks = conn.execute(
            """
            SELECT task_id, title, status, updated_at, meta_json
            FROM work_tree_tasks
            WHERE branch_id = ?
            ORDER BY updated_at DESC
            """,
            (r["branch_id"],),
        ).fetchall()
        openish = [t for t in tasks if t["status"] in ("open", "blocked", "ready", "in_progress")]
        print("  tasks total", len(tasks), "openish", len(openish))
        for t in openish:
            print("   *", t["status"], t["task_id"], t["title"])
            print("     meta", (t["meta_json"] or "")[:350])
        # last few completed
        for t in tasks[:5]:
            if t["status"] not in ("open", "blocked", "ready", "in_progress"):
                print("   .", t["status"], t["task_id"], t["title"][:70], t["updated_at"])

    print("\n=== memory reload ===")
    wt.reload_persisted_state()
    for bid, b in wt._BRANCHES.items():
        if "Resolve regression" in (b.title or "") or "source-root" in (b.title or "").lower():
            opens = [
                t
                for t in wt._TASKS.values()
                if t.branch_id == bid and t.status.value in ("open", "blocked", "ready", "in_progress")
            ]
            print(bid, b.status.value, "res=", b.resolution_state, "title=", b.title, "open=", len(opens))
            for t in opens:
                print("  ", t.task_id, t.status.value, t.title, t.meta)

    # specifically task_a057bda6
    print("\n=== task_a057bda6 ===")
    t = conn.execute("SELECT * FROM work_tree_tasks WHERE task_id='task_a057bda6'").fetchone()
    if t:
        print(dict(t))
    else:
        print("not found")

    # any blocked tasks anywhere active tree
    print("\n=== all blocked/open on active trees ===")
    for r in conn.execute(
        """
        SELECT t.task_id, t.title, t.status, b.branch_id, b.title AS branch_title,
               b.status AS branch_status, b.resolution_state, w.title AS tree_title
        FROM work_tree_tasks t
        JOIN work_tree_branches b ON b.branch_id = t.branch_id
        JOIN work_trees w ON w.tree_id = b.tree_id
        WHERE w.status = 'active'
          AND t.status IN ('open', 'blocked', 'ready', 'in_progress')
        ORDER BY t.status, t.updated_at DESC
        """
    ):
        print(f"[{r['status']}] {r['title']}")
        print(f"  branch={r['branch_status']}/{r['resolution_state']} {r['branch_title']} ({r['branch_id']})")


if __name__ == "__main__":
    main()
