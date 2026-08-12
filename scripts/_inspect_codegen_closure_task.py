#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = ROOT / "runtime" / "_internal" / "work_tree.db"


def main() -> None:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    rows = con.execute(
        """
        SELECT *
        FROM work_tree_branches
        WHERE lower(title) LIKE '%codegen%'
           OR branch_id = 'branch_a5e487c8'
           OR lower(ifnull(source_key,'')) LIKE '%codegen%'
        ORDER BY updated_at DESC
        """
    ).fetchall()
    print("hits", len(rows))
    for row in rows:
        d = dict(row)
        payload = {}
        try:
            payload = json.loads(d.get("source_payload_json") or "{}")
        except Exception:
            pass
        sp = payload.get("solution_progress") or {}
        print("===", d.get("branch_id"), d.get("status"), d.get("resolution_state"))
        print("title:", d.get("title"))
        print("work_class:", d.get("work_class"), "source_type:", d.get("source_type"))
        print("source_key:", d.get("source_key"))
        print("preferred_tool:", d.get("preferred_tool"))
        print("evidence_count field:", d.get("evidence_count"))
        print(
            "progress:",
            sp.get("percent"),
            sp.get("motion"),
            sp.get("family_key"),
            "|",
            sp.get("operator_summary"),
        )
        print("intent:", sp.get("intent"))
        print("solution:", sp.get("solution"))
        print("doing:", sp.get("doing") or sp.get("current_step_title"))
        print("markers_total:", sp.get("markers_total"), "achieved:", sp.get("markers_achieved"))
        for m in sp.get("markers") or []:
            print(
                " ",
                m.get("id"),
                m.get("quality"),
                m.get("achieved"),
                m.get("note"),
                "label=",
                m.get("label"),
            )
        bid = d["branch_id"]
        ev = con.execute(
            "SELECT tool_name, COUNT(*) n FROM work_tree_evidence WHERE branch_id=? GROUP BY tool_name",
            (bid,),
        ).fetchall()
        print("evidence_by_tool:", [dict(x) for x in ev])
        # also search evidence text for branch id
        ev2 = con.execute(
            """
            SELECT tool_name, created_at, substr(result_text,1,120) AS head
            FROM work_tree_evidence
            WHERE branch_id=? OR result_text LIKE ?
            ORDER BY rowid DESC LIMIT 8
            """,
            (bid, f"%{bid}%"),
        ).fetchall()
        print("evidence_rows:")
        for e in ev2:
            print(" ", dict(e))

    # how get_ladder resolves for this source type
    from services.work_tree_task_progress import get_ladder, SOLUTION_LADDERS

    print("\nknown ladder families:")
    for k in sorted(SOLUTION_LADDERS.keys()):
        print(" ", k)

    ladder = get_ladder(
        work_class="governance_pressure",
        source_type="self_repair_closure_inventory",
    )
    print("\nget_ladder(governance_pressure, self_repair_closure_inventory) ->", ladder.family_key, ladder.intent)

    ladder2 = get_ladder(work_class="governance_pressure", source_type="safety_envelope")
    print("get_ladder(governance_pressure, safety_envelope) ->", ladder2.family_key, ladder2.intent)

    # inspect get_ladder implementation path
    import inspect
    from services import work_tree_task_progress as wtp

    src = inspect.getsource(wtp.get_ladder)
    print("\nget_ladder source:\n", src[:2500])


if __name__ == "__main__":
    main()
