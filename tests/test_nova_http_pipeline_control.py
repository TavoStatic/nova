import tempfile
import unittest
from pathlib import Path

from services.nova_http_pipeline_control import HTTP_PIPELINE_CONTROL_SERVICE


class _PipelineService:
    def __init__(self):
        self.calls = []

    def payload(self, **kwargs):
        self.calls.append(("payload", kwargs))
        return {"ok": True, "selected_pipeline_id": kwargs.get("selected_pipeline_id")}

    def append_note(self, payload, **kwargs):
        self.calls.append(("append_note", payload, kwargs))
        return True, "pipeline_note_recorded", {"pipeline_id": payload.get("pipeline_id")}, "note"

    def create_lane(self, payload, **kwargs):
        self.calls.append(("create_lane", payload, kwargs))
        return True, "pipeline_created", {"pipeline_id": payload.get("pipeline_id")}, "create"

    def set_enabled(self, payload, **kwargs):
        self.calls.append(("set_enabled", payload, kwargs))
        msg = "pipeline_started" if kwargs.get("enabled") else "pipeline_paused"
        return True, msg, {"pipeline_id": payload.get("pipeline_id")}, msg

    def update_lane_metadata(self, payload, **kwargs):
        self.calls.append(("update_lane_metadata", payload, kwargs))
        return True, "pipeline_metadata_updated", {"pipeline_id": payload.get("pipeline_id")}, "update"

    def upsert_population_definition(self, payload, **kwargs):
        self.calls.append(("upsert_population_definition", payload, kwargs))
        return True, "pipeline_population_saved", {"pipeline_id": payload.get("pipeline_id")}, "population"

    def archive_lane(self, payload, **kwargs):
        self.calls.append(("archive_lane", payload, kwargs))
        return True, "pipeline_archived", {"pipeline_id": payload.get("pipeline_id")}, "archive"

    def run_query_preview(self, payload, **kwargs):
        self.calls.append(("run_query_preview", payload, kwargs))
        return True, "pipeline_query_preview_ok", {"pipeline_id": payload.get("pipeline_id"), "result": {"ok": True}}, "preview"

    def run_query_live(self, payload, **kwargs):
        self.calls.append(("run_query_live", payload, kwargs))
        return True, "pipeline_query_live_ok", {"pipeline_id": payload.get("pipeline_id"), "result": {"ok": True}}, "live"


class TestNovaHttpPipelineControlService(unittest.TestCase):
    def _scope(self, root: Path, service: _PipelineService):
        return {
            "CONTROL_PIPELINES_SERVICE": service,
            "DATA_SOURCES_DIR": root,
            "pipeline_list_summaries": lambda _root: [{"pipeline_id": "sis_test"}],
            "pipeline_get_status": lambda pipeline_id, **_kwargs: {"pipeline_id": pipeline_id},
            "pipeline_get_schema_probe": lambda pipeline_id, **_kwargs: {"pipeline_id": pipeline_id, "schema": True},
            "preview_pipeline_query": lambda *_args, **_kwargs: {"ok": True},
            "run_pipeline_query": lambda *_args, **_kwargs: {"ok": True},
        }

    def test_payload_from_runtime_binds_data_lane_dependencies(self):
        with tempfile.TemporaryDirectory() as td:
            service = _PipelineService()
            payload = HTTP_PIPELINE_CONTROL_SERVICE.payload_from_runtime(
                self._scope(Path(td), service),
                selected_pipeline_id="sis_test",
            )

        self.assertEqual(payload["selected_pipeline_id"], "sis_test")
        call_name, kwargs = service.calls[0]
        self.assertEqual(call_name, "payload")
        self.assertTrue(callable(kwargs["list_pipeline_summaries_fn"]))
        self.assertTrue(callable(kwargs["get_pipeline_status_fn"]))
        self.assertTrue(callable(kwargs["get_pipeline_schema_probe_fn"]))

    def test_action_hooks_from_runtime_bind_pipeline_actions(self):
        with tempfile.TemporaryDirectory() as td:
            service = _PipelineService()
            hooks = HTTP_PIPELINE_CONTROL_SERVICE.action_hooks_from_runtime(self._scope(Path(td), service))
            ok, msg, extra, detail = hooks["pipeline_pause_action_fn"]({"pipeline_id": "sis_test"})

        self.assertTrue(ok)
        self.assertEqual(msg, "pipeline_paused")
        self.assertEqual(extra["pipeline_id"], "sis_test")
        self.assertEqual(detail, "pipeline_paused")
        call_name, payload, kwargs = service.calls[0]
        self.assertEqual(call_name, "set_enabled")
        self.assertFalse(kwargs["enabled"])
        self.assertTrue(callable(kwargs["list_pipeline_summaries_fn"]))

    def test_action_hooks_bind_pipeline_query_actions(self):
        with tempfile.TemporaryDirectory() as td:
            service = _PipelineService()
            hooks = HTTP_PIPELINE_CONTROL_SERVICE.action_hooks_from_runtime(self._scope(Path(td), service))
            ok, msg, extra, detail = hooks["pipeline_query_preview_action_fn"](
                {"pipeline_id": "sis_test", "operation": "list_schools"}
            )

        self.assertTrue(ok)
        self.assertEqual(msg, "pipeline_query_preview_ok")
        self.assertEqual(extra["pipeline_id"], "sis_test")
        self.assertEqual(detail, "preview")


if __name__ == "__main__":
    unittest.main()
