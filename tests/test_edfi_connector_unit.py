from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipelines.base import PipelineManifest
from backpacks.edfi.pipeline.connector import EdFiPipeline


def _manifest(tmp: Path) -> PipelineManifest:
    settings = tmp / "settings.json"
    settings.write_text(
        '{"connection_id":"c1","scope_mode":"single_lea","district_lea_id":"031901"}',
        encoding="utf-8",
    )
    return PipelineManifest(
        pipeline_id="edfi",
        display_name="Ed-Fi",
        kind="backpack",
        version="1.0.0",
        description="test",
        read_only=True,
        network_scope="district",
        connector_module="backpacks.edfi.pipeline.connector",
        connector_class="EdFiPipeline",
        pipeline_dir=tmp,
        schema_manifest_path=tmp / "schema_manifest.json",
        query_templates_path=tmp / "query_templates.json",
        local_config_path=settings,
        audit_log_path=tmp / "audit.jsonl",
        meta={"backpack_id": "edfi"},
    )


class TestEdFiConnectorUnit(unittest.TestCase):
    def test_scope_snapshot_and_lea_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipe = EdFiPipeline(_manifest(Path(tmp)))
            snap = pipe._scope_snapshot()
            self.assertEqual(snap["scope_mode"], "single_lea")
            self.assertEqual(snap["district_lea_id"], "31901")

            lea, err = pipe._resolve_lea_for_query({})
            self.assertIsNone(err)
            self.assertEqual(lea, "31901")

            lea2, err2 = pipe._resolve_lea_for_query({"district_lea_id": "031901"})
            self.assertIsNone(err2)
            self.assertEqual(lea2, "31901")

    def test_readiness_blockers_when_no_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipe = EdFiPipeline(_manifest(Path(tmp)))
            with mock.patch(
                "backpacks.edfi.pipeline.connector.load_connection_config",
                return_value=None,
            ), mock.patch(
                "backpacks.edfi.pipeline.connector.load_capability_profile",
                return_value={},
            ), mock.patch(
                "backpacks.edfi.pipeline.connector.load_sync_state",
                return_value={},
            ):
                readiness = pipe._readiness()
            self.assertIn("edfi_connection_config_missing", readiness["blockers"])
            self.assertFalse(readiness["ready"])

    def test_multi_lea_rejects_outside_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Build manifest first (writes default settings), then replace settings.
            manifest = _manifest(root)
            manifest.local_config_path.write_text(  # type: ignore[union-attr]
                '{"scope_mode":"multi_lea","district_lea_id":"31901",'
                '"allowed_lea_ids":"31901,108904"}',
                encoding="utf-8",
            )
            pipe = EdFiPipeline(manifest)
            lea, err = pipe._resolve_lea_for_query({"lea_id": "99999"})
            self.assertEqual(err, "lea_not_in_allowed_list")
            self.assertEqual(lea, "")


if __name__ == "__main__":
    unittest.main()
