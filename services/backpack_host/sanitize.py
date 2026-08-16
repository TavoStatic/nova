from __future__ import annotations

"""Uninstall sanitization for every backpack, not just Ed-Fi.

A backpack can write outside runtime/{id}/. Those extra paths must come from
the backpack's own manifest and settings defaults, plus a small overlay for
Nova surfaces that backpack does not declare (work-tree sources, fusion cache,
maintenance keys). If a path is not on that list, residue scan reports it.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Any

from services.backpack_host.install_state import (
    backpack_runtime_installed,
    write_backpack_uninstall_mark,
)

# Nova surfaces the backpack package cannot declare in backpack.json.
# Keep this thin. Manifest runtime/settings paths are discovered automatically.
BACKPACK_SURFACE_OVERLAYS: dict[str, dict[str, Any]] = {
    "edfi": {
        "signal_sources": ("edfi_capability_profile", "edfi_core", "backpack_edfi"),
        "fusion_scan": True,
        "maintenance_state_keys": ("last_edfi_warehouse_sync",),
    }
}

_TEMPLATE_TAIL = re.compile(r"/\{[^}]+\}.*")


def _safe_id(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in {"_", "-"})


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _looks_like_runtime_path(value: Any) -> bool:
    text = str(value or "").replace("\\", "/").strip()
    if not text or "://" in text:
        return False
    return text.startswith("runtime/") or text.startswith("runtime\\")


def _resolve_under_runtime(raw: str, *, runtime_root: Path) -> Path | None:
    text = str(raw or "").replace("\\", "/").strip()
    if not text:
        return None
    text = _TEMPLATE_TAIL.sub("", text).rstrip("/")
    if not text or text == "runtime":
        return None
    if text.startswith("runtime/"):
        rel = text[len("runtime/") :]
    else:
        rel = text
    if not rel or ".." in Path(rel).parts:
        return None
    root = Path(runtime_root).resolve()
    path = (root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if path == root:
        return None
    return path


def _manifest_paths(backpack_id: str, *, backpacks_root: Path | None) -> dict[str, Any]:
    bid = _safe_id(backpack_id)
    payload: dict[str, Any] = {
        "backpack_id": bid,
        "pipeline_id": bid,
        "runtime_decls": [],
        "package_present": False,
    }
    if not bid or backpacks_root is None:
        return payload
    manifest_path = Path(backpacks_root) / bid / "backpack.json"
    data = _read_json(manifest_path)
    if not data:
        return payload
    payload["package_present"] = True
    payload["pipeline_id"] = _safe_id(data.get("pipeline_id") or bid) or bid
    runtime_block = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
    decls: list[str] = []
    for value in runtime_block.values():
        if _looks_like_runtime_path(value):
            decls.append(str(value).replace("\\", "/").strip())
    schema = _read_json(Path(backpacks_root) / bid / "settings_schema.json")
    for item in list(schema.get("settings") or []):
        if not isinstance(item, dict):
            continue
        default = item.get("default")
        if _looks_like_runtime_path(default):
            decls.append(str(default).replace("\\", "/").strip())
    payload["runtime_decls"] = sorted(set(decls))
    return payload


def backpack_touch_points(
    backpack_id: str,
    *,
    runtime_root: Path | None = None,
    backpacks_root: Path | None = None,
) -> dict[str, Any]:
    bid = _safe_id(backpack_id)
    overlay = dict(BACKPACK_SURFACE_OVERLAYS.get(bid) or {})
    manifest = _manifest_paths(bid, backpacks_root=backpacks_root)
    pipeline_id = str(manifest.get("pipeline_id") or overlay.get("pipeline_id") or bid)
    extra_paths: list[str] = []
    if runtime_root is not None:
        seen: set[str] = set()
        for raw in list(manifest.get("runtime_decls") or []):
            resolved = _resolve_under_runtime(raw, runtime_root=runtime_root)
            if resolved is None:
                continue
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            extra_paths.append(key)
    return {
        "backpack_id": bid,
        "runtime_dir": bid,
        "pipeline_ids": tuple(dict.fromkeys([pipeline_id, bid, *(overlay.get("pipeline_ids") or ())])),
        "signal_sources": tuple(overlay.get("signal_sources") or ()),
        "fusion_scan": bool(overlay.get("fusion_scan")),
        "maintenance_state_keys": tuple(overlay.get("maintenance_state_keys") or ()),
        "package_present": bool(manifest.get("package_present")),
        "runtime_decls": list(manifest.get("runtime_decls") or []),
        "extra_runtime_paths": extra_paths,
    }


def _rm(path: Path, removed: list[str], errors: list[str]) -> None:
    try:
        if path.is_file():
            path.unlink()
            removed.append(str(path))
        elif path.is_dir():
            shutil.rmtree(path)
            removed.append(str(path))
    except Exception as exc:
        errors.append(f"{path}: {exc}")


def _clear_pipeline_workers(runtime_root: Path, pipeline_ids: tuple[str, ...], removed: list[str], errors: list[str]) -> None:
    for pipeline_id in pipeline_ids:
        slug = _safe_id(pipeline_id)
        if not slug:
            continue
        _rm(runtime_root / "pipelines" / slug, removed, errors)


def _fusion_scan_belongs_to(runtime_root: Path, backpack_id: str) -> bool:
    scan_path = runtime_root / "backpacks" / "capability_scan.json"
    if not scan_path.is_file():
        return False
    data = _read_json(scan_path)
    owner = _safe_id(data.get("backpack_id"))
    return (not owner) or owner == _safe_id(backpack_id)


def _clear_maintenance_state(runtime_root: Path, keys: tuple[str, ...], removed: list[str], errors: list[str]) -> None:
    if not keys:
        return
    path = runtime_root / "autonomy_maintenance_state.json"
    if not path.is_file():
        return
    try:
        data = _read_json(path)
        changed = False
        for key in keys:
            if key in data:
                data.pop(key, None)
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            removed.append(f"{path}#keys:{','.join(keys)}")
    except Exception as exc:
        errors.append(f"maintenance_state:{exc}")


def _sanitize_work_tree(backpack_id: str, *, points: dict[str, Any], reason: str) -> list[dict[str, Any]]:
    bid = _safe_id(backpack_id)
    match_sources = {
        bid,
        f"backpack_{bid}",
        *(str(item or "").strip() for item in list(points.get("signal_sources") or []) if str(item or "").strip()),
        *(str(item or "").strip() for item in list(points.get("pipeline_ids") or []) if str(item or "").strip()),
    }
    match_sources.discard("")
    try:
        import work_tree
        from services.work_tree_signal_ingestion import (
            WorkTreeSignalIngestionService,
            _is_archived_signal_branch,
            _mark_branch_resolved_with_lifecycle,
        )
        from work_tree_contracts import BranchStatus

        if hasattr(work_tree, "reload_persisted_state"):
            work_tree.reload_persisted_state()
        service = WorkTreeSignalIngestionService()
        tree = service._find_signal_tree()
        if tree is None:
            return []
        results: list[dict[str, Any]] = []
        now = __import__("datetime").datetime.now()
        for branch in list(work_tree.list_tree_branches(tree.tree_id) or []):
            if branch.branch_id == tree.root_branch_id:
                continue
            if _is_archived_signal_branch(branch):
                continue
            resolution = str(getattr(branch, "resolution_state", "") or "").strip().lower()
            if resolution in {"resolved", "retired"} and branch.status == BranchStatus.COMPLETE:
                continue
            source_type = str(getattr(branch, "source_type", "") or "").strip()
            payload = dict(getattr(branch, "source_payload", {}) or {})
            payload_backpack = str(payload.get("backpack_id") or "").strip()
            payload_pipeline = str(payload.get("pipeline_id") or "").strip()
            matched = (
                source_type in match_sources
                or payload_backpack == bid
                or payload_pipeline in match_sources
            )
            if not matched:
                continue
            _mark_branch_resolved_with_lifecycle(
                branch,
                note=reason,
                completion_action="backpack_uninstalled",
            )
            branch.last_seen_at = now
            work_tree.touch_branch(branch.branch_id)
            results.append(
                {
                    "action": "resolved",
                    "tree_id": tree.tree_id,
                    "branch_id": branch.branch_id,
                    "source_type": source_type,
                    "reason": reason,
                }
            )
        return results
    except Exception as exc:
        return [{"action": "work_tree_sanitize_failed", "error": str(exc)[:240]}]


def planned_sanitize_paths(
    backpack_id: str,
    *,
    runtime_root: Path,
    backpacks_root: Path | None = None,
) -> list[Path]:
    points = backpack_touch_points(backpack_id, runtime_root=runtime_root, backpacks_root=backpacks_root)
    rt = Path(runtime_root)
    planned = [rt / str(points["runtime_dir"])]
    for pipeline_id in list(points.get("pipeline_ids") or []):
        slug = _safe_id(pipeline_id)
        if slug:
            planned.append(rt / "pipelines" / slug)
    for raw in list(points.get("extra_runtime_paths") or []):
        planned.append(Path(raw))
    if points.get("fusion_scan") or _fusion_scan_belongs_to(rt, backpack_id):
        planned.append(rt / "backpacks" / "capability_scan.json")
    return planned


def scan_backpack_residue(
    backpack_id: str,
    *,
    runtime_root: Path,
    backpacks_root: Path | None = None,
) -> dict[str, Any]:
    """Report leftover runtime files for a backpack, including undeclared paths."""
    bid = _safe_id(backpack_id)
    rt = Path(runtime_root)
    points = backpack_touch_points(bid, runtime_root=rt, backpacks_root=backpacks_root)
    planned = {path.resolve() for path in planned_sanitize_paths(bid, runtime_root=rt, backpacks_root=backpacks_root)}
    found: list[str] = []
    undeclared: list[str] = []

    def _note(path: Path) -> None:
        if not path.exists():
            return
        found.append(str(path))
        resolved = path.resolve()
        covered = any(resolved == item or item in resolved.parents or resolved in item.parents for item in planned)
        if not covered:
            undeclared.append(str(path))

    _note(rt / bid)
    for pipeline_id in list(points.get("pipeline_ids") or []):
        slug = _safe_id(pipeline_id)
        if slug:
            _note(rt / "pipelines" / slug)
    for raw in list(points.get("extra_runtime_paths") or []):
        _note(Path(raw))
    scan_path = rt / "backpacks" / "capability_scan.json"
    if _fusion_scan_belongs_to(rt, bid):
        _note(scan_path)

    return {
        "backpack_id": bid,
        "installed": backpack_runtime_installed(bid, runtime_root=rt),
        "found": found,
        "undeclared": undeclared,
        "touch_points": points,
        "residue": bool(found),
    }


def sanitize_uninstalled_backpack(
    backpack_id: str,
    *,
    runtime_root: Path,
    connection_id: str = "",
    nova_user: str = "operator",
    uninstalled_at: str = "",
    sanitize_work_tree: bool = True,
    backpacks_root: Path | None = None,
) -> dict[str, Any]:
    """Remove install residue and quiet every declared Nova surface the backpack touched."""
    bid = _safe_id(backpack_id)
    rt = Path(runtime_root)
    if backpacks_root is None:
        try:
            from services.nova_runtime_context import BASE_DIR

            backpacks_root = Path(BASE_DIR) / "backpacks"
        except Exception:
            backpacks_root = None
    points = backpack_touch_points(bid, runtime_root=rt, backpacks_root=backpacks_root)
    removed: list[str] = []
    errors: list[str] = []

    for path in planned_sanitize_paths(bid, runtime_root=rt, backpacks_root=backpacks_root):
        _rm(path, removed, errors)
    _clear_maintenance_state(rt, tuple(points.get("maintenance_state_keys") or ()), removed, errors)

    mark_path = ""
    try:
        mark = write_backpack_uninstall_mark(
            bid,
            runtime_root=rt,
            payload={
                "connection_id": str(connection_id or "").strip(),
                "uninstalled_by": str(nova_user or "operator").strip() or "operator",
                "uninstalled_at": str(uninstalled_at or "").strip(),
                "touch_points": {
                    "pipeline_ids": list(points.get("pipeline_ids") or []),
                    "signal_sources": list(points.get("signal_sources") or []),
                    "fusion_scan": bool(points.get("fusion_scan")),
                    "runtime_decls": list(points.get("runtime_decls") or []),
                    "extra_runtime_paths": list(points.get("extra_runtime_paths") or []),
                },
            },
        )
        mark_path = str(mark)
        removed.append(mark_path)
    except Exception as exc:
        errors.append(f"uninstall_mark:{exc}")

    work_tree_results: list[dict[str, Any]] = []
    if sanitize_work_tree:
        work_tree_results = _sanitize_work_tree(
            bid,
            points=points,
            reason=f"{bid} backpack was uninstalled; leftover pressure is residue, not live work.",
        )

    residue = scan_backpack_residue(bid, runtime_root=rt, backpacks_root=backpacks_root)
    return {
        "ok": not errors and not residue.get("undeclared"),
        "backpack_id": bid,
        "installed": backpack_runtime_installed(bid, runtime_root=rt),
        "removed": removed,
        "errors": errors,
        "touch_points": points,
        "uninstall_mark": mark_path,
        "work_tree": work_tree_results,
        "residue": residue,
    }
