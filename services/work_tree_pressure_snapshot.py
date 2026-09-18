from __future__ import annotations

from typing import Any

from services.type_utils import _as_dict, _as_int, _as_list, _text
from services.work_tree_operator_hold import node_is_operator_hold


def _branches_from_counts(counts: dict, *, fallback: int = 0) -> int:
    """Accept either a branch total or the per-status dict the visual tree uses."""
    raw = counts.get("branches") if isinstance(counts, dict) else None
    if isinstance(raw, dict):
        total = sum(_as_int(value, 0) for value in raw.values())
        if total:
            return total
    numbered = _as_int(raw, 0)
    if numbered:
        return numbered
    return fallback


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _enum_value(value: Any) -> str:
    return _text(getattr(value, "value", value), 120)


def _branch_total(tree_payload: dict) -> int:
    counts = _as_dict(tree_payload.get("counts"))
    branch_counts = _as_dict(counts.get("branches"))
    if branch_counts:
        return sum(_as_int(value, 0) for value in branch_counts.values())
    return _as_int(counts.get("branches"), 0)


def _current_task_payload(tasks: list[Any]) -> dict:
    open_tasks = [
        task for task in tasks
        if _enum_value(getattr(task, "status", "")).lower() not in {"complete", "dropped"}
    ]
    open_tasks.sort(
        key=lambda task: (
            getattr(task, "created_at", None) is None,
            str(getattr(task, "created_at", "")),
            str(getattr(task, "task_id", "")),
        )
    )
    if not open_tasks:
        return {}
    task = open_tasks[0]
    return {
        "task_id": _text(getattr(task, "task_id", ""), 120),
        "title": _text(getattr(task, "title", ""), 240),
        "status": _enum_value(getattr(task, "status", "")),
        "meta": _as_dict(getattr(task, "meta", {})),
    }


def _node_from_branch(branch: Any, current_task: dict) -> dict:
    return {
        "id": _text(getattr(branch, "branch_id", ""), 120),
        "title": _text(getattr(branch, "title", ""), 240),
        "status": _enum_value(getattr(branch, "status", "")),
        "source_type": _text(getattr(branch, "source_type", ""), 120),
        "source_key": _text(getattr(branch, "source_key", ""), 200),
        "source_payload": _as_dict(getattr(branch, "source_payload", {})),
        "work_class": _text(getattr(branch, "work_class", ""), 120),
        "actionability": _text(getattr(branch, "actionability", ""), 80),
        "resolution_state": _text(getattr(branch, "resolution_state", ""), 80),
        "current_task": current_task or None,
    }


def _release_stale_ready_node(node: dict) -> bool:
    if _text(node.get("status"), 80).lower() != "ready":
        return False
    current_task = _as_dict(node.get("current_task"))
    branch_title = _text(node.get("title"), 240).lower()
    task_title = _text(current_task.get("title"), 240).lower()
    haystack = f"{branch_title}\n{task_title}"
    return any(
        token in haystack
        for token in (
            "release-stale",
            "release stale",
            "validation outcome is missing",
        )
    )


def _pressure_from_nodes(
    *,
    counts: dict,
    nodes: list[dict],
    total_trees: int,
    active_trees: int,
    stale_count: int = 0,
    oldest_open_age_min: int = 0,
    branches: list[dict] | None = None,
) -> dict:
    open_task_count = _as_int(counts.get("open_tasks"), 0)
    pending_count = _as_int(counts.get("pending"), 0)
    working_count = _as_int(counts.get("working"), 0)
    blocked_count = _as_int(counts.get("blocked"), 0)
    complete_count = _as_int(counts.get("complete"), 0)
    branch_count = _branches_from_counts(counts, fallback=len(nodes))
    if branch_count <= 0 and nodes:
        branch_count = len(nodes)

    observing_count = 0
    blocked_observing_count = 0
    operator_hold_count = 0
    self_repair_blocked_count = 0
    self_repair_observing_count = 0
    latent_root_signal_count = 0
    release_stale_ready_count = 0

    for node in nodes:
        if not isinstance(node, dict):
            continue
        status_text = _text(node.get("status"), 80).lower()
        resolution_text = _text(node.get("resolution_state"), 80).lower()
        operator_hold = node_is_operator_hold(node)
        if operator_hold:
            operator_hold_count += 1
        elif status_text == "blocked":
            self_repair_blocked_count += 1
        if _release_stale_ready_node(node):
            release_stale_ready_count += 1
        if resolution_text == "observing" and status_text not in {"complete", "archived"}:
            observing_count += 1
            if status_text == "blocked":
                blocked_observing_count += 1
            if not operator_hold:
                self_repair_observing_count += 1
                if (
                    status_text == "blocked"
                    and _text(node.get("source_type"), 120).lower() == "subconscious"
                    and _text(node.get("work_class"), 120).lower() == "candidate_review"
                ):
                    latent_root_signal_count += 1

    if self_repair_blocked_count > 0 or self_repair_observing_count > 0:
        status = "blocked_observing"
    elif operator_hold_count > 0:
        status = "operator_hold"
    elif open_task_count > 0 or pending_count > 0 or working_count > 0:
        status = "open"
    else:
        status = "clear"

    snapshot = {
        "status": status,
        "tree_count": total_trees,
        "active_tree_count": active_trees,
        "branch_count": branch_count,
        "open_task_count": open_task_count,
        "pending_count": pending_count,
        "working_count": working_count,
        "blocked_count": blocked_count,
        "blocked_branch_count": blocked_count,
        "complete_count": complete_count,
        "operator_hold_count": operator_hold_count,
        "operator_hold_branch_count": operator_hold_count,
        "self_repair_blocked_count": self_repair_blocked_count,
        "self_repair_blocked_branch_count": self_repair_blocked_count,
        "self_repair_observing_count": self_repair_observing_count,
        "self_repair_observing_branch_count": self_repair_observing_count,
        "observing_count": observing_count,
        "observing_branch_count": observing_count,
        "blocked_observing_count": blocked_observing_count,
        "latent_root_signal_count": latent_root_signal_count,
        "release_stale_ready_count": release_stale_ready_count,
        "stale_count": stale_count,
        "oldest_open_age_min": oldest_open_age_min,
    }
    if branches is not None:
        snapshot["branches"] = list(branches)
    return snapshot


