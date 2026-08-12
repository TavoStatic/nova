"""Report decision-judge calibration sample size and the two watch signals."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime" / "autonomy_maintenance_state.json"
DB = ROOT / "runtime" / "_internal" / "work_tree.db"

# Enough to start trusting patterns (not enough to flip enforce alone).
MIN_CYCLES_FOR_SIGNAL = 12
MIN_CYCLES_FOR_ENFORCE_REVIEW = 30


def main() -> None:
    st: dict = {}
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))

    hist = list(st.get("decision_judge_history") or [])
    ep = dict(st.get("last_decision_episode") or {})
    jp = dict(st.get("last_decision_judge") or {})
    prop = dict(st.get("last_decision_proposal") or {})
    ex = dict(st.get("last_autonomy_execution") or {})
    orch = dict(st.get("last_autonomy_orchestrator") or {})

    print("=== state ===")
    print("history_len", len(hist))
    print("last_exec", ex.get("ts"), ex.get("action_type"), ex.get("result"))
    print("last_orch", orch.get("ts"), orch.get("decision_type"))
    print(
        "last_proposal",
        {k: prop.get(k) for k in ("action_id", "tool_name", "pressure_id") if prop},
    )
    print(
        "last_judge",
        jp.get("disposition"),
        "controlling=",
        jp.get("controlling_dimension"),
    )
    print("last_episode", ep.get("episode_id"), ep.get("disposition"))
    print("last_prediction", ep.get("prediction_outcome"))

    disps: Counter[str] = Counter()
    pred_none = pred_true = pred_false = 0
    for row in hist:
        if not isinstance(row, dict):
            continue
        disps[str(row.get("disposition") or "")] += 1
        outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
        pm = outcome.get("predicate_moved")
        if pm is None:
            pm = row.get("progress_moved")
        if pm is None and row.get("close_condition_remained_false") is None:
            pred_none += 1
        elif pm is True:
            pred_true += 1
        elif pm is False:
            pred_false += 1
        else:
            pred_none += 1

    print("dispositions", dict(disps))
    print("history_predicate_moved true/false/none", pred_true, pred_false, pred_none)

    # Work-tree episodes
    n_task = 0
    n_ep = 0
    ctrl: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    pm_none = pm_known = 0
    useful: Counter[str] = Counter()
    if DB.exists():
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "select meta_json from work_tree_tasks "
            "where meta_json like '%decision_episode%' "
            "   or meta_json like '%decision_judge%' "
            "limit 2000"
        ).fetchall()
        for row in rows:
            try:
                meta = json.loads(row["meta_json"] or "{}")
            except Exception:
                continue
            if not isinstance(meta, dict):
                continue
            n_task += 1
            episodes = list(meta.get("decision_episodes") or [])
            if meta.get("last_decision_episode"):
                episodes.append(meta["last_decision_episode"])
            for item in episodes:
                if not isinstance(item, dict):
                    continue
                n_ep += 1
                jr = item.get("judge_report") or {}
                prop_i = item.get("proposal") or {}
                ctrl[str(jr.get("controlling_dimension") or "")] += 1
                tools[str(prop_i.get("tool_name") or prop_i.get("action_id") or "")] += 1
                po = item.get("prediction_outcome") or {}
                if po.get("predicate_moved") is None:
                    pm_none += 1
                else:
                    pm_known += 1
                useful[str(po.get("judge_was_useful"))] += 1

    print("=== work_item episodes ===")
    print("tasks_with_meta", n_task, "episodes", n_ep)
    print("controlling_dimension", dict(ctrl))
    print("tools_or_actions", dict(tools.most_common(12)))
    print("predicate_moved known/none", pm_known, pm_none)
    print("judge_was_useful", dict(useful))

    total = max(len(hist), n_ep)
    print("=== calibration gate ===")
    print("sample_size", total, "(history vs episodes max)")
    if total < MIN_CYCLES_FOR_SIGNAL:
        print(
            "verdict: NOT ENOUGH — need at least",
            MIN_CYCLES_FOR_SIGNAL,
            "episodes/history rows before patterns are meaningful",
        )
        return
    if total < MIN_CYCLES_FOR_ENFORCE_REVIEW:
        print(
            "verdict: ENOUGH FOR SIGNALS — watch the two calibration flags; "
            "do not flip enforce yet (want ~",
            MIN_CYCLES_FOR_ENFORCE_REVIEW,
            ")",
        )
    else:
        print(
            "verdict: ENOUGH VOLUME TO REVIEW ENFORCE — only flip "
            "decision_judge_enforce if prediction quality looks honest"
        )

    # Watch signals
    none_rate = (pm_none / n_ep) if n_ep else (pred_none / len(hist) if hist else 1.0)
    print(f"watch1_predicate_moved_none_rate={none_rate:.2%}")
    if none_rate > 0.6:
        print(
            "  signal: predicate_moved often None — close condition not resolved post-execute"
        )
    top_ctrl = ctrl.most_common(1)
    if top_ctrl and top_ctrl[0][0] == "context_completeness" and top_ctrl[0][1] >= max(3, n_ep // 2):
        print(
            "  signal: controlling_dimension often context_completeness — map/catalog gaps"
        )


if __name__ == "__main__":
    main()
