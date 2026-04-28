from pathlib import Path
import tempfile
import unittest

from pipelines.privileged_protocol import archive_request
from pipelines.privileged_protocol import build_protocol_paths
from pipelines.privileged_protocol import claim_next_request
from pipelines.privileged_protocol import load_request
from pipelines.privileged_protocol import submit_request
from pipelines.privileged_protocol import wait_for_response
from pipelines.privileged_protocol import write_response


class TestPipelinePrivilegedProtocol(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_root = Path(self.temp_dir.name)
        self.paths = build_protocol_paths(self.runtime_root, "sis_test")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_submit_claim_and_archive_request(self):
        request = submit_request(
            self.paths,
            pipeline_id="sis_test",
            operation="student_lookup",
            params={"student_id": "12345"},
            row_limit=5,
            requested_by="test",
        )
        claimed = claim_next_request(self.paths)
        self.assertIsNotNone(claimed)
        payload = load_request(claimed)
        self.assertEqual(payload["request_id"], request["request_id"])
        archived = archive_request(self.paths, claimed, status="done")
        self.assertTrue(archived.exists())

    def test_wait_for_response_returns_written_payload(self):
        request = submit_request(
            self.paths,
            pipeline_id="sis_test",
            operation="student_lookup",
            params={"student_id": "12345"},
        )
        write_response(
            self.paths,
            request["request_id"],
            {"ok": True, "request_id": request["request_id"], "result": {"row_count": 0}},
        )
        response = wait_for_response(self.paths, request["request_id"], timeout_sec=2, poll_interval_sec=0.1)
        self.assertIsNotNone(response)
        self.assertTrue(response["ok"])


if __name__ == "__main__":
    unittest.main()
