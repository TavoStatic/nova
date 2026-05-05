from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


CORE_HEALTH_WORK_IDENTITY = "system:core-health-brief"
CORE_HEALTH_ALLOWED_TOOLS = [
    "health",
    "system_check",
    "pulse",
    "queue_status",
    "read",
    "find",
    "patch_apply",
    "patch_rollback",
    "update_now",
]


def _compact(value: Any, max_chars: int = 220) -> str:
    text = str(value or "").strip()
    return text[: max(1, int(max_chars))]


def _slug(value: Any) -> str:
    text = _compact(value, 400).lower()
    if not text:
        text = "core-health"
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _priority_rank(priority: str) -> int:
    return {"high": 0, "failure": 0, "warning": 1, "medium": 1, "info": 2, "low": 3}.get(
        str(priority or "").strip().lower(),
        2,
    )


def _tool_from_command(command: str, title: str = "") -> str:
    text = f"{command} {title}".strip().lower()
    if "queue" in text:
        return "queue_status"
    if "pulse" in text or "fallback" in text:
        return "pulse"
    if "rollback" in text:
        return "patch_rollback"
    if "update now" in text or "update" in text:
        return "update_now"
    if "patch" in text or "fix" in text or "repair" in text:
        return "patch_apply"
    if "read" in text or "log" in text or "artifact" in text:
        return "read"
    if "find" in text or "locate" in text:
        return "find"
    if "system" in text or "runtime-status" in text or "doctor" in text:
        return "system_check"
    return "health"


def _order(
    *,
    source: str,
    priority: str,
    title: str,
    reason: str,
    command: str = "",
    recommended_tool: str = "",
    target: dict[str, object] | None = None,
) -> dict[str, object]:
    clean_title = _compact(title, 120) or "Review core health signal"
    clean_reason = _compact(reason, 280)
    clean_command = _compact(command, 120)
    tool = _compact(recommended_tool, 40) or _tool_from_command(clean_command, clean_title)
    signal_seed = "|".join([_compact(source, 80), clean_title, clean_reason, clean_command, tool])
    return {
        "order_id": f"core_health:{_slug(signal_seed)}",
        "source": _compact(source, 80) or "core_health",
        "priority": _compact(priority, 24) or "info",
        "title": clean_title,
        "reason": clean_reason,
        "command": clean_command,
        "recommended_tool": tool,
        "target": dict(target or {}),
    }


def _is_training_pressure_advisory(*, title: str, reason: str, command: str, source: str = "") -> bool:
    text = " ".join([source, title, reason, command]).strip().lower()
    if "fallback" not in text and "training pressure" not in text:
        return False
    if any(token in text for token in ("failed", "failure", "error", "blocked", "degraded", "drift")):
        return False
    return True


def _is_enforced_cleanup_advisory(*, title: str, reason: str, command: str, source: str = "") -> bool:
    text = " ".join([source, title, reason, command]).strip().lower()
    if "cleanup pressure" not in text and "kidney" not in text:
        return False
    if "actively enforcing cleanup" in text or "mode=enforce" in text or "enforcing cleanup" in text:
        return True
    return False


def _is_advisory_order(order: dict[str, object]) -> bool:
    title = str(order.get("title") or "")
    reason = str(order.get("reason") or "")
    command = str(order.get("command") or "")
    source = str(order.get("source") or "")
    return _is_training_pressure_advisory(source=source, title=title, reason=reason, command=command) or _is_enforced_cleanup_advisory(source=source, title=title, reason=reason, command=command)


