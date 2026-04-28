from pathlib import Path
import unittest
from unittest import mock

from services.data_pipeline_registry import get_pipeline_schema_probe
from services.data_pipeline_registry import get_pipeline_status
from services.data_pipeline_registry import list_pipeline_summaries
from services.data_pipeline_registry import preview_pipeline_query
from services.data_pipeline_registry import run_pipeline_query


class TestDataPipelineRegistryService(unittest.TestCase):
    def setUp(self):
        self.data_sources_root = Path(__file__).resolve().parents[1] / "data_sources"

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
        self.assertEqual(result["effective_row_limit"], 25)

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
