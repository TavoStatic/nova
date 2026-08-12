"""Why control still shows regression branch as blocked."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "runtime" / "_internal" / "work_tree.db"


def main() -> None:
    print("=== DB branch_4c126ff9 ===")
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    b = conn.execute(
        "SELECT status, resolution_state, open_stem_count, preferred_tool, notes FROM work_tree_branches WHERE branch_id=?",
        ("branch_4c126ff9",),
    ).fetchone()
    print(dict(b) if b else "missing")
    opens = conn.execute(
        "SELECT task_id, title, status FROM work_tree_tasks WHERE branch_id=? AND status NOT IN ('complete','dropped')",
        ("branch_4c126ff9",),
    ).fetchall()
    print("open tasks", [dict(x) for x in opens])

    print("\n=== other work_tree dbs ===")
    for p in ROOT.joinpath("runtime").rglob("work_tree*.db"):
        print(p, p.stat().st_size)

    import work_tree as wt

    wt.reload_persisted_state()
    branch = wt._BRANCHES.get("branch_4c126ff9")
    print("\n=== memory branch ===")
    if branch:
        print(branch.status, branch.resolution_state, branch.open_stem_count)
        opens_m = [
            t
            for t in wt._TASKS.values()
            if t.branch_id == "branch_4c126ff9" and t.status.value not in ("complete", "dropped")
        ]
        print("open mem", [(t.task_id, t.status.value, t.title) for t in opens_m])

    # control-facing summaries
    print("\n=== list_trees / pressure ===")
    try:
        from services.work_tree_pressure_snapshot import build_work_tree_pressure_snapshot

        snap = build_work_tree_pressure_snapshot()
        print(json.dumps(snap, indent=2, default=str)[:3000])
    except Exception as e:
        print("pressure fail", e)

    # branch summary used by control
    try:
        trees = wt.list_trees()
        for tree in trees:
            status = str(getattr(getattr(tree, "status", None), "value", tree.status) or "")
            if status != "active":
                continue
            print("tree", tree.tree_id, tree.title, status)
            for br in wt.list_tree_branches(tree.tree_id):
                st = str(getattr(getattr(br, "status", None), "value", br.status) or "")
                res = str(br.resolution_state or "")
                if "regression" in (br.title or "").lower() or st == "blocked" or res in ("open", "observing"):
                    print(" ", br.branch_id, st, res, br.open_stem_count, br.title[:80])
    except Exception as e:
        print("list fail", e)

    # status cache
    cache = ROOT / "runtime" / "control_status_cache.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
            print("\n=== control_status_cache work_tree fields ===")
            for k in sorted(payload.keys()):
                if "work_tree" in k:
                    print(k, ":", str(payload.get(k))[:200])
            # nested work tree truth
            for key in ("work_tree_truth", "work_tree", "work_tree_pressure"):
                if key in payload:
                    print(key, json.dumps(payload[key], default=str)[:1500])
        except Exception as e:
            print("cache read fail", e)
    else:
        print("no control_status_cache.json")

    # find any cache files
    for p in ROOT.joinpath("runtime").glob("*status*cache*"):
        print("cache file", p)


if __name__ == "__main__":
    main()
