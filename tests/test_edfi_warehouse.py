from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.edfi import warehouse as wh
from services.edfi import warehouse_sync as sync


class TestEdFiWarehouse(unittest.TestCase):
    def test_replace_and_list_schools(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(wh, "WAREHOUSE_ROOT", root):
                n = wh.replace_schools(
                    connection_id="district-main",
                    lea_id="031901",
                    rows=[
                        {"school_id": "1", "school_name": "Alpha High"},
                        {"school_id": "2", "school_name": "Beta Elem"},
                    ],
                    sync_run_id=1,
                )
                self.assertEqual(n, 2)
                rows = wh.list_schools(connection_id="district-main", lea_id="031901")
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["school_name"], "Alpha High")
                status = wh.warehouse_status("district-main", lea_id="031901")
                self.assertTrue(status["ok"])
                self.assertEqual(status["schools_count"], 2)

    def test_schedule_gate_respects_min_gap(self) -> None:
        settings = {
            "connection_id": "district-main",
            "district_lea_id": "031901",
            "warehouse_sync_enabled": True,
            "warehouse_sync_local_hour": 0,
            "warehouse_sync_min_gap_hours": 20,
        }
        last = {"finished_at": 1_700_000_000.0, "status": "ok"}
        with mock.patch.object(sync, "load_backpack_settings", return_value=settings), mock.patch(
            "services.edfi.warehouse.last_successful_sync",
            return_value=last,
        ), mock.patch("services.edfi.warehouse_sync.time") as t:
            t.time.return_value = 1_700_000_000.0 + (5 * 3600)  # 5 hours later
            gate = sync.due_for_scheduled_sync(settings=settings)
        self.assertFalse(gate["due"])
        self.assertEqual(gate["reason"], "min_gap_not_elapsed")


if __name__ == "__main__":
    unittest.main()
