"""Start durable guard (breakaway job), then run one climb advisory+execute."""
from __future__ import annotations

import json
import time
from pathlib import Path

import autonomy_maintenance as am


def main() -> None:
    # Clear dead lock so health is honest before start.
    for name in ("guard.lock", "guard_pid.json", "guard.stop"):
        path = Path("runtime") / name
        try:
            path.unlink()
        except Exception:
            pass

    ok, msg = am._maintenance_start_guard()
    print("guard_start", ok, msg)
    for i in range(6):
        time.sleep(1)
        print(f"health_t{i+1}", am._guard_health_for_orchestrator())

    state = am._load_state()
    kidney = dict(state.get("last_kidney_status") or {})
    result = am._run_autonomy_orchestrator_advisory(state, kidney)
    am._save_state(state)

    orch = state.get("last_autonomy_orchestrator") or {}
    ex = state.get("last_autonomy_execution") or {}
    print(
        "orch",
        {
            "decision": orch.get("decision_type") or orch.get("decision"),
            "reason": (orch.get("reason") or "")[:200],
            "rec": orch.get("recommended_action") or orch.get("action"),
        },
    )
    print(
        "exec",
        {
            "action": ex.get("action_type"),
            "result": ex.get("result"),
            "message": ex.get("message"),
            "ok": ex.get("ok"),
        },
    )
    print("health_after", am._guard_health_for_orchestrator())
    # compact result decision
    print(
        "packet",
        {
            "decision_type": result.get("decision_type"),
            "recommended_action": result.get("recommended_action"),
            "confidence": result.get("confidence"),
        },
    )


if __name__ == "__main__":
    main()
