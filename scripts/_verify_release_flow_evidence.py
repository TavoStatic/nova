"""Ground-truth: what release tools actually did (DB evidence + ledger + reports)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "runtime" / "_internal" / "work_tree.db"
LEDGER = ROOT / "runtime" / "exports" / "release_packages" / "release_ledger.jsonl"


def main() -> None:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    print("=== work_tree evidence: release tools (last 40) ===")
    rows = con.execute(
        """
        select e.created_at, e.tool_name, e.branch_id, e.task_id,
               substr(e.result_text, 1, 280) as r, e.tool_args_json
        from work_tree_evidence e
        where e.tool_name in (
            'release_rebuild_verify','release_validation_run',
            'release_promotion_judgment','release_record_validation_outcome','read'
        )
        order by e.created_at desc
        limit 40
        """
    ).fetchall()
    for r in rows:
        print("---")
        print(r["created_at"], r["tool_name"], r["branch_id"], r["task_id"])
        print(" args", (r["tool_args_json"] or "")[:160])
        print(" ", (r["r"] or "").replace("\n", " | ")[:280])

    print("\n=== ledger last 15 events ===")
    if LEDGER.exists():
        lines = LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-15:]:
            try:
                ev = json.loads(line)
            except Exception:
                print(line[:200])
                continue
            print(
                ev.get("recorded_at") or ev.get("ts"),
                ev.get("event") or ev.get("kind"),
                "result=",
                ev.get("result") or ev.get("validation_result") or ev.get("status"),
                "artifact=",
                str(ev.get("artifact_name") or ev.get("artifact") or "")[:60],
            )
            # short note if present
            for k in ("readiness_state", "note", "failure_reason", "verdict"):
                if ev.get(k):
                    print("  ", k, str(ev.get(k))[:120])

    print("\n=== open release tasks now ===")
    for t in con.execute(
        """
        select t.updated_at, t.status, t.title, t.meta_json, b.title as bt
        from work_tree_tasks t
        join work_tree_branches b on b.branch_id=t.branch_id
        where lower(t.status) in ('open','blocked','in_progress')
          and b.work_class='release_readiness_gap'
        order by t.updated_at desc limit 15
        """
    ):
        meta = json.loads(t["meta_json"] or "{}")
        print(
            t["updated_at"],
            t["status"],
            meta.get("expected_tool"),
            (t["title"] or "")[:50],
            "|",
            (t["bt"] or "")[:40],
        )

    latest = ROOT / "runtime" / "validation" / "release" / "latest_release_validation.json"
    if latest.exists():
        print("\n=== latest_release_validation.json ===")
        data = json.loads(latest.read_text(encoding="utf-8"))
        for k in (
            "completed",
            "ok",
            "validation_result",
            "result",
            "artifact_path",
            "record_path",
            "record_complete",
            "generated_at",
            "failure_reason",
        ):
            if k in data or True:
                v = data.get(k)
                if v is not None and v != "":
                    print(k, ":", str(v)[:200])
        # nested
        for k in ("summary", "status", "checks"):
            if k in data:
                print(k, ":", str(data.get(k))[:300])


if __name__ == "__main__":
    main()
