import sqlite3, json
from pathlib import Path
c = sqlite3.connect(r"runtime/_internal/work_tree.db")
c.row_factory = sqlite3.Row
print("evidence columns:", [r[1] for r in c.execute("pragma table_info(work_tree_evidence)")])
print("task columns sample:", [r[1] for r in c.execute("pragma table_info(work_tree_tasks)")])
opens = c.execute(
    """
    SELECT t.task_id, t.title, t.status, t.updated_at, t.created_at, t.meta_json,
           b.branch_id, b.title as branch, b.evidence_count, b.last_seen_at, b.resolution_state
    FROM work_tree_tasks t
    JOIN work_tree_branches b ON b.branch_id = t.branch_id
    JOIN work_trees w ON w.tree_id = b.tree_id
    WHERE w.status = 'active' AND t.status IN ('open','blocked','ready','in_progress')
    """
).fetchall()
print("open tasks", len(opens))
for t in opens:
    n = c.execute("SELECT COUNT(*) FROM work_tree_evidence WHERE task_id=?", (t["task_id"],)).fetchone()[0]
    print(f"  {t['status']} ev={n} branch_ev={t['evidence_count']} | {t['title'][:70]}")
    print(f"    created={t['created_at']} updated={t['updated_at']} last_seen={t['last_seen_at']}")
    meta = json.loads(t["meta_json"] or "{}")
    for k in ("expected_tool","allowed_tools","recurring_finding_satisfaction_status","recurring_finding_key"):
        if k in meta:
            print(f"    {k}={meta[k]}")
    evs = c.execute(
        "SELECT tool_name, created_at, substr(result_text,1,100) FROM work_tree_evidence WHERE task_id=? ORDER BY created_at",
        (t["task_id"],),
    ).fetchall()
    for e in evs:
        print(f"    evidence: {e[0]} @ {e[1]} :: {e[2]!r}")
# recent completed with evidence
print("\nrecent completed tasks with evidence (5):")
for t in c.execute(
    """
    SELECT t.task_id, t.title, t.updated_at,
      (SELECT COUNT(*) FROM work_tree_evidence e WHERE e.task_id=t.task_id) n
    FROM work_tree_tasks t
    WHERE t.status='complete'
    ORDER BY t.updated_at DESC LIMIT 5
    """
):
    print(f"  n={t[3]} {t[2]} {t[1][:60]}")
