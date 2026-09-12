import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree
from services.work_tree_signal_ingestion import WORK_TREE_SIGNAL_INGESTION_SERVICE

signal = {
    "source": "release",
    "signal_class": "release_readiness_gap",
    "title": "Release package is verified but validation outcome is missing",
    "fingerprint": {
        "class": "release_readiness_gap",
        "surface": "release",
        "error": "release_validation_outcome_missing",
        "symbol": "release_package",
    },
    "payload": {
        "release_status_ok": True,
        "latest_state": "verified",
        "latest_readiness_state": "needs-verification",
        "latest_ready_to_ship": False,
        "latest_artifact_path": "dist/package.zip",
        "ledger_path": "runtime/release_ledger.jsonl",
        "rationale": "validation",
    },
    "severity": "medium",
    "actionability": "safe_now",
    "allowed_tools": ["read", "find", "system_check", "release_validation_run", "release_promotion_judgment", "release_record_validation_outcome"],
    "preferred_tool": "release_validation_run",
    "next_task": "Read release ledger and verify the latest package before promotion judgment",
    "task_sequence": [
        {
            "title": "Read release ledger for current package",
            "allowed_tools": ["read"],
            "preferred_tool": "read",
            "tool_args": ["runtime/release_ledger.jsonl"],
        },
        {
            "title": "Run release validation profile from current artifact",
            "allowed_tools": ["release_validation_run"],
            "preferred_tool": "release_validation_run",
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
