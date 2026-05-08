from pathlib import Path
import tempfile
import threading
import time
import unittest

from services.pipeline_privileged_bridge import queue_privileged_pipeline_query
from services.pipeline_privileged_bridge import run_privileged_pipeline_query
from services.pipeline_privileged_bridge import wait_for_privileged_pipeline_query
from services.nova_runtime_context import RUNTIME_DIR
from pipelines.privileged_protocol import build_protocol_paths
from pipelines.privileged_protocol import load_request
from pipelines.privileged_protocol import write_response


class TestPipelinePrivilegedBridge(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_runtime_root_uses_runtime_context(self):
        from services import pipeline_privileged_bridge as bridge

        self.assertEqual(bridge.RUNTIME_ROOT, RUNTIME_DIR)

    def test_queue_and_wait_for_privileged_pipeline_query(self):
        request = queue_privileged_pipeline_query(
            "sis_test",
            "student_lookup",
            {"student_id": "12345"},
            row_limit=5,
            requested_by="test",
            runtime_root=self.runtime_root,
        )
        paths = build_protocol_paths(self.runtime_root, "sis_test")
        request_path = paths.requests_dir / f"{request['request_id']}.request.json"
        payload = load_request(request_path)
        self.assertEqual(payload["operation"], "student_lookup")

        write_response(
            paths,
            request["request_id"],
            {"ok": True, "request_id": request["request_id"], "result": {"row_count": 0}},
        )
        response = wait_for_privileged_pipeline_query(
            "sis_test",
            request["request_id"],
            timeout_sec=2,
            poll_interval_sec=0.1,
            runtime_root=self.runtime_root,
        )
        self.assertTrue(response["ok"])

    def test_run_privileged_pipeline_query_waits_for_worker_response(self):
        holder: dict[str, str] = {}

        def worker():
            while "request_id" not in holder:
                time.sleep(0.05)
            paths = build_protocol_paths(self.runtime_root, "sis_test")
            write_response(
                paths,
                holder["request_id"],
                {"ok": True, "request_id": holder["request_id"], "result": {"row_count": 2}},
            )

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        original_queue = queue_privileged_pipeline_query

        def wrapped_queue(*args, **kwargs):
            request = original_queue(*args, **kwargs)
            holder["request_id"] = request["request_id"]
            return request

        from services import pipeline_privileged_bridge as bridge

        old_queue = bridge.queue_privileged_pipeline_query
        try:
            bridge.queue_privileged_pipeline_query = wrapped_queue
            response = run_privileged_pipeline_query(
                "sis_test",
                "student_lookup",
                {"student_id": "12345"},
                row_limit=5,
                runtime_root=self.runtime_root,
                timeout_sec=5,
                poll_interval_sec=0.1,
            )
        finally:
            bridge.queue_privileged_pipeline_query = old_queue

        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["row_count"], 2)


if __name__ == "__main__":
    unittest.main()
