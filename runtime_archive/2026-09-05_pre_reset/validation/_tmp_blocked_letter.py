import json
import sqlite3
from pathlib import Path

p = Path(r"C:\nova\runtime\_internal\work_tree.db")
con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

for title in (
    "Operator outbox has open operator-control work",
    "Source wiring probe found missing source-derived paths",
):
    print("====", title)
    row = con.execute(
        """
        SELECT branch_id, status, resolution_state, preferred_tool,
               substr(ifnull(notes,''),1,1200) AS notes,
               substr(ifnull(source_payload_json,''),1,4000) AS payload
        FROM work_tree_branches
        WHERE title = ? AND status NOT IN ('archived')
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (title,),
    ).fetchone()
    if not row:
        print("missing")
        continue
    print({k: row[k] for k in row.keys() if k != "payload"})
    print("NOTES", row["notes"])
    print("PAYLOAD", row["payload"][:3500])
    print("TASKS")
    for task in con.execute(
        """
        SELECT title, status, substr(ifnull(meta_json,''),1,900) AS meta
        FROM work_tree_tasks WHERE branch_id = ? AND status NOT IN ('complete','dropped')
        """,
        (row["branch_id"],),
    ):
        print(dict(task))
    print()
