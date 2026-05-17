from pathlib import Path
import unittest
from unittest import mock

from services.data_pipeline_registry import get_pipeline_schema_probe
from services.data_pipeline_registry import get_pipeline_status
from services.data_pipeline_registry import list_pipeline_summaries
from services.data_pipeline_registry import plan_pipeline_report
from services.data_pipeline_registry import preview_pipeline_query
from services.data_pipeline_registry import run_pipeline_query
from services.data_pipeline_registry import search_pipeline_vendor_dictionary


DATA_SOURCES_ROOT = Path(__file__).resolve().parents[1] / "data_sources"
SIS_TEST_ACTIVE = (DATA_SOURCES_ROOT / "sis_test" / "pipeline.json").exists()
INSTALL_PROFILE_LANES = ("sis_test",)
INSTALL_PROFILE_INACTIVE_BEHAVIOR = "skip_when_absent"


@unittest.skipUnless(SIS_TEST_ACTIVE, "sis_test pipeline is not active in this install")
class TestDataPipelineRegistryService(unittest.TestCase):
    def setUp(self):
        self.data_sources_root = DATA_SOURCES_ROOT

    def test_list_pipeline_summaries_includes_sis_test(self):
        summaries = list_pipeline_summaries(self.data_sources_root)
        pipeline_ids = [item["pipeline_id"] for item in summaries]
        self.assertIn("sis_test", pipeline_ids)

    def test_get_pipeline_status_reports_read_only_pipeline(self):
        status = get_pipeline_status("sis_test", data_sources_root=self.data_sources_root)
        self.assertEqual(status["pipeline_id"], "sis_test")
        self.assertTrue(status["read_only"])
        self.assertEqual(status["network_scope"], "district_only")
        self.assertTrue(status["execution_supported"])

    def test_get_pipeline_schema_probe_returns_grounded_tables(self):
        probe = get_pipeline_schema_probe("sis_test", data_sources_root=self.data_sources_root)
        entities = probe["schema"]["entities"]
        table_names = {table for entity in entities for table in entity.get("tables", [])}
        self.assertIn("dbo.REG", table_names)
        self.assertIn("dbo.REG_PROGRAMS", table_names)
        population_keys = {item["key"] for item in probe["population_definitions"]["populations"]}
        self.assertIn("eb", population_keys)
        self.assertIn("sped", population_keys)

    def test_search_pipeline_vendor_dictionary_finds_core_columns(self):
        result = search_pipeline_vendor_dictionary(
            "sis_test",
            "program_id",
            data_sources_root=self.data_sources_root,
            limit=20,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["grounding_status"], "vendor_dictionary_grounded")
        tables = [item["table"] for item in result["matches"]]
        self.assertIn("dbo.REG_PROGRAMS", tables)
        reg_programs = next(item for item in result["matches"] if item["table"] == "dbo.REG_PROGRAMS")
        column_names = [item["name"] for item in reg_programs["column_hits"]]
        self.assertIn("PROGRAM_ID", column_names)

    def test_plan_pipeline_report_matches_population_and_candidate_tables(self):
        result = plan_pipeline_report(
            "sis_test",
            "show EB students by campus",
            data_sources_root=self.data_sources_root,
            limit=8,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["default_row_limit"], 20)
        self.assertEqual(result["matched_populations"][0]["key"], "eb")
        self.assertEqual(result["suggested_operation"], "program_membership_lookup")
        self.assertEqual(result["intent"]["report_kind"], "student_population")
        self.assertIn("campus", result["intent"]["group_by"])
        self.assertEqual(result["intent"]["filters"][0]["program_id"], "146")
        self.assertEqual(result["intent"]["filters"][0]["field_number"], "5")
        required_tables = [item["table"] for item in result["required_tables"]]
        self.assertEqual(required_tables[:2], ["dbo.REG_PROGRAMS", "dbo.REG"])
        self.assertIn("dbo.REG_BUILDING", required_tables)
        reg_building = next(item for item in result["required_tables"] if item["table"] == "dbo.REG_BUILDING")
        self.assertEqual(reg_building["role"], "support_lookup")
        self.assertEqual(reg_building["join_key"], "BUILDING")
        self.assertEqual(reg_building["active_status_source"], "unresolved")
        self.assertEqual(reg_building["activity_inference"]["signal"], "current_student_records_by_building")
        self.assertEqual(reg_building["activity_inference"]["evidence_tables"], ["dbo.REG"])
        self.assertEqual(reg_building["active_status_candidates_to_verify"][0]["table"], "dbo.REGTB_BLDG_TYPES")
        tables = [item["table"] for item in result["candidate_tables"]]
        self.assertIn("dbo.REG_PROGRAMS", tables)

    def test_preview_pipeline_query_returns_governed_dry_run(self):
        result = preview_pipeline_query(
            "sis_test",
            "student_lookup",
            {"student_id": "12345"},
            row_limit=200,
            data_sources_root=self.data_sources_root,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_mode"], "dry_run")
        self.assertEqual(result["effective_row_limit"], 20)

    def test_preview_schema_inventory_uses_twenty_row_guard(self):
        result = preview_pipeline_query(
            "sis_test",
            "schema_inventory",
            {"schema_like": "dbo", "table_like": "REG_%"},
            row_limit=200,
            data_sources_root=self.data_sources_root,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_mode"], "dry_run")
        self.assertEqual(result["effective_row_limit"], 20)
        self.assertEqual(result["params"]["table_like"], "REG_%")

    def test_preview_pipeline_query_blocks_paused_lane(self):
        control_path = self.data_sources_root / "sis_test" / "lane_control.json"
        old_text = control_path.read_text(encoding="utf-8") if control_path.exists() else None
        try:
            control_path.write_text('{"enabled": false, "state": "paused"}', encoding="utf-8")
            result = preview_pipeline_query(
                "sis_test",
                "student_lookup",
                {"student_id": "12345"},
                data_sources_root=self.data_sources_root,
            )
        finally:
            if old_text is None:
                control_path.unlink(missing_ok=True)
            else:
                control_path.write_text(old_text, encoding="utf-8")

        self.assertFalse(result["ok"])
        self.assertEqual(result["execution_mode"], "blocked")
        self.assertIn("paused", result["error"])

    def test_run_pipeline_query_requests_live_mode(self):
        with mock.patch(
            "services.data_pipeline_registry.build_pipeline_registry"
        ) as build_registry:
            pipeline = mock.Mock()
            pipeline.safe_query.return_value = {"ok": True, "execution_mode": "live"}
            registry = mock.Mock()
            registry.instantiate.return_value = pipeline
            build_registry.return_value = registry

            result = run_pipeline_query(
                "sis_test",
                "student_lookup",
                {"student_id": "12345"},
            )

            self.assertTrue(result["ok"])
            pipeline.safe_query.assert_called_once_with(
                "student_lookup",
                {"student_id": "12345"},
                row_limit=None,
                dry_run=False,
            )


if __name__ == "__main__":
    unittest.main()
