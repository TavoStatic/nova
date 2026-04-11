import unittest
from pathlib import Path

from services.tool_execution import ToolExecutionService
from tools import ToolInvocationError


class _FakeRegistryService:
    def __init__(self):
        self.calls = []
        self.mode = "ok"

    def run_tool(self, name, args, ctx):
        self.calls.append((name, args, ctx))
        if self.mode == "ok":
            return "done"
        if self.mode == "invocation_error":
            raise ToolInvocationError("files_tool_disabled")
        raise RuntimeError("boom")


class TestToolExecutionService(unittest.TestCase):
    def setUp(self):
        self.registry = _FakeRegistryService()
        self.policy = {
            "allowed_root": str(Path(".").resolve()),
            "tools_enabled": {"files": True},
        }
        self.service = ToolExecutionService(
            policy_loader=lambda: dict(self.policy),
            active_user_getter=lambda: "tester",
            base_dir=Path("."),
            registry_service=self.registry,
        )

    def test_build_tool_context(self):
        ctx = self.service.build_tool_context(is_admin=True, extra={"k": "v"})
        self.assertEqual(ctx.user_id, "tester")
        self.assertTrue(ctx.is_admin)
        self.assertEqual(ctx.extra.get("k"), "v")
        self.assertTrue(Path(ctx.allowed_root).exists())

    def test_execute_registered_tool_ok(self):
        out = self.service.execute_registered_tool("filesystem", {"action": "ls"})
        self.assertEqual(out, "done")
        self.assertEqual(len(self.registry.calls), 1)

    def test_execute_registered_tool_invocation_error(self):
        self.registry.mode = "invocation_error"
        out = self.service.execute_registered_tool("filesystem", {})
        self.assertEqual(out, "File tools disabled by policy.")

    def test_execute_registered_tool_runtime_error(self):
        self.registry.mode = "runtime_error"
        out = self.service.execute_registered_tool("filesystem", {})
        self.assertIn("filesystem tool failed", out)

    def test_tool_error_message_admin(self):
        msg = ToolExecutionService.tool_error_message("patch", "admin_required")
        self.assertIn("admin-approved", msg)


if __name__ == "__main__":
    unittest.main()
