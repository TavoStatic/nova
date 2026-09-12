import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree  # noqa: E402

SNAPSHOT_PATH = ROOT / "runtime" / "open_task_snapshot.json"

def normalize_status(value) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def collect_open_rows():
    rows = []
    for tree in work_tree.list_trees():
        for branch in work_tree.list_tree_branches(tree.tree_id):
            b_status = normalize_status(branch.status)
            if b_status in {"complete", "archived"}:
                continue
            for task in work_tree.list_branch_tasks(branch.branch_id):
                t_status = normalize_status(getattr(task, "status", ""))
                if t_status in {"complete", "dropped"}:
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

def recent_repeat_signal(branch_id: str, task_title: str, window: int = 40) -> int:
    tasks = work_tree.list_branch_tasks(branch_id)
    tasks_sorted = sorted(tasks, key=lambda t: str(getattr(t, "updated_at", "")), reverse=True)
    recent = tasks_sorted[:window]
    return sum(1 for t in recent if str(getattr(t, "title", "")) == task_title)

def load_prev_snapshot():
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

def save_snapshot(rows):
    payload = {
        "captured_at": now_utc_iso(),
        "rows": rows,
    }
    SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def main():
    rows = collect_open_rows()
    prev = load_prev_snapshot()

    by_id = {r["task_id"]: r for r in rows}
    by_branch = defaultdict(list)
    for r in rows:
        by_branch[r["branch_id"]].append(r)

    print("captured_at", now_utc_iso())
    print("total_open_tasks", len(rows))
    print("branches_with_open_tasks", len(by_branch))

    title_counts = Counter(r["task_title"] for r in rows)
    print("top_open_titles")
    for title, count in title_counts.most_common(10):
        print(count, "|", title)

    multi = [(bid, rs[0]["branch_title"], len(rs)) for bid, rs in by_branch.items() if len(rs) > 1]
    print("branches_with_multiple_open_tasks", len(multi))
    for bid, btitle, count in sorted(multi, key=lambda x: x[2], reverse=True)[:15]:
        print(count, "|", bid, "|", btitle)

    if prev and isinstance(prev, dict):
        prev_rows = prev.get("rows") or []
        prev_ids = {r.get("task_id") for r in prev_rows if isinstance(r, dict)}
        curr_ids = set(by_id)

        persisted = curr_ids & prev_ids
        new_ids = curr_ids - prev_ids
        closed_ids = prev_ids - curr_ids

        print("since_previous_snapshot")
        print("persisted_open_tasks", len(persisted))
        print("new_open_tasks", len(new_ids))
        print("closed_since_last", len(closed_ids))

        if new_ids:
            print("new_open_sample")
            for tid in list(new_ids)[:20]:
                row = by_id[tid]
                print(row["branch_id"], "|", tid, "|", row["task_title"])

    else:
        print("since_previous_snapshot")
        print("no_previous_snapshot")

    print("repeat_risk_check")
    risky = []
    for r in rows:
        repeats = recent_repeat_signal(r["branch_id"], r["task_title"], window=40)
        if repeats >= 6:
            risky.append((repeats, r["branch_id"], r["task_id"], r["task_title"]))

    print("high_repeat_risk_count", len(risky))
    for repeats, bid, tid, title in sorted(risky, reverse=True)[:20]:
        print(repeats, "|", bid, "|", tid, "|", title)

    save_snapshot(rows)
    print("snapshot_saved", str(SNAPSHOT_PATH))

if __name__ == "__main__":
    main()
