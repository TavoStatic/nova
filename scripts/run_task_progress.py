#!/usr/bin/env python3
"""Learn solution ladders from completed tasks and report progress on open work.

Examples:
  python scripts/run_task_progress.py learn
  python scripts/run_task_progress.py report
  python scripts/run_task_progress.py open
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def cmd_learn(args: argparse.Namespace) -> int:
    from services.work_tree_task_progress import learn_families_from_history

    result = learn_families_from_history(
        limit_tasks=int(args.limit),
        min_samples=int(args.min_samples),
        persist=not args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result.get("ok") else 1


def cmd_report(args: argparse.Namespace) -> int:
    from services.work_tree_task_progress import list_seeded_families, load_learned_ladders

    seeded = list_seeded_families()
    learned = load_learned_ladders()
    print(f"seeded families: {len(seeded)}")
    for row in seeded:
        print(f"  [seed] {row['family_key']} markers={row['marker_count']}")
        print(f"         intent: {row['intent'][:100]}")
    print(f"learned families: {len(learned)}")
    for key, ladder in sorted(learned.items()):
        print(f"  [learn] {key} markers={len(ladder.markers)} source={ladder.source}")
        print(f"          intent: {ladder.intent[:100]}")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    import work_tree as wt

    wt.reload_persisted_state()
    rows = []
    seen_branches: set[str] = set()
    for task in wt._TASKS.values():
        branch = wt._BRANCHES.get(task.branch_id)
        if branch is None or branch.branch_id in seen_branches:
            continue
        tree = wt._TREES.get(branch.tree_id)
        if tree is None or str(getattr(tree.status, "value", tree.status)) != "active":
            continue
        status = str(getattr(task.status, "value", task.status))
        if status not in {"open", "blocked", "ready", "in_progress"}:
            continue
        seen_branches.add(branch.branch_id)
        # Root unit: solution progress on the branch/finding.
        progress = wt._branch_progress_payload(branch) or {}
        if not progress:
            continue
        rows.append((int(progress.get("percent") or 0), progress, branch.title))
    rows.sort(key=lambda item: (-item[0], item[2] or ""))
    if not rows:
        print("No open solution work on active trees.")
        return 0
    for _pct, progress, branch_title in rows:
        print("-" * 72)
        print(progress.get("operator_summary"))
        print("  unit: solution (branch/finding)")
        print("  branch:", branch_title or progress.get("branch_title"))
        print("  current step:", progress.get("current_step_title") or progress.get("doing"))
        print("  on radar:", progress.get("surfaced_at") or "—", end="")
        if progress.get("surfaced_age_sec") is not None:
            print(f"  ({int(progress.get('surfaced_age_sec') or 0)}s ago)", end="")
        print()
        started = progress.get("work_started_at") or ""
        if not started or str(progress.get("work_start_state") or "") == "not_started":
            print("  work started: not started (no tool evidence yet)")
        else:
            print("  work started:", started, end="")
            if progress.get("work_started_age_sec") is not None:
                print(f"  ({int(progress.get('work_started_age_sec') or 0)}s ago)", end="")
            print()
        print("  step opened:", progress.get("current_step_opened_at") or "—")
        print("  last seen:", progress.get("last_seen_at") or "—")
        print("  intent:", progress.get("intent"))
        print("  solution:", progress.get("solution"))
        print("  family:", progress.get("family_key"), f"({progress.get('ladder_source')})")
        for marker in progress.get("markers") or []:
            mark = "Y" if marker.get("achieved") else "N"
            print(f"  [{mark}] stage={marker.get('stage')} {marker.get('label')} — {marker.get('note')}")
        print(f"  effort steps: {progress.get('effort_count')}")
        for row in progress.get("effort") or []:
            print(f"    • {row.get('created_at')} {row.get('tool_name')} {str(row.get('summary') or '')[:80]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Work-tree task solution progress")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_learn = sub.add_parser("learn", help="Mine completed tasks and save learned ladders")
    p_learn.add_argument("--limit", type=int, default=1500)
    p_learn.add_argument("--min-samples", type=int, default=5)
    p_learn.add_argument("--dry-run", action="store_true")
    p_learn.set_defaults(func=cmd_learn)

    p_report = sub.add_parser("report", help="Show seeded + learned families")
    p_report.set_defaults(func=cmd_report)

    p_open = sub.add_parser("open", help="Measure progress on open active tasks")
    p_open.set_defaults(func=cmd_open)

    args = parser.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
