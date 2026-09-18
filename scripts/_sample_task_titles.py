import sqlite3
c = sqlite3.connect(r"runtime/_internal/work_tree.db")
rows = c.execute(
    """
    SELECT t.title, b.title, t.status
    FROM work_tree_tasks t
    JOIN work_tree_branches b ON b.branch_id = t.branch_id
    JOIN work_trees w ON w.tree_id = b.tree_id
    WHERE w.status = 'active'
    ORDER BY t.updated_at DESC
    LIMIT 12
    """
).fetchall()
for r in rows:
    print(f"[{r[2]}] {r[0]}")
    print(f"    branch: {r[1][:90]}")
