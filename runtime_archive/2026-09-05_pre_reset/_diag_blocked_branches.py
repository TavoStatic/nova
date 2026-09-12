import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import work_tree
from services.source_root_judgment import build_source_root_judgment

for bid in ["branch_c37c40e1", "branch_a00c67c3"]:
    print("=" * 70, bid)
    ev = work_tree.list_branch_evidence(bid, limit=80)
    failed = []
    for row in ev:
        text = row.get("result_text") or ""
        low = text.lower()
        is_fail = (
            (not text.strip())
            or low.startswith("[fail]")
            or '"ok": false' in low
            or "tool error" in low
            or "not a file" in low
        )
        if is_fail:
            failed.append(row)
    print("total evidence", len(ev), "failed-looking", len(failed))
    for row in failed[:8]:
        rt = (row.get("result_text") or "")[:320]
        print(" FAIL tool=%s task=%s" % (row.get("tool_name"), str(row.get("task_id", ""))[:12]))
        print("  ", rt.replace("\n", " "))
    for row in ev:
        if row.get("tool_name") == "source_root_judgment":
            print(" JUDGMENT RESULT:")
            print((row.get("result_text") or "")[:2500])
    j = build_source_root_judgment(bid)
    print(
        " LIVE JUDGMENT:",
        j.get("verdict"),
        "|",
        j.get("reason"),
        "| failed_count",
        j.get("failed_evidence_count"),
    )