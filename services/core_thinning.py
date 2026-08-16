from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from services.nova_runtime_context import RUNTIME_DIR
from services.recurring_finding_lifecycle import (
    DECISION_ACTIVE,
    DECISION_ACTIVE_UPDATE,
    DECISION_INACTIVE_RESOLVE,
    DECISION_REOPEN,
    DECISION_SATISFIED,
    DECISION_SKIP,
    KEY_FINDING,
    KEY_SATISFACTION_FINGERPRINT,
    REOPEN_RECURRING_PRESSURE,
    classify_task_meta,
    fingerprint_from_parts,
    finding_key_from_meta,
    initial_task_meta,
    reopen_task_meta,
    stamp_satisfaction,
    summarize_feed_pressure,
    update_open_fingerprint,
)


CORE_THINNING_WORK_IDENTITY = "system:core-thinning"
CORE_THINNING_ALLOWED_TOOLS = ["core_thinning", "read", "find", "patch_apply", "system_check", "health"]
CORE_THINNING_PUBLIC_ADAPTER_NAMES = {
    "clear_runtime_device_location",
    "render_nova_pulse",
    "speak_chunked",
    "update_now_pending_payload",
    "write_action_ledger_record",
}

_REPO_SCAN_EXCLUDED_DIRS = frozenset({
    ".git",
    ".github",
    ".venv",
    ".ci_venv",
    ".pytest_cache",
    "__pycache__",
    "agent-tools",
    "logs",
    "memory",
    "runtime",
    "terminals",
    "updates",
})

_CORE_ATTRIBUTE_BASE_NAMES = frozenset({"nova_core", "core", "core_module"})


def _protected_public_wrapper_names() -> set[str]:
    names = set(CORE_THINNING_PUBLIC_ADAPTER_NAMES)
    try:
        from services.nova_tool_dispatch import _PLANNED_TOOL_NAMES

        names.update(str(item or "").strip() for item in _PLANNED_TOOL_NAMES)
    except Exception:
        pass
    try:
        from services.nova_action_ledger import _FINALIZE_ACTION_LEDGER_RECORD_HOOKS

        names.update(str(item or "").strip() for item in _FINALIZE_ACTION_LEDGER_RECORD_HOOKS.values())
    except Exception:
        pass
    return {str(name or "").strip() for name in names if str(name or "").strip()}


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower() or "core-thinning"
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _priority_rank(value: Any) -> int:
    return {"high": 0, "medium": 1, "low": 2, "info": 3}.get(str(value or "").strip().lower(), 4)


def _branch_priority(value: Any) -> int:
    return {"high": 90, "medium": 70, "low": 40, "info": 20}.get(str(value or "").strip().lower(), 50)


HTTP_ORDER_KINDS = frozenset({"http_surface_candidate", "http_surface_extract"})


def _normalized_target_file(target: dict[str, object] | None) -> str:
    file_name = str((target or {}).get("file") or "").replace("\\", "/").strip()
    return Path(file_name).name.lower()


def _target_semantic_key(kind: Any, target: dict[str, object] | None) -> str:
    data = dict(target or {})
    kind_text = str(kind or "").strip().lower()
    file_name = _normalized_target_file(data)
    if kind_text in HTTP_ORDER_KINDS:
        theme = str(data.get("theme") or "").strip().lower()
        return "|".join([kind_text, file_name, theme])
    name = str(data.get("name") or data.get("function") or "").strip().lower()
    wrapped = str(data.get("wrapped_call") or "").strip().lower()
    return "|".join([kind_text, file_name, name, wrapped])


def _core_thinning_order_task_fields(
    order: dict[str, object],
    *,
    brief: dict[str, object] | None = None,
) -> dict[str, object]:
    target = _normalize_core_thinning_target(order)
    return {
        "kind": str(order.get("kind") or ""),
        "priority": str(order.get("priority") or ""),
        "reason": str(order.get("reason") or ""),
        "scope": "single_block_only",
        "target": target,
        "core_thinning_brief_generated_at": str((brief or {}).get("generated_at") or ""),
    }


def _order_satisfaction_key(order: dict[str, object] | None) -> str:
    data = dict(order or {})
    target = dict(data.get("target") or {}) if isinstance(data.get("target"), dict) else {}
    kind_text = str(data.get("kind") or "").strip().lower()
    parts = [kind_text, _target_semantic_key(kind_text, target)]
    if kind_text not in HTTP_ORDER_KINDS:
        parts.append(str(target.get("wrapped_call") or "").strip().lower())
    return fingerprint_from_parts(parts)


def is_http_extract_stage_block(result: dict[str, object] | None) -> bool:
    payload = dict(result or {}) if isinstance(result, dict) else {}
    action = str(payload.get("action") or "").strip().lower()
    reason = str(payload.get("reason") or "").strip().lower()
    return action == "blocked_http_extraction" or reason == "http_extraction_not_implemented"


def _repair_core_thinning_task_meta(
    task: object,
    meta: dict[str, object],
    order: dict[str, object],
    *,
    brief: dict[str, object],
    work_tree_module,
) -> dict[str, object]:
    if not order:
        return dict(meta or {})
    payload = dict(meta or {})
    order_fields = _core_thinning_order_task_fields(order, brief=brief)
    if any(payload.get(key) != value for key, value in order_fields.items()):
        payload.update(order_fields)
        setattr(task, "meta", payload)
        if hasattr(work_tree_module, "touch_branch"):
            work_tree_module.touch_branch(getattr(task, "branch_id"))
    # Do not restamp a historical productive action onto a new fingerprint.
    # If the current scan still sees this order, classify/reopen must decide.
    return payload


def _clear_failed_core_thinning_tool(work_tree_module, task: object) -> None:
    get_branch = getattr(work_tree_module, "get_branch", None)
    if not callable(get_branch):
        return
    branch = get_branch(getattr(task, "branch_id", ""))
    if branch is None or not isinstance(getattr(branch, "tool_state", None), dict):
        return
    raw = branch.tool_state.get("core_thinning")
    if str(getattr(raw, "value", raw) or "").strip().lower() != "failed":
        return
    try:
        from work_tree_contracts import ToolStatus

        branch.tool_state["core_thinning"] = ToolStatus.READY
    except Exception:
        branch.tool_state["core_thinning"] = "ready"
    touch = getattr(work_tree_module, "touch_branch", None)
    if callable(touch):
        touch(getattr(branch, "branch_id", ""))


