import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree
from services.evidence_validity import evidence_result_valid
from services.work_tree_signal_ingestion import _sequence_item_satisfied

branch_id = "branch_882b7612"
seq = [
    {
        "title": "Read source root inventory catalog",
        "allowed_tools": ["read"],
        "preferred_tool": "read",
        "tool_args": ["services/nova_root_inventory.py"],
    },
    {
        "title": "Read central subsystem wiring inventory",
        "allowed_tools": ["read"],
        "preferred_tool": "read",
        "tool_args": ["services/nova_wiring_inventory.py"],
    },
    {
        "title": "Find wiring, status, and evidence references for source_root_inventory",
        "allowed_tools": ["find"],
        "preferred_tool": "find",
        "tool_args": ["source_root_inventory|status_payload|source_wiring_probe|root_closure_inventory"],
    },
]
print("sequence_len", len(seq))
for i, item in enumerate(seq, start=1):
    title = item.get("title")
    print(i, title, "satisfied=", _sequence_item_satisfied(branch_id, item))

print("--- recent evidence validity ---")
ev = work_tree.list_branch_evidence(branch_id, limit=30)
for row in ev[:15]:
    tid = row.get("task_id")
    tool = row.get("tool_name")
    valid = evidence_result_valid(row)
    print(tid, tool, "valid=", valid)