def build_core_health_brief(
    *,
    core_steward: dict | None = None,
    self_status: dict | None = None,
    runtime_summary: dict | None = None,
    runtime_artifacts: dict | None = None,
    pipeline_summary: dict | None = None,
) -> dict[str, object]:
    """Build a single structured repair brief from existing health surfaces."""

    steward = dict(core_steward or {})
    self_payload = dict(self_status or {})
    runtime = dict(runtime_summary or {})
    artifacts = dict(runtime_artifacts or {})
    pipelines = dict(pipeline_summary or {})

    orders: list[dict[str, object]] = []
    advisories: list[dict[str, object]] = []
    for item in list(steward.get("maintenance_queue") or []):
        if not isinstance(item, dict):
            continue
        order = _order(
            source="core_steward",
            priority=str(item.get("priority") or "info"),
            title=str(item.get("title") or "Review Core Steward item"),
            reason=str(item.get("reason") or ""),
            command=str(item.get("command") or ""),
        )
        if _is_advisory_order(order):
            advisories.append(order)
        else:
            orders.append(order)

    for event in list(self_payload.get("events") or []):
        if not isinstance(event, dict):
            continue
        severity = str(event.get("severity") or "info").strip().lower()
        if severity not in {"failure", "warning"}:
            continue
        order = _order(
            source=str(event.get("source") or "self_status"),
            priority=severity,
            title=str(event.get("title") or "Review Nova self-status event"),
            reason=str(event.get("detail") or ""),
            command=str(event.get("command") or ""),
        )
        if _is_advisory_order(order):
            advisories.append(order)
        else:
            orders.append(order)

    for service_name in ("guard", "core", "webui"):
        status = dict(runtime.get(service_name) or {}) if isinstance(runtime.get(service_name), dict) else {}
        state = str(status.get("status") or "").strip().lower()
        if state in {"boot_timeout", "heartbeat_stale", "stale_identity", "stopping"}:
            orders.append(
                _order(
                    source="runtime_summary",
                    priority="high" if state in {"boot_timeout", "heartbeat_stale"} else "medium",
                    title=f"Resolve {service_name} runtime state",
                    reason=f"{service_name} reports {state}.",
                    command="nova runtime-status",
                    target={"service": service_name, "status": state},
                )
            )

    for artifact in list(artifacts.get("items") or []):
        if not isinstance(artifact, dict):
            continue
        status = str(artifact.get("status") or "").strip().lower()
        if status not in {"stale", "present"}:
            continue
        name = str(artifact.get("name") or "").strip()
        if name not in {"core.heartbeat", "guard.stop"} and status != "stale":
            continue
        orders.append(
            _order(
                source="runtime_artifacts",
                priority="medium" if status == "stale" else "low",
                title=f"Review runtime artifact {name}",
                reason=str(artifact.get("summary") or f"{name} is {status}."),
                command="read runtime artifact",
                target={"artifact": name, "path": str(artifact.get("path") or "")},
            )
        )

    pipeline_worker = dict(pipelines.get("worker") or {}) if isinstance(pipelines.get("worker"), dict) else {}
    worker_status = str(pipeline_worker.get("status") or pipeline_worker.get("last_cycle_status") or "").strip().lower()
    if worker_status and worker_status not in {"ok", "running", "idle"}:
        orders.append(
            _order(
                source="pipeline_summary",
                priority="medium",
                title="Review data-lane worker status",
                reason=f"Data-lane worker reports {worker_status}.",
                command="pipeline status",
                target={"worker_status": worker_status},
            )
        )

    deduped: dict[str, dict[str, object]] = {}
    for item in orders:
        deduped[str(item.get("order_id") or "")] = item
    ordered = sorted(deduped.values(), key=lambda item: (_priority_rank(str(item.get("priority") or "")), str(item.get("title") or "")))
    advisory_deduped: dict[str, dict[str, object]] = {}
    for item in advisories:
        advisory_deduped[str(item.get("order_id") or "")] = item
    ordered_advisories = sorted(advisory_deduped.values(), key=lambda item: (_priority_rank(str(item.get("priority") or "")), str(item.get("title") or "")))

    steward_level = str(steward.get("level") or "").strip().lower()
    self_level = str(self_payload.get("level") or "").strip().lower()
    if any(str(item.get("priority") or "").lower() in {"high", "failure"} for item in ordered) or steward_level == "repair" or self_level == "failed":
        level = "repair"
    elif ordered or steward_level == "watch":
        level = "watch"
    else:
        level = "steady"

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "summary": "core repair signals queued" if ordered else ("core health clear; advisories recorded" if ordered_advisories else "core health signals are clear"),
        "source_levels": {
            "core_steward": steward_level or "unknown",
            "self_status": self_level or "unknown",
        },
        "repair_order_count": len(ordered),
        "repair_work_orders": ordered,
        "advisory_count": len(ordered_advisories),
        "advisories": ordered_advisories,
    }


def write_core_health_brief(path: Path, brief: dict[str, object]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(brief, ensure_ascii=True, indent=2), encoding="utf-8")


def render_core_health_brief(brief: dict | None = None, *, feed_result: dict | None = None) -> str:
    data = dict(brief or {})
    orders = list(data.get("repair_work_orders") or [])
    advisories = list(data.get("advisories") or [])
    lines = [
        f"Core Health Brief - {data.get('generated_at') or ''}",
        f"Level: {data.get('level') or 'unknown'}",
        f"Summary: {data.get('summary') or 'No summary available.'}",
        f"Repair orders: {int(data.get('repair_order_count', len(orders)) or 0)}",
        f"Advisories: {int(data.get('advisory_count', len(advisories)) or 0)}",
    ]
    if isinstance(feed_result, dict) and feed_result:
        lines.append(
            "Work tree: "
            f"{feed_result.get('status') or 'unknown'}"
            f" | tree={feed_result.get('tree_id') or '-'}"
            f" | added={int(feed_result.get('added_count', 0) or 0)}"
            f" | deduped={int(feed_result.get('deduped_count', 0) or 0)}"
            f" | resolved={int(feed_result.get('resolved_count', 0) or 0)}"
        )

    if not orders:
        lines.append("Signals:")
        lines.append("- No repair work orders are open.")
        for item in advisories[:8]:
            reason = _compact(item.get("reason"), 180)
            lines.append(f"- [ADVISORY] {item.get('title')}: {reason}" if reason else f"- [ADVISORY] {item.get('title')}")
        return "\n".join(lines)

    lines.append("Repair work orders:")
    for index, item in enumerate(orders[:12], start=1):
        lines.append(
            f"{index}. [{str(item.get('priority') or 'info').upper()}] {item.get('title')}"
            f" (tool: {item.get('recommended_tool') or 'health'})"
        )
        reason = _compact(item.get("reason"), 220)
        if reason:
            lines.append(f"   reason: {reason}")
    return "\n".join(lines)


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _active_core_health_tree(work_tree_module):
    if hasattr(work_tree_module, "reload_persisted_state"):
        work_tree_module.reload_persisted_state()
    for tree in list(work_tree_module.list_trees() or []):
        meta = dict(getattr(tree, "meta", {}) or {})
        if str(meta.get("work_identity_key") or "").strip() != CORE_HEALTH_WORK_IDENTITY:
            continue
        if _status_value(getattr(tree, "status", "")) == "archived":
            continue
        return tree
    return None