def _close_unimplemented_http_extract(work_tree_module, task: object) -> None:
    stamp_core_thinning_task_satisfaction(
        task,
        {
            "ok": False,
            "blocked": True,
            "action": "blocked_http_extraction",
            "reason": "http_extraction_not_implemented",
        },
    )
    mark_complete = getattr(work_tree_module, "mark_task_complete", None)
    if callable(mark_complete):
        mark_complete(getattr(task, "task_id", ""))
    _clear_failed_core_thinning_tool(work_tree_module, task)


def stamp_core_thinning_task_satisfaction(task: object, result: dict[str, object] | None) -> None:
    """Record completion evidence on a core-thinning task before it is marked complete."""
    payload = dict(result or {})
    extract_block = is_http_extract_stage_block(payload)
    if not bool(payload.get("ok")) and not extract_block:
        return
    meta = dict(getattr(task, "meta", {}) or {}) if isinstance(getattr(task, "meta", None), dict) else {}
    order = {
        "kind": str(meta.get("kind") or ""),
        "reason": str(meta.get("reason") or ""),
        "target": dict(meta.get("target") or {}) if isinstance(meta.get("target"), dict) else {},
    }
    action = str(payload.get("action") or "").strip()
    if extract_block and not action:
        action = "blocked_http_extraction"
    setattr(
        task,
        "meta",
        stamp_satisfaction(
            meta,
            satisfaction_fingerprint=_order_satisfaction_key(order),
            completion_action=action,
            ok=True,
        ),
    )


def _normalize_core_thinning_target(order: dict[str, object]) -> dict[str, object]:
    target = dict(order.get("target") or {}) if isinstance(order.get("target"), dict) else {}
    if target:
        target.setdefault("function", str(target.get("name") or ""))
        target.setdefault("block", str(order.get("kind") or "core_thinning"))
    return target


def _reopen_core_thinning_task(
    work_tree_module,
    task: object,
    order: dict[str, object],
    *,
    brief: dict[str, object],
) -> None:
    target = _normalize_core_thinning_target(order)
    prior_meta = dict(getattr(task, "meta", {}) or {}) if isinstance(getattr(task, "meta", None), dict) else {}
    order_id = str(order.get("order_id") or finding_key_from_meta(prior_meta) or "")
    meta_updates = reopen_task_meta(
        prior_meta,
        finding_key=order_id,
        satisfaction_fingerprint=_order_satisfaction_key(order),
        reason=REOPEN_RECURRING_PRESSURE,
        extra=_core_thinning_order_task_fields(order, brief=brief),
    )
    if hasattr(work_tree_module, "reopen_task"):
        work_tree_module.reopen_task(getattr(task, "task_id"), meta_updates=meta_updates)
    branch = work_tree_module.get_branch(getattr(task, "branch_id")) if hasattr(work_tree_module, "get_branch") else None
    if branch is not None:
        branch.priority = _branch_priority(order.get("priority"))
        work_tree_module.touch_branch(getattr(task, "branch_id"))


def _function_span(node: ast.AST) -> int:
    start = int(getattr(node, "lineno", 0) or 0)
    end = int(getattr(node, "end_lineno", start) or start)
    return max(1, end - start + 1)


def _called_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = [func.attr]
        value = func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _return_call_name(node: ast.AST) -> str:
    if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Call):
        return ""
    return _called_name(node.value)


