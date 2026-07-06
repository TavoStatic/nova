from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipelines.registry import PipelineRegistry
from services.data_pipeline_registry import (
    get_pipeline_schema_probe,
    get_pipeline_status,
    list_pipeline_summaries,
    preview_pipeline_query,
    run_pipeline_query,
)


DATA_SOURCES_ROOT = Path(__file__).resolve().parents[1] / "data_sources"
EDFI_BISD_ACTIVE = (DATA_SOURCES_ROOT / "edfi_bisd" / "pipeline.json").exists()


@unittest.skipUnless(EDFI_BISD_ACTIVE, "edfi_bisd lane is not present")
class TestEdFiBisdPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.data_sources_root = DATA_SOURCES_ROOT

    def test_registry_discovers_edfi_bisd(self) -> None:
        manifests = PipelineRegistry(self.data_sources_root).discover()
        ids = [item.pipeline_id for item in manifests]
        self.assertIn("edfi_bisd", ids)

    def test_status_reports_edfi_lane(self) -> None:
        with mock.patch(
            "data_sources.edfi_bisd.connector.load_connection_config",
            return_value=mock.Mock(district_lea_id="31901"),
        ), mock.patch(
            "data_sources.edfi_bisd.connector.load_capability_profile",
            return_value={"auth": {"ok": True}, "health": "ok"},
        ), mock.patch(
            "data_sources.edfi_bisd.connector.profile_summary",
            return_value={"ok": True, "health": "ok", "resource_count": 445},
        ):
            status = get_pipeline_status("edfi_bisd", data_sources_root=self.data_sources_root)
        self.assertEqual(status["pipeline_id"], "edfi_bisd")
        self.assertTrue(status["read_only"])
        self.assertEqual(status["district_lea_id"], "31901")
        self.assertTrue(status["live_query_ready"])

    def test_schema_probe_lists_templates(self) -> None:
        with mock.patch(
            "data_sources.edfi_bisd.connector.load_connection_config",
            return_value=mock.Mock(district_lea_id="31901"),
        ), mock.patch(
            "data_sources.edfi_bisd.connector.load_capability_profile",
            return_value={"auth": {"ok": True}},
        ), mock.patch(
            "data_sources.edfi_bisd.connector.profile_summary",
            return_value={"ok": True, "health": "ok", "resource_count": 10},
        ):
            probe = get_pipeline_schema_probe("edfi_bisd", data_sources_root=self.data_sources_root)
        self.assertIn("list_schools", probe["query_templates"])
        entities = probe["schema"]["entities"]
        self.assertTrue(any(item["name"] == "schools" for item in entities))

    def test_preview_list_schools_dry_run(self) -> None:
        with mock.patch(
            "data_sources.edfi_bisd.connector.load_connection_config",
            return_value=mock.Mock(district_lea_id="31901"),
        ), mock.patch(
            "data_sources.edfi_bisd.connector.load_capability_profile",
            return_value={"auth": {"ok": True}},
        ), mock.patch(
            "data_sources.edfi_bisd.connector.profile_summary",
            return_value={"ok": True, "health": "ok", "resource_count": 10},
        ):
            result = preview_pipeline_query(
                "edfi_bisd",
                "list_schools",
                {"offset": 0},
                row_limit=10,
                data_sources_root=self.data_sources_root,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_mode"], "dry_run")
        self.assertEqual(result["effective_row_limit"], 10)

    def test_live_list_schools_returns_rows(self) -> None:
        edfi_payload = {
            "ok": True,
            "resource": "ed-fi/schools",
            "items": [{"schoolId": 31901001, "nameOfInstitution": "Hanna Early College High School"}],
            "district_filter_strategy": "client_side",
            "records_scanned": 3200,
        }
        with mock.patch(
            "data_sources.edfi_bisd.connector.load_connection_config",
            return_value=mock.Mock(district_lea_id="31901"),
        ), mock.patch(
            "data_sources.edfi_bisd.connector.load_capability_profile",
            return_value={"auth": {"ok": True}},
        ), mock.patch(
            "data_sources.edfi_bisd.connector.profile_summary",
            return_value={"ok": True, "health": "ok", "resource_count": 10},
        ), mock.patch(
            "data_sources.edfi_bisd.connector.read_preset",
            return_value=edfi_payload,
        ):
            result = run_pipeline_query(
                "edfi_bisd",
                "list_schools",
                {},
                row_limit=5,
                data_sources_root=self.data_sources_root,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_mode"], "live")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["rows"][0]["schoolId"], 31901001)

    def test_list_summaries_includes_lane_state(self) -> None:
        summaries = list_pipeline_summaries(self.data_sources_root)
        match = next(item for item in summaries if item["pipeline_id"] == "edfi_bisd")
        self.assertIn("lane_state", match)


if __name__ == "__main__":
    unittest.main()