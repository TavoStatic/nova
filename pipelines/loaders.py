from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pipelines.base import PipelineManifest


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return data


def _resolve_path(root: Path, relative_path: Optional[str]) -> Optional[Path]:
    if not relative_path:
        return None
    path = Path(relative_path)
    return path if path.is_absolute() else (root / path).resolve()


def load_pipeline_manifest(pipeline_dir: Path) -> PipelineManifest:
    manifest_path = pipeline_dir / "pipeline.json"
    data = _read_json(manifest_path)
    return PipelineManifest(
        pipeline_id=str(data["pipeline_id"]),
        display_name=str(data.get("display_name") or data["pipeline_id"]),
        kind=str(data.get("kind") or "unknown"),
        version=str(data.get("version") or "0.1.0"),
        description=str(data.get("description") or ""),
        read_only=bool(data.get("read_only", True)),
        network_scope=str(data.get("network_scope") or "local"),
        safe_operations=tuple(str(item) for item in (data.get("safe_operations") or [])),
        connector_module=str(data.get("connector_module") or ""),
        connector_class=str(data.get("connector_class") or ""),
        pipeline_dir=pipeline_dir.resolve(),
        schema_manifest_path=_resolve_path(pipeline_dir, str(data.get("schema_manifest") or "schema_manifest.json")) or (pipeline_dir / "schema_manifest.json"),
        query_templates_path=_resolve_path(pipeline_dir, str(data.get("query_templates") or "query_templates.json")) or (pipeline_dir / "query_templates.json"),
        field_dictionary_path=_resolve_path(pipeline_dir, data.get("field_dictionary")),
        config_example_path=_resolve_path(pipeline_dir, data.get("config_example")),
        local_config_path=_resolve_path(pipeline_dir, data.get("local_config")),
        audit_log_path=_resolve_path(pipeline_dir, data.get("audit_log")),
        meta={key: value for key, value in data.items() if key not in {
            "pipeline_id",
            "display_name",
            "kind",
            "version",
            "description",
            "read_only",
            "network_scope",
            "safe_operations",
            "connector_module",
            "connector_class",
            "schema_manifest",
            "query_templates",
            "field_dictionary",
            "config_example",
            "local_config",
            "audit_log",
        }},
    )
