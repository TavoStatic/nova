import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree
from services.work_tree_signal_ingestion import WORK_TREE_SIGNAL_INGESTION_SERVICE

signal = {
    "source": "source_root_inventory",
    "signal_class": "governance_pressure",
    "title": "Source root inventory has uncovered unwired roots or files",
    "fingerprint": {
        "class": "governance_pressure",
        "surface": "source_root_inventory",
        "error": "source_root_inventory_gap",
        "symbol": "source_root_inventory_gap",
    },
    "payload": {"rationale": "validation"},
    "severity": "high",
    "actionability": "safe_now",
    "allowed_tools": ["read", "find", "pulse", "system_check"],
    "preferred_tool": "read",
    "next_task": "Read source root inventory and compare every discovered root to wiring surfaces",
    "task_sequence": [
        {
            "title": "Read source root inventory catalog",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["services/nova_root_inventory.py"],
        },
        {
            "title": "Find missing source root wiring references",
            "allowed_tools": ["find"],
            "preferred_tool": "find",
            "tool_args": ["source_root_inventory", "."],
        },
    ],
}

result = WORK_TREE_SIGNAL_INGESTION_SERVICE.ingest_signal(signal)
print("ingest_status", result.get("status"), "branch", result.get("branch_id"))

bid = str(result.get("branch_id") or "")
if bid:
    open_tasks = [
        t for t in work_tree.list_branch_tasks(bid)
        if str(getattr(getattr(t, "status", ""), "value", getattr(t, "status", "")) or "").lower() not in {"complete", "dropped"}
    ]
    print("open_tasks", len(open_tasks))
    for t in open_tasks:
        print("OPEN", t.task_id, "|", t.title)
