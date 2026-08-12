"""List open/blocked tasks on active trees with problem context."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "runtime" / "_internal" / "work_tree.db"


def main() -> None:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT t.task_id, t.title, t.status, t.priority, t.score, t.updated_at, t.meta_json,
               b.branch_id, b.title AS branch_title, b.status AS branch_status, b.bucket,
               b.work_class, b.actionability, b.resolution_state, b.notes,
               b.source_type, b.source_key, b.source_payload_json, b.blocked_by_json,
               w.tree_id, w.title AS tree_title, w.status AS tree_status
        FROM work_tree_tasks t
        JOIN work_tree_branches b ON b.branch_id = t.branch_id
        JOIN work_trees w ON w.tree_id = b.tree_id
        WHERE t.status IN ('open', 'ready', 'blocked', 'in_progress')
          AND w.status = 'active'
        ORDER BY CASE t.status WHEN 'blocked' THEN 0 ELSE 1 END, t.updated_at DESC
        """
    ).fetchall()

    print(f"count={len(rows)}")
    for r in rows:
        meta = {}
        try:
            meta = json.loads(r["meta_json"] or "{}")
        except Exception:
            pass
        payload = {}
        try:
            payload = json.loads(r["source_payload_json"] or "{}")
        except Exception:
            pass

        print("=" * 72)
        print("TASK:", r["title"])
        print("  id:", r["task_id"], "status:", r["status"], "updated:", r["updated_at"])
        print("  tree:", r["tree_title"], f"({r['tree_status']})")
        print(
            "  branch:",
            r["branch_title"],
            "bucket=",
            r["bucket"],
            "branch_status=",
            r["branch_status"],
            "resolution=",
            r["resolution_state"],
        )
        print("  work_class:", r["work_class"], "source_type:", r["source_type"])
        print("  source_key:", str(r["source_key"] or "")[:160])
        for k in (
            "blocked_reason",
            "block_reason",
            "expected_tool",
            "allowed_tools",
            "recurring_finding_satisfaction_status",
            "recurring_finding_key",
        ):
            if k in meta and meta[k] not in (None, "", []):
                print(f"  meta.{k}:", str(meta[k])[:240])
        notes = (r["notes"] or "").strip()
        if notes:
            print("  notes:", notes[:500].replace("\n", " | "))
        for k in (
            "rationale",
            "reason",
            "error",
            "profile_drift_count",
            "source_observed_count",
            "latest_readiness_note",
            "latest_state",
            "decision",
            "rejection_reasons",
        ):
            if k in payload and payload[k] not in (None, "", []):
                print(f"  payload.{k}:", str(payload[k])[:280])


if __name__ == "__main__":
    main()
