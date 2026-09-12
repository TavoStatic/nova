import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree
from collections import Counter

TREE_ID = "tree_f7f132c4"
branches = work_tree.list_tree_branches(TREE_ID)
print("tree_id", TREE_ID)
print("branch_count", len(branches))
status_counts = Counter()
open_rows = []
for b in branches:
    status = str(getattr(getattr(b, "status", ""), "value", getattr(b, "status", "")) or "").lower()
    status_counts[status] += 1
    if status in {"open", "ready", "pending", "in_progress"}:
        open_rows.append(b)

print("status_counts", dict(status_counts))
print("open_like_count", len(open_rows))
for b in open_rows[:80]:
    status = str(getattr(getattr(b, "status", ""), "value", getattr(b, "status", "")) or "")
    print(getattr(b, "branch_id", ""), "|", status, "|", getattr(b, "title", ""))
