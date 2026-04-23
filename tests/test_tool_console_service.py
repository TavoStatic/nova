import unittest

from services.tool_console import ToolConsoleService


class TestToolConsoleService(unittest.TestCase):
    def test_list_tools_text_includes_direct_and_registered_sections(self):
        service = ToolConsoleService(
            decide_turn_fn=lambda _text: [],
            execute_planned_action_fn=lambda tool, args: "",
            handle_commands_fn=lambda text: "",
            describe_tools_fn=lambda: "filesystem\nvision",
            direct_tools=["queue_status", "screen"],
        )

        text = service.list_tools_text()

        self.assertIn("run_tools direct routes:", text)
        self.assertIn("- queue_status", text)
        self.assertIn("Registered tools:", text)
        self.assertIn("filesystem", text)

    def test_handle_tools_runs_direct_tool(self):
        calls = []
        status_lines = []
        service = ToolConsoleService(
            decide_turn_fn=lambda _text: [{"type": "run_tool", "tool": "queue_status", "args": []}],
            execute_planned_action_fn=lambda tool, args: calls.append((tool, args)) or "Queue is empty.",
            handle_commands_fn=lambda text: "",
            describe_tools_fn=lambda: "",
        )

        out = service.handle_tools("show queue", emit_status=status_lines.append)

        self.assertEqual(out, "Queue is empty.")
        self.assertEqual(calls, [("queue_status", [])])
        self.assertEqual(status_lines, ["Nova: tool -> queue_status"])

    def test_handle_tools_routes_legacy_commands(self):
        handled = []
        service = ToolConsoleService(
            decide_turn_fn=lambda _text: [{"type": "route_command"}],
            execute_planned_action_fn=lambda tool, args: "",
            handle_commands_fn=lambda text: handled.append(text) or "Command output",
            describe_tools_fn=lambda: "",
        )

        out = service.handle_tools("patch list-previews")

        self.assertEqual(out, "Command output")
        self.assertEqual(handled, ["patch list-previews"])


if __name__ == "__main__":
    unittest.main()