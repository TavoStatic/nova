import json
import sqlite3
from pathlib import Path

con = sqlite3.connect("runtime/_internal/work_tree.db")
con.row_factory = sqlite3.Row

print("=== open release-ish branches ===")
for b in con.execute(
    """
    select branch_id, title, status, preferred_tool, open_stem_count, updated_at, work_class
    from work_tree_branches
    where lower(status) not in ('archived','done','complete','closed')
      and (work_class='release_readiness_gap' or lower(title) like '%release%' or lower(title) like '%validation%')
    order by updated_at desc
    limit 12
    """
):
    print(
        b["updated_at"],
        b["status"],
        "pref=",
        b["preferred_tool"],
        "stems=",
        b["open_stem_count"],
        b["branch_id"],
        (b["title"] or "")[:55],
    )

print("=== open tasks (release branches) ===")
for t in con.execute(
    """
    select t.task_id, t.branch_id, t.title, t.status, t.updated_at, t.meta_json
    from work_tree_tasks t
    join work_tree_branches b on b.branch_id = t.branch_id
    where lower(t.status) in ('open','ready','in_progress','blocked')
      and (b.work_class='release_readiness_gap' or lower(b.title) like '%release%' or lower(b.title) like '%validation%')
    order by t.updated_at desc
    limit 20
    """
):
    meta = {}
    try:
        meta = json.loads(t["meta_json"] or "{}")
    except Exception:
        pass
    print(
        t["updated_at"],
        t["status"],
        "tool=",
        meta.get("expected_tool"),
        t["branch_id"],
        (t["title"] or "")[:55],
    )

print("=== branch_0aa0383a ===")
b = con.execute(
    "select * from work_tree_branches where branch_id=?", ("branch_0aa0383a",)
).fetchone()
if not b:
    print("branch gone")
else:
    d = dict(b)
    print(
        "title",
        d["title"],
        "status",
        d["status"],
        "pref",
        d["preferred_tool"],
        "stems",
        d["open_stem_count"],
        "upd",
        d["updated_at"],
    )
    p = json.loads(d.get("source_payload_json") or "{}")
    print(
        "readiness",
        p.get("latest_readiness_state"),
        "phase",
        p.get("release_phase_code"),
    )
    for t in con.execute(
        "select task_id, title, status, updated_at, meta_json from work_tree_tasks "
        "where branch_id=? order by updated_at desc limit 12",
        ("branch_0aa0383a",),
    ):
        meta = json.loads(t["meta_json"] or "{}")
        print(
            " ",
            t["status"],
            "tool=",
            meta.get("expected_tool"),
            (t["title"] or "")[:60],
            t["updated_at"],
        )

st = json.loads(Path("runtime/autonomy_maintenance_state.json").read_text(encoding="utf-8"))
orch = st.get("last_autonomy_orchestrator") or {}
ex = st.get("last_autonomy_execution") or {}
sig = st.get("last_pre_execution_signal_ingestion") or st.get("last_signal_ingestion") or {}
print("=== cycles ===")
print("signal", sig.get("ts") if isinstance(sig, dict) else sig)
print("orch", orch.get("ts"), orch.get("decision_type"), str(orch.get("reason") or "")[:90])
print(
    "exec",
    ex.get("ts"),
    ex.get("action_type"),
    ex.get("result"),
    (ex.get("extra") or {}).get("cycle", {}).get("history", [{}])[:1]
    if isinstance((ex.get("extra") or {}).get("cycle"), dict)
    else "",
)
rec = orch.get("recommended_action") or {}
print("recommended", rec.get("action_type"), rec.get("recommended_tool"), rec.get("target_id"))
