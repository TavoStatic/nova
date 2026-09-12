"""Scan every non-archived tree the Scheduled Tree GET would see.

Load once (persisted). Record branch/task/resolution facts.
Run the same refresh the GET uses (persist=False).
Diff what flipped. Do not interpret yet.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import work_tree


def _st(val) -> str:
    return str(getattr(val, "value", val) or "")


def _closed_task(status: str) -> bool:
    return status in {"complete", "dropped"}


def snapshot_tree(tree_id: str) -> dict:
    tree = work_tree.get_tree(tree_id)
    branches = list(work_tree.list_tree_branches(tree_id))
    meta = tree.meta if isinstance(getattr(tree, "meta", None), dict) else {}
    branch_rows = []
    status_c = Counter()
    res_c = Counter()
    ready_blocked = 0
    open_stems = 0
    open_tasks = 0
    complete_tasks = 0
    unresolved_with_work = 0
    blocked_by_n = 0
    for b in branches:
        tasks = list(work_tree.list_branch_tasks(b.branch_id))
        st = _st(b.status)
        res = str(b.resolution_state or "") or "(none)"
        status_c[st] += 1
        res_c[res] += 1
        opens = [t for t in tasks if not _closed_task(_st(t.status))]
        closed = [t for t in tasks if _closed_task(_st(t.status))]
        open_stems += int(b.open_stem_count or 0)
        open_tasks += len(opens)
        complete_tasks += len(closed)
        if list(b.blocked_by or []):
            blocked_by_n += 1
        if st in {"ready", "blocked", "active"}:
            ready_blocked += 1
        had_work = bool(closed)
        unresolved = res not in {"resolved", "retired"}
        if had_work and unresolved and st != "archived":
            unresolved_with_work += 1
        if st in {"ready", "blocked", "active"} or (had_work and unresolved and st == "complete"):
            branch_rows.append(
                {
                    "id": b.branch_id,
                    "status": st,
                    "open_stem": int(b.open_stem_count or 0),
                    "resolution": res,
                    "depends_on": list(b.depends_on or []),
                    "blocked_by": list(b.blocked_by or []),
                    "tasks": len(tasks),
                    "open_tasks": len(opens),
                    "closed_tasks": len(closed),
                    "source_type": str(b.source_type or ""),
                    "title": str(b.title or "")[:90],
                }
            )
    try:
        complete_fn = work_tree.is_tree_complete(tree_id)
    except Exception as exc:
        complete_fn = f"err:{exc}"
    return {
        "tree_id": tree_id,
        "title": str(tree.title or "")[:90],
        "tree_status": _st(tree.status),
        "kind": str(meta.get("kind") or ""),
        "source": str(meta.get("source") or ""),
        "is_tree_complete": complete_fn,
        "branch_n": len(branches),
        "status_counts": dict(status_c),
        "resolution_counts": dict(res_c),
        "ready_blocked_active": ready_blocked,
        "open_stems": open_stems,
        "open_tasks": open_tasks,
        "closed_tasks": complete_tasks,
        "unresolved_with_work": unresolved_with_work,
        "branches_with_blocked_by": blocked_by_n,
        "interest_branches": branch_rows,
    }


def main() -> None:
    work_tree.reload_persisted_state()
    trees = [
        t
        for t in work_tree.list_trees()
        if _st(t.status) != "archived"
    ]
    trees.sort(key=lambda t: str(t.title))
    print("NON_ARCHIVED", len(trees))
    before = []
    for t in trees:
        before.append(snapshot_tree(t.tree_id))

    print("\n===== AFTER LOAD (persisted, no GET refresh) =====")
    for row in before:
        print(
            json.dumps(
                {
                    k: row[k]
                    for k in (
                        "tree_id",
                        "title",
                        "tree_status",
                        "kind",
                        "source",
                        "is_tree_complete",
                        "status_counts",
                        "resolution_counts",
                        "ready_blocked_active",
                        "open_stems",
                        "open_tasks",
                        "unresolved_with_work",
                        "branches_with_blocked_by",
                    )
                },
                sort_keys=False,
            )
        )

    after = []
    for t in trees:
        work_tree._refresh_tree_state(t.tree_id, persist=False)
        after.append(snapshot_tree(t.tree_id))

    print("\n===== AFTER GET-STYLE REFRESH persist=False =====")
    flips = []
    for b, a in zip(before, after):
        delta = {
            "tree_id": a["tree_id"],
            "title": a["title"],
            "tree_status": f"{b['tree_status']} -> {a['tree_status']}",
            "is_tree_complete": f"{b['is_tree_complete']} -> {a['is_tree_complete']}",
            "status_counts": f"{b['status_counts']} -> {a['status_counts']}",
            "ready_blocked_active": f"{b['ready_blocked_active']} -> {a['ready_blocked_active']}",
        }
        changed = (
            b["tree_status"] != a["tree_status"]
            or b["status_counts"] != a["status_counts"]
            or b["ready_blocked_active"] != a["ready_blocked_active"]
            or b["is_tree_complete"] != a["is_tree_complete"]
        )
        print(json.dumps(delta))
        if changed:
            flips.append(a["tree_id"])
            print("  INTEREST after:")
            for br in a["interest_branches"]:
                print("   ", json.dumps(br))

    print("\n===== FLIPPED TREE IDS =====")
    print(flips)

    print("\n===== HISTOGRAM AFTER REFRESH (what Working now would sum) =====")
    hist = Counter()
    for a in after:
        for st, n in a["status_counts"].items():
            hist[st] += n
    print(dict(hist))
    print(
        "working/active",
        hist.get("active", 0),
        "pending/ready",
        hist.get("ready", 0),
        "blocked",
        hist.get("blocked", 0),
        "complete",
        hist.get("complete", 0),
    )


if __name__ == "__main__":
    main()