def _is_service_wrapper(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = [item for item in list(node.body or []) if not isinstance(item, ast.Expr) or not isinstance(getattr(item, "value", None), ast.Constant)]
    if len(body) != 1:
        return ""
    called = _return_call_name(body[0])
    if called.startswith("service_"):
        return called
    return ""


def _is_pure_delegation_wrapper(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when the function body is only a single call (return or statement).

    These are already-extracted shims. Counting them as HTTP extraction mass
    invents false thinning pressure after ownership has moved into services.
    """
    body = [
        item
        for item in list(node.body or [])
        if not isinstance(item, ast.Expr) or not isinstance(getattr(item, "value", None), ast.Constant)
    ]
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return True
    return False


def _function_bounds(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, int]:
    start = int(getattr(node, "lineno", 0) or 0)
    end = int(getattr(node, "end_lineno", start) or start)
    return start, end


def _functions_named(tree: ast.AST, name: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    clean_name = str(name or "").strip()
    if not clean_name:
        return []
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == clean_name
    ]


def _http_surface_theme(name: str) -> str:
    clean = str(name or "").strip().lstrip("_")
    if not clean:
        return ""
    if clean.startswith("pipeline_") or clean.startswith("control_pipelines") or "_pipeline_" in clean:
        return "pipeline_control"
    if clean.startswith("chat_") or clean.startswith("session_") or "_session" in clean or "chat_session" in clean:
        return "chat_sessions"
    if clean.startswith("control_") or "_control_" in clean or clean.startswith("guard_") or clean.startswith("core_") or clean.startswith("runtime_"):
        return "runtime_control"
    if clean.startswith("generated_") or "generated_queue" in clean or "test_session" in clean:
        return "generated_work"
    if clean.startswith("policy_") or "web_mode" in clean or "search_provider" in clean or "search_endpoint" in clean:
        return "policy_search"
    if clean.startswith("artifact_") or "artifact" in clean or "timeline" in clean or "metrics" in clean:
        return "runtime_observability"
    if clean.startswith("developer_") or clean.startswith("assistant_") or clean.startswith("location_") or clean.startswith("color_") or clean.startswith("animal_"):
        return "chat_reply_helpers"
    return clean.split("_", 1)[0] if "_" in clean else ""


def _http_surface_candidates(path: Path, functions: list[dict[str, object]], *, limit: int = 8) -> list[dict[str, object]]:
    if "http" not in path.stem.lower():
        return []
    # Only remaining non-shim mass is extraction pressure. Pure single-call
    # delegations already live in services; clustering them reopens forever.
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in functions:
        name = str(item.get("name") or "")
        if "." in name:
            continue
        if bool(item.get("pure_wrapper")):
            continue
        theme = _http_surface_theme(name)
        if not theme or theme in {"is", "parse", "safe", "read", "render", "build", "load"}:
            continue
        grouped.setdefault(theme, []).append(dict(item))

    candidates: list[dict[str, object]] = []
    for theme, rows in grouped.items():
        rows.sort(key=lambda item: int(item.get("start_line", 0) or 0))
        clusters: list[list[dict[str, object]]] = []
        current: list[dict[str, object]] = []
        previous_end = 0
        for row in rows:
            start = int(row.get("start_line", 0) or 0)
            current_start = int(current[0].get("start_line", start) or start) if current else start
            if current and (start - previous_end > 90 or start - current_start > 220):
                clusters.append(current)
                current = []
            current.append(row)
            previous_end = int(row.get("end_line", start) or start)
        if current:
            clusters.append(current)

        for cluster_index, cluster_rows in enumerate(clusters, start=1):
            # Require real remaining body mass, not a handful of thin adapters.
            if len(cluster_rows) < 3:
                continue
            start_line = int(cluster_rows[0].get("start_line", 0) or 0)
            end_line = int(cluster_rows[-1].get("end_line", 0) or 0)
            span = max(1, end_line - start_line + 1)
            total_function_lines = sum(int(row.get("line_count", 0) or 0) for row in cluster_rows)
            if total_function_lines < 40 and span < 80:
                continue
            label = theme if len(clusters) == 1 else f"{theme}:{cluster_index}"
            candidates.append(
                {
                    "name": f"http:{label}",
                    "theme": theme,
                    "cluster": cluster_index,
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": span,
                    "function_count": len(cluster_rows),
                    "function_names": [str(row.get("name") or "") for row in cluster_rows[:20]],
                    "total_function_lines": total_function_lines,
                    "substantive_only": True,
                }
            )
    candidates.sort(
        key=lambda item: (
            -int(item.get("total_function_lines", 0) or 0),
            -int(item.get("function_count", 0) or 0),
            -int(item.get("line_count", 0) or 0),
            str(item.get("theme") or ""),
        )
    )
    return candidates[: max(0, int(limit))]


def _runtime_hook_reference_names(paths: list[Path]) -> set[str]:
    service_dirs = {Path(path).resolve().parent / "services" for path in paths}
    names: set[str] = set()
    for service_dir in service_dirs:
        if not service_dir.exists():
            continue
        for service_file in service_dir.glob("*.py"):
            try:
                tree = ast.parse(service_file.read_text(encoding="utf-8-sig", errors="ignore"))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    for value in list(node.values or []):
                        if isinstance(value, ast.Constant) and isinstance(value.value, str):
                            hook_name = str(value.value or "").strip()
                            if hook_name.isidentifier():
                                names.add(hook_name)
                elif isinstance(node, ast.Call):
                    if _called_name(node) != "_runtime_hook" or len(node.args) < 2:
                        continue
                    hook_name = node.args[1]
                    if isinstance(hook_name, ast.Constant) and isinstance(hook_name.value, str):
                        hook_text = str(hook_name.value or "").strip()
                        if hook_text.isidentifier():
                            names.add(hook_text)
                elif isinstance(node, ast.Attribute):
                    attr = str(node.attr or "").strip()
                    if not attr.isidentifier():
                        continue
                    base = node.value
                    while isinstance(base, ast.Attribute):
                        base = base.value
                    base_name = base.id if isinstance(base, ast.Name) else ""
                    if attr.startswith("_") or base_name in {"core", "core_module", "nova_core"}:
                        names.add(attr)
    return names


def _order(*, kind: str, title: str, reason: str, target: dict[str, object], priority: str = "medium") -> dict[str, object]:
    seed = _target_semantic_key(kind, target) or "|".join([kind, title])
    return {
        "order_id": f"core_thinning:{_slug(seed)}",
        "kind": kind,
        "priority": priority,
        "title": title,
        "reason": reason,
        "recommended_tool": "core_thinning",
        "target": dict(target),
    }


def _core_paths(core_path: Path | list[Path] | tuple[Path, ...]) -> list[Path]:
    if isinstance(core_path, (list, tuple)):
        return [Path(item) for item in core_path]
    return [Path(core_path)]


def _analyze_core_file(
    path: Path,
    *,
    large_function_threshold: int,
    wrapper_limit: int,
    protected_wrapper_names: set[str] | None = None,
) -> dict[str, object]:
    path = Path(path)
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except Exception as exc:
        return {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ok": False,
            "error": str(exc),
            "path": str(path),
            "line_count": 0,
            "function_count": 0,
            "wrapper_candidate_count": 0,
            "large_function_count": 0,
            "http_surface_candidate_count": 0,
            "orders": [],
        }

    line_count = len(source.splitlines())
    functions: list[dict[str, object]] = []
    wrappers: list[dict[str, object]] = []
    large: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        dotted_name = node.name
        for parent in ast.walk(tree):
            if parent is node:
                break
        span = _function_span(node)
        pure_wrapper = _is_pure_delegation_wrapper(node)
        row = {
            "name": dotted_name,
            "start_line": int(getattr(node, "lineno", 0) or 0),
            "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0),
            "line_count": span,
            "pure_wrapper": pure_wrapper,
        }
        functions.append(row)
        wrapped = _is_service_wrapper(node)
        if wrapped:
            wrappers.append({**row, "wrapped_call": wrapped})
        if span >= large_function_threshold:
            large.append(row)

    protected_names = set(protected_wrapper_names or set()) | _protected_public_wrapper_names()
    wrapper_reference_counts = _repo_wide_reference_counts(
        {str(item.get("name") or "") for item in wrappers},
        declaring_path=path,
    )
    actionable_wrappers: list[dict[str, object]] = []
    referenced_wrappers: list[dict[str, object]] = []
    for item in wrappers:
        name = str(item.get("name") or "")
        reference_count = int(wrapper_reference_counts.get(name, 0) or 0)
        hook_protected = name in protected_names
        enriched = {**item, "reference_count": reference_count, "hook_protected": hook_protected}
        if reference_count > 0 or hook_protected:
            referenced_wrappers.append(enriched)
        else:
            actionable_wrappers.append(enriched)

    actionable_wrappers.sort(key=lambda item: (int(item["line_count"]), str(item["name"])))
    referenced_wrappers.sort(key=lambda item: (int(item["line_count"]), str(item["name"])))
    large.sort(key=lambda item: (-int(item["line_count"]), str(item["name"])))
    http_surfaces = _http_surface_candidates(path, functions)

    orders: list[dict[str, object]] = []
    for item in actionable_wrappers[: max(0, int(wrapper_limit))]:
        orders.append(
            _order(
                kind="wrapper_candidate",
                priority="low",
                title=f"Review wrapper shim {item['name']}",
                reason=f"{item['name']} only delegates to {item['wrapped_call']}; it may be safe to collapse after callers are checked.",
                target={"file": str(path), **item},
            )
        )
    for item in large[:6]:
        orders.append(
            _order(
                kind="large_core_surface",
                priority="medium",
                title=f"Map extraction boundary for {item['name']}",
                reason=f"{item['name']} is {item['line_count']} lines inside {path.name}.",
                target={"file": str(path), **item},
            )
        )
    for item in http_surfaces:
        theme = str(item.get("theme") or "http")
        substantive_lines = int(item.get("total_function_lines", 0) or 0)
        function_count = int(item.get("function_count", 0) or 0)
        map_target = {"file": str(path), **item, "block": "http_surface_candidate"}
        orders.append(
            _order(
                kind="http_surface_candidate",
                priority="medium",
                title=f"Map HTTP extraction boundary: {theme}",
                reason=(
                    f"{theme} still has {substantive_lines} non-shim lines across "
                    f"{function_count} substantive functions inside {path.name}; "
                    f"map this remaining cluster before extraction."
                ),
                target=map_target,
            )
        )
        extract_target = {"file": str(path), **item, "block": "http_surface_extract"}
        orders.append(
            _order(
                kind="http_surface_extract",
                priority="medium",
                title=f"Extract HTTP surface: {theme}",
                reason=(
                    f"{theme} mapping can close after a verified witness; "
                    f"extraction is a separate step for the remaining "
                    f"{function_count} functions / {substantive_lines} lines in {path.name}."
                ),
                target=extract_target,
            )
        )

    return {
        "ok": True,
        "path": str(path),
        "line_count": line_count,
        "function_count": len(functions),
        "wrapper_candidate_count": len(actionable_wrappers),
        "referenced_wrapper_count": len(referenced_wrappers),
        "wrapper_scan_count": len(wrappers),
        "large_function_count": len(large),
        "http_surface_candidate_count": len(http_surfaces),
        "orders": orders,
    }


def build_core_thinning_brief(core_path: Path | list[Path] | tuple[Path, ...], *, large_function_threshold: int = 160, wrapper_limit: int = 12) -> dict[str, object]:
    paths = _core_paths(core_path)
    protected_wrapper_names = _runtime_hook_reference_names(paths)
    file_reports = [
        _analyze_core_file(
            path,
            large_function_threshold=large_function_threshold,
            wrapper_limit=wrapper_limit,
            protected_wrapper_names=protected_wrapper_names,
        )
        for path in paths
    ]
    orders: list[dict[str, object]] = []
    for report in file_reports:
        orders.extend([dict(item) for item in list(report.get("orders") or []) if isinstance(item, dict)])
    orders.sort(key=lambda item: (_priority_rank(item.get("priority")), str(item.get("kind") or ""), str(item.get("title") or "")))

    ok = all(bool(report.get("ok")) for report in file_reports)
    errors = [f"{Path(str(report.get('path') or '')).name}: {report.get('error')}" for report in file_reports if not bool(report.get("ok"))]
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": ok,
        "core_path": str(paths[0]) if len(paths) == 1 else "",
        "core_paths": [str(path) for path in paths],
        "files": file_reports,
        "error": "; ".join(errors),
        "line_count": sum(int(report.get("line_count", 0) or 0) for report in file_reports),
        "function_count": sum(int(report.get("function_count", 0) or 0) for report in file_reports),
        "wrapper_candidate_count": sum(int(report.get("wrapper_candidate_count", 0) or 0) for report in file_reports),
        "referenced_wrapper_count": sum(int(report.get("referenced_wrapper_count", 0) or 0) for report in file_reports),
        "wrapper_scan_count": sum(int(report.get("wrapper_scan_count", 0) or 0) for report in file_reports),
        "large_function_count": sum(int(report.get("large_function_count", 0) or 0) for report in file_reports),
        "http_surface_candidate_count": sum(int(report.get("http_surface_candidate_count", 0) or 0) for report in file_reports),
        "orders": orders,
        "order_count": len(orders),
    }


def build_core_thinning_owner_verdict(
    brief: dict[str, object] | None,
    *,
    feed_result: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return Mission-compatible owner pressure without making Mission own thinning."""

    data = dict(brief or {})
    feed = dict(feed_result or {}) if isinstance(feed_result, dict) else {}
    ok = bool(data.get("ok", False)) and bool(feed.get("ok", True))
    order_count = int(data.get("order_count", 0) or 0)
    blocker_code = ""
    detail = ""
    blocks_green = False
    lifecycle = summarize_feed_pressure(pressure_count=order_count, feed_result=feed)
    if not ok:
        blocker_code = "core_thinning_unavailable"
        detail = str(data.get("error") or feed.get("error") or "core thinning evidence unavailable").strip()
        blocks_green = True
    elif order_count > 0:
        blocker_code = "core_http_thinning_pressure"
        detail = f"{order_count} core/http thinning work order(s) ready"
        if lifecycle.get("lifecycle_gap"):
            detail = (
                f"{order_count} core/http thinning work order(s) ready; "
                f"{int(lifecycle.get('executable_count', 0) or 0)} executable"
            )
    blockers = []
    if blocker_code:
        blocker_payload = {
            "owner": "core_thinning",
            "code": blocker_code,
            "detail": detail,
            "source": "core_thinning",
        }
        if blocker_code == "core_http_thinning_pressure":
            blocker_payload["remediation"] = {
                "action": "active_work_tree_run_next",
                "tools": ["core_thinning"],
            }
        blockers.append(blocker_payload)
    return {
        "owner": "core_thinning",
        "ready": not blockers,
        "status": "ready" if not blockers else "pressure",
        "source": "core_thinning",
        "summary": (
            "core/http thinning evidence unavailable"
            if blocker_code == "core_thinning_unavailable"
            else (
                f"core/http thinning has {order_count} ready work order(s)"
                if order_count > 0
                else "core/http thinning has no ready work orders"
            )
        ),
        "blocks_green": blocks_green,
        "blockers": blockers,
        "evidence": {
            "order_count": order_count,
            "line_count": int(data.get("line_count", 0) or 0),
            "function_count": int(data.get("function_count", 0) or 0),
            "large_function_count": int(data.get("large_function_count", 0) or 0),
            "http_surface_candidate_count": int(data.get("http_surface_candidate_count", 0) or 0),
            "wrapper_candidate_count": int(data.get("wrapper_candidate_count", 0) or 0),
            **lifecycle,
        },
    }


def render_core_thinning_brief(brief: dict | None = None, *, feed_result: dict | None = None) -> str:
    data = dict(brief or {})
    if not bool(data.get("ok", True)):
        return f"Core Thinning Brief failed: {data.get('error') or 'unknown error'}"
    lines = [
        f"Core Thinning Brief - {data.get('generated_at') or ''}",
        f"core files: {len(list(data.get('files') or [])) or 1}",
        f"total lines: {int(data.get('line_count', 0) or 0)}",
        f"functions: {int(data.get('function_count', 0) or 0)}",
        f"wrapper candidates: {int(data.get('wrapper_candidate_count', 0) or 0)}",
        f"referenced wrappers protected: {int(data.get('referenced_wrapper_count', 0) or 0)}",
        f"large functions: {int(data.get('large_function_count', 0) or 0)}",
        f"HTTP extraction candidates: {int(data.get('http_surface_candidate_count', 0) or 0)}",
        f"work orders: {int(data.get('order_count', 0) or 0)}",
    ]
    for report in list(data.get("files") or []):
        if not isinstance(report, dict):
            continue
        name = Path(str(report.get("path") or "core")).name
        lines.append(
            f"- {name}: {int(report.get('line_count', 0) or 0)} lines, "
            f"{int(report.get('function_count', 0) or 0)} functions, "
            f"{int(report.get('wrapper_candidate_count', 0) or 0)} wrappers, "
            f"{int(report.get('referenced_wrapper_count', 0) or 0)} protected wrappers, "
            f"{int(report.get('http_surface_candidate_count', 0) or 0)} HTTP candidates"
        )
    if isinstance(feed_result, dict) and feed_result:
        lines.append(
            "Work tree: "
            f"{feed_result.get('status') or 'unknown'}"
            f" | tree={feed_result.get('tree_id') or '-'}"
            f" | added={int(feed_result.get('added_count', 0) or 0)}"
            f" | deduped={int(feed_result.get('deduped_count', 0) or 0)}"
            f" | reopened={int(feed_result.get('reopened_count', 0) or 0)}"
            f" | executable={int(feed_result.get('executable_count', 0) or 0)}"
            f" | resolved={int(feed_result.get('resolved_count', 0) or 0)}"
        )
    for index, item in enumerate(list(data.get("orders") or [])[:12], start=1):
        lines.append(f"{index}. [{str(item.get('priority') or 'info').upper()}] {item.get('title')}")
        lines.append(f"   reason: {item.get('reason') or ''}")
    return "\n".join(lines)


def _target_from_payload(payload: str | dict[str, object]) -> dict[str, object]:
    if isinstance(payload, dict):
        raw = payload
    else:
        try:
            raw = json.loads(str(payload or "{}"))
        except Exception:
            return {}
    target = raw.get("target") if isinstance(raw.get("target"), dict) else raw
    return dict(target or {}) if isinstance(target, dict) else {}


def _name_reference_count(tree: ast.AST, name: str) -> int:
    return int(_name_reference_counts(tree, {name}).get(name, 0) or 0)


def _name_reference_counts(tree: ast.AST, names: set[str]) -> dict[str, int]:
    clean_names = {str(name or "").strip() for name in names if str(name or "").strip()}
    counts = {name: 0 for name in clean_names}
    if not counts:
        return counts
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in counts:
            counts[node.id] += 1
    return counts


def _module_import_name(path: Path, repo_root: Path) -> str:
    try:
        rel = Path(path).resolve().relative_to(Path(repo_root).resolve())
    except ValueError:
        return ""
    if rel.suffix != ".py":
        return ""
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        return ".".join(parts[:-1])
    return ".".join(parts[:-1] + [rel.stem])


def _import_aliases_for_module(tree: ast.AST, module_name: str) -> set[str]:
    if not module_name:
        return set()
    aliases: set[str] = set()
    module_tail = module_name.rsplit(".", 1)[-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                full = str(alias.name or "").strip()
                if not full or full != module_name:
                    continue
                aliases.add(str(alias.asname or module_tail))
        elif isinstance(node, ast.ImportFrom):
            mod = str(node.module or "").strip()
            if mod != module_name:
                continue
            aliases.add(module_tail)
    return {str(name or "").strip() for name in aliases if str(name or "").strip()}


def _repo_root_for_path(path: Path) -> Path:
    resolved = Path(path).resolve()
    for parent in [resolved, *resolved.parents]:
        if (parent / "policy.json").is_file() and (parent / "nova_core.py").is_file():
            return parent
    return resolved.parent


def _iter_reference_scan_files(*, declaring_path: Path, repo_root: Path) -> list[Path]:
    declaring = Path(declaring_path).resolve()
    canonical_core = (repo_root / "nova_core.py").resolve()
    files: list[Path] = []
    if declaring == canonical_core:
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [name for name in dirnames if name not in _REPO_SCAN_EXCLUDED_DIRS]
            current = Path(dirpath)
            try:
                rel_parts = current.relative_to(repo_root).parts
            except ValueError:
                continue
            if any(part in _REPO_SCAN_EXCLUDED_DIRS for part in rel_parts):
                continue
            for filename in filenames:
                if filename.endswith(".py"):
                    files.append(current / filename)
        return files

    local_root = declaring.parent
    for candidate in local_root.rglob("*.py"):
        try:
            rel_parts = candidate.relative_to(local_root).parts
        except ValueError:
            continue
        if any(part in _REPO_SCAN_EXCLUDED_DIRS for part in rel_parts):
            continue
        files.append(candidate)
    return files


def _symbol_reference_counts_in_tree(
    tree: ast.AST,
    names: set[str],
    *,
    attribute_base_names: set[str] | None = None,
) -> dict[str, int]:
    clean_names = {str(name or "").strip() for name in names if str(name or "").strip()}
    counts = {name: 0 for name in clean_names}
    if not counts:
        return counts
    base_names = {
        str(name or "").strip()
        for name in (attribute_base_names or set())
        if str(name or "").strip()
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in counts:
            counts[node.id] += 1
        elif isinstance(node, ast.Attribute):
            attr = str(node.attr or "").strip()
            if attr not in counts:
                continue
            base = node.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id in base_names:
                counts[attr] += 1
    return counts


def _repo_wide_reference_counts(names: set[str], *, declaring_path: Path) -> dict[str, int]:
    clean_names = {str(name or "").strip() for name in names if str(name or "").strip()}
    counts = {name: 0 for name in clean_names}
    if not counts:
        return counts
    repo_root = _repo_root_for_path(declaring_path)
    declaring_module = _module_import_name(declaring_path, repo_root)
    default_bases = set(_CORE_ATTRIBUTE_BASE_NAMES)
    if declaring_module:
        default_bases.add(declaring_module.rsplit(".", 1)[-1])
    for file_path in _iter_reference_scan_files(declaring_path=declaring_path, repo_root=repo_root):
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8-sig", errors="ignore"))
        except Exception:
            continue
        attribute_bases = set(default_bases)
        attribute_bases.update(_import_aliases_for_module(tree, declaring_module))
        file_counts = _symbol_reference_counts_in_tree(
            tree,
            clean_names,
            attribute_base_names=attribute_bases,
        )
        for name, value in file_counts.items():
            counts[name] += int(value or 0)
    return counts


def _refresh_release_source_identity(path: Path) -> None:
    """Normalize corrupt future mtimes after a verified self-edit."""
    try:
        resolved = Path(path).resolve()
        stat = resolved.stat()
        now = time.time()
        if float(stat.st_mtime) > now + 60.0 or float(stat.st_atime) > now + 60.0:
            os.utime(resolved, (now, now))
    except Exception:
        pass


def _behavioral_verify_core_edit(*, path: Path, repo_root: Path, python_executable: str) -> dict[str, object]:
    import_name = _module_import_name(path, repo_root)
    if not import_name:
        return {"ok": True}

    py = str(python_executable or sys.executable)
    if import_name != "nova_core":
        proc = subprocess.run(
            [py, "-c", f"import importlib; importlib.import_module({import_name!r})"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "reason": "import_failed",
                "command": f"import {import_name}",
                "stderr": (proc.stderr or proc.stdout or "")[-1000:],
            }
        return {"ok": True}
    proc = subprocess.run(
        [py, "-c", "import nova_core"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=90,
    )
    if proc.returncode != 0:
        return {
            "ok": False,
            "reason": "import_failed",
            "command": "import nova_core",
            "stderr": (proc.stderr or proc.stdout or "")[-1000:],
        }

    for command in (
        "import nova_http",
        "import importlib; importlib.import_module('tools.registry')",
        "import nova_core; getattr(nova_core, 'build_pulse_payload'); getattr(nova_core, 'render_nova_pulse')",
    ):
        proc = subprocess.run(
            [py, "-c", command],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "reason": "surface_import_failed",
                "command": command,
                "stderr": (proc.stderr or proc.stdout or "")[-1000:],
            }
    return {"ok": True}

def _write_pre_mutation_snapshot(*, path: Path, source: str) -> str:
    snapshot_dir = RUNTIME_DIR / "core_thinning" / "pre_mutation_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(path))
    snapshot_path = snapshot_dir / f"{safe_name}.{time.time_ns()}.py"
    snapshot_path.write_text(source, encoding="utf-8")
    return str(snapshot_path)


def execute_core_thinning_order(payload: str | dict[str, object], *, python_executable: str | None = None) -> dict[str, object]:
    """Execute one tightly scoped core-thinning order.

    First supported operation: remove an unused service-wrapper function. This
    deliberately blocks when callers still exist.
    """

    target = _target_from_payload(payload)
    name = str(target.get("name") or "").strip()
    block = str(target.get("block") or target.get("kind") or "").strip()
    wrapped_call = str(target.get("wrapped_call") or "").strip()
    file_name = str(target.get("file") or "").strip()
    start_line = target.get("start_line")
    end_line = target.get("end_line")
    if not name or not file_name:
        return {"ok": False, "scope_ok": False, "verified": False, "reason": "missing_target"}
    if not isinstance(start_line, int) or not isinstance(end_line, int) or start_line <= 0 or end_line < start_line:
        return {"ok": False, "scope_ok": False, "verified": False, "reason": "invalid_target_lines"}

    path = Path(file_name)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        return {"ok": False, "scope_ok": False, "verified": False, "reason": f"parse_failed:{exc}"}

    payload_kind = ""
    if isinstance(payload, dict):
        payload_kind = str(payload.get("kind") or "").strip()
    if block == "http_surface_extract" or payload_kind == "http_surface_extract":
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "blocked": True,
            "action": "blocked_http_extraction",
            "reason": "http_extraction_not_implemented",
            "target": {
                "file": str(path),
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
            },
        }

    if block == "http_surface_candidate" or name.startswith("http:"):
        lines = source.splitlines()
        if end_line > len(lines):
            return {"ok": False, "scope_ok": False, "verified": False, "reason": "target_line_drift"}
        function_names = [str(item or "").strip() for item in list(target.get("function_names") or []) if str(item or "").strip()]
        found_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and start_line <= int(getattr(node, "lineno", 0) or 0) <= end_line
        }
        missing = [item for item in function_names[:20] if item not in found_names]
        if missing:
            return {"ok": False, "scope_ok": True, "verified": False, "reason": "target_members_drift", "missing": missing[:6]}
        return {
            "ok": True,
            "scope_ok": True,
            "verified": True,
            "action": "witnessed_http_extraction_boundary",
            "target": {
                "file": str(path),
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
                "function_count": len(function_names),
                "function_names": function_names[:20],
            },
        }

    if not wrapped_call:
        return {"ok": False, "scope_ok": False, "verified": False, "reason": "missing_wrapper_target"}

    matches = _functions_named(tree, name)
    if not matches:
        return {"ok": False, "scope_ok": False, "verified": False, "reason": "wrapper_missing"}
    if len(matches) > 1:
        return {"ok": False, "scope_ok": False, "verified": False, "reason": "ambiguous_wrapper_target"}

    matched = matches[0]
    actual_start, actual_end = _function_bounds(matched)
    line_drift_resolved = actual_start != start_line or actual_end != end_line
    if _is_service_wrapper(matched) != wrapped_call:
        return {"ok": False, "scope_ok": False, "verified": False, "reason": "wrapper_shape_drift"}
    start_line, end_line = actual_start, actual_end

    if name in _protected_public_wrapper_names():
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "reason": "public_adapter_protected",
            "line_drift_resolved": line_drift_resolved,
            "target": {"file": str(path), "name": name, "start_line": start_line, "end_line": end_line},
        }

    if name in _runtime_hook_reference_names([path]):
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "reason": "runtime_hook_still_present",
            "line_drift_resolved": line_drift_resolved,
            "target": {"file": str(path), "name": name, "start_line": start_line, "end_line": end_line},
        }

    reference_count = int(_repo_wide_reference_counts({name}, declaring_path=path).get(name, 0) or 0)
    if reference_count > 0:
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "reason": "callers_still_present",
            "reference_count": reference_count,
            "line_drift_resolved": line_drift_resolved,
            "target": {"file": str(path), "name": name, "start_line": start_line, "end_line": end_line},
        }

    lines = source.splitlines()
    next_lines = lines[: start_line - 1] + lines[end_line:]
    next_source = "\n".join(next_lines) + ("\n" if source.endswith("\n") else "")
    try:
        ast.parse(next_source)
    except Exception as exc:
        return {"ok": False, "scope_ok": True, "verified": False, "reason": f"rewrite_failed:{exc}"}

    repo_root = _repo_root_for_path(path)
    py = str(python_executable or sys.executable)
    snapshot_path = _write_pre_mutation_snapshot(path=path, source=source)
    path.write_text(next_source, encoding="utf-8")
    proc = subprocess.run([py, "-m", "py_compile", str(path)], cwd=str(repo_root), capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        path.write_text(source, encoding="utf-8")
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "reason": "py_compile_failed",
            "rolled_back": True,
            "stderr": (proc.stderr or proc.stdout or "")[-1000:],
        }

    behavioral = _behavioral_verify_core_edit(path=path, repo_root=repo_root, python_executable=py)
    if not bool(behavioral.get("ok")):
        path.write_text(source, encoding="utf-8")
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "reason": str(behavioral.get("reason") or "behavioral_verify_failed"),
            "rolled_back": True,
            "behavioral": behavioral,
        }

    _refresh_release_source_identity(path)
    return {
        "ok": True,
        "scope_ok": True,
        "verified": True,
        "action": "removed_unused_wrapper",
        "line_drift_resolved": line_drift_resolved,
        "snapshot_path": snapshot_path,
        "target": {"file": str(path), "name": name, "start_line": start_line, "end_line": end_line},
    }


