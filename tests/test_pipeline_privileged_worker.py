from pathlib import Path
import tempfile
import unittest

from pipelines.privileged_protocol import build_protocol_paths
from pipelines.privileged_protocol import load_response
from pipelines.privileged_protocol import submit_request
from pipelines.privileged_worker import process_next_privileged_request


class TestPipelinePrivilegedWorker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_root = Path(self.temp_dir.name)
        self.paths = build_protocol_paths(self.runtime_root, "sis_test")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_process_next_privileged_request_writes_response(self):
        request = submit_request(
            self.paths,
            pipeline_id="sis_test",
            operation="student_lookup",
            params={"student_id": "12345"},
            row_limit=5,
            requested_by="test",
        )

        def fake_execute(pipeline_id, operation, params, row_limit=None, data_sources_root=None):
            self.assertEqual(pipeline_id, "sis_test")
            self.assertEqual(operation, "student_lookup")
            self.assertEqual(params["student_id"], "12345")
            self.assertEqual(row_limit, 5)
            return {"ok": True, "execution_mode": "live", "row_count": 1}

        response = process_next_privileged_request(
            "sis_test",
            runtime_root=self.runtime_root,
            data_sources_root=Path(self.temp_dir.name),
            execute_fn=fake_execute,
        )
        self.assertIsNotNone(response)
        self.assertTrue(response["ok"])
        stored = load_response(self.paths, request["request_id"])
        self.assertTrue(stored["ok"])
        self.assertEqual(stored["result"]["row_count"], 1)


if __name__ == "__main__":
    unittest.main()
