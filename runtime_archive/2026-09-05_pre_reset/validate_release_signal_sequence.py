import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.work_tree_signal_ingestion import _release_readiness_signal_from_status

status_payload = {
    "release_status": {
        "ok": True,
        "latest_state": "verified",
        "latest_readiness_state": "needs-verification",
        "latest_ready_to_ship": False,
        "ledger_path": "runtime/release_ledger.jsonl",
        "latest_artifact_path": "dist/pkg.zip",
        "latest_artifact_name": "pkg.zip",
    }
}

signal = _release_readiness_signal_from_status(status_payload)
print("preferred_tool", signal.get("preferred_tool"))
for item in signal.get("task_sequence") or []:
    print(item.get("title"), "|", item.get("preferred_tool"))
