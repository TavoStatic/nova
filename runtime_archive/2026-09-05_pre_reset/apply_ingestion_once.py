import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree
from services.work_tree_signal_ingestion import WORK_TREE_SIGNAL_INGESTION_SERVICE

snap_path = ROOT / "runtime" / "pulse_snapshot.json"
if not snap_path.exists():
    print("missing", snap_path)
    raise SystemExit(1)

status_payload = json.loads(snap_path.read_text(encoding="utf-8"))
results = WORK_TREE_SIGNAL_INGESTION_SERVICE.ingest_status_snapshot(status_payload)
print("ingestion_results", len(results))

for bid in ("branch_882b7612", "branch_3175ae5e"):
    b = work_tree.get_branch(bid)
    if not b:
        continue
    print("branch", bid, "|", b.title)
    open_tasks = [
        t for t in work_tree.list_branch_tasks(bid)
        if str(getattr(getattr(t, "status", ""), "value", getattr(t, "status", "")) or "").lower() not in {"complete", "dropped"}
    ]
    for t in open_tasks:
        print(" OPEN", t.task_id, "|", t.title)
