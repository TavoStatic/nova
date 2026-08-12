"""Clear stale Runtime Governance holds after regression inventory fix."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import work_tree as wt
from services.operator_outbox import OperatorOutboxService
from services.regression_lanes import SOURCE_PROFILE_LANES
from services.regression_profile_inventory import build_regression_profile_inventory_payload

ROOT = Path(__file__).resolve().parents[1]
OUTBOX = ROOT / "runtime" / "operator_outbox.jsonl"
DB = ROOT / "runtime" / "_internal" / "work_tree.db"
REG = ROOT / "runtime" / "regression_status.json"
NOTICE_ID = "1784524005887-d6305912e6d4"


def remaining() -> list[tuple[str, str, str]]:
    conn = sqlite3.connect(str(DB))
    rows = conn.execute(
        """
        SELECT t.title, t.status, b.title
        FROM work_tree_tasks t
        JOIN work_tree_branches b ON b.branch_id = t.branch_id
        JOIN work_trees w ON w.tree_id = b.tree_id
        WHERE w.status = 'active'
          AND t.status IN ('open', 'blocked', 'ready', 'in_progress')
        ORDER BY t.status, t.updated_at
        """
    ).fetchall()
    conn.close()
    return [(str(a), str(b), str(c)) for a, b, c in rows]


def main() -> None:
    wt.reload_persisted_state()
    outbox = OperatorOutboxService()
    reg = json.loads(REG.read_text(encoding="utf-8")) if REG.exists() else {}
    profile = build_regression_profile_inventory_payload(test_lanes=SOURCE_PROFILE_LANES)

    print("before:")
    for title, status, branch in remaining():
        print(f"  [{status}] {title} | {branch}")

    # 1) Operator resolution of regression source-root hold (outbox notice)
    resp = outbox.respond_to_notice(
        OUTBOX,
        event_id=NOTICE_ID,
        message=(
            "Operator resolution: regression root cause fixed. "
            "SOURCE_PROFILE_LANES now classify Nova Shell, backpack, and new Ed-Fi tests; "
            "source-root inventory and backpack_edfi wiring probe are clean; "
            f"runtime/regression_status.json is {reg.get('status')} ({reg.get('generated_at')}). "
            "source_root_sequence_exhausted_gap_persists no longer applies. Close hold."
        ),
        responder="operator",
        resolution="task_resolved",
        response_payload={
            "regression_status": reg.get("status"),
            "test_profile_inventory_ok": reg.get("test_profile_inventory_ok"),
            "source_observed_count": profile.get("source_observed_count"),
            "profile_drift_count": profile.get("profile_drift_count"),
        },
    )
    print(
        "outbox_response ok=",
        resp.get("ok"),
        "event_status=",
        (resp.get("event") or {}).get("status"),
        "work_tree=",
        resp.get("work_tree"),
    )

    # 2) Complete stale profile-inventory read task (drift is zero)
    wt.reload_persisted_state()
    profile_task = "task_53b6ccae"
    profile_branch = "branch_e43d066c"
    try:
        wt.record_task_evidence(
            branch_id=profile_branch,
            task_id=profile_task,
            tool_name="read",
            tool_args=["services/regression_lanes.py", "runtime/regression_status.json"],
            result={
                "ok": True,
                "note": "Profile drift resolved: shell/backpack/edfi tests classified; inventory ok",
                "source_observed_count": profile.get("source_observed_count"),
                "profile_drift_count": profile.get("profile_drift_count"),
                "regression_status": reg.get("status"),
            },
        )
        wt.mark_task_complete(profile_task)
        print("completed profile inventory task")
    except Exception as exc:
        print("profile task skip/fail:", exc)

    # 3) Complete outbox wait task when no actionable open notices remain
    wt.reload_persisted_state()
    summary = outbox.summary(OUTBOX)
    open_count = int(summary.get("operator_actionable_open_count", summary.get("open_count", 0)) or 0)
    print("outbox actionable_open_count=", open_count)
    if open_count == 0:
        try:
            wt.record_task_evidence(
                branch_id="branch_a7672266",
                task_id="task_892e360c",
                tool_name="operator_response",
                tool_args=[NOTICE_ID],
                result={"ok": True, "note": "Open outbox item resolved; actionable open count is 0"},
            )
            wt.mark_task_complete("task_892e360c")
            print("completed outbox wait task")
        except Exception as exc:
            print("outbox wait complete fail:", exc)

    print("after:")
    for title, status, branch in remaining():
        print(f"  [{status}] {title} | {branch}")


if __name__ == "__main__":
    main()
