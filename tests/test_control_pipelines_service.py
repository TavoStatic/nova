import json
import tempfile
import unittest
from pathlib import Path

from services.control_pipelines import CONTROL_PIPELINES_SERVICE
from services.data_pipeline_registry import get_pipeline_status
from services.data_pipeline_registry import preview_pipeline_query


class TestControlPipelinesService(unittest.TestCase):
    def test_payload_includes_selected_pipeline_detail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sis_test").mkdir()

            payload = CONTROL_PIPELINES_SERVICE.payload(
                data_sources_root=root,
                list_pipeline_summaries_fn=lambda _root: [{"pipeline_id": "sis_test", "display_name": "SIS", "read_only": True}],
                get_pipeline_status_fn=lambda pipeline_id, **_kwargs: {"pipeline_id": pipeline_id, "live_query_ready": False},
                get_pipeline_schema_probe_fn=lambda pipeline_id, **_kwargs: {"pipeline_id": pipeline_id, "query_templates": ["student_lookup"]},
                selected_pipeline_id="sis_test",
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["selected_pipeline_id"], "sis_test")
            self.assertEqual(payload["detail"]["status"]["pipeline_id"], "sis_test")
            self.assertEqual(payload["detail"]["schema_probe"]["query_templates"], ["student_lookup"])

    def test_append_note_scopes_to_pipeline_intake_log(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sis_test").mkdir()

            ok, msg, extra, detail = CONTROL_PIPELINES_SERVICE.append_note(
                {"pipeline_id": "sis_test", "note_type": "population_definition", "note": "EB uses PROGRAM_ID 146."},
                data_sources_root=root,
                list_pipeline_summaries_fn=lambda _root: [{"pipeline_id": "sis_test"}],
                now_fn=lambda: 123,
            )

            self.assertTrue(ok)
            self.assertEqual(msg, "pipeline_note_recorded")
            self.assertEqual(detail, "pipeline_note_recorded:sis_test")
            path = root / "sis_test" / "operator_intake.jsonl"
            entry = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual(entry["pipeline_id"], "sis_test")
            self.assertEqual(entry["note_type"], "population_definition")
            self.assertIn("EB uses", entry["note"])
            self.assertEqual(extra["intake"]["count_recent"], 1)

    def test_create_pause_start_and_archive_lane(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            known = []

            def list_summaries(_root):
                return [{"pipeline_id": item} for item in known]

            ok, msg, extra, detail = CONTROL_PIPELINES_SERVICE.create_lane(
                {"pipeline_id": "New Lane", "display_name": "New Lane"},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                now_fn=lambda: 100,
            )

            self.assertTrue(ok)
            self.assertEqual(msg, "pipeline_created")
            self.assertEqual(extra["pipeline_id"], "new_lane")
            self.assertTrue((root / "new_lane" / "pipeline.json").exists())
            self.assertFalse(get_pipeline_status("new_lane", data_sources_root=root)["execution_supported"])
            known.append("new_lane")

            ok, msg, extra, detail = CONTROL_PIPELINES_SERVICE.set_enabled(
                {"pipeline_id": "new_lane"},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                enabled=False,
                now_fn=lambda: 101,
            )
            self.assertTrue(ok)
            self.assertEqual(msg, "pipeline_paused")
            self.assertFalse(extra["lane_state"]["enabled"])

            ok, msg, extra, detail = CONTROL_PIPELINES_SERVICE.set_enabled(
                {"pipeline_id": "new_lane"},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                enabled=True,
                now_fn=lambda: 102,
            )
            self.assertTrue(ok)
            self.assertEqual(msg, "pipeline_started")
            self.assertTrue(extra["lane_state"]["enabled"])

            ok, msg, extra, detail = CONTROL_PIPELINES_SERVICE.archive_lane(
                {"pipeline_id": "new_lane"},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                now_fn=lambda: 103,
            )
            self.assertTrue(ok)
            self.assertEqual(msg, "pipeline_archived")
            self.assertFalse((root / "new_lane").exists())
            self.assertTrue(Path(extra["archive_path"]).exists())

    def test_created_lane_can_be_paused_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            known = []

            def list_summaries(_root):
                return [{"pipeline_id": item} for item in known]

            ok, _msg, extra, _detail = CONTROL_PIPELINES_SERVICE.create_lane(
                {"pipeline_id": "Temp Lane"},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                now_fn=lambda: 100,
            )
            self.assertTrue(ok)
            known.append(extra["pipeline_id"])
            CONTROL_PIPELINES_SERVICE.set_enabled(
                {"pipeline_id": extra["pipeline_id"]},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                enabled=False,
            )

            result = preview_pipeline_query(extra["pipeline_id"], "anything", {}, data_sources_root=root)

            self.assertFalse(result["ok"])
            self.assertEqual(result["execution_mode"], "blocked")
            self.assertIn("paused", result["error"])

    def test_update_lane_metadata_edits_manifest_without_renaming_lane(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            known = []

            def list_summaries(_root):
                return [{"pipeline_id": item} for item in known]

            ok, _msg, extra, _detail = CONTROL_PIPELINES_SERVICE.create_lane(
                {"pipeline_id": "sis_lane", "display_name": "SIS Lane"},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                now_fn=lambda: 100,
            )
            self.assertTrue(ok)
            known.append(extra["pipeline_id"])

            ok, msg, extra, detail = CONTROL_PIPELINES_SERVICE.update_lane_metadata(
                {
                    "pipeline_id": "sis_lane",
                    "display_name": "SIS Data Lane",
                    "description": "Read-only SIS reporting lane.",
                    "network_scope": "district_vpn",
                },
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                now_fn=lambda: 200,
            )

            self.assertTrue(ok)
            self.assertEqual(msg, "pipeline_metadata_updated")
            self.assertEqual(detail, "pipeline_metadata_updated:sis_lane")
            self.assertEqual(extra["updated_fields"]["display_name"], "SIS Data Lane")
            manifest = json.loads((root / "sis_lane" / "pipeline.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["pipeline_id"], "sis_lane")
            self.assertEqual(manifest["display_name"], "SIS Data Lane")
            self.assertEqual(manifest["description"], "Read-only SIS reporting lane.")
            self.assertEqual(manifest["network_scope"], "district_vpn")
            self.assertEqual(manifest["updated_at"], 200)

    def test_upsert_population_definition_scopes_to_lane(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            known = []

            def list_summaries(_root):
                return [{"pipeline_id": item} for item in known]

            ok, _msg, extra, _detail = CONTROL_PIPELINES_SERVICE.create_lane(
                {"pipeline_id": "sis_lane"},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                now_fn=lambda: 100,
            )
            self.assertTrue(ok)
            known.append(extra["pipeline_id"])

            ok, msg, extra, detail = CONTROL_PIPELINES_SERVICE.upsert_population_definition(
                {
                    "pipeline_id": "sis_lane",
                    "key": "Emergent Bilingual",
                    "label": "Emergent Bilingual",
                    "program_id": "146",
                    "field_number": "5",
                    "notes": "District EB population.",
                },
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                now_fn=lambda: 300,
            )

            self.assertTrue(ok)
            self.assertEqual(msg, "pipeline_population_saved")
            self.assertEqual(detail, "pipeline_population_created:sis_lane:emergent_bilingual")
            self.assertEqual(extra["population"]["key"], "emergent_bilingual")
            data = json.loads((root / "sis_lane" / "population_definitions.json").read_text(encoding="utf-8"))
            self.assertEqual(data["populations"][0]["program_id"], "146")
            self.assertEqual(data["populations"][0]["field_number"], "5")

            ok, _msg, extra, detail = CONTROL_PIPELINES_SERVICE.upsert_population_definition(
                {
                    "pipeline_id": "sis_lane",
                    "key": "emergent_bilingual",
                    "label": "EB",
                    "program_id": "146",
                    "field_number": "5",
                },
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                now_fn=lambda: 301,
            )

            self.assertTrue(ok)
            self.assertEqual(detail, "pipeline_population_updated:sis_lane:emergent_bilingual")
            self.assertEqual(extra["population"]["label"], "EB")
            data = json.loads((root / "sis_lane" / "population_definitions.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["populations"]), 1)
            self.assertEqual(data["populations"][0]["label"], "EB")


    def test_run_query_preview_delegates_to_registry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            def list_summaries(_root):
                return [{"pipeline_id": "edfi_bisd"}]

            ok, msg, extra, detail = CONTROL_PIPELINES_SERVICE.run_query_preview(
                {"pipeline_id": "edfi_bisd", "operation": "list_schools", "row_limit": 3},
                data_sources_root=root,
                list_pipeline_summaries_fn=list_summaries,
                preview_pipeline_query_fn=lambda *_args, **_kwargs: {
                    "ok": True,
                    "execution_mode": "dry_run",
                    "operation": "list_schools",
                },
            )

            self.assertTrue(ok)
            self.assertEqual(msg, "pipeline_query_preview_ok")
            self.assertEqual(extra["operation"], "list_schools")
            self.assertEqual(detail, "pipeline_query_preview_ok:edfi_bisd:list_schools")


if __name__ == "__main__":
    unittest.main()
