import json
import sqlite3
from pathlib import Path

from services.nova_mission import NovaMissionService

con = sqlite3.connect("runtime/_internal/work_tree.db")
con.row_factory = sqlite3.Row
bid = "branch_0aa0383a"
b = dict(con.execute("select * from work_tree_branches where branch_id=?", (bid,)).fetchone())
p = json.loads(b["source_payload_json"] or "{}")
print("title", b["title"])
print("status", b["status"], "preferred", b["preferred_tool"], "stems", b["open_stem_count"])
print("seq", json.dumps(p.get("task_sequence"), indent=2)[:1200])
print("lifecycle", p.get("recurring_finding_lifecycle"))
sp = p.get("solution_progress") or {}
print(
    "progress",
    sp.get("percent"),
    sp.get("motion"),
    sp.get("solution_status"),
    sp.get("doing"),
    sp.get("expected_tool"),
)
for t in con.execute(
    "select task_id,title,status,updated_at from work_tree_tasks where branch_id=? order by created_at",
    (bid,),
):
    print(t["status"], t["task_id"], (t["title"] or "")[:70], t["updated_at"])

print("--- evidence ---")
for e in con.execute(
    "select tool_name,created_at,substr(result_text,1,120) r from work_tree_evidence "
    "where branch_id=? order by created_at desc limit 10",
    (bid,),
):
    print(e["created_at"], e["tool_name"], (e["r"] or "").replace("\n", " ")[:100])

st = json.loads(Path("runtime/autonomy_maintenance_state.json").read_text(encoding="utf-8"))
m = st["last_nova_mission"]
ctx = {
    "recommended_tool": "source_root_judgment",
    "tool": "source_root_judgment",
    "title": b["title"],
    "branch_id": bid,
}
print(
    "allow source_root_judgment",
    NovaMissionService._hold_allows_active_work_tool(
        m, "source_root_judgment", action_context=ctx
    ),
)
print(
    "blocks",
    NovaMissionService.hold_blocks_action(
        "active_work_tree_run_next", mission_snapshot=m, action_context=ctx
    ),
)
print("RELEASE_LADDER_HOLD_TOOLS", sorted(NovaMissionService.RELEASE_LADDER_HOLD_TOOLS))
print("also core_thinning in allow path via set | core_thinning")