def build_work_tree_pressure_snapshot(work_trees_payload: dict | None, *, branches: list[dict] | None = None) -> dict:
    payload = _as_dict(work_trees_payload)
    counts = _as_dict(payload.get("counts"))
    nodes: list[dict] = []
    tree_branch_total = 0
    tree_open_total = 0
    tree_rows = _as_list(payload.get("trees"))
    for tree in tree_rows:
        tree_payload = _as_dict(tree)
        tree_branch_total += _branch_total(tree_payload)
        tree_open_total += _as_int(_as_dict(tree_payload.get("counts")).get("open_tasks"), 0)
        nodes.extend([node for node in _as_list(tree_payload.get("nodes")) if isinstance(node, dict)])
    normalized_counts = {
        "total": _as_int(counts.get("total"), len(tree_rows)),
        "active": _as_int(counts.get("active"), 0),
        "branches": _branches_from_counts(counts, fallback=tree_branch_total or len(nodes)),
        "open_tasks": _as_int(counts.get("open_tasks"), 0) or tree_open_total,
        "working": _as_int(counts.get("working"), 0),
        "pending": _as_int(counts.get("pending"), 0),
        "blocked": _as_int(counts.get("blocked"), 0),
        "complete": _as_int(counts.get("complete"), 0),
        "stale": _as_int(counts.get("stale"), 0),
        "oldest_open_age_min": _as_int(counts.get("oldest_open_age_min"), 0),
    }
    return _pressure_from_nodes(
        counts=normalized_counts,
        nodes=nodes,
        total_trees=normalized_counts["total"],
        active_trees=normalized_counts["active"],
        stale_count=normalized_counts["stale"],
        oldest_open_age_min=normalized_counts["oldest_open_age_min"],
        branches=branches,
    )


def build_work_tree_pressure_snapshot_from_module(work_tree_module: Any) -> dict:
    trees = list(work_tree_module.list_trees())
    nodes: list[dict] = []
    branch_count = 0
    open_task_count = 0
    pending_count = 0
    working_count = 0
    blocked_count = 0
    complete_count = 0
    active_tree_count = 0

    for tree in trees:
        tree_status = _enum_value(getattr(tree, "status", "")).lower()
        if tree_status == "active":
            active_tree_count += 1
        branches = list(work_tree_module.list_tree_branches(getattr(tree, "tree_id", "")))
        branch_count += len(branches)
        for branch in branches:
            branch_status = _enum_value(getattr(branch, "status", "")).lower()
            if branch_status == "active":
                working_count += 1
            elif branch_status == "ready":
                pending_count += 1
            elif branch_status == "blocked":
                blocked_count += 1
            elif branch_status == "complete":
                complete_count += 1
            tasks = list(work_tree_module.list_branch_tasks(getattr(branch, "branch_id", "")))
            open_task_count += sum(
                1
                for task in tasks
                if _enum_value(getattr(task, "status", "")).lower() not in {"complete", "dropped"}
            )
            nodes.append(_node_from_branch(branch, _current_task_payload(tasks)))

    return _pressure_from_nodes(
        counts={
            "branches": branch_count,
            "open_tasks": open_task_count,
            "working": working_count,
            "pending": pending_count,
            "blocked": blocked_count,
            "complete": complete_count,
        },
        nodes=nodes,
        total_trees=len(trees),
        active_trees=active_tree_count,
    )
