import unittest
from unittest import mock

import run_tools


class TestRunTools(unittest.TestCase):
    def test_parse_args_supports_list_tools(self):
        args = run_tools.parse_args(["--list-tools"])
        self.assertTrue(args.list_tools)

    def test_handle_tools_uses_shared_planner_and_executes_direct_tool(self):
        with mock.patch("run_tools.planner_decision.decide_turn", return_value=[{"type": "run_tool", "tool": "queue_status", "args": []}]), \
            mock.patch("run_tools.nova_core.execute_planned_action", return_value="Queue is empty.") as execute_mock:
            out = run_tools.handle_tools("show queue")

        self.assertEqual(out, "Queue is empty.")
        execute_mock.assert_called_once_with("queue_status", [])

    def test_handle_tools_returns_clarify_prompt(self):
        with mock.patch("run_tools.planner_decision.decide_turn", return_value=[{"type": "ask_clarify", "question": "What location should I use?"}]):
            out = run_tools.handle_tools("weather")

        self.assertEqual(out, "What location should I use?")

    def test_handle_tools_uses_legacy_command_router_when_requested(self):
        with mock.patch("run_tools.planner_decision.decide_turn", return_value=[{"type": "route_command"}]), \
            mock.patch("run_tools.nova_core.handle_commands", return_value="Command output") as handle_mock:
            out = run_tools.handle_tools("patch list-previews")

        self.assertEqual(out, "Command output")
        handle_mock.assert_called_once_with("patch list-previews")

    def test_list_tools_text_includes_direct_and_registered_sections(self):
        with mock.patch.object(run_tools.nova_core.TOOL_REGISTRY_SERVICE, "describe_tools", return_value="filesystem\nvision"):
            text = run_tools.list_tools_text()

        self.assertIn("run_tools direct routes:", text)
        self.assertIn("- queue_status", text)
        self.assertIn("Registered tools:", text)
        self.assertIn("filesystem", text)

    def test_ask_nova_uses_sessioned_voice_chat(self):
        with mock.patch.object(run_tools.VOICE_INTERACTION_SERVICE, "chat", return_value="reply") as chat_mock:
            reply = run_tools.ask_nova("hello")

        self.assertEqual(reply, "reply")
        chat_mock.assert_called_once_with("hello", session_id="run-tools")


if __name__ == "__main__":
    unittest.main()