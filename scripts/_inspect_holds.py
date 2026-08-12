from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "runtime" / "_internal" / "work_tree.db"


def main() -> None:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    print("=== BLOCKED TASKS / BRANCHES (what the holds say) ===\n")
    tasks = con.execute(
        """
        SELECT t.task_id, t.title AS task_title, t.status AS task_status,
               t.updated_at AS task_updated, t.meta_json,
               b.branch_id, b.title AS branch_title, b.status AS branch_status,
               b.notes, b.blocked_by_json, b.source_type, b.source_key,
               b.source_payload_json, b.work_class, b.actionability,
               b.resolution_state, b.preferred_tool, b.allowed_tools_json,
               b.required_tools_json, b.tool_state_json,
               tr.title AS tree_title, tr.status AS tree_status
        FROM work_tree_tasks t
        JOIN work_tree_branches b ON b.branch_id = t.branch_id
        JOIN work_trees tr ON tr.tree_id = b.tree_id
        WHERE tr.status = 'active'
          AND (t.status = 'blocked' OR b.status = 'blocked')
        ORDER BY t.updated_at DESC
        """
    ).fetchall()

    for t in tasks:
        print("=" * 64)
        print(f"HOLD: {t['branch_title']}")
        print(f"  branch_status: {t['branch_status']}   task_status: {t['task_status']}")
        print(f"  task: {t['task_title']}")
        print(f"  task_id: {t['task_id']}")
        print(f"  tree: {t['tree_title']}")
        print(f"  updated: {t['task_updated']}")
        print(f"  work_class: {t['work_class']}  actionability: {t['actionability']}")
        print(f"  resolution_state: {t['resolution_state']}")
        print(f"  source: {t['source_type']} / {t['source_key']}")
        if t["notes"]:
            print(f"  notes: {t['notes']}")
        if t["preferred_tool"]:
            print(f"  preferred_tool: {t['preferred_tool']}")
        if t["allowed_tools_json"]:
            print(f"  allowed_tools: {t['allowed_tools_json']}")
        if t["required_tools_json"]:
            print(f"  required_tools: {t['required_tools_json']}")
        if t["blocked_by_json"]:
            print(f"  blocked_by: {t['blocked_by_json']}")
        try:
            meta = json.loads(t["meta_json"] or "{}")
        except Exception:
            meta = {}
        if meta:
            print("  task_meta:")
            print(json.dumps(meta, indent=4, default=str)[:2000])
        try:
            payload = json.loads(t["source_payload_json"] or "{}")
        except Exception:
            payload = {}
        if payload:
            # pull human language fields
            keys = (
                "title",
                "message",
                "reason",
                "rationale",
                "detail",
                "headline",
                "error",
                "next_task",
                "blocked_reason",
                "hold_reason",
                "summary",
            )
            slim = {k: payload.get(k) for k in keys if payload.get(k) not in (None, "", [], {})}
            if not slim:
                slim = {k: payload[k] for k in list(payload)[:12]}
            print("  source_payload (what the hold is about):")
            print(json.dumps(slim, indent=4, default=str)[:2500])
        try:
            tool_state = json.loads(t["tool_state_json"] or "{}")
        except Exception:
            tool_state = {}
        if tool_state:
            print("  tool_state:", json.dumps(tool_state, indent=2, default=str)[:800])
        print()

    print("\n=== LATEST OPERATOR OUTBOX MESSAGES (what Nova is saying to you) ===\n")
    outbox = ROOT / "runtime" / "operator_outbox.jsonl"
    if outbox.is_file():
        lines = outbox.read_text(encoding="utf-8", errors="replace").splitlines()
        # newest first
        for line in reversed(lines[-30:]):
            try:
                o = json.loads(line)
            except Exception:
                continue
            st = str(o.get("status") or "").lower()
            if st not in {"new", "open", "pending", "waiting", "active", "stale"}:
                continue
            print("-" * 56)
            print("status:", o.get("status"))
            print("message:", o.get("message"))
            for k in ("reason", "detail", "headline", "next_step"):
                if o.get(k):
                    print(f"{k}:", o.get(k))
            print("dedupe:", str(o.get("dedupe_key") or "")[:140])
            print()

    auto = ROOT / "runtime" / "autonomy_maintenance_state.json"
    if auto.is_file():
        a = json.loads(auto.read_text(encoding="utf-8"))
        orch = a.get("last_autonomy_orchestrator") or {}
        print("=== WHAT AUTONOMY SAYS (why it won't move) ===")
        print("decision:", orch.get("decision_type"), "/", orch.get("decision"))
        print("reason:", orch.get("reason") or orch.get("explain_text"))
        print("rejections:", orch.get("rejection_reasons"))
        ms = orch.get("mission_snapshot") or {}
        print("mission headline:", ms.get("headline"))
        print("mission status/action:", ms.get("status"), "/", ms.get("action"))
        print("truth_blockers:", ms.get("truth_blockers"))


if __name__ == "__main__":
    main()
