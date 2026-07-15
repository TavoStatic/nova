import unittest
from unittest import mock

from services.pipeline_privileged_bridge import (
    run_governed_pipeline_query,
    unwrap_privileged_pipeline_response,
)


class TestPipelineGovernedRouting(unittest.TestCase):
    def test_unwrap_privileged_pipeline_response_returns_inner_result(self) -> None:
        result = unwrap_privileged_pipeline_response(
            {
                "ok": True,
                "request_id": "req-1",
                "result": {"ok": True, "row_count": 2, "execution_mode": "live"},
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["governed_route"], "privileged_worker")
        self.assertEqual(result["privileged_request_id"], "req-1")

    def test_run_governed_pipeline_query_delegates_to_privileged_bridge(self) -> None:
        with mock.patch(
            "services.pipeline_privileged_bridge.run_privileged_pipeline_query",
            return_value={
                "ok": True,
                "request_id": "req-2",
                "result": {"ok": True, "operation": "list_schools"},
            },
        ) as privileged_mock:
            result = run_governed_pipeline_query(
                "edfi_bisd",
                "list_schools",
                {"offset": 0},
                row_limit=5,
                requested_by="test",
            )
        privileged_mock.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "list_schools")
        self.assertEqual(result["governed_route"], "privileged_worker")


if __name__ == "__main__":
    unittest.main()