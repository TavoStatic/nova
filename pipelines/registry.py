from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Optional

from pipelines.base import BaseDataPipeline
from pipelines.base import PipelineManifest
from pipelines.loaders import load_pipeline_manifest


class PipelineRegistry:
    """Discover and instantiate Nova-native data pipelines."""

    def __init__(self, data_sources_root: Path):
        self.data_sources_root = data_sources_root.resolve()
        self._manifest_cache: Optional[dict[str, PipelineManifest]] = None

    def discover(self, *, refresh: bool = False) -> list[PipelineManifest]:
        if refresh or self._manifest_cache is None:
            manifests: dict[str, PipelineManifest] = {}
            if self.data_sources_root.exists():
                for child in self.data_sources_root.iterdir():
                    if not child.is_dir():
                        continue
                    manifest_path = child / "pipeline.json"
                    if not manifest_path.exists():
                        continue
                    manifest = load_pipeline_manifest(child)
                    manifests[manifest.pipeline_id] = manifest
            self._manifest_cache = manifests
        return [
            self._manifest_cache[pipeline_id]
            for pipeline_id in sorted(self._manifest_cache.keys(), key=str.lower)
        ]

    def list_summaries(self) -> list[dict[str, object]]:
        return [manifest.summary() for manifest in self.discover()]

    def get_manifest(self, pipeline_id: str) -> PipelineManifest:
        wanted = (pipeline_id or "").strip().lower()
        for manifest in self.discover():
            if manifest.pipeline_id.lower() == wanted:
                return manifest
        raise KeyError(pipeline_id)

    def instantiate(self, pipeline_id: str) -> BaseDataPipeline:
        manifest = self.get_manifest(pipeline_id)
        try:
            module = importlib.import_module(manifest.connector_module)
        except ModuleNotFoundError:
            connector_path = manifest.pipeline_dir / "connector.py"
            if not connector_path.exists():
                raise
            module_name = f"_nova_pipeline_{manifest.pipeline_id}"
            spec = importlib.util.spec_from_file_location(module_name, connector_path)
            if spec is None or spec.loader is None:
                raise
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        pipeline_class = getattr(module, manifest.connector_class)
        return pipeline_class(manifest)
