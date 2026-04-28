from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class PipelineManifest:
    pipeline_id: str
    display_name: str
    kind: str
    version: str
    description: str
    read_only: bool
    network_scope: str
    safe_operations: tuple[str, ...] = field(default_factory=tuple)
    connector_module: str = ""
    connector_class: str = ""
    pipeline_dir: Path = Path(".")
    schema_manifest_path: Path = Path("schema_manifest.json")
    query_templates_path: Path = Path("query_templates.json")
    field_dictionary_path: Optional[Path] = None
    config_example_path: Optional[Path] = None
    local_config_path: Optional[Path] = None
    audit_log_path: Optional[Path] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "version": self.version,
            "description": self.description,
            "read_only": self.read_only,
            "network_scope": self.network_scope,
            "safe_operations": list(self.safe_operations),
            "connector_module": self.connector_module,
            "connector_class": self.connector_class,
            "pipeline_dir": str(self.pipeline_dir),
            "schema_manifest_path": str(self.schema_manifest_path),
            "query_templates_path": str(self.query_templates_path),
            "field_dictionary_path": str(self.field_dictionary_path) if self.field_dictionary_path else None,
            "config_example_path": str(self.config_example_path) if self.config_example_path else None,
            "local_config_path": str(self.local_config_path) if self.local_config_path else None,
            "audit_log_path": str(self.audit_log_path) if self.audit_log_path else None,
        }


class BaseDataPipeline(ABC):
    """Common contract for Nova-native data pipelines."""

    def __init__(self, manifest: PipelineManifest):
        self.manifest = manifest
        self._schema_manifest_cache: Optional[dict[str, Any]] = None
        self._query_template_cache: Optional[dict[str, dict[str, Any]]] = None
        self._field_dictionary_cache: Optional[dict[str, Any]] = None

    def load_schema_manifest(self) -> dict[str, Any]:
        if self._schema_manifest_cache is None:
            self._schema_manifest_cache = _read_json_dict(self.manifest.schema_manifest_path)
        return dict(self._schema_manifest_cache)

    def load_query_templates(self) -> dict[str, dict[str, Any]]:
        if self._query_template_cache is None:
            raw = _read_json_dict(self.manifest.query_templates_path)
            normalized: dict[str, dict[str, Any]] = {}
            for key, value in raw.items():
                if not isinstance(value, dict):
                    continue
                normalized[str(key)] = dict(value)
            self._query_template_cache = normalized
        return {name: dict(template) for name, template in self._query_template_cache.items()}

    def load_field_dictionary(self) -> dict[str, Any]:
        if self.manifest.field_dictionary_path is None:
            return {}
        if self._field_dictionary_cache is None:
            self._field_dictionary_cache = _read_json_dict(self.manifest.field_dictionary_path)
        return dict(self._field_dictionary_cache)

    def schema_probe(self) -> dict[str, Any]:
        schema = self.load_schema_manifest()
        return {
            "pipeline_id": self.manifest.pipeline_id,
            "display_name": self.manifest.display_name,
            "kind": self.manifest.kind,
            "read_only": self.manifest.read_only,
            "network_scope": self.manifest.network_scope,
            "schema": schema,
            "field_dictionary": self.load_field_dictionary(),
            "query_templates": sorted(self.load_query_templates().keys()),
        }

    @abstractmethod
    def status(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def safe_query(
        self,
        operation: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        row_limit: Optional[int] = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        raise NotImplementedError
