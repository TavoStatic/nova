import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree

for tree in work_tree.list_visual_trees(limit=20):
    tree_title = str(tree.get("title") or "")
    if tree_title != "Signal Intake: Runtime Governance":
        continue
    branches = tree.get("branches") or []
    executable = [b for b in branches if bool(b.get("executable", False))]
    open_like = [
        b
        for b in branches
        if str(b.get("status") or "").lower() in {"open", "ready", "pending", "in_progress"}
    ]
    print("tree", tree.get("tree_id", ""), tree_title)
    print("branches_total", len(branches))
    print("branches_open_like", len(open_like))
    print("branches_executable", len(executable))
    print("first_10_executable")
    for b in executable[:10]:
        print(b.get("branch_id", ""), "|", b.get("title", ""), "|", b.get("recommended_tool", ""), "|", b.get("task_id", ""))
    break
