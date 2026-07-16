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
        self.assertIn("sync_status", probe["query_templates"])
        self.assertIn("changes_since", probe["query_templates"])
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
        self.assertTrue(result["redaction_applied"])
        self.assertEqual(result["redaction_profile"], "education_org_default")

    def test_live_list_students_redacts_sensitive_fields(self) -> None:
        edfi_payload = {
            "ok": True,
            "resource": "ed-fi/students",
            "items": [
                {
                    "studentUniqueId": "S123",
                    "firstName": "Ada",
                    "lastSurname": "Lovelace",
                    "birthDate": "2010-01-01",
                }
            ],
            "district_filter_strategy": "client_side",
            "records_scanned": 120,
            "scan_cap_hit": False,
            "district_page_complete": True,
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
                "list_students",
                {},
                row_limit=5,
                data_sources_root=self.data_sources_root,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["rows"][0]["firstName"], "[REDACTED]")
        self.assertEqual(result["rows"][0]["studentUniqueId"], "S123")
        self.assertEqual(result["edfi"]["district_page_complete"], True)

    def test_live_changes_since_students_redacts_sensitive_fields(self) -> None:
        edfi_payload = {
            "ok": True,
            "resource": "ed-fi/students",
            "items": [
                {
                    "studentUniqueId": "S123",
                    "firstName": "Ada",
                    "lastSurname": "Lovelace",
                    "birthDate": "2010-01-01",
                }
            ],
            "mechanism": "changeQueries",
            "min_change_version": 10,
            "next_change_version": 11,
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
            "data_sources.edfi_bisd.connector.pull_changes_since",
            return_value=edfi_payload,
        ):
            result = run_pipeline_query(
                "edfi_bisd",
                "changes_since",
                {"resource": "ed-fi/students"},
                row_limit=5,
                data_sources_root=self.data_sources_root,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["redaction_profile"], "student_default")
        self.assertEqual(result["rows"][0]["firstName"], "[REDACTED]")
        self.assertEqual(result["rows"][0]["studentUniqueId"], "S123")

    def test_live_error_response_redacts_edfi_items(self) -> None:
        edfi_payload = {
            "ok": False,
            "resource": "ed-fi/students",
            "error_code": "edfi_query_failed",
            "error": "upstream failure",
            "items": [
                {
                    "studentUniqueId": "S123",
                    "firstName": "Ada",
                }
            ],
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
                "list_students",
                {},
                row_limit=5,
                data_sources_root=self.data_sources_root,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["redaction_profile"], "student_default")
        self.assertEqual(result["edfi"]["items"][0]["firstName"], "[REDACTED]")

    def test_live_changes_since_students_redacts_when_resource_only_in_payload(self) -> None:
        edfi_payload = {
            "ok": True,
            "resource": "ed-fi/students",
            "items": [
                {
                    "studentUniqueId": "S123",
                    "firstName": "Ada",
                    "birthDate": "2010-01-01",
                }
            ],
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
            "data_sources.edfi_bisd.connector.pull_changes_since",
            return_value=edfi_payload,
        ):
            result = run_pipeline_query(
                "edfi_bisd",
                "changes_since",
                {},
                row_limit=5,
                data_sources_root=self.data_sources_root,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["redaction_profile"], "student_default")
        self.assertTrue(result["redaction_applied"])
        self.assertEqual(result["rows"][0]["firstName"], "[REDACTED]")

    def test_preview_sync_status_dry_run(self) -> None:
        with mock.patch(
            "data_sources.edfi_bisd.connector.load_connection_config",
            return_value=mock.Mock(district_lea_id="31901"),
        ), mock.patch(
            "data_sources.edfi_bisd.connector.load_capability_profile",
            return_value={"auth": {"ok": True}},
        ), mock.patch(
            "data_sources.edfi_bisd.connector.load_sync_state",
            return_value={"resources": {}},
        ), mock.patch(
            "data_sources.edfi_bisd.connector.profile_summary",
            return_value={"ok": True, "health": "ok", "resource_count": 10},
        ):
            result = preview_pipeline_query(
                "edfi_bisd",
                "sync_status",
                {},
                data_sources_root=self.data_sources_root,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_mode"], "dry_run")

    def test_list_summaries_includes_lane_state(self) -> None:
        summaries = list_pipeline_summaries(self.data_sources_root)
        match = next(item for item in summaries if item["pipeline_id"] == "edfi_bisd")
        self.assertIn("lane_state", match)


if __name__ == "__main__":
    unittest.main()