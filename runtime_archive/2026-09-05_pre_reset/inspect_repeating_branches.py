import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree

TARGET_TITLES = {
    "Read source root inventory catalog",
    "Read release ledger for current package",
}

for tree in work_tree.list_trees():
    for branch in work_tree.list_tree_branches(tree.tree_id):
        bstatus = str(getattr(getattr(branch, "status", ""), "value", getattr(branch, "status", "")) or "").lower()
        if bstatus in {"complete", "archived"}:
            continue
        open_tasks = []
        for task in work_tree.list_branch_tasks(branch.branch_id):
            tstatus = str(getattr(getattr(task, "status", ""), "value", getattr(task, "status", "")) or "").lower()
            if tstatus in {"complete", "dropped"}:
                continue
            if str(getattr(task, "title", "")) in TARGET_TITLES:
                open_tasks.append(task)
        if not open_tasks:
            continue

        print("=" * 90)
        print("branch", branch.branch_id, "|", branch.title)
        for task in open_tasks:
            print("OPEN", task.task_id, "|", task.title, "|", getattr(task, "updated_at", ""))

        all_tasks = [t for t in work_tree.list_branch_tasks(branch.branch_id) if str(getattr(t, "title", "")) in TARGET_TITLES]
        all_tasks_sorted = sorted(all_tasks, key=lambda t: str(getattr(t, "updated_at", "")), reverse=True)
        print("recent_same_title_tasks", len(all_tasks_sorted))
        for t in all_tasks_sorted[:8]:
            tstatus = str(getattr(getattr(t, "status", ""), "value", getattr(t, "status", "")) or "")
            print("  ", t.task_id, "|", tstatus, "|", t.title, "|", getattr(t, "updated_at", ""))

        ev = work_tree.list_branch_evidence(branch.branch_id, limit=60)
        print("recent_evidence_count", len(ev))
        for row in ev[:12]:
            txt = str(row.get("result_text") or "").replace("\n", " ")
            if len(txt) > 180:
                txt = txt[:180] + "..."
            print(
                "  EV",
                row.get("created_at", ""),
                "|",
                row.get("task_id", ""),
                "|",
                row.get("tool_name", ""),
                "|",
                txt,
            )
