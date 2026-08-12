import json
import sqlite3

con = sqlite3.connect("runtime/_internal/work_tree.db")
con.row_factory = sqlite3.Row
bid = "branch_804e1fc3"

tasks = con.execute(
    "select task_id,title,status,created_at,updated_at,meta_json "
    "from work_tree_tasks where branch_id=? order by created_at",
    (bid,),
).fetchall()
print("=== TASK TIMELINE", len(tasks), "===")
for t in tasks:
    d = dict(t)
    meta = {}
    try:
        meta = json.loads(d["meta_json"] or "{}")
    except Exception:
        pass
    br = str(meta.get("blocked_reason") or meta.get("block_reason") or "")
    line = (
        f"{d['created_at']} -> {d['updated_at']} | {str(d['status']):10} | "
        f"{str(d['title'])[:55]} | {br[:60]}"
    )
    print(line)

ev = con.execute(
    "select tool_name,created_at,substr(result_text,1,140) r "
    "from work_tree_evidence where branch_id=? order by created_at",
    (bid,),
).fetchall()
print("=== EVIDENCE", len(ev), "===")
for e in ev:
    r = (e["r"] or "").replace("\n", " ")
    print(e["created_at"], e["tool_name"], r[:120])

b = con.execute(
    "select created_at,updated_at,status,resolution_state,last_seen_at,source_payload_json "
    "from work_tree_branches where branch_id=?",
    (bid,),
).fetchone()
print("=== BRANCH ===")
print(
    "created",
    b["created_at"],
    "updated",
    b["updated_at"],
    "status",
    b["status"],
    "res",
    b["resolution_state"],
    "last_seen",
    b["last_seen_at"],
)
p = json.loads(b["source_payload_json"] or "{}")
print("lifecycle", json.dumps(p.get("recurring_finding_lifecycle") or {}, indent=2))
sp = p.get("solution_progress") or {}
print("surfaced", sp.get("surfaced_at"), "work_started", sp.get("work_started_at"))
print(
    "scheduler",
    {
        k: p.get(k)
        for k in ("maintenance_scheduler_mode", "maintenance_scheduler_status")
    },
)

# count hold cycles
holds = [
    t
    for t in tasks
    if "operator judgment" in str(t["title"] or "").lower()
]
print("operator_hold_tasks", len(holds))
print(
    "hold_statuses",
    {str(t["status"]): sum(1 for x in holds if x["status"] == t["status"]) for t in holds},
)
