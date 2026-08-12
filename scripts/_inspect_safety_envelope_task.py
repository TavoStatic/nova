#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "runtime" / "_internal" / "work_tree.db"
BID = "branch_e6e96c6c"


def main() -> None:
    con = sqlite3.connect(str(DB))
    print("evidence_total", con.execute("SELECT COUNT(*) FROM work_tree_evidence").fetchone()[0])
    print(
        "evidence_branch",
        con.execute("SELECT COUNT(*) FROM work_tree_evidence WHERE branch_id=?", (BID,)).fetchone()[0],
    )
    print(
        "phase2_evidence",
        con.execute(
            "SELECT COUNT(*) FROM work_tree_evidence WHERE tool_name LIKE ?",
            ("%phase2%",),
        ).fetchone()[0],
    )
    print(
        "branch_evidence_count_field",
        con.execute(
            "SELECT evidence_count FROM work_tree_branches WHERE branch_id=?",
            (BID,),
        ).fetchone()[0],
    )

    # sample complete tasks meta
    rows = con.execute(
        """
        SELECT task_id, status, created_at, updated_at, meta_json
        FROM work_tree_tasks
        WHERE branch_id=? AND title LIKE 'Run safety-envelope audit%' AND status='complete'
        ORDER BY created_at DESC LIMIT 5
        """,
        (BID,),
    ).fetchall()
    print("recent_complete_audit_tasks")
    for r in rows:
        print(r)

    # open task meta full
    open_row = con.execute(
        """
        SELECT task_id, status, created_at, updated_at, meta_json
        FROM work_tree_tasks
        WHERE branch_id=? AND status='open'
        ORDER BY created_at DESC LIMIT 3
        """,
        (BID,),
    ).fetchall()
    print("open_tasks_full")
    for r in open_row:
        print(r[0], r[1], r[2], r[3])
        print(r[4][:800] if r[4] else "")

    # pending review filesystem
    for rel in (
        "runtime/test_sessions/pending_review",
        "runtime/test_sessions/quarantine",
    ):
        p = ROOT / rel
        print(rel, "exists", p.is_dir())
        if p.is_dir():
            files = [x for x in p.rglob("*") if x.is_file()]
            print("  file_count", len(files))
            for f in files[:8]:
                print(" ", f.relative_to(ROOT))

    import sys

    sys.path.insert(0, str(ROOT))
    import autonomy_maintenance as am
    from services.tool_identity import PHASE2_AUDIT

    print("PHASE2_AUDIT", PHASE2_AUDIT)
    print("in_execute", PHASE2_AUDIT in am.ACTIVE_WORK_TREE_EXECUTE_TOOLS)

    # try render status quickly
    try:
        import nova_safety_envelope

        raw = nova_safety_envelope.policy_safety_envelope()
        print("policy keys sample", {k: raw.get(k) for k in list(raw)[:12]})
        # status function if any
        if hasattr(nova_safety_envelope, "render_status"):
            text = str(nova_safety_envelope.render_status() or "")
            print("render_status head:\n", text[:1200])
    except Exception as exc:
        print("safety err", type(exc).__name__, exc)


if __name__ == "__main__":
    main()
