"""Frozen Work Tree mission loop — kernel, not a panel.

One governed mission through mill execute. Score the seven links from
disk state, not from a chat reply. No prompt-fitting.

This is not live 76a2bb4e. That cover stem would fail for the wrong reason.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import work_tree
from services.recurring_finding_lifecycle import (
    KEY_SATISFACTION_STATUS,
    STATUS_SATISFIED,
    finding_key_from_meta,
    read_task_state,
)
from work_tree_contracts import BranchStatus, TaskStatus


LINKS = (
    "admits_correctly",
    "selects_authorized_action",
    "executes_real_capability",
    "produces_verifiable_evidence",
    "updates_finding_from_evidence",
    "closes_only_when_target_changed",
    "refuses_when_link_missing",
)


def _status(value: object) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _tmp_db(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root / f"wt_loop_{uuid.uuid4().hex}.sqlite3"


def _link_score(*, observed: dict[str, bool], expected: dict[str, bool]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name in LINKS:
        out[name] = bool(observed.get(name)) == bool(expected.get(name))
    return out


def _observe_after_step(
    *,
    branch,
    task,
    step: dict[str, Any],
    authorized: set[str],
    expected_tool: str,
    require_args: bool,
    before_resolution: str,
    before_satisfied: bool,
    before_evidence: int,
) -> dict[str, bool]:
    action = str(step.get("action") or "")
    selected = str(step.get("recommended_tool") or step.get("tool") or "")
    task_status = _status(task.status)
    resolution = str(getattr(branch, "resolution_state", "") or "").strip().lower()
    evidence = list(work_tree.list_branch_evidence(branch.branch_id) or [])
    satisfied = False
    meta = dict(getattr(task, "meta", {}) or {})
    if finding_key_from_meta(meta):
        satisfied = str(read_task_state(meta).get(KEY_SATISFACTION_STATUS) or "").strip().lower() == STATUS_SATISFIED
    args = [str(item).strip() for item in list(step.get("tool_args") or []) if str(item).strip()]
    last_attempt = dict(meta.get("last_attempt") or {}) if isinstance(meta.get("last_attempt"), dict) else {}
    finding_closed = resolution in {"resolved", "retired"} or _status(branch.status) == BranchStatus.COMPLETE.value
    executed = action == "executed"
    real_capability = executed and (not require_args or bool(args))
    admits = action in {"execute", "executed"} or (
        action == "tool_failed" and selected == expected_tool
    )
    if require_args and not args and action == "tool_failed":
        # Empty read admitted as a real read job — category error.
        admits_correctly = False
    elif expected_tool and selected and selected != expected_tool and action in {"executed", "tool_failed"}:
        admits_correctly = False
    else:
        admits_correctly = admits and (selected == expected_tool or not expected_tool)

    observed = {
        "admits_correctly": admits_correctly,
        "selects_authorized_action": bool(selected) and selected in authorized,
        "executes_real_capability": real_capability,
        "produces_verifiable_evidence": len(evidence) > before_evidence,
        "updates_finding_from_evidence": bool(
            (satisfied and not before_satisfied)
            or last_attempt
            or (len(evidence) > before_evidence)
        ),
        "closes_only_when_target_changed": (not finding_closed) or bool(satisfied and not before_satisfied),
        "refuses_when_link_missing": (not finding_closed) if (not satisfied or not real_capability) else True,
    }
    observed["_raw"] = {
        "action": action,
        "selected": selected,
        "task_status": task_status,
        "resolution": resolution,
        "satisfied": satisfied,
        "finding_closed": finding_closed,
        "evidence_n": len(evidence),
        "tool_args": args,
        "before_resolution": before_resolution,
    }
    return observed


def run_empty_read_refusal(db_path: Path) -> dict[str, Any]:
    """Cover stem with read and no target — must not close; admit as read is wrong."""
    work_tree._set_db_path(db_path)
    tree = work_tree.initialize_tree("Inspect loop empty read")
    branch = work_tree._BRANCHES[tree.root_branch_id]
    branch.resolution_state = "open"
    branch.work_class = "release_readiness_gap"
    task = work_tree.add_task_to_branch(
        branch.branch_id,
        "Meta continuity: unresolved finding has no actionable stem",
        meta={
            "recurring_finding_key": "inspect:empty-read",
            "expected_tool": "read",
            "allowed_tools": ["read"],
        },
    )
    work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["read"], require_explicit_allow=True)
    work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
    before = (str(branch.resolution_state or ""), False, len(work_tree.list_branch_evidence(branch.branch_id) or []))
    step = work_tree.execute_autonomous_step(
        tree.tree_id,
        execute_planned_action_fn=lambda tool, args=None: {"ok": True, "text": "should not run"},
    )
    task = work_tree._TASKS[task.task_id]
    observed = _observe_after_step(
        branch=branch,
        task=task,
        step=step or {},
        authorized={"read"},
        expected_tool="read",
        require_args=True,
        before_resolution=before[0],
        before_satisfied=before[1],
        before_evidence=before[2],
    )
    action = str((step or {}).get("action") or "")
    # Category error: mill admitted a read job that did not exist.
    observed["admits_correctly"] = action not in {"executed", "tool_failed"}
    expected = {
        "admits_correctly": True,
        "selects_authorized_action": False,
        "executes_real_capability": False,
        "produces_verifiable_evidence": False,
        "updates_finding_from_evidence": False,
        "closes_only_when_target_changed": True,
        "refuses_when_link_missing": True,
    }
    links = _link_score(observed=observed, expected=expected)
    raw = dict(observed.pop("_raw", {}))
    return {
        "sample": "refuse_empty_read_is_not_a_real_job",
        "step": {k: (step or {}).get(k) for k in ("action", "tool", "tool_args", "error", "task_close")},
        "links": links,
        "observed": {k: observed[k] for k in LINKS},
        "expected": expected,
        "raw": raw,
        "justified_loop": all(links.values()),
    }


def run_close_when_thinning_changes_target(db_path: Path) -> dict[str, Any]:
    """Authorized thinning that actually closes a stage — finding may close."""
    work_tree._set_db_path(db_path)
    tree = work_tree.initialize_tree("Inspect loop thinning close")
    branch = work_tree._BRANCHES[tree.root_branch_id]
    branch.resolution_state = "open"
    task = work_tree.add_task_to_branch(
        branch.branch_id,
        "Review wrapper shim leftover",
        meta={
            "kind": "wrapper_candidate",
            "recurring_finding_key": "core_thinning:inspect-wrapper",
            "expected_tool": "core_thinning",
            "allowed_tools": ["core_thinning"],
        },
    )
    work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["core_thinning"], require_explicit_allow=True)
    work_tree.set_branch_tools(branch.branch_id, allowed_tools=["core_thinning"], preferred_tool="core_thinning")
    before_sat = False
    before_ev = len(work_tree.list_branch_evidence(branch.branch_id) or [])
    step = work_tree.execute_autonomous_step(
        tree.tree_id,
        execute_planned_action_fn=lambda tool, args=None: {
            "ok": True,
            "verified": True,
            "action": "removed_unused_wrapper",
        },
    )
    task = work_tree._TASKS[task.task_id]
    observed = _observe_after_step(
        branch=branch,
        task=task,
        step=step or {},
        authorized={"core_thinning"},
        expected_tool="core_thinning",
        require_args=False,
        before_resolution="open",
        before_satisfied=before_sat,
        before_evidence=before_ev,
    )
    expected = {name: True for name in LINKS}
    links = _link_score(observed=observed, expected=expected)
    raw = dict(observed.pop("_raw", {}))
    return {
        "sample": "close_when_thinning_changes_target",
        "step": {k: (step or {}).get(k) for k in ("action", "tool", "tool_args", "error", "task_close")},
        "links": links,
        "observed": {k: observed[k] for k in LINKS},
        "expected": expected,
        "raw": raw,
        "justified_loop": all(links.values()),
    }


def run_refuse_close_on_unsatisfied_read(db_path: Path, target_file: Path) -> dict[str, Any]:
    """Real read of a real file. Finding stays open unless mill stamps satisfaction."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("inspect-loop-marker\n", encoding="utf-8")
    work_tree._set_db_path(db_path)
    tree = work_tree.initialize_tree("Inspect loop unsatisfied read")
    branch = work_tree._BRANCHES[tree.root_branch_id]
    branch.resolution_state = "open"
    task = work_tree.add_task_to_branch(
        branch.branch_id,
        f"Read {target_file.name}",
        meta={
            "recurring_finding_key": "inspect:unsatisfied-read",
            "expected_tool": "read",
            "allowed_tools": ["read"],
            "tool_args": [str(target_file)],
        },
    )
    work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["read"], require_explicit_allow=True)
    work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
    before_ev = len(work_tree.list_branch_evidence(branch.branch_id) or [])
    step = work_tree.execute_autonomous_step(
        tree.tree_id,
        execute_planned_action_fn=lambda tool, args=None: target_file.read_text(encoding="utf-8"),
    )
    task = work_tree._TASKS[task.task_id]
    observed = _observe_after_step(
        branch=branch,
        task=task,
        step=step or {},
        authorized={"read"},
        expected_tool="read",
        require_args=True,
        before_resolution="open",
        before_satisfied=False,
        before_evidence=before_ev,
    )
    expected = {
        "admits_correctly": True,
        "selects_authorized_action": True,
        "executes_real_capability": True,
        "produces_verifiable_evidence": True,
        "updates_finding_from_evidence": True,
        "closes_only_when_target_changed": True,
        "refuses_when_link_missing": True,
    }
    links = _link_score(observed=observed, expected=expected)
    raw = dict(observed.pop("_raw", {}))
    return {
        "sample": "refuse_close_when_read_does_not_satisfy",
        "step": {k: (step or {}).get(k) for k in ("action", "tool", "tool_args", "error", "task_close")},
        "links": links,
        "observed": {k: observed[k] for k in LINKS},
        "expected": expected,
        "raw": raw,
        "justified_loop": all(links.values()),
    }


def run_frozen_suite(tmp_root: Path) -> dict[str, Any]:
    tmp_root = Path(tmp_root)
    results = [
        run_empty_read_refusal(_tmp_db(tmp_root)),
        run_close_when_thinning_changes_target(_tmp_db(tmp_root)),
        run_refuse_close_on_unsatisfied_read(_tmp_db(tmp_root), tmp_root / f"marker_{uuid.uuid4().hex}.txt"),
    ]
    return {
        "purpose": "frozen governed Work Tree mission loop",
        "not": ["panels", "routes", "health_percent", "live_branch_76a2bb4e", "prompt_fitting"],
        "samples": results,
        "justified_loop": all(bool(item.get("justified_loop")) for item in results),
        "failed_samples": [item["sample"] for item in results if not item.get("justified_loop")],
    }
