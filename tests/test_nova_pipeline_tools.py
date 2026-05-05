from pathlib import Path
import unittest

from services import nova_pipeline_tools


class TestNovaPipelineTools(unittest.TestCase):
    def test_parse_pipeline_preview_command_extracts_params(self):
        parsed = nova_pipeline_tools.parse_pipeline_command(
            "pipeline preview sis_test student_lookup student_id=12345 row_limit=200"
        )

        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["action"], "preview")
        self.assertEqual(parsed["pipeline_id"], "sis_test")
        self.assertEqual(parsed["operation"], "student_lookup")
        self.assertEqual(parsed["params"], {"student_id": "12345"})
        self.assertEqual(parsed["row_limit"], 200)

    def test_parse_pipeline_search_command_extracts_query(self):
        parsed = nova_pipeline_tools.parse_pipeline_command("pipeline search sis_test program id limit=5")

        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["action"], "search")
        self.assertEqual(parsed["pipeline_id"], "sis_test")
        self.assertEqual(parsed["query"], "program id")
        self.assertEqual(parsed["limit"], 5)

    def test_parse_pipeline_plan_command_extracts_request(self):
        parsed = nova_pipeline_tools.parse_pipeline_command("pipeline plan sis_test EB students by campus limit=4")

        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["action"], "plan")
        self.assertEqual(parsed["pipeline_id"], "sis_test")
        self.assertEqual(parsed["request"], "EB students by campus")
        self.assertEqual(parsed["limit"], 4)

    def test_schema_renderer_shows_population_definitions(self):
        out = nova_pipeline_tools.render_pipeline_schema({
            "pipeline_id": "sis_test",
            "schema": {"entities": []},
            "query_templates": ["student_lookup"],
            "vendor_dictionary": {
                "source": {"grounding_status": "vendor_dictionary_grounded"},
                "table_count": 1222,
            },
            "predefined_reports": {
                "summary": {"module_count": 21, "file_count": 84, "table_count": 25}
            },
            "population_definitions": {
                "populations": [
                    {"key": "eb"},
                    {"key": "sped"},
                ]
            },
        })

        self.assertIn("Population definitions: eb, sped", out)
        self.assertIn("Vendor dictionary: vendor_dictionary_grounded; tables=1222", out)
        self.assertIn("Predefined reports: modules=21; files=84; tables=25", out)

    def test_preview_uses_dry_run_registry_path(self):
        calls = []

        out = nova_pipeline_tools.handle_pipeline_command(
            "pipeline preview sis_test student_lookup student_id=12345 row_limit=200",
            data_sources_root=Path("data_sources"),
            list_pipeline_summaries_fn=lambda *_args, **_kwargs: [],
            get_pipeline_status_fn=lambda *_args, **_kwargs: {},
            get_pipeline_schema_probe_fn=lambda *_args, **_kwargs: {},
            preview_pipeline_query_fn=lambda *args, **kwargs: calls.append((args, kwargs)) or {
                "ok": True,
                "pipeline_id": "sis_test",
                "operation": "student_lookup",
                "execution_mode": "dry_run",
                "tables": ["dbo.REG"],
                "effective_row_limit": 25,
                "read_only": True,
                "params": {"student_id": "12345"},
            },
            run_privileged_pipeline_query_fn=lambda *_args, **_kwargs: {"ok": False},
        )

        self.assertIn("dry_run result", out)
        self.assertEqual(calls[0][0][:3], ("sis_test", "student_lookup", {"student_id": "12345"}))
        self.assertTrue(calls[0][1]["dry_run"])
        self.assertEqual(calls[0][1]["row_limit"], 200)

    def test_search_uses_vendor_dictionary_registry_path(self):
        calls = []

        out = nova_pipeline_tools.handle_pipeline_command(
            "pipeline search sis_test program_id limit=3",
            data_sources_root=Path("data_sources"),
            list_pipeline_summaries_fn=lambda *_args, **_kwargs: [],
            get_pipeline_status_fn=lambda *_args, **_kwargs: {},
            get_pipeline_schema_probe_fn=lambda *_args, **_kwargs: {},
            preview_pipeline_query_fn=lambda *_args, **_kwargs: {"ok": False},
            run_privileged_pipeline_query_fn=lambda *_args, **_kwargs: {"ok": False},
            search_pipeline_vendor_dictionary_fn=lambda *args, **kwargs: calls.append((args, kwargs)) or {
                "ok": True,
                "pipeline_id": "sis_test",
                "query": "program_id",
                "grounding_status": "vendor_dictionary_grounded",
                "match_count": 1,
                "matches": [
                    {
                        "table": "dbo.REG_PROGRAMS",
                        "title": "Program-Tracked Student Data",
                        "page": 119,
                        "column_count": 14,
                        "column_hits": [{"name": "PROGRAM_ID", "data_type": "char(5)"}],
                    }
                ],
            },
        )

        self.assertIn("Vendor dictionary search for sis_test: program_id", out)
        self.assertIn("dbo.REG_PROGRAMS", out)
        self.assertEqual(calls[0][0][:2], ("sis_test", "program_id"))
        self.assertEqual(calls[0][1]["limit"], 3)

    def test_plan_uses_report_planning_registry_path(self):
        calls = []

        out = nova_pipeline_tools.handle_pipeline_command(
            "pipeline plan sis_test EB students by campus limit=4",
            data_sources_root=Path("data_sources"),
            list_pipeline_summaries_fn=lambda *_args, **_kwargs: [],
            get_pipeline_status_fn=lambda *_args, **_kwargs: {},
            get_pipeline_schema_probe_fn=lambda *_args, **_kwargs: {},
            preview_pipeline_query_fn=lambda *_args, **_kwargs: {"ok": False},
            run_privileged_pipeline_query_fn=lambda *_args, **_kwargs: {"ok": False},
            plan_pipeline_report_fn=lambda *args, **kwargs: calls.append((args, kwargs)) or {
                "ok": True,
                "pipeline_id": "sis_test",
                "request": "EB students by campus",
                "grounding_status": "vendor_dictionary_grounded",
                "live_schema_status": "not_verified_by_live_inventory",
                "default_row_limit": 20,
                "intent": {
                    "report_kind": "student_population",
                    "group_by": ["campus"],
                    "filters": [{"type": "population", "key": "eb", "program_id": "146", "field_number": "5"}],
                    "missing_inputs": [],
                },
                "matched_populations": [{"key": "eb", "program_id": "146", "field_number": "5"}],
                "suggested_operation": "program_membership_lookup",
                "required_tables": [
                    {"table": "dbo.REG_PROGRAMS", "title": "Program-Tracked Student Data", "reason": "population_definition"},
                    {
                        "table": "dbo.REG_BUILDING",
                        "title": "Building Configuration",
                        "reason": "campus_name_lookup",
                        "role": "support_lookup",
                        "join_key": "BUILDING",
                        "active_status_note": "Verify live active status field.",
                        "activity_inference": {
                            "signal": "current_student_records_by_building",
                            "join_rule": "dbo.REG.BUILDING = dbo.REG_BUILDING.BUILDING",
                        },
                        "active_status_candidates_to_verify": [{"table": "dbo.REGTB_BLDG_TYPES", "field": "ACTIVE"}],
                    },
                ],
                "candidate_tables": [{"table": "dbo.REG_PROGRAMS", "title": "Program-Tracked Student Data", "matched_terms": ["eb"]}],
                "next_step": "Review before preview.",
            },
        )

        self.assertIn("Pipeline report plan for sis_test", out)
        self.assertIn("populations: eb(146/5)", out)
        self.assertIn("intent: student_population; group_by=campus", out)
        self.assertIn("filters: eb PROGRAM_ID=146 FIELD_NUMBER=5", out)
        self.assertIn("Required tables:", out)
        self.assertIn("role=support_lookup; join_key=BUILDING", out)
        self.assertIn("active_status: Verify live active status field.", out)
        self.assertIn(
            "activity_inference: current_student_records_by_building; join=dbo.REG.BUILDING = dbo.REG_BUILDING.BUILDING",
            out,
        )
        self.assertIn("active_status_candidates_to_verify: dbo.REGTB_BLDG_TYPES.ACTIVE", out)
        self.assertIn("dbo.REG_PROGRAMS", out)
        self.assertEqual(calls[0][0][:2], ("sis_test", "EB students by campus"))
        self.assertEqual(calls[0][1]["limit"], 4)

    def test_run_uses_privileged_bridge(self):
        calls = []

        out = nova_pipeline_tools.handle_pipeline_command(
            "pipeline run sis_test student_lookup student_id=12345 row_limit=5",
            data_sources_root=Path("data_sources"),
            list_pipeline_summaries_fn=lambda *_args, **_kwargs: [],
            get_pipeline_status_fn=lambda *_args, **_kwargs: {},
            get_pipeline_schema_probe_fn=lambda *_args, **_kwargs: {},
            preview_pipeline_query_fn=lambda *_args, **_kwargs: {"ok": False},
            run_privileged_pipeline_query_fn=lambda *args, **kwargs: calls.append((args, kwargs)) or {
                "ok": True,
                "pipeline_id": "sis_test",
                "operation": "student_lookup",
                "execution_mode": "live",
                "tables": ["dbo.REG"],
                "effective_row_limit": 5,
                "read_only": True,
                "columns": ["STUDENT_ID"],
                "rows": [{"STUDENT_ID": "12345"}],
                "row_count": 1,
            },
        )

        self.assertIn("live result", out)
        self.assertIn("row_count: 1", out)
        self.assertEqual(calls[0][0][:3], ("sis_test", "student_lookup", {"student_id": "12345"}))
        self.assertEqual(calls[0][1]["requested_by"], "nova_pipeline_command")


if __name__ == "__main__":
    unittest.main()
