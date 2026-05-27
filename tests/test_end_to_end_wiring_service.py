from __future__ import annotations

import unittest

from services.end_to_end_wiring import run_end_to_end_wiring_check


class EndToEndWiringServiceTests(unittest.TestCase):
    def test_offline_wiring_check_closes_source_self_repair_lane(self) -> None:
        report = run_end_to_end_wiring_check(include_runtime=False)

        names = {check["name"] for check in report["checks"]}
        self.assertIn("frontdoor:command_cases", names)
        self.assertIn("data-lanes:registry", names)
        self.assertIn("release-clean:frontdoor_wired", names)
        self.assertIn("wiring-source:self-repair-closure", names)
        self.assertIn("runtime:live_checks", names)
        failed = {check["name"]: check for check in report["checks"] if not check.get("ok")}
        self.assertNotIn("wiring-source:self-repair-closure", failed)
        self_repair = next(check for check in report["checks"] if check["name"] == "wiring-source:self-repair-closure")
        data = self_repair.get("data") or {}
        self.assertTrue(self_repair["ok"], self_repair)
        self.assertEqual(data.get("gap_count"), 0)
        self.assertEqual(data.get("gap_roots"), [])


if __name__ == "__main__":
    unittest.main()
