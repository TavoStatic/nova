from __future__ import annotations

import unittest

from scripts.generate_nova_ledger import _latest_unique, _scan_finding_identity, render


class TestGenerateNovaLedger(unittest.TestCase):
    def test_scan_findings_collapse_cycle_reprints(self) -> None:
        findings = [
            {
                "entry_type": "ring1_scan",
                "ring": 1,
                "module": "map_integrity",
                "result": "drifted",
                "detail": "gap_count=14, unwired_roots=1, unclassified_files=13",
                "date": "2026-08-16",
            },
            {
                "entry_type": "ring1_scan",
                "ring": 1,
                "module": "map_integrity",
                "result": "drifted",
                "detail": "gap_count=14, unwired_roots=1, unclassified_files=13",
                "date": "2026-08-16",
            },
            {
                "entry_type": "ring1_scan",
                "ring": 1,
                "module": "nova_root_inventory",
                "result": "drifted",
                "detail": "13 source file(s) have no SOURCE_ROOT classification",
                "date": "2026-08-16",
            },
            {
                "entry_type": "ring2_scan",
                "ring": 2,
                "module": "live_closure",
                "result": "drifted",
                "detail": "closure_gaps=28",
                "date": "2026-08-16",
            },
            {
                "entry_type": "ring2_scan",
                "ring": 2,
                "module": "live_closure",
                "result": "drifted",
                "detail": "closure_gaps=35",
                "date": "2026-08-16",
            },
            {
                "entry_type": "drift_alert",
                "ring": 1,
                "module": "nova_root_inventory",
                "detail": "same alert also lives in Drift Alerts",
                "date": "2026-08-16",
            },
        ]
        text = render([], findings)
        scan_block = text.split("## Nova Scan Findings", 1)[1].split("## Drift Alerts", 1)[0]
        self.assertEqual(scan_block.count("Ring 1 `map_integrity`"), 1)
        self.assertEqual(scan_block.count("Ring 1 `nova_root_inventory`"), 1)
        self.assertEqual(scan_block.count("Ring 2 `live_closure`"), 1)
        self.assertIn("closure_gaps=35", scan_block)
        self.assertNotIn("closure_gaps=28", scan_block)
        self.assertNotIn("same alert also lives in Drift Alerts", scan_block)

    def test_latest_unique_keeps_last_key(self) -> None:
        rows = _latest_unique(
            [{"k": "a", "n": 1}, {"k": "a", "n": 2}, {"k": "b", "n": 3}],
            lambda row: row["k"],
        )
        self.assertEqual([row["n"] for row in rows], [2, 3])

    def test_scan_identity_ignores_fluctuating_counts(self) -> None:
        first = _scan_finding_identity({"entry_type": "ring2_scan", "ring": 2, "module": "x", "detail": "gaps=28"})
        second = _scan_finding_identity({"entry_type": "ring2_scan", "ring": 2, "module": "x", "detail": "gaps=35"})
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
