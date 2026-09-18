import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.backpack_host.registry import BackpackAwarePipelineRegistry


class TestBackpackPipelineRegistry(unittest.TestCase):
    def test_discovers_synthetic_backpack_without_resurfacing_uninstalled_lane(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backpack = root / "backpacks" / "example_backpack"
            backpack.mkdir(parents=True)
            (backpack / "backpack.json").write_text(json.dumps({
                "id": "example_backpack", "pipeline_id": "inventory_connector"
            }), encoding="utf-8")
            with mock.patch(
                "services.backpack_host.install_state.backpack_runtime_installed", return_value=True
            ):
                registry = BackpackAwarePipelineRegistry(
                    root / "data_sources", root / "backpacks", nova_root=root, runtime_root=root / "runtime"
                )
                ids = [item.pipeline_id for item in registry.discover()]
            self.assertEqual(ids, ["inventory_connector"])
