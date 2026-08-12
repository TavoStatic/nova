"""Force one orchestrator advisory+execute cycle for climb (no daily regression)."""
from __future__ import annotations

import json
from pathlib import Path

import autonomy_maintenance as am


def main() -> None:
    state = am._load_state()
    kidney = dict(state.get("last_kidney_status") or {})
    result = am._run_autonomy_orchestrator_advisory(state, kidney)
    am._save_state(state)
    print(json.dumps(result, indent=2, default=str)[:4000])
    orch = state.get("last_autonomy_orchestrator") or {}
    print(
        "summary",
        {
            "ts": orch.get("ts"),
            "decision": orch.get("decision_type") or orch.get("decision"),
            "reason": (orch.get("reason") or "")[:160],
            "action": orch.get("recommended_action") or orch.get("action"),
            "execution": state.get("last_autonomy_execution"),
            "active": state.get("last_active_work_tree_cycle"),
            "mission": {
                k: (state.get("last_nova_mission") or {}).get(k)
                for k in (
                    "status",
                    "action",
                    "green_cycle",
                    "regression_current",
                )
            },
        },
    )


if __name__ == "__main__":
    main()
