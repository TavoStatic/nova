from __future__ import annotations

"""
Backpack Manifest Loader

Translates backpack.json (backpack.v1 schema) into a PipelineManifest
that the existing PipelineRegistry / instantiate() machinery can use.

Design contract:
- connector_module is built as "backpacks.{id}.{pipeline_rel_without_ext}"
  so importlib.import_module() resolves it when nova_root is in sys.path
- local_config_path → runtime/{backpack_id}/settings.json
  This is the flat settings file the BackpackInstaller writes at install time
  and that the connector reads via manifest.local_config_path
- schema_manifest_path / query_templates_path point into the backpack dir;
  if the files don't exist, BaseDataPipeline returns {} (no raise)
"""

import json
from pathlib import Path
from typing import Any

from pipelines.base import PipelineManifest


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _module_from_rel_path(backpack_id: str, rel_file: str) -> str:
    """
    Translate a relative file path to a Python module path scoped under backpacks.

    'pipeline/connector.py' → 'backpacks.edfi.pipeline.connector'
    """
    normalized = rel_file.replace("\\", "/")
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    parts = normalized.replace("/", ".")
    return f"backpacks.{backpack_id}.{parts}"


def load_backpack_manifest(
    backpack_dir: Path,
    *,
    nova_root: Path,
    runtime_root: Path,
) -> PipelineManifest:
    """
    Parse backpack.json and return a PipelineManifest.

    Args:
        backpack_dir:  Absolute path to the backpack root (e.g. backpacks/edfi/).
        nova_root:     Nova project root (C:\\NOVA). Used to resolve relative runtime paths.
        runtime_root:  Nova runtime root (C:\\NOVA\\runtime). Settings file written here.

    Raises:
        ValueError: if backpack.json is missing or has no 'id' field.
    """
    backpack_dir = backpack_dir.resolve()
    data = _read_json(backpack_dir / "backpack.json")
    if not data:
        raise ValueError(f"backpack.json missing or empty in {backpack_dir}")

    backpack_id = str(data.get("id") or "").strip()
    if not backpack_id:
        raise ValueError(f"backpack.json missing 'id' in {backpack_dir}")

    pipeline_id = str(data.get("pipeline_id") or backpack_id).strip()
    tools = data.get("tools") or {}

    connector_class = str(tools.get("pipeline_class") or "").strip()
    pipeline_rel = str(tools.get("pipeline") or "").strip()
    connector_module = _module_from_rel_path(backpack_id, pipeline_rel) if pipeline_rel else ""

    runtime_block = data.get("runtime") or {}

    # Audit log path: resolve relative to nova_root if not absolute
    audit_log_rel = str(runtime_block.get("audit_log") or "").strip()
    audit_log_path: Path | None = None
    if audit_log_rel:
        p = Path(audit_log_rel)
        audit_log_path = p if p.is_absolute() else (nova_root / p).resolve()

    # Settings file: written by BackpackInstaller, read by connector._settings()
    # via manifest.local_config_path
    local_config_path = (runtime_root / backpack_id / "settings.json").resolve()

    return PipelineManifest(
        pipeline_id=pipeline_id,
        display_name=str(data.get("name") or pipeline_id),
        kind="backpack",
        version=str(data.get("version") or "0.1.0"),
        description=str(data.get("description") or data.get("name") or pipeline_id),
        read_only=bool(data.get("read_only", True)),
        network_scope=str(data.get("network_scope") or "local"),
        connector_module=connector_module,
        connector_class=connector_class,
        pipeline_dir=backpack_dir,
        # backpack pipelines don't use these files but BaseDataPipeline.load_*
        # returns {} gracefully when the file doesn't exist
        schema_manifest_path=backpack_dir / "schema_manifest.json",
        query_templates_path=backpack_dir / "query_templates.json",
        # Prefer backpack-local templates; connector safe_query requires them.
        local_config_path=local_config_path,
        audit_log_path=audit_log_path,
        meta={
            "backpack_id": backpack_id,
            "protocol_version": str(data.get("protocol_version") or "backpack.v1"),
            "operations": str(data.get("operations") or "operations.json"),
            "settings": str(data.get("settings") or "settings_schema.json"),
            "brief": str(data.get("brief") or "brief.md"),
            "tools": dict(tools),
            "requires": dict(data.get("requires") or {}),
            "runtime": dict(runtime_block),
        },
    )
