import json
import unittest
from unittest import mock

from tools.base_tool import ToolContext, ToolInvocationError
from tools.edfi_tool import EdFiExploreTool, PIPELINE_ID


class TestEdFiExploreTool(unittest.TestCase):
    def test_pipeline_id_is_backpack_edfi(self) -> None:
        self.assertEqual(PIPELINE_ID, "edfi")

    def test_schools_action_uses_local_report(self) -> None:
        tool = EdFiExploreTool()
        report = {
            "ok": True,
            "summary": "1 school",
            "rows": [{"school_id": "1", "school_name": "Alpha"}],
            "columns": ["school_id", "school_name"],
            "row_count": 1,
            "from_extract": True,
            "governed_route": "local_extract",
        }
        with mock.patch(
            "services.backpack_host.reports.run_backpack_report",
            return_value=report,
        ) as report_mock:
            rendered = tool.run({"action": "schools", "limit": 5}, ToolContext())

        report_mock.assert_called_once()
        self.assertEqual(report_mock.call_args.kwargs.get("prefer_local"), True)
        self.assertEqual(report_mock.call_args.kwargs.get("force_refresh"), False)
        payload = json.loads(rendered)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload.get("live_pull"))
        self.assertEqual(payload["row_count"], 1)

    def test_admin_context_uses_account_admin_role(self) -> None:
        tool = EdFiExploreTool()
        with mock.patch(
            "tools.edfi_tool.run_backpack_query",
            return_value={"ok": True, "operation": "connection_health", "health": "ok"},
        ) as query_mock, mock.patch(
            "services.backpack_host.capability_surface.get_fusion_status",
            return_value={"available_capability_ids": ["edfi.connection_health_local"], "nova_must_know": {}, "teach_rules": [], "local_hold": {}},
        ):
            tool.run({"action": "health"}, ToolContext(is_admin=True))
        self.assertEqual(query_mock.call_args.kwargs.get("role"), "account_admin")

    def test_viewer_role_arg_passed(self) -> None:
        tool = EdFiExploreTool()
        with mock.patch(
            "tools.edfi_tool.run_backpack_query",
            return_value={"ok": True, "operation": "connection_health", "health": "ok"},
        ) as query_mock, mock.patch(
            "services.backpack_host.capability_surface.get_fusion_status",
            return_value={"available_capability_ids": [], "nova_must_know": {}, "teach_rules": [], "local_hold": {}},
        ):
            tool.run({"action": "health", "role": "viewer"}, ToolContext())
        self.assertEqual(query_mock.call_args.kwargs.get("role"), "viewer")

    def test_generic_read_action_is_blocked(self) -> None:
        tool = EdFiExploreTool()
        with self.assertRaises(ToolInvocationError):
            tool.run({"action": "read", "resource": "ed-fi/students"}, ToolContext())


if __name__ == "__main__":
    unittest.main()
