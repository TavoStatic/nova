import json
import tempfile
import unittest
from pathlib import Path

from services.backpack_host.loader import load_backpack_manifest
from services.backpack_host.ops_map import pipeline_op_to_backpack_op, resolve_shell_role


class TestBackpackHost(unittest.TestCase):
    def test_loads_synthetic_manifest_and_operation_map(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backpack = root / "backpacks" / "example_backpack"
            backpack.mkdir(parents=True)
            (backpack / "backpack.json").write_text(json.dumps({
                "id": "example_backpack",
                "name": "Example Backpack",
                "pipeline_id": "inventory_connector",
                "tools": {"pipeline": "connector.py", "pipeline_class": "InventoryConnector"},
                "operations": "operations.json",
            }), encoding="utf-8")
            (backpack / "operations.json").write_text(json.dumps({"operations": [
                {"id": "view_status", "pipeline_operation": "status"},
                {"id": "view_items", "pipeline_operation": "inventory/items"},
            ]}), encoding="utf-8")
            manifest = load_backpack_manifest(backpack, nova_root=root, runtime_root=root / "runtime")
            self.assertEqual(manifest.pipeline_id, "inventory_connector")
            self.assertEqual(manifest.kind, "backpack")
            self.assertEqual(pipeline_op_to_backpack_op(backpack, "inventory/items"), "view_items")

    def test_resolves_generic_shell_roles(self):
        self.assertEqual(resolve_shell_role(role="viewer"), "viewer")
        self.assertEqual(resolve_shell_role(is_admin=True), "account_admin")
