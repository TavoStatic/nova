"""Overnight autonomy + decision-judge snapshot."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime" / "autonomy_maintenance_state.json"
LOG = ROOT / "runtime" / "autonomy_maintenance.log"
LEDGER = ROOT / "runtime" / "autonomy_orchestrator_ledger.jsonl"


def main() -> None:
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    print("=== state timestamps ===")
    for key in (
        "last_autonomy_orchestrator",
        "last_autonomy_execution",
        "last_decision_judge",
        "last_decision_episode",
        "last_decision_proposal",
        "last_nova_mission",
        "last_active_work_tree_cycle",
        "last_signal_ingestion",
        "last_regression_status",
        "last_regression_at",
    ):
        val = st.get(key)
        if isinstance(val, dict):
            print(
                key,
                val.get("ts") or val.get("created_at_utc") or val.get("updated_at") or list(val.keys())[:6],
            )
        elif isinstance(val, list):
            print(key, "len", len(val))
        else:
            print(key, val)

    hist = st.get("decision_judge_history") or []
    print("\n=== decision_judge_history", len(hist), "===")
    disps: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    for row in hist if isinstance(hist, list) else []:
        if not isinstance(row, dict):
            continue
        disps[str(row.get("disposition") or "")] += 1
        tools[str(row.get("tool_name") or row.get("action_id") or "")] += 1
        print(
            " ",
            row.get("ts"),
            row.get("action_id") or row.get("action_type"),
            row.get("tool_name"),
            row.get("disposition"),
            row.get("result"),
            "conf",
            row.get("confidence"),
        )
    print("dispositions", dict(disps))
    print("tools", dict(tools))

    jp = st.get("last_decision_judge") or {}
    prop = st.get("last_decision_proposal") or {}
    ep = st.get("last_decision_episode") or {}
    if jp:
        print("\n=== last_decision_judge ===")
        print("disposition", jp.get("disposition"), "controlling", jp.get("controlling_dimension"))
        for dim in ("reversibility", "context_completeness", "mission_alignment"):
            d = jp.get(dim) or {}
            print(f"  {dim}: status={d.get('status')} score={d.get('score')} reason={d.get('reason')}")
        print("resolution", jp.get("resolution_action"))
        print("outcome", jp.get("outcome"))
    if prop:
        print("\n=== last_decision_proposal ===")
        print({k: prop.get(k) for k in ("action_id", "tool_name", "pressure_id", "intended_effect", "close_condition", "field_sources")})
    if ep:
        print("\n=== last_decision_episode ===")
        print("id", ep.get("episode_id"), "disp", ep.get("disposition"))
        print("prediction", ep.get("prediction_outcome"))
        print("execution", ep.get("execution"))

    # Log overnight orchestrator decisions
    print("\n=== log orchestrator lines (scan) ===")
    if LOG.exists():
        text = LOG.read_text(encoding="utf-8", errors="replace")
        lines = [ln for ln in text.splitlines() if "autonomy_orchestrator" in ln]
        print("orchestrator_lines_total", len(lines))
        for ln in lines[-25:]:
            print(ln)
        # count by action overnight-ish
        acts: Counter[str] = Counter()
        for ln in lines:
            m = re.search(r"action=([a-zA-Z0-9_]+)", ln)
            d = re.search(r"decision=([a-zA-Z0-9_]+)", ln)
            if m:
                acts[m.group(1)] += 1
            elif d:
                acts["decision:" + d.group(1)] += 1
        print("action_counts_all_log", dict(acts.most_common(15)))

    # ledger last N with execution
    if LEDGER.exists():
        lines = LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()
        print("\n=== ledger last 30 ===")
        for line in lines[-30:]:
            try:
                row = json.loads(line)
            except Exception:
                continue
            action = row.get("recommended_action") or row.get("action") or {}
            at = action.get("action_type") if isinstance(action, dict) else ""
            print(
                row.get("ts") or row.get("created_at_utc"),
                row.get("decision_type") or row.get("decision"),
                at,
                "exec",
                (row.get("execution") or {}).get("result") if isinstance(row.get("execution"), dict) else row.get("execution_result"),
            )

    mission = st.get("last_nova_mission") or {}
    if mission:
        print("\n=== mission ===")
        print(
            {
                k: mission.get(k)
                for k in (
                    "status",
                    "action",
                    "green_cycle",
                    "headline",
                    "regression_current",
                    "truth_blockers",
                )
            }
        )


if __name__ == "__main__":
    main()
