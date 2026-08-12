from __future__ import annotations

"""
Backpack-Aware Pipeline Registry

Extends PipelineRegistry to also discover backpacks from backpacks/*/ in
addition to the existing data_sources/*/ pipelines.

Backpack manifests (backpack.json) are translated to PipelineManifest via
the BackpackManifestLoader so the existing instantiate() machinery works
unchanged: importlib.import_module(connector_module) resolves the pipeline
class from the backpack's pipeline/connector.py.

Merge rule: if a backpack has the same pipeline_id as a data_sources pipeline,
the backpack wins. This allows backpacks to provide domain-specific
pipelines (e.g., data_connector → edfi) when the district migrates to the backpack.
"""

import logging
from pathlib import Path
from typing import Optional

from pipelines.base import PipelineManifest
from pipelines.registry import PipelineRegistry
from services.backpack_host.loader import load_backpack_manifest

logger = logging.getLogger(__name__)


class BackpackAwarePipelineRegistry(PipelineRegistry):
    """
    PipelineRegistry that also discovers backpacks from backpacks_root.

    Args:
        data_sources_root:  Path to data_sources/ (existing pipeline.json manifests)
        backpacks_root:     Path to backpacks/ (backpack.json manifests)
        nova_root:          Nova project root; defaults to BASE_DIR from runtime context
        runtime_root:       Nova runtime root; defaults to RUNTIME_DIR
    """

    def __init__(
        self,
        data_sources_root: Path,
        backpacks_root: Path,
        *,
        nova_root: Optional[Path] = None,
        runtime_root: Optional[Path] = None,
    ) -> None:
        super().__init__(data_sources_root)
        self.backpacks_root = backpacks_root.resolve()

        # Defer runtime context import so this module can be imported early
        if nova_root is None or runtime_root is None:
            from services.nova_runtime_context import BASE_DIR, RUNTIME_DIR
            nova_root = nova_root or BASE_DIR
            runtime_root = runtime_root or RUNTIME_DIR

        self._nova_root = nova_root
        self._runtime_root = runtime_root
        self._backpack_manifest_cache: Optional[dict[str, PipelineManifest]] = None

    # ── Backpack discovery ─────────────────────────────────────────────────

    def _discover_backpacks(self, *, refresh: bool = False) -> list[PipelineManifest]:
        if refresh or self._backpack_manifest_cache is None:
            manifests: dict[str, PipelineManifest] = {}
            if self.backpacks_root.exists():
                for child in sorted(self.backpacks_root.iterdir()):
                    if not child.is_dir():
                        continue
                    if not (child / "backpack.json").exists():
                        continue
                    try:
                        manifest = load_backpack_manifest(
                            child,
                            nova_root=self._nova_root,
                            runtime_root=self._runtime_root,
                        )
                        manifests[manifest.pipeline_id] = manifest
                    except Exception as exc:
                        # Bad backpack.json should not crash the host
                        logger.warning(
                            "backpack_manifest_load_failed backpack_dir=%s error=%s",
                            child,
                            exc,
                        )
            self._backpack_manifest_cache = manifests
        return list(self._backpack_manifest_cache.values())

    # ── Override discover ──────────────────────────────────────────────────

    def discover(self, *, refresh: bool = False) -> list[PipelineManifest]:
        """
        Return all pipeline manifests: data_sources pipelines + backpacks.

        Backpacks shadow same-id data_sources pipelines (intentional: migration
        path from data_connector → edfi).
        """
        pipeline_manifests = {m.pipeline_id: m for m in super().discover(refresh=refresh)}
        backpack_manifests = {m.pipeline_id: m for m in self._discover_backpacks(refresh=refresh)}
        merged = {**pipeline_manifests, **backpack_manifests}
        return sorted(merged.values(), key=lambda m: m.pipeline_id.lower())
