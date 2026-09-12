import sqlite3, json, re
from collections import Counter, defaultdict
c = sqlite3.connect(r"runtime/_internal/work_tree.db")
c.row_factory = sqlite3.Row
# families by work_class + source_type
rows = c.execute(
    """
    SELECT b.work_class, b.source_type, b.source_key, t.title, t.status, t.task_id, t.meta_json,
           b.branch_id, b.title as branch_title
    FROM work_tree_tasks t
    JOIN work_tree_branches b ON b.branch_id = t.branch_id
    WHERE t.status = 'complete'
    ORDER BY t.updated_at DESC
    LIMIT 800
    """
).fetchall()
print("complete sample", len(rows))
by = Counter()
for r in rows:
    by[(r["work_class"] or "?", r["source_type"] or "?")] += 1
print("top families:")
for k,v in by.most_common(15):
    print(f"  {v:4d}  {k}")
# evidence tool sequences for top families
for fam in by.most_common(5):
    wc, st = fam[0]
    print("\n===", wc, st, "===")
    seq_counter = Counter()
    for r in rows:
        if (r["work_class"] or "?") != wc or (r["source_type"] or "?") != st:
            continue
        tools = [x[0] for x in c.execute(
            "SELECT tool_name FROM work_tree_evidence WHERE task_id=? ORDER BY created_at",
            (r["task_id"],),
        )]
        if tools:
            seq_counter[tuple(tools[:6])] += 1
    for seq, n in seq_counter.most_common(8):
        print(f"  {n:3d}  {' -> '.join(seq)}")
