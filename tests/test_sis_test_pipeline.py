from pathlib import Path
import unittest
from unittest import mock

from pipelines.registry import PipelineRegistry


class TestSisTestPipeline(unittest.TestCase):
    def setUp(self):
        self.registry = PipelineRegistry(Path(__file__).resolve().parents[1] / "data_sources")
        self.pipeline = self.registry.instantiate("sis_test")

    def test_schema_probe_exposes_known_entities(self):
        probe = self.pipeline.schema_probe()
        entity_names = [item["name"] for item in probe["schema"]["entities"]]
        self.assertIn("student_registration", entity_names)
        self.assertIn("program_memberships", entity_names)
        self.assertIn("district_registration_history", entity_names)
        field_dictionary = probe["field_dictionary"]
        self.assertEqual(field_dictionary["source_summary"]["primary_shape"], "eschoolplus")
        field_names = [item["field"] for item in field_dictionary["fields"]]
        self.assertIn("reg.student_id", field_names)
        self.assertIn("reg_contact.email", field_names)
        self.assertIn("reg_entry_with.grade", field_names)
        table_names = [item["table"] for item in field_dictionary["table_families"]]
        self.assertIn("dbo.REG_ENTRY_WITH", table_names)
        usage_types = [item["question_type"] for item in field_dictionary["usage_patterns"]]
        self.assertIn("current_year_grade_change_history", usage_types)

    def test_status_exposes_local_config_path(self):
        with mock.patch.object(self.pipeline, "_installed_odbc_drivers", return_value=["ODBC Driver 17 for SQL Server"]):
            with mock.patch.object(self.pipeline, "_network_probe", return_value={"reachable": True, "reason": "connected"}):
                with mock.patch.object(self.pipeline, "_auth_probe", return_value={"authenticated": False, "reason": "login failed"}):
                    status = self.pipeline.status()
        self.assertEqual(status["pipeline_id"], "sis_test")
        self.assertTrue(status["local_config_path"].endswith("local_config.json"))
        self.assertEqual(status["query_template_count"], 3)
        self.assertEqual(status["driver_selected"], "ODBC Driver 17 for SQL Server")
        self.assertFalse(status["live_query_ready"])

    def test_safe_query_denies_missing_required_identifier(self):
        result = self.pipeline.safe_query("student_lookup", {"campus_id": "101"})
        self.assertFalse(result["ok"])
        self.assertIn("requires one of", result["error"])

    def test_safe_query_live_mode_blocks_when_not_ready(self):
        with mock.patch.object(self.pipeline, "status", return_value={
            "live_query_ready": False,
            "auth_probe": {"reason": "login failed"},
        }):
            result = self.pipeline.safe_query(
                "student_lookup",
                {"student_id": "12345"},
                dry_run=False,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution_mode"], "blocked")
        self.assertIn("login failed", result["error"])

    def test_safe_query_live_mode_executes_when_ready(self):
        with mock.patch.object(self.pipeline, "status", return_value={
            "live_query_ready": True,
            "driver_selected": "ODBC Driver 17 for SQL Server",
        }):
            with mock.patch.object(self.pipeline, "_execute_live_query", return_value={
                "columns": ["STUDENT_ID"],
                "rows": [{"STUDENT_ID": "12345"}],
                "row_count": 1,
            }):
                result = self.pipeline.safe_query(
                    "student_lookup",
                    {"student_id": "12345"},
                    dry_run=False,
                )
        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_mode"], "live")
        self.assertEqual(result["row_count"], 1)

    def test_sanitize_error_text_redacts_password_and_normalizes_login_failure(self):
        message = self.pipeline._sanitize_error_text(
            'Provider=MSDASQL;Uid=guribe.tst;Pwd=supersecret; Login failed for user "guribe.tst".',
            {"username": "guribe.tst", "password": "supersecret"},
        )
        self.assertEqual(
            message,
            "Login failed for configured SIS read-only user (guribe.tst).",
        )


if __name__ == "__main__":
    unittest.main()
