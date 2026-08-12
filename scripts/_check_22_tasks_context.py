import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
con = sqlite3.connect(str(ROOT / "runtime" / "_internal" / "work_tree.db"))
con.row_factory = sqlite3.Row

open_n = con.execute(
    "select count(*) as c from work_tree_tasks "
    "where lower(status) in ('open','ready','in_progress','blocked')"
).fetchone()["c"]
total = con.execute("select count(*) as c from work_tree_tasks").fetchone()["c"]
print("open_tasks", open_n, "total_tasks", total)

by_status = Counter(
    r["status"]
    for r in con.execute("select lower(status) as status from work_tree_tasks")
)
print("status_counts", dict(by_status.most_common(12)))

n_dec = con.execute(
    "select count(*) as c from work_tree_tasks "
    "where meta_json like '%decision_%'"
).fetchone()["c"]
print("tasks_meta_decision", n_dec)

# open blocked titles sample
rows = con.execute(
    "select task_id, title, status, substr(meta_json,1,80) m "
    "from work_tree_tasks "
    "where lower(status) in ('open','ready','in_progress','blocked') "
    "order by updated_at desc limit 25"
).fetchall()
print("recent_openish", len(rows))
for r in rows[:22]:
    print(" ", r["status"], r["task_id"], (r["title"] or "")[:70])

ledger = ROOT / "runtime" / "autonomy_orchestrator_ledger.jsonl"
if ledger.exists():
    lines = ledger.read_text(encoding="utf-8", errors="replace").splitlines()
    print("ledger_lines", len(lines))
    recent = []
    for line in lines[-100:]:
        try:
            recent.append(json.loads(line))
        except Exception:
            pass
    acts: Counter[str] = Counter()
    for r in recent:
        a = r.get("recommended_action") or r.get("action") or {}
        if isinstance(a, dict):
            acts[str(a.get("action_type") or r.get("decision_type") or "")] += 1
        else:
            acts[str(r.get("decision_type") or "")] += 1
    print("recent100_decision_types", dict(acts))
    if recent:
        last = recent[-1]
        print(
            "last_ledger",
            last.get("ts") or last.get("created_at_utc") or last.get("timestamp_utc"),
            last.get("decision_type") or last.get("decision"),
        )

log = ROOT / "runtime" / "autonomy_maintenance.log"
if log.exists():
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    print("=== log tail interest ===")
    for line in tail:
        low = line.lower()
        if any(k in low for k in ("orchestrator", "active_work", "decision", "cycle_complete")):
            print(line)

state = json.loads((ROOT / "runtime" / "autonomy_maintenance_state.json").read_text(encoding="utf-8"))
print("state_has_judge", bool(state.get("last_decision_judge") or state.get("decision_judge_history")))
print("state_last_exec", (state.get("last_autonomy_execution") or {}).get("ts"))
