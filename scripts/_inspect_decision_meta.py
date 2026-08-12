import json
import sqlite3
from collections import Counter
from pathlib import Path

con = sqlite3.connect(str(Path("runtime/_internal/work_tree.db")))
con.row_factory = sqlite3.Row
rows = con.execute(
    "select task_id, title, meta_json from work_tree_tasks "
    "where meta_json like '%decision_%' limit 80"
).fetchall()
keys: Counter[str] = Counter()
hits = 0
for r in rows:
    m = json.loads(r["meta_json"] or "{}")
    for k in m:
        if "decision" in k.lower() or "judge" in k.lower() or "episode" in k.lower():
            keys[k] += 1
    if any(
        x in m
        for x in (
            "last_decision_episode",
            "decision_judge",
            "decision_episodes",
            "decision_proposal",
        )
    ):
        hits += 1
        print("HIT", r["task_id"], (r["title"] or "")[:60], sorted(m.keys())[:20])

print("rows_scanned", len(rows), "judge_hits", hits)
print("meta_keys_with_decisionish", dict(keys))
if rows:
    m = json.loads(rows[0]["meta_json"] or "{}")
    print("sample_keys", list(m.keys())[:40])
    for k, v in m.items():
        if "decision" in k.lower():
            print(" ", k, type(v).__name__, str(v)[:120])