def _resolve_stale_core_health_tasks(work_tree_module, tree, active_order_ids: set[str]) -> int:
    resolved_count = 0
    for task in list(work_tree_module.list_tree_tasks(tree.tree_id) or []):
        meta = dict(getattr(task, "meta", {}) or {})
        order_id = str(meta.get("core_health_order_id") or "").strip()
        status = _status_value(getattr(task, "status", ""))
        if not order_id or status in {"complete", "dropped"} or order_id in active_order_ids:
            continue
        work_tree_module.mark_task_complete(task.task_id)
        resolved_count += 1
    return resolved_count


def feed_core_health_brief_to_work_tree(brief: dict[str, object], *, work_tree_module) -> dict[str, object]:
    """Create or update the dedicated Core Health work tree from repair orders."""

    orders = [dict(item) for item in list((brief or {}).get("repair_work_orders") or []) if isinstance(item, dict)]
    active_order_ids = {str(item.get("order_id") or "").strip() for item in orders if str(item.get("order_id") or "").strip()}
    tree = _active_core_health_tree(work_tree_module)
    if not orders:
        resolved_count = _resolve_stale_core_health_tasks(work_tree_module, tree, active_order_ids) if tree is not None else 0
        return {
            "ok": True,
            "status": "clear",
            "tree_id": str(getattr(tree, "tree_id", "") or "") if tree is not None else "",
            "created": False,
            "added_count": 0,
            "deduped_count": 0,
            "resolved_count": resolved_count,
        }

    created = False
    if tree is None:
        tree = work_tree_module.initialize_tree(
            "Core Health Brief",
            meta={
                "work_identity_key": CORE_HEALTH_WORK_IDENTITY,
                "work_identity_label": "core health",
                "source": "core_health_brief",
                "execution_policy": {
                    "allowed_tools": list(CORE_HEALTH_ALLOWED_TOOLS),
                    "require_explicit_allow": True,
                },
            },
        )
        created = True
    elif hasattr(work_tree_module, "set_tree_execution_policy"):
        work_tree_module.set_tree_execution_policy(
            tree.tree_id,
            allowed_tools=list(CORE_HEALTH_ALLOWED_TOOLS),
            require_explicit_allow=True,
        )

    existing_order_ids: set[str] = set()
    for task in list(work_tree_module.list_tree_tasks(tree.tree_id) or []):
        meta = dict(getattr(task, "meta", {}) or {})
        order_id = str(meta.get("core_health_order_id") or "").strip()
        status = _status_value(getattr(task, "status", ""))
        if order_id and status not in {"complete", "dropped"}:
            existing_order_ids.add(order_id)
    resolved_count = _resolve_stale_core_health_tasks(work_tree_module, tree, active_order_ids)

    root = work_tree_module.get_branch(tree.root_branch_id)
    added_count = 0
    deduped_count = 0
    for order in orders:
        order_id = str(order.get("order_id") or "").strip()
        if not order_id or order_id in existing_order_ids:
            deduped_count += 1
            continue
        title = _compact(order.get("title"), 90) or "Review core health signal"
        branch = work_tree_module.add_branch_to_tree(tree.tree_id, title, "core_health", getattr(root, "branch_id", None))
        task_title = f"{title}: {_compact(order.get('reason'), 140)}".strip(": ")
        task = work_tree_module.add_task_to_branch(
            branch.branch_id,
            task_title,
            meta={
                "core_health_order_id": order_id,
                "source": str(order.get("source") or ""),
                "priority": str(order.get("priority") or ""),
                "command": str(order.get("command") or ""),
                "target": dict(order.get("target") or {}) if isinstance(order.get("target"), dict) else {},
            },
        )
        tool = str(order.get("recommended_tool") or "health").strip()
        if tool not in CORE_HEALTH_ALLOWED_TOOLS:
            tool = "health"
        work_tree_module.set_branch_tools(branch.branch_id, allowed_tools=[tool], preferred_tool=tool)
        existing_order_ids.add(order_id)
        added_count += 1

    return {
        "ok": True,
        "status": "seeded" if added_count else "deduped",
        "tree_id": str(getattr(tree, "tree_id", "") or ""),
        "created": created,
        "added_count": added_count,
        "deduped_count": deduped_count,
        "resolved_count": resolved_count,
    }
