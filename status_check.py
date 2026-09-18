"""Read-only live mill snapshot. Not a health gate."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path(r"C:\NOVA\runtime\_internal\work_tree.db")


def main() -> None:
    print("db_exists", DB.exists(), "size", DB.stat().st_size if DB.exists() else 0)
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")]
    print("tables", tables)

    def count(sql: str, args=()) -> int:
        return int(cur.execute(sql, args).fetchone()[0])

    print("trees", count("SELECT COUNT(*) FROM work_trees"))
    print("active_trees", count("SELECT COUNT(*) FROM work_trees WHERE status='active'"))
    print("branches", count("SELECT COUNT(*) FROM work_tree_branches"))
    print("tasks_openish", count("SELECT COUNT(*) FROM work_tree_tasks WHERE status IN ('open','active','attempted')"))

    print("--- trees ---")
    for row in cur.execute(
        "SELECT tree_id, title, status, json_extract(meta_json,'$.kind') AS kind, json_extract(meta_json,'$.source') AS source, updated_at FROM work_trees ORDER BY updated_at DESC"
    ):
        print(dict(row))

    print("--- refused judgments ---")
    n_refused = 0
    reasons: dict[str, int] = {}
    for row in cur.execute(
        """
        SELECT branch_id, title, status, resolution_state, source_key, source_payload_json
        FROM work_tree_branches
        WHERE source_payload_json LIKE '%"judgment": "refused"%'
           OR source_payload_json LIKE '%"judgment":"refused"%'
        """
    ):
        payload = {}
        try:
            payload = json.loads(row["source_payload_json"] or "{}")
        except Exception:
            payload = {}
        judgments = payload.get("attempt_judgments") or []
        refused = [j for j in judgments if isinstance(j, dict) and str(j.get("judgment") or "").lower() == "refused"]
        if not refused:
            continue
        n_refused += 1
        last = refused[-1]
        why = str(last.get("reason") or "")
        reasons[why] = reasons.get(why, 0) + 1
        pressure = last.get("pressure") or {}
        print(
            json.dumps(
                {
                    "branch_id": row["branch_id"],
                    "title": row["title"],
                    "status": row["status"],
                    "resolution_state": row["resolution_state"],
                    "source_key": row["source_key"],
                    "reason": why,
                    "pressure": pressure,
                    "retry_when": last.get("retry_when"),
                    "n_refused": len(refused),
                    "n_judgments": len(judgments),
                },
                default=str,
            )
        )
    print("refused_branches", n_refused, "reasons", reasons)
    con.close()


if __name__ == "__main__":
    main()
