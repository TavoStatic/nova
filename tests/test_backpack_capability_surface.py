from __future__ import annotations

import unittest

from services.backpack_host.capability_surface import (
    declared_capabilities_edfi,
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


if __name__ == "__main__":
    unittest.main()
