from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from pipelines.registry import PipelineRegistry


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_SOURCES_ROOT = BASE_DIR / "data_sources"


def _lane_control_state(pipeline_id: str, *, data_sources_root: Optional[Path] = None) -> dict[str, Any]:
    root = data_sources_root or DATA_SOURCES_ROOT
    safe_id = "".join(ch for ch in str(pipeline_id or "").strip() if ch.isalnum() or ch in {"_", "-"})
    path = root / safe_id / "lane_control.json"
    if not path.exists():
        return {"enabled": True, "state": "running"}
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    enabled = bool(data.get("enabled", True))
    return {**data, "enabled": enabled, "state": "running" if enabled else "paused"}


def _lane_paused_result(pipeline_id: str, operation: str) -> dict[str, Any]:
    return {
        "ok": False,
        "pipeline_id": pipeline_id,
        "operation": operation,
        "execution_mode": "blocked",
        "error": "Data lane is paused from the control panel.",
    }


def build_pipeline_registry(data_sources_root: Optional[Path] = None) -> PipelineRegistry:
    return PipelineRegistry(data_sources_root or DATA_SOURCES_ROOT)


def list_pipeline_summaries(data_sources_root: Optional[Path] = None) -> list[dict[str, Any]]:
    root = data_sources_root or DATA_SOURCES_ROOT
    summaries = []
    for item in build_pipeline_registry(root).list_summaries():
        summaries.append({**item, "lane_state": _lane_control_state(str(item.get("pipeline_id") or ""), data_sources_root=root)})
    return summaries


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
