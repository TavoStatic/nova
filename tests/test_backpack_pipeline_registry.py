from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.backpack_host.registry import BackpackAwarePipelineRegistry


class TestUninstalledBackpackHidesLegacyLane(unittest.TestCase):
    def test_uninstalled_edfi_does_not_resurface_edfi_bisd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_sources = root / "data_sources" / "edfi_bisd"
            data_sources.mkdir(parents=True)
            (data_sources / "pipeline.json").write_text(
                json.dumps(
                    {
                        "pipeline_id": "edfi_bisd",
                        "display_name": "legacy edfi",
                        "kind": "edfi",
                        "connector_module": "missing",
                        "connector_class": "Missing",
                    }
                ),
                encoding="utf-8",
            )
            backpack = root / "backpacks" / "edfi"
            backpack.mkdir(parents=True)
            (backpack / "backpack.json").write_text(
                json.dumps({"id": "edfi", "name": "Ed-Fi", "pipeline_id": "edfi"}),
                encoding="utf-8",
            )
            (backpack / "settings_schema.json").write_text("{}", encoding="utf-8")
            runtime = root / "runtime"
            (runtime / "backpacks" / "uninstalled").mkdir(parents=True)
            (runtime / "backpacks" / "uninstalled" / "edfi.json").write_text(
                json.dumps(
                    {
                        "backpack_id": "edfi",
                        "status": "uninstalled",
                        "touch_points": {"pipeline_ids": ["edfi", "edfi_bisd"]},
                    }
                ),
                encoding="utf-8",
            )

            registry = BackpackAwarePipelineRegistry(
                root / "data_sources",
                root / "backpacks",
                nova_root=root,
                runtime_root=runtime,
            )
            ids = [item.pipeline_id for item in registry.discover()]
            self.assertNotIn("edfi_bisd", ids)
            self.assertNotIn("edfi", ids)

    def test_unrelated_data_source_lane_stays_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_sources = root / "data_sources" / "sis_test"
            data_sources.mkdir(parents=True)
            (data_sources / "pipeline.json").write_text(
                json.dumps(
                    {
                        "pipeline_id": "sis_test",
                        "display_name": "SIS test",
                        "kind": "sis",
                        "connector_module": "missing",
                        "connector_class": "Missing",
                    }
                ),
                encoding="utf-8",
            )
            backpack = root / "backpacks" / "edfi"
            backpack.mkdir(parents=True)
            (backpack / "backpack.json").write_text(
                json.dumps({"id": "edfi", "pipeline_id": "edfi"}),
                encoding="utf-8",
            )
            (backpack / "settings_schema.json").write_text("{}", encoding="utf-8")
            runtime = root / "runtime"
            runtime.mkdir()

            registry = BackpackAwarePipelineRegistry(
                root / "data_sources",
                root / "backpacks",
                nova_root=root,
                runtime_root=runtime,
            )
            ids = [item.pipeline_id for item in registry.discover()]
            self.assertIn("sis_test", ids)
            self.assertNotIn("edfi", ids)


if __name__ == "__main__":
    unittest.main()
