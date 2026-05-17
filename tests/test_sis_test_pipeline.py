from pathlib import Path
import unittest
from unittest import mock

from pipelines.registry import PipelineRegistry


DATA_SOURCES_ROOT = Path(__file__).resolve().parents[1] / "data_sources"
SIS_TEST_ACTIVE = (DATA_SOURCES_ROOT / "sis_test" / "pipeline.json").exists()
INSTALL_PROFILE_LANES = ("sis_test",)
INSTALL_PROFILE_INACTIVE_BEHAVIOR = "skip_when_absent"


@unittest.skipUnless(SIS_TEST_ACTIVE, "sis_test pipeline is not active in this install")
class TestSisTestPipeline(unittest.TestCase):
    def setUp(self):
        self.registry = PipelineRegistry(DATA_SOURCES_ROOT)
        self.pipeline = self.registry.instantiate("sis_test")

    def test_schema_probe_exposes_known_entities(self):
        probe = self.pipeline.schema_probe()
        self.assertEqual(probe["schema"]["source"]["verification_status"], "seeded_unverified")
        self.assertEqual(probe["vendor_dictionary"]["source"]["grounding_status"], "vendor_dictionary_grounded")
        self.assertGreater(probe["vendor_dictionary"]["table_count"], 1000)
        self.assertGreaterEqual(probe["predefined_reports"]["summary"]["module_count"], 20)
        report_tables = [item["table"] for item in probe["predefined_reports"]["top_tables"]]
        self.assertIn("dbo.REG", report_tables)
        self.assertIn("dbo.REG_PROGRAMS", report_tables)
        entity_names = [item["name"] for item in probe["schema"]["entities"]]
        self.assertIn("student_registration", entity_names)
        self.assertIn("program_memberships", entity_names)
        self.assertIn("district_registration_history", entity_names)
        self.assertNotIn("student_contact_and_identity", entity_names)
        self.assertNotIn("student_gpa_and_rank", entity_names)
        field_dictionary = probe["field_dictionary"]
        self.assertEqual(field_dictionary["source_summary"]["primary_shape"], "eschoolplus")
        populations = probe["population_definitions"]["populations"]
        population_by_key = {item["key"]: item for item in populations}
        self.assertEqual(population_by_key["foster"]["program_id"], "146")
        self.assertEqual(population_by_key["foster"]["field_number"], "31")
        self.assertEqual(population_by_key["sped"]["program_id"], "148")
        self.assertEqual(population_by_key["sped"]["field_number"], "4")
        field_names = [item["field"] for item in field_dictionary["fields"]]
        self.assertIn("reg.student_id", field_names)
        self.assertIn("reg_entry_with.grade", field_names)
        self.assertNotIn("reg_contact.email", field_names)
        self.assertNotIn("mr_stu_gpa.cum_gpa", field_names)
        table_names = [item["table"] for item in field_dictionary["table_families"]]
        self.assertIn("dbo.REG_ENTRY_WITH", table_names)
        usage_types = [item["question_type"] for item in field_dictionary["usage_patterns"]]
        self.assertIn("current_year_grade_change_history", usage_types)

    def test_vendor_dictionary_index_contains_core_tables_and_columns(self):
        dictionary = self.pipeline.load_vendor_dictionary()
        tables = {item["table"].upper(): item for item in dictionary["tables"]}

        self.assertIn("DBO.REG", tables)
        self.assertIn("DBO.REG_ENTRY_WITH", tables)
        self.assertIn("DBO.REG_PROGRAMS", tables)
        reg_columns = {item["name"] for item in tables["DBO.REG"]["columns"]}
        programs_columns = {item["name"] for item in tables["DBO.REG_PROGRAMS"]["columns"]}
        self.assertIn("STUDENT_ID", reg_columns)
        self.assertIn("CURRENT_STATUS", reg_columns)
        self.assertIn("PROGRAM_ID", programs_columns)
        self.assertIn("FIELD_NUMBER", programs_columns)

    def test_predefined_report_index_contains_dashboard_patterns(self):
        reports = self.pipeline.load_predefined_reports()
        self.assertEqual(reports["source"]["kind"], "dashboard_predefined_reports")
        self.assertGreaterEqual(reports["summary"]["file_count"], 80)
        modules = {item["name"]: item for item in reports["modules"]}
        self.assertIn("Enrollment", modules)
        self.assertIn("dyslexia", modules)
        top_tables = [item["table"] for item in reports["top_tables"]]
        self.assertIn("dbo.REG_ENTRY_WITH", top_tables)
        filters = {
            (item["program_id"], item["field_number"])
            for item in reports["top_population_filters"]
        }
        self.assertIn(("146", "5"), filters)

    def test_status_exposes_local_config_path(self):
        with mock.patch.object(self.pipeline, "_installed_odbc_drivers", return_value=["ODBC Driver 17 for SQL Server"]):
            with mock.patch.object(self.pipeline, "_client_module_available", return_value=True):
                with mock.patch("data_sources.sis_test.connector._current_windows_identity", return_value="K12AD\\guribe.tst"):
                    with mock.patch.object(self.pipeline, "_network_probe", return_value={"reachable": True, "reason": "connected"}):
                        with mock.patch.object(self.pipeline, "_auth_probe", return_value={"authenticated": False, "reason": "login failed"}):
                            status = self.pipeline.status()
        self.assertEqual(status["pipeline_id"], "sis_test")
        self.assertTrue(status["local_config_path"].endswith("local_config.json"))
        self.assertEqual(status["query_template_count"], 4)
        self.assertEqual(status["driver_selected"], "ODBC Driver 17 for SQL Server")
        self.assertFalse(status["live_query_ready"])
        self.assertEqual((status["readiness"] or {}).get("state"), "blocked")
        self.assertIn("auth_not_ready", status["readiness_blockers"])
        self.assertIn("login failed", status["next_step"])

    def test_schema_inventory_builds_metadata_query(self):
        sql, args = self.pipeline._build_live_query(
            "schema_inventory",
            {"schema_like": "dbo", "table_like": "REG_%"},
            20,
        )

        self.assertIn("SELECT TOP 20", sql)
        self.assertIn("FROM sys.tables t", sql)
        self.assertIn("JOIN sys.columns c", sql)
        self.assertIn("WHERE s.name LIKE ? AND t.name LIKE ?", sql)
        self.assertEqual(args, ["dbo", "REG_%"])

    def test_schema_inventory_rejects_unsafe_like_pattern(self):
        with self.assertRaises(Exception):
            self.pipeline._build_live_query(
                "schema_inventory",
                {"schema_like": "dbo", "table_like": "REG_%'; DROP TABLE dbo.REG;--"},
                20,
            )

    def test_safe_query_denies_missing_required_identifier(self):
        result = self.pipeline.safe_query("student_lookup", {"campus_id": "101"})
        self.assertFalse(result["ok"])
        self.assertIn("requires one of", result["error"])

    def test_safe_query_defaults_to_twenty_row_guard(self):
        result = self.pipeline.safe_query("campus_enrollment_summary", {"campus_id": "101"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_mode"], "dry_run")
        self.assertEqual(result["requested_row_limit"], 20)
        self.assertEqual(result["effective_row_limit"], 20)

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

    def test_sanitize_error_text_reports_integrated_identity_login_failure(self):
        message = self.pipeline._sanitize_error_text(
            "Login failed for user 'K12AD\\guribe'.",
            {"auth_mode": "trusted"},
        )

        self.assertEqual(
            message,
            "Login failed for Windows integrated SIS identity (K12AD\\guribe).",
        )

    def test_status_reports_trusted_auth_identity_mismatch(self):
        config = {
            "host": "10.80.42.50",
            "database": "BNV_eSpTrain",
            "driver": "ODBC Driver 17 for SQL Server",
            "auth_mode": "trusted",
            "intended_windows_identity": "K12AD\\guribe.tst",
        }
        with mock.patch("data_sources.sis_test.connector._load_local_config", return_value=config):
            with mock.patch("data_sources.sis_test.connector._current_windows_identity", return_value="K12AD\\guribe"):
                with mock.patch.object(self.pipeline, "_installed_odbc_drivers", return_value=["ODBC Driver 17 for SQL Server"]):
                    with mock.patch.object(self.pipeline, "_network_probe", return_value={"reachable": True, "reason": "connected"}):
                        with mock.patch.object(
                            self.pipeline,
                            "_auth_probe",
                            return_value={
                                "authenticated": False,
                                "reason": "Login failed for Windows integrated SIS identity (K12AD\\guribe).",
                            },
                        ):
                            status = self.pipeline.status()

        self.assertEqual(status["auth_mode"], "trusted")
        self.assertEqual(status["current_windows_identity"], "K12AD\\guribe")
        self.assertEqual(status["intended_windows_identity"], "K12AD\\guribe.tst")
        self.assertTrue(status["windows_identity_mismatch"])
        self.assertEqual(status["auth_probe"]["reason"], "windows_identity_mismatch")
        self.assertIn("windows_identity_mismatch", status["readiness_blockers"])
        self.assertIn("K12AD\\guribe.tst", status["next_step"])

    def test_status_reports_trusted_auth_failure_when_identity_matches(self):
        config = {
            "host": "10.80.42.50",
            "database": "BNV_eSpTrain",
            "driver": "ODBC Driver 17 for SQL Server",
            "auth_mode": "trusted",
            "intended_windows_identity": "K12AD\\guribe.tst",
        }
        with mock.patch("data_sources.sis_test.connector._load_local_config", return_value=config):
            with mock.patch("data_sources.sis_test.connector._current_windows_identity", return_value="K12AD\\guribe.tst"):
                with mock.patch.object(self.pipeline, "_installed_odbc_drivers", return_value=["ODBC Driver 17 for SQL Server"]):
                    with mock.patch.object(self.pipeline, "_client_module_available", return_value=True):
                        with mock.patch.object(self.pipeline, "_network_probe", return_value={"reachable": True, "reason": "connected"}):
                            with mock.patch.object(
                                self.pipeline,
                                "_auth_probe",
                                return_value={"authenticated": False, "reason": "Login failed for Windows integrated SIS identity (K12AD\\guribe.tst)."},
                            ):
                                status = self.pipeline.status()

        self.assertFalse(status["windows_identity_mismatch"])
        self.assertEqual(status["current_windows_identity"], "K12AD\\guribe.tst")
        self.assertEqual(status["auth_probe"]["reason"], "Login failed for Windows integrated SIS identity (K12AD\\guribe.tst).")
        self.assertIn("auth_not_ready", status["readiness_blockers"])
        self.assertIn("Fix SIS read-only authentication", status["next_step"])

    def test_safe_query_next_step_explains_trusted_identity_mismatch(self):
        message = self.pipeline._safe_query_next_step(
            {
                "configured": True,
                "network_probe": {"reachable": True},
                "auth_probe": {"authenticated": False, "reason": "login failed"},
                "windows_identity_mismatch": True,
                "current_windows_identity": "K12AD\\guribe",
                "intended_windows_identity": "K12AD\\guribe.tst",
            },
            False,
        )

        self.assertIn("K12AD\\guribe.tst", message)
        self.assertIn("K12AD\\guribe", message)
        self.assertIn("trusted auth uses the process identity", message)


if __name__ == "__main__":
    unittest.main()
