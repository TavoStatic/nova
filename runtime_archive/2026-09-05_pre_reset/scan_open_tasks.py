import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree
from collections import Counter, defaultdict


def open_task_rows():
    rows = []
    for tree in work_tree.list_trees():
        for branch in work_tree.list_tree_branches(tree.tree_id):
            branch_status = str(getattr(branch.status, "value", branch.status) or "").lower()
            if branch_status in {"complete", "archived"}:
                continue
            for task in work_tree.list_branch_tasks(branch.branch_id):
                task_status = str(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")) or "").lower()
                if task_status in {"complete", "dropped"}:
                    continue
                rows.append(
                    {
                        "branch_id": branch.branch_id,
                        "branch_title": branch.title,
                        "task_id": task.task_id,
                        "task_title": task.title,
                        "updated_at": str(getattr(task, "updated_at", "")),
                    }
                )
    return rows


def main() -> None:
    rows = open_task_rows()
    print("total_open_tasks", len(rows))
    print("branches_with_open_tasks", len({r["branch_id"] for r in rows}))

    title_counts = Counter(r["task_title"] for r in rows)
    print("top_open_task_titles")
    for title, count in title_counts.most_common(10):
        print(count, title)

    by_branch = defaultdict(list)
    for row in rows:
        by_branch[row["branch_id"]].append(row)

    multi = [
        (bid, branch_rows[0]["branch_title"], len(branch_rows))
        for bid, branch_rows in by_branch.items()
        if len(branch_rows) > 1
    ]
    print("branches_with_multiple_open_tasks", len(multi))
    for bid, btitle, count in sorted(multi, key=lambda x: x[2], reverse=True)[:20]:
        print(count, bid, btitle)

    print("latest_open_rows")
    for row in sorted(rows, key=lambda x: x["updated_at"], reverse=True)[:30]:
        print(row["branch_id"], row["task_id"], row["task_title"])


if __name__ == "__main__":
    main()
