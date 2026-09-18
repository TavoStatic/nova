import json
import tempfile
import unittest
from pathlib import Path

from services.control_backpacks import ControlBackpacksService


class TestControlBackpacksService(unittest.TestCase):
    def test_lists_and_installs_synthetic_backpack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backpack = root / "backpacks" / "example_backpack"
            backpack.mkdir(parents=True)
            (backpack / "backpack.json").write_text(json.dumps({
                "id": "example_backpack", "pipeline_id": "inventory_connector", "name": "Example Backpack"
            }), encoding="utf-8")
            (backpack / "settings_schema.json").write_text(json.dumps({"sections": [{"fields": [
                {"key": "endpoint", "label": "Endpoint", "type": "url", "required": True}
            ]}]}), encoding="utf-8")
            service = ControlBackpacksService(backpacks_root=root / "backpacks", runtime_root=root / "runtime", nova_root=root)
            self.assertEqual(service.list_backpacks()[0]["backpack_id"], "example_backpack")
            ok, message, _extra, _rows = service.install({"backpack_id": "example_backpack", "settings": {"endpoint": "https://example.invalid"}}, skip_profile=True)
            self.assertTrue(ok, message)
            self.assertTrue((root / "runtime" / "example_backpack" / "settings.json").exists())
