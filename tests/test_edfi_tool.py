import json
import unittest
from unittest import mock

from tools.base_tool import ToolContext, ToolInvocationError
from tools.edfi_tool import EdFiExploreTool


class TestEdFiExploreTool(unittest.TestCase):
    def test_schools_action_uses_governed_pipeline(self) -> None:
        tool = EdFiExploreTool()
        governed = {
            "ok": True,
            "operation": "list_schools",
            "rows": [{"schoolId": 31901001}],
            "governed_route": "privileged_worker",
        }
        with mock.patch(
            "tools.edfi_tool.run_governed_pipeline_query",
            return_value=governed,
        ) as governed_mock:
            rendered = tool.run({"action": "schools", "limit": 5}, ToolContext())

        governed_mock.assert_called_once()
        self.assertEqual(governed_mock.call_args.args[0], "edfi_bisd")
        self.assertEqual(governed_mock.call_args.args[1], "list_schools")
        payload = json.loads(rendered)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["governed_route"], "privileged_worker")

    def test_generic_read_action_is_blocked(self) -> None:
        tool = EdFiExploreTool()
        with self.assertRaises(ToolInvocationError):
            tool.run({"action": "read", "resource": "ed-fi/students"}, ToolContext())


if __name__ == "__main__":
    unittest.main()