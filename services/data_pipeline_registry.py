from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from pipelines.registry import PipelineRegistry
from services.pipeline_privileged_bridge import run_governed_pipeline_query
from services.pipeline_worker_supervision import summarize_pipeline_workers


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_SOURCES_ROOT = BASE_DIR / "data_sources"


def _lane_control_state(pipeline_id: str, *, data_sources_root: Optional[Path] = None) -> dict[str, Any]:
    root = data_sources_root or DATA_SOURCES_ROOT
    safe_id = "".join(ch for ch in str(pipeline_id or "").strip() if ch.isalnum() or ch in {"_", "-"})
    path = root / safe_id / "lane_control.json"
    if not path.exists():
        return {"enabled": True, "state": "uncontrolled", "control_present": False}
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    enabled = bool(data.get("enabled", True))
    return {**data, "enabled": enabled, "state": "running" if enabled else "paused", "control_present": True}


def _lane_paused_result(pipeline_id: str, operation: str) -> dict[str, Any]:
    return {
        "ok": False,
        "pipeline_id": pipeline_id,
        "operation": operation,
        "execution_mode": "blocked",
        "error": "Data lane is paused from the control panel.",
    }


def build_pipeline_registry(data_sources_root: Optional[Path] = None) -> PipelineRegistry:
    """Build registry including backpacks/*/backpack.json (shadow same-id data_sources)."""
    root = data_sources_root or DATA_SOURCES_ROOT
    try:
        from services.backpack_host.registry import BackpackAwarePipelineRegistry
        from services.nova_runtime_context import BASE_DIR, RUNTIME_DIR

        backpacks_root = BASE_DIR / "backpacks"
        if backpacks_root.is_dir():
            return BackpackAwarePipelineRegistry(
                root,
                backpacks_root,
                nova_root=BASE_DIR,
                runtime_root=RUNTIME_DIR,
            )
    except Exception:
        pass
    return PipelineRegistry(root)


def list_pipeline_summaries(data_sources_root: Optional[Path] = None) -> list[dict[str, Any]]:
    root = data_sources_root or DATA_SOURCES_ROOT
    summaries = []
    pipeline_ids: list[str] = []
    for item in build_pipeline_registry(root).list_summaries():
        pipeline_id = str(item.get("pipeline_id") or "").strip()
        pipeline_ids.append(pipeline_id)
        summaries.append({**item, "lane_state": _lane_control_state(pipeline_id, data_sources_root=root)})
    worker_summary = summarize_pipeline_workers(pipeline_ids)
    for item in summaries:
        pipeline_id = str(item.get("pipeline_id") or "").strip()
        worker = next(
            (
                entry
                for entry in list(worker_summary.get("workers") or [])
                if str(entry.get("pipeline_id") or "").strip() == pipeline_id
            ),
            None,
        )
        item["worker_supervision"] = dict(worker or {})
    return summaries


def pipeline_worker_summary(data_sources_root: Optional[Path] = None) -> dict[str, Any]:
    pipeline_ids = [
        str(item.get("pipeline_id") or "").strip()
        for item in build_pipeline_registry(data_sources_root).list_summaries()
        if str(item.get("pipeline_id") or "").strip()
    ]
    return summarize_pipeline_workers(pipeline_ids)


def get_pipeline_status(
    pipeline_id: str,
    *,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    state = _lane_control_state(pipeline_id, data_sources_root=data_sources_root)
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return {**pipeline.status(), "lane_state": state, "lane_enabled": bool(state.get("enabled", True))}


def get_pipeline_schema_probe(
    pipeline_id: str,
    *,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return {**pipeline.schema_probe(), "lane_state": _lane_control_state(pipeline_id, data_sources_root=data_sources_root)}


def search_pipeline_vendor_dictionary(
    pipeline_id: str,
    query: str,
    *,
    limit: int = 12,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return {
        **pipeline.search_vendor_dictionary(query, limit=limit),
        "lane_state": _lane_control_state(pipeline_id, data_sources_root=data_sources_root),
    }


def plan_pipeline_report(
    pipeline_id: str,
    request: str,
    *,
    limit: int = 8,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return {
        **pipeline.plan_report(request, limit=limit),
        "lane_state": _lane_control_state(pipeline_id, data_sources_root=data_sources_root),
    }


def preview_pipeline_query(
    pipeline_id: str,
    operation: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    row_limit: Optional[int] = None,
    dry_run: bool = True,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    if not bool(_lane_control_state(pipeline_id, data_sources_root=data_sources_root).get("enabled", True)):
        return _lane_paused_result(pipeline_id, operation)
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return pipeline.safe_query(operation, params, row_limit=row_limit, dry_run=dry_run)


def run_pipeline_query(
    pipeline_id: str,
    operation: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    row_limit: Optional[int] = None,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    if not bool(_lane_control_state(pipeline_id, data_sources_root=data_sources_root).get("enabled", True)):
        return _lane_paused_result(pipeline_id, operation)
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return pipeline.safe_query(operation, params, row_limit=row_limit, dry_run=False)


def run_governed_live_pipeline_query(
    pipeline_id: str,
    operation: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    row_limit: Optional[int] = None,
    requested_by: str = "governed_pipeline_query",
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    if not bool(_lane_control_state(pipeline_id, data_sources_root=data_sources_root).get("enabled", True)):
        return _lane_paused_result(pipeline_id, operation)
    return run_governed_pipeline_query(
        pipeline_id,
        operation,
        params,
        row_limit=row_limit,
        requested_by=requested_by,
    )