def _active_core_thinning_tree(work_tree_module):
    if hasattr(work_tree_module, "reload_persisted_state"):
        work_tree_module.reload_persisted_state()
    for tree in list(work_tree_module.list_trees() or []):
        meta = dict(getattr(tree, "meta", {}) or {})
        if str(meta.get("work_identity_key") or "").strip() == CORE_THINNING_WORK_IDENTITY and _status_value(getattr(tree, "status", "")) != "archived":
            return tree
    return None


def feed_core_thinning_brief_to_work_tree(brief: dict[str, object], *, work_tree_module) -> dict[str, object]:
    orders = [dict(item) for item in list((brief or {}).get("orders") or []) if isinstance(item, dict)]
    active_order_ids = {str(item.get("order_id") or "").strip() for item in orders if str(item.get("order_id") or "").strip()}
    order_by_id = {str(item.get("order_id") or "").strip(): item for item in orders if str(item.get("order_id") or "").strip()}
    order_by_semantic_key = {}
    for item in orders:
        target = dict(item.get("target") or {}) if isinstance(item.get("target"), dict) else {}
        semantic_key = _target_semantic_key(item.get("kind"), target)
        if semantic_key:
            order_by_semantic_key[semantic_key] = item
    tree = _active_core_thinning_tree(work_tree_module)
    if tree is None:
        tree = work_tree_module.initialize_tree(
            "Core Thinning",
            meta={
                "work_identity_key": CORE_THINNING_WORK_IDENTITY,
                "work_identity_label": "core thinning",
                "source": "core_thinning",
                "execution_policy": {
                    "allowed_tools": list(CORE_THINNING_ALLOWED_TOOLS),
                    "require_explicit_allow": True,
                },
            },
        )
        created = True
    else:
        created = False
        if hasattr(work_tree_module, "set_tree_execution_policy"):
            work_tree_module.set_tree_execution_policy(tree.tree_id, allowed_tools=list(CORE_THINNING_ALLOWED_TOOLS), require_explicit_allow=True)

    existing_order_ids: set[str] = set()
    existing_identities: set[str] = set()
    resolved_count = 0
    updated_count = 0
    reopened_count = 0
    satisfied_count = 0
    satisfied_active_count = 0

    def _claim_order(order_payload: dict[str, object] | None, fallback_id: str = "") -> str:
        claimed = str((order_payload or {}).get("order_id") or "").strip() or str(fallback_id or "").strip()
        identity = ""
        if order_payload:
            target = dict(order_payload.get("target") or {}) if isinstance(order_payload.get("target"), dict) else {}
            identity = _target_semantic_key(order_payload.get("kind"), target)
        if claimed:
            existing_order_ids.add(claimed)
        if identity:
            existing_identities.add(identity)
        return claimed

    for task in list(work_tree_module.list_tree_tasks(tree.tree_id) or []):
        meta = dict(getattr(task, "meta", {}) or {})
        order_id = finding_key_from_meta(meta)
        status = _status_value(getattr(task, "status", ""))
        task_target = dict(meta.get("target") or {}) if isinstance(meta.get("target"), dict) else {}
        identity = _target_semantic_key(meta.get("kind"), task_target)
        order = dict(order_by_id.get(order_id) or {})
        if not order and identity:
            order = dict(order_by_semantic_key.get(identity) or {})
        meta = _repair_core_thinning_task_meta(task, meta, order, brief=brief, work_tree_module=work_tree_module)
        current_fingerprint = _order_satisfaction_key(order) if order else ""
        decision = classify_task_meta(
            meta=meta,
            item_status=status,
            active_finding_keys=active_order_ids,
            current_fingerprint=current_fingerprint,
        )
        if decision == DECISION_SKIP:
            continue
        if decision == DECISION_REOPEN:
            _reopen_core_thinning_task(work_tree_module, task, order, brief=brief)
            reopened_count += 1
            _claim_order(order, order_id)
            continue
        if decision == DECISION_SATISFIED:
            satisfied_count += 1
            claimed_id = _claim_order(order or order_by_semantic_key.get(identity) or {}, order_id)
            if claimed_id and claimed_id in active_order_ids:
                satisfied_active_count += 1
            resolved_count += 1
            continue
        if decision in {DECISION_ACTIVE, DECISION_ACTIVE_UPDATE}:
            target = _normalize_core_thinning_target(order)
            next_fingerprint = _order_satisfaction_key(order)
            if decision == DECISION_ACTIVE_UPDATE:
                meta = update_open_fingerprint(meta, satisfaction_fingerprint=next_fingerprint)
                task.meta = meta
                work_tree_module.touch_branch(task.branch_id)
                updated_count += 1
            elif target:
                order_fields = _core_thinning_order_task_fields(order, brief=brief)
                if any(meta.get(key) != value for key, value in order_fields.items()):
                    meta.update(order_fields)
                    meta[KEY_SATISFACTION_FINGERPRINT] = next_fingerprint
                    task.meta = meta
                    work_tree_module.touch_branch(task.branch_id)
                    updated_count += 1
            branch = work_tree_module.get_branch(task.branch_id) if hasattr(work_tree_module, "get_branch") else None
            expected_priority = _branch_priority(order.get("priority"))
            if branch is not None and int(getattr(branch, "priority", 0) or 0) != expected_priority:
                branch.priority = expected_priority
                work_tree_module.touch_branch(task.branch_id)
                updated_count += 1
            _claim_order(order, order_id)
            continue
        semantic_key = identity or _target_semantic_key(meta.get("kind"), task_target)
        semantic_order = dict(order_by_semantic_key.get(semantic_key) or {}) if semantic_key else {}
        semantic_order_id = str(semantic_order.get("order_id") or "").strip()
        if semantic_order_id:
            meta.update(_core_thinning_order_task_fields(semantic_order, brief=brief))
            meta[KEY_FINDING] = semantic_order_id
            task.meta = meta
            branch = work_tree_module.get_branch(task.branch_id) if hasattr(work_tree_module, "get_branch") else None
            if branch is not None:
                branch.priority = _branch_priority(semantic_order.get("priority"))
            work_tree_module.touch_branch(task.branch_id)
            _claim_order(semantic_order, semantic_order_id)
            updated_count += 1
            continue
        if hasattr(work_tree_module, "mark_task_dropped"):
            work_tree_module.mark_task_dropped(task.task_id, reason="core_thinning_order_no_longer_active")
        else:
            work_tree_module.mark_task_complete(task.task_id)
        resolved_count += 1

    root = work_tree_module.get_branch(tree.root_branch_id)
    added_count = 0
    deduped_count = 0
    for order in orders:
        order_id = str(order.get("order_id") or "").strip()
        target = dict(order.get("target") or {}) if isinstance(order.get("target"), dict) else {}
        identity = _target_semantic_key(order.get("kind"), target)
        if not order_id or order_id in existing_order_ids or (identity and identity in existing_identities):
            deduped_count += 1
            continue
        target = _normalize_core_thinning_target(order)
        branch = work_tree_module.add_branch_to_tree(tree.tree_id, str(order.get("title") or "Review core thinning target"), "core_thinning", getattr(root, "branch_id", None))
        branch.priority = _branch_priority(order.get("priority"))
        work_tree_module.add_task_to_branch(
            branch.branch_id,
            f"{order.get('title')}: {order.get('reason')}",
            meta=initial_task_meta(
                finding_key=order_id,
                satisfaction_fingerprint=_order_satisfaction_key(order),
                extra=_core_thinning_order_task_fields(order, brief=brief),
            ),
        )
        work_tree_module.set_branch_tools(branch.branch_id, allowed_tools=[str(order.get("recommended_tool") or "patch_apply")], preferred_tool=str(order.get("recommended_tool") or "patch_apply"))
        existing_order_ids.add(order_id)
        if identity:
            existing_identities.add(identity)
        added_count += 1

    for task in list(work_tree_module.list_tree_tasks(tree.tree_id) or []):
        meta = dict(getattr(task, "meta", {}) or {})
        if str(meta.get("kind") or "").strip() != "http_surface_extract":
            continue
        if _status_value(getattr(task, "status", "")) in {"complete", "dropped"}:
            continue
        _close_unimplemented_http_extract(work_tree_module, task)
        claimed_id = _claim_order(
            {
                "order_id": finding_key_from_meta(meta),
                "kind": "http_surface_extract",
                "target": dict(meta.get("target") or {}) if isinstance(meta.get("target"), dict) else {},
            },
            finding_key_from_meta(meta),
        )
        satisfied_count += 1
        if claimed_id and claimed_id in active_order_ids:
            satisfied_active_count += 1
        resolved_count += 1

    executable_count = 0
    for task in list(work_tree_module.list_tree_tasks(tree.tree_id) or []):
        meta = dict(getattr(task, "meta", {}) or {})
        order_id = finding_key_from_meta(meta)
        status = _status_value(getattr(task, "status", ""))
        if not order_id or order_id not in active_order_ids:
            continue
        if status in {"complete", "dropped"}:
            continue
        executable_count += 1

    status = "seeded"
    if reopened_count:
        status = "reopened"
    elif added_count:
        status = "seeded"
    elif resolved_count:
        status = "resolved"
    elif updated_count:
        status = "updated"
    elif deduped_count:
        status = "deduped"

    return {
        "ok": True,
        "status": status,
        "tree_id": str(getattr(tree, "tree_id", "") or ""),
        "created": created,
        "added_count": added_count,
        "deduped_count": deduped_count,
        "resolved_count": resolved_count,
        "updated_count": updated_count,
        "reopened_count": reopened_count,
        "satisfied_count": satisfied_count,
        "satisfied_active_count": satisfied_active_count,
        "executable_count": executable_count,
        "order_count": len(orders),
    }
