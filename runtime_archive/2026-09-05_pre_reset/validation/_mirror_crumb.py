import json
import sqlite3
from collections import Counter

con = sqlite3.connect("runtime/_internal/work_tree.db")
con.row_factory = sqlite3.Row
rows = list(
    con.execute(
        """
        SELECT branch_id, title, status, resolution_state, source_payload_json, evidence_count, work_class
        FROM work_tree_branches
        WHERE title LIKE '%HTTP%'
           OR title LIKE '%extraction%'
           OR title LIKE '%pipeline lane%'
           OR title LIKE '%thinning%'
        """
    )
)
print("extract-like branches", len(rows))
ids = [row["branch_id"] for row in rows]
for row in rows:
    raw = row["source_payload_json"] or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    judgments = data.get("attempt_judgments") or []
    tools = Counter()
    for item in judgments:
        if isinstance(item, dict) and str(item.get("judgment") or "").lower() == "redundant":
            tool = str(item.get("tool") or "").lower()
            if tool:
                tools[tool] += 1
    print(
        row["branch_id"][:14],
        row["status"],
        row["resolution_state"],
        "ev",
        row["evidence_count"],
        str(row["title"])[:58],
        "j",
        len(judgments),
        dict(tools.most_common(3)),
    )

print("\nopen tasks on those branches")
if ids:
    placeholders = ",".join("?" for _ in ids)
    for row in con.execute(
        f"""
        SELECT branch_id, title, status
        FROM work_tree_tasks
        WHERE branch_id IN ({placeholders})
          AND status NOT IN ('complete', 'dropped')
        ORDER BY updated_at DESC
        LIMIT 25
        """,
        ids,
    ):
        print(dict(row))
con.close()
