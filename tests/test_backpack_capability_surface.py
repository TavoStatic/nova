from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.backpack_host.capability_surface import (
    declared_capabilities_edfi,
    load_last_scan,
    scan_backpack_fusion,
)


class TestBackpackCapabilitySurface(unittest.TestCase):
    def test_declared_capabilities_include_local_schools(self) -> None:
        ids = {c["id"] for c in declared_capabilities_edfi()}
        self.assertIn("edfi.schools_local", ids)
        self.assertIn("edfi.teach_rules", ids)

    def test_scan_runs_and_registers_tool(self) -> None:
        scan = scan_backpack_fusion("edfi", persist=True)
        self.assertIn("probes", scan)
        self.assertIn("available_capability_ids", scan)
        self.assertIn("nova_must_know", scan)
        self.assertTrue(scan.get("nova_must_know", {}).get("must_prefer_local"))
        probe_names = {p.get("probe") for p in scan.get("probes") or []}
        self.assertIn("tool_edfi_explore_registered", probe_names)
        tool_probe = next(
            p for p in scan["probes"] if p.get("probe") == "tool_edfi_explore_registered"
        )
        self.assertTrue(tool_probe.get("ok"), scan.get("probes"))

    def test_not_installed_scan_does_not_persist_and_drops_leftover_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scan_path = Path(tmp) / "capability_scan.json"
            scan_path.write_text(
                json.dumps({"ok": True, "installed": False, "status": "not_installed", "backpack_id": "edfi"}),
                encoding="utf-8",
            )
            with mock.patch("services.backpack_host.capability_surface.SCAN_PATH", scan_path), mock.patch(
                "services.backpack_host.install_state.backpack_runtime_installed",
                return_value=False,
            ):
                scan = scan_backpack_fusion("edfi", persist=True)
                last = load_last_scan()
            self.assertEqual(scan.get("status"), "not_installed")
            self.assertFalse(scan.get("installed"))
            self.assertNotIn("scan_path", scan)
            self.assertIsNone(last)
            self.assertFalse(scan_path.is_file())


if __name__ == "__main__":
    unittest.main()
