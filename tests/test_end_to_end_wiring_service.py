from __future__ import annotations

import unittest

from services.end_to_end_wiring import run_end_to_end_wiring_check


class EndToEndWiringServiceTests(unittest.TestCase):
    def test_offline_wiring_check_passes_for_current_repo(self) -> None:
        report = run_end_to_end_wiring_check(include_runtime=False)

        self.assertTrue(report["ok"], report)
        names = {check["name"] for check in report["checks"]}
        self.assertIn("frontdoor:command_cases", names)
        self.assertIn("data-lanes:registry", names)
        self.assertIn("release-clean:frontdoor_wired", names)
        self.assertIn("runtime:live_checks", names)


if __name__ == "__main__":
    unittest.main()
