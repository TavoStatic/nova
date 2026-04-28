from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from pipelines.registry import PipelineRegistry


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_SOURCES_ROOT = BASE_DIR / "data_sources"


def build_pipeline_registry(data_sources_root: Optional[Path] = None) -> PipelineRegistry:
    return PipelineRegistry(data_sources_root or DATA_SOURCES_ROOT)


def list_pipeline_summaries(data_sources_root: Optional[Path] = None) -> list[dict[str, Any]]:
    return build_pipeline_registry(data_sources_root).list_summaries()


def get_pipeline_status(
    pipeline_id: str,
    *,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return pipeline.status()


def get_pipeline_schema_probe(
    pipeline_id: str,
    *,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return pipeline.schema_probe()


def preview_pipeline_query(
    pipeline_id: str,
    operation: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    row_limit: Optional[int] = None,
    dry_run: bool = True,
    data_sources_root: Optional[Path] = None,
) -> dict[str, Any]:
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
    pipeline = build_pipeline_registry(data_sources_root).instantiate(pipeline_id)
    return pipeline.safe_query(operation, params, row_limit=row_limit, dry_run=False)
