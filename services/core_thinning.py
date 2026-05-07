from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


CORE_THINNING_WORK_IDENTITY = "system:core-thinning"
CORE_THINNING_ALLOWED_TOOLS = ["core_thinning", "read", "find", "patch_apply", "system_check", "health"]


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower() or "core-thinning"
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _priority_rank(value: Any) -> int:
    return {"high": 0, "medium": 1, "low": 2, "info": 3}.get(str(value or "").strip().lower(), 4)


def _branch_priority(value: Any) -> int:
    return {"high": 90, "medium": 70, "low": 40, "info": 20}.get(str(value or "").strip().lower(), 50)


def _target_semantic_key(kind: Any, target: dict[str, object] | None) -> str:
    data = dict(target or {})
    file_name = str(data.get("file") or "").replace("\\", "/").lower()
    name = str(data.get("name") or data.get("function") or "").strip().lower()
    wrapped = str(data.get("wrapped_call") or "").strip().lower()
    theme = str(data.get("theme") or "").strip().lower()
    cluster = str(data.get("cluster") or "").strip().lower()
    return "|".join([str(kind or "").strip().lower(), file_name, name, wrapped, theme, cluster])


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
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in functions:
        name = str(item.get("name") or "")
        if "." in name:
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
            if len(cluster_rows) < 4:
                continue
            start_line = int(cluster_rows[0].get("start_line", 0) or 0)
            end_line = int(cluster_rows[-1].get("end_line", 0) or 0)
            span = max(1, end_line - start_line + 1)
            total_function_lines = sum(int(row.get("line_count", 0) or 0) for row in cluster_rows)
            if span < 40 and total_function_lines < 35:
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
                }
            )
    candidates.sort(key=lambda item: (-int(item.get("function_count", 0) or 0), -int(item.get("line_count", 0) or 0), str(item.get("theme") or "")))
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
                        if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.startswith("_"):
                            names.add(value.value)
                elif isinstance(node, ast.Call):
                    if _called_name(node) != "_runtime_hook" or len(node.args) < 2:
                        continue
                    hook_name = node.args[1]
                    if isinstance(hook_name, ast.Constant) and isinstance(hook_name.value, str) and hook_name.value.startswith("_"):
                        names.add(hook_name.value)
                elif isinstance(node, ast.Attribute) and str(node.attr or "").startswith("_"):
                    names.add(str(node.attr or ""))
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
        row = {
            "name": dotted_name,
            "start_line": int(getattr(node, "lineno", 0) or 0),
            "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0),
            "line_count": span,
        }
        functions.append(row)
        wrapped = _is_service_wrapper(node)
        if wrapped:
            wrappers.append({**row, "wrapped_call": wrapped})
        if span >= large_function_threshold:
            large.append(row)

    protected_names = set(protected_wrapper_names or set())
    wrapper_reference_counts = _name_reference_counts(tree, {str(item.get("name") or "") for item in wrappers})
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
        orders.append(
            _order(
                kind="http_surface_candidate",
                priority="medium",
                title=f"Map HTTP extraction boundary: {theme}",
                reason=(
                    f"{theme} spans {item['line_count']} lines across {item['function_count']} "
                    f"related functions inside {path.name}; map this cluster before extraction."
                ),
                target={"file": str(path), **item},
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
            "action": "mapped_http_extraction_boundary",
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

    if name in _runtime_hook_reference_names([path]):
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "reason": "runtime_hook_still_present",
            "line_drift_resolved": line_drift_resolved,
            "target": {"file": str(path), "name": name, "start_line": start_line, "end_line": end_line},
        }

    if _name_reference_count(tree, name) > 0:
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "reason": "callers_still_present",
            "line_drift_resolved": line_drift_resolved,
            "target": {"file": str(path), "name": name, "start_line": start_line, "end_line": end_line},
        }

    lines = source.splitlines()
    next_lines = lines[: start_line - 1] + lines[end_line:]
    next_source = "\n".join(next_lines) + ("\n" if source.endswith("\n") else "")
    try:
        ast.parse(next_source)
        path.write_text(next_source, encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "scope_ok": True, "verified": False, "reason": f"rewrite_failed:{exc}"}

    py = str(python_executable or sys.executable)
    proc = subprocess.run([py, "-m", "py_compile", str(path)], cwd=str(path.parent), capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return {
            "ok": False,
            "scope_ok": True,
            "verified": False,
            "reason": "py_compile_failed",
            "stderr": (proc.stderr or proc.stdout or "")[-1000:],
        }
    return {
        "ok": True,
        "scope_ok": True,
        "verified": True,
        "action": "removed_unused_wrapper",
        "line_drift_resolved": line_drift_resolved,
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
    resolved_count = 0
    updated_count = 0
    for task in list(work_tree_module.list_tree_tasks(tree.tree_id) or []):
        meta = dict(getattr(task, "meta", {}) or {})
        order_id = str(meta.get("core_thinning_order_id") or "").strip()
        status = _status_value(getattr(task, "status", ""))
        if not order_id:
            continue
        if status == "complete" and order_id in active_order_ids:
            existing_order_ids.add(order_id)
            continue
        if status == "dropped":
            continue
        if order_id in active_order_ids:
            order = dict(order_by_id.get(order_id) or {})
            target = dict(order.get("target") or {}) if isinstance(order.get("target"), dict) else {}
            if target:
                target.setdefault("function", str(target.get("name") or ""))
                target.setdefault("block", str(order.get("kind") or "core_thinning"))
            if target and (meta.get("scope") != "single_block_only" or meta.get("target") != target):
                meta["scope"] = "single_block_only"
                meta["target"] = target
                task.meta = meta
                work_tree_module.touch_branch(task.branch_id)
                updated_count += 1
            branch = work_tree_module.get_branch(task.branch_id) if hasattr(work_tree_module, "get_branch") else None
            expected_priority = _branch_priority(order.get("priority"))
            if branch is not None and int(getattr(branch, "priority", 0) or 0) != expected_priority:
                branch.priority = expected_priority
                work_tree_module.touch_branch(task.branch_id)
                updated_count += 1
            existing_order_ids.add(order_id)
            continue
        semantic_key = _target_semantic_key(meta.get("kind"), meta.get("target") if isinstance(meta.get("target"), dict) else {})
        semantic_order = dict(order_by_semantic_key.get(semantic_key) or {}) if semantic_key else {}
        semantic_order_id = str(semantic_order.get("order_id") or "").strip()
        if semantic_order_id:
            target = dict(semantic_order.get("target") or {}) if isinstance(semantic_order.get("target"), dict) else {}
            if target:
                target.setdefault("function", str(target.get("name") or ""))
                target.setdefault("block", str(semantic_order.get("kind") or "core_thinning"))
            meta["core_thinning_order_id"] = semantic_order_id
            meta["kind"] = str(semantic_order.get("kind") or meta.get("kind") or "")
            meta["priority"] = str(semantic_order.get("priority") or meta.get("priority") or "")
            meta["scope"] = "single_block_only"
            meta["target"] = target
            task.meta = meta
            branch = work_tree_module.get_branch(task.branch_id) if hasattr(work_tree_module, "get_branch") else None
            if branch is not None:
                branch.priority = _branch_priority(semantic_order.get("priority"))
            work_tree_module.touch_branch(task.branch_id)
            existing_order_ids.add(semantic_order_id)
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
        if not order_id or order_id in existing_order_ids:
            deduped_count += 1
            continue
        target = dict(order.get("target") or {}) if isinstance(order.get("target"), dict) else {}
        if target:
            target.setdefault("function", str(target.get("name") or ""))
            target.setdefault("block", str(order.get("kind") or "core_thinning"))
        branch = work_tree_module.add_branch_to_tree(tree.tree_id, str(order.get("title") or "Review core thinning target"), "core_thinning", getattr(root, "branch_id", None))
        branch.priority = _branch_priority(order.get("priority"))
        work_tree_module.add_task_to_branch(
            branch.branch_id,
            f"{order.get('title')}: {order.get('reason')}",
            meta={
                "core_thinning_order_id": order_id,
                "kind": str(order.get("kind") or ""),
                "priority": str(order.get("priority") or ""),
                "scope": "single_block_only",
                "target": target,
            },
        )
        work_tree_module.set_branch_tools(branch.branch_id, allowed_tools=[str(order.get("recommended_tool") or "patch_apply")], preferred_tool=str(order.get("recommended_tool") or "patch_apply"))
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
        "updated_count": updated_count,
    }
