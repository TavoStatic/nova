from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    snap = ROOT / "runtime" / "open_task_snapshot.json"
    if snap.is_file():
        print("=== open_task_snapshot ===")
        data = json.loads(snap.read_text(encoding="utf-8"))
        print(json.dumps(data, indent=2, default=str)[:5000])
        print()

    db = ROOT / "runtime" / "_internal" / "work_tree.db"
    if not db.is_file():
        print("no work_tree.db")
        return
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    print("=== tables ===")
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")]
    for t in tables:
        print(t)
    print()

    # Heuristic: find task-like tables
    for t in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        colset = {c.lower() for c in cols}
        if not ({"status", "state", "title", "name"} & colset):
            continue
        print(f"=== sample {t} cols={cols[:12]} ===")
        try:
            rows = con.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 30").fetchall()
        except Exception as exc:
            print("  err", exc)
            continue
        for row in rows[:15]:
            d = {k: row[k] for k in row.keys()}
            # compact
            compact = {
                k: d[k]
                for k in d
                if k.lower()
                in {
                    "id",
                    "task_id",
                    "tree_id",
                    "branch_id",
                    "status",
                    "state",
                    "title",
                    "name",
                    "hold_reason",
                    "blocked_reason",
                    "reason",
                    "source",
                    "updated_at",
                    "created_at",
                }
                or "status" in k.lower()
                or "hold" in k.lower()
                or "title" in k.lower()
            }
            if not compact:
                compact = {k: d[k] for k in list(d)[:8]}
            print(json.dumps(compact, default=str)[:400])
        print()

    # autonomy state snippet
    auto = ROOT / "runtime" / "autonomy_maintenance_state.json"
    if auto.is_file():
        a = json.loads(auto.read_text(encoding="utf-8"))
        print("=== autonomy keys ===", list(a.keys())[:30])
        for key in (
            "generated_queue",
            "last_work_tree_cycle",
            "last_generated_queue_run",
            "runtime_worker",
            "holds",
            "blocked",
        ):
            if key in a:
                print(f"--- {key} ---")
                print(json.dumps(a.get(key), indent=2, default=str)[:2000])


if __name__ == "__main__":
    main()
