"""Print the actual problems behind operator holds, not the instructions."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "runtime" / "_internal" / "work_tree.db"
REG = ROOT / "runtime" / "regression_status.json"
AUTO = ROOT / "runtime" / "autonomy_maintenance_state.json"


def main() -> None:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    print("=== THE ACTUAL PROBLEM (regression) ===")
    print(f"status: {reg.get('status')}")
    print(f"failed_lane: {reg.get('failed_lane')}")
    print(f"failed_tests: {reg.get('failed_tests')}")
    print(f"inventory_ok: {reg.get('test_profile_inventory_ok')}")
    print(f"source_observed_count: {reg.get('test_profile_source_observed_count')}")
    print(f"profile_drift_count: {reg.get('test_profile_profile_drift_count')}")
    print("drift files (tests exist on disk but are NOT in any curated regression lane):")
    for row in reg.get("test_profile_profile_drift_tests") or []:
        print(f"  - {row.get('path')}  class={row.get('profile_class')}  lanes={row.get('lanes')}")

    print("\n=== WHY THAT BLOCKS NOVA ===")
    print(
        "Mission/orchestrator treat regression_failed as truth not green. "
        "Open work-tree tasks park behind operator holds instead of running."
    )

    if AUTO.exists():
        auto = json.loads(AUTO.read_text(encoding="utf-8"))
        print("\n=== AUTONOMY STATE (problem language) ===")
        for k in (
            "status",
            "hold_reason",
            "block_reason",
            "mission_status",
            "last_decision",
            "summary",
            "reason",
            "validation_required",
            "operator_hold_pending",
        ):
            if k in auto:
                print(f"  {k}: {auto[k]}")
        # dump top-level keys if thin
        if len(auto) < 30:
            print(json.dumps(auto, indent=2, default=str)[:3000])

    if not DB.exists():
        print("no work_tree.db")
        return

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("\n=== DB TABLES ===", tables)

    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        interesting = any(
            x in c.lower()
            for c in cols
            for x in ("reason", "hold", "message", "body", "summary", "title", "content", "kind", "status", "payload")
        )
        if not interesting and "operator" not in t.lower() and "outbox" not in t.lower() and "hold" not in t.lower():
            continue
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception as e:
            print(t, "count err", e)
            continue
        if n == 0:
            continue
        print(f"\n--- {t} ({n} rows) cols={cols}")
        # try status filters
        rows = conn.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 8").fetchall()
        for r in rows:
            d = {k: r[k] for k in r.keys()}
            # shorten long blobs
            for k, v in list(d.items()):
                if isinstance(v, str) and len(v) > 400:
                    d[k] = v[:400] + "..."
            print(json.dumps(d, default=str)[:2000])
            print("---")


if __name__ == "__main__":
    main()
