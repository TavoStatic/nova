from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.edfi import extract_store


class TestEdFiExtractStore(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(extract_store, "EXTRACTS_ROOT", root):
                path = extract_store.save_extract(
                    backpack_id="edfi",
                    intent="schools",
                    lea="031901",
                    connection_id="district-main",
                    columns=["school_id", "school_name"],
                    rows=[
                        {"school_id": "1", "school_name": "Alpha"},
                        {"school_id": "2", "school_name": "Beta"},
                    ],
                    summary="2 schools",
                )
                self.assertTrue(path.is_file())
                # Load without connection_id still finds the extract (connection-agnostic path).
                loaded = extract_store.load_extract(
                    backpack_id="edfi",
                    intent="schools_directory",
                    lea="031901",
                    connection_id="",
                )
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded["row_count"], 2)
                self.assertEqual(loaded["rows"][0]["school_name"], "Alpha")
                self.assertEqual(loaded["intent"], "schools")


class TestReportPrefersLocal(unittest.TestCase):
    def test_schools_report_uses_extract_without_ods(self) -> None:
        from services.backpack_host.reports import run_backpack_report

        fake_extract = {
            "columns": ["school_id", "school_name", "lea_id"],
            "rows": [{"school_id": "1", "school_name": "Local High", "lea_id": "031901"}],
            "row_count": 1,
            "summary": "1 school",
            "synced_at": "2026-07-24T00:00:00Z",
            "connection_id": "district-main",
            "lea": "031901",
            "extract_path": "x",
        }
        with mock.patch(
            "services.edfi.extract_store.load_extract",
            return_value=fake_extract,
        ), mock.patch(
            "services.backpack_host.query.run_backpack_query",
        ) as q:
            report = run_backpack_report(
                "schools",
                prefer_local=True,
                force_refresh=False,
                use_cache=True,
            )
        q.assert_not_called()
        self.assertTrue(report["ok"])
        self.assertTrue(report.get("from_extract"))
        self.assertEqual(report["rows"][0]["school_name"], "Local High")
        self.assertIn("local extract", report["summary"].lower())


if __name__ == "__main__":
    unittest.main()
