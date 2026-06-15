import json
import unittest
from unittest.mock import patch
from pathlib import Path

from tools import ToolContext, build_default_registry
from tools.base_tool import ToolInvocationError


class TestCodegenTool(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_registry()
        self.context = ToolContext(
            user_id="tester",
            session_id="sess-codegen",
            policy={
                "tools_enabled": {"codegen": True},
                "codegen": {"enabled": True},
                "models": {"chat": "qwen2.5:7b"},
            },
            is_admin=True,
            allowed_root="C:/NOVA",
        )

    def test_preview_returns_preview_only_artifacts(self):
        raw = self.registry.run_tool(
            "codegen",
            {
                "action": "preview",
                "spec": {
                    "name": "leah_v2",
                    "purpose": "Add a new assistant surface",
                    "files": [
                        {"path": "services/leah_v2_service.py", "kind": "service", "intent": "Serve Leah v2 responses"},
                        {"path": "templates/leah_v2.html", "kind": "template", "intent": "Render Leah v2 UI"},
                    ],
                },
            },
            self.context,
        )

        payload = json.loads(raw)
        self.assertEqual(payload["schema"], "nova.codegen.preview.v1")
        self.assertEqual(payload["status"], "preview")
        self.assertTrue(payload["preview_only"])
        self.assertFalse(payload["apply_allowed"])
        self.assertEqual(payload["spec"]["name"], "leah_v2")
        self.assertEqual(len(payload["artifacts"]), 2)
        self.assertEqual(payload["provenance"]["model"], "qwen2.5:7b")
        self.assertTrue(payload["provenance"]["prompt_hash"])

    def test_codegen_requires_policy_enablement(self):
        ctx = ToolContext(
            user_id="tester",
            session_id="sess-codegen-off",
            policy={"tools_enabled": {"codegen": False}, "codegen": {"enabled": False}},
            is_admin=True,
            allowed_root="C:/NOVA",
        )
        with self.assertRaises(ToolInvocationError) as err:
            self.registry.run_tool(
                "codegen",
                {
                    "action": "preview",
                    "spec": {
                        "name": "demo",
                        "purpose": "demo",
                        "files": [{"path": "services/demo.py"}],
                    },
                },
                ctx,
            )
        self.assertEqual(str(err.exception), "codegen_tool_disabled")

    def test_codegen_rejects_unsafe_path(self):
        with self.assertRaises(ToolInvocationError) as err:
            self.registry.run_tool(
                "codegen",
                {
                    "action": "preview",
                    "spec": {
                        "name": "unsafe",
                        "purpose": "unsafe",
                        "files": [{"path": "../outside.py"}],
                    },
                },
                self.context,
            )
        self.assertEqual(str(err.exception), "codegen_spec_path_outside_allowed_root")

    def test_preview_includes_memory_injection_when_patterns_available(self):
        """CodegenTool should inject prior patterns from memory into preview."""
        with patch("tools.codegen_tool.PATCH_PROMOTION_MEMORY_SERVICE") as mock_memory:
            mock_memory.get_memory_injection.return_value = "\n## Prior Pattern\nReuse class Handler\n"
            
            raw = self.registry.run_tool(
                "codegen",
                {
                    "action": "preview",
                    "spec": {
                        "name": "handler_feature",
                        "purpose": "Add event handler",
                        "files": [
                            {"path": "services/handler.py", "kind": "module"},
                        ],
                    },
                },
                self.context,
            )

            payload = json.loads(raw)
            # Verify memory injection was requested
            mock_memory.get_memory_injection.assert_called_once_with(
                "handler_feature",
                "Add event handler"
            )
            # Verify context was included in payload
            self.assertIn("prior_patterns_context", payload)
            self.assertIn("Prior Pattern", payload["prior_patterns_context"])

    def test_preview_handles_memory_injection_failure_gracefully(self):
        """CodegenTool should continue if memory lookup fails."""
        with patch("tools.codegen_tool.PATCH_PROMOTION_MEMORY_SERVICE") as mock_memory:
            mock_memory.get_memory_injection.side_effect = Exception("Memory lookup failed")
            
            # Should not raise, should continue
            raw = self.registry.run_tool(
                "codegen",
                {
                    "action": "preview",
                    "spec": {
                        "name": "feature",
                        "purpose": "Feature",
                        "files": [
                            {"path": "services/module.py", "kind": "module"},
                        ],
                    },
                },
                self.context,
            )

            payload = json.loads(raw)
            # Should have valid preview even if memory lookup failed
            self.assertEqual(payload["schema"], "nova.codegen.preview.v1")
            self.assertIsNotNone(payload["artifacts"])

    def test_preview_omits_injection_context_when_no_patterns(self):
        """CodegenTool should omit injection context when no prior patterns found."""
        with patch("tools.codegen_tool.PATCH_PROMOTION_MEMORY_SERVICE") as mock_memory:
            mock_memory.get_memory_injection.return_value = ""  # No patterns found
            
            raw = self.registry.run_tool(
                "codegen",
                {
                    "action": "preview",
                    "spec": {
                        "name": "new_feature",
                        "purpose": "Brand new feature",
                        "files": [
                            {"path": "services/new.py", "kind": "module"},
                        ],
                    },
                },
                self.context,
            )

            payload = json.loads(raw)
            # Should not include prior_patterns_context when empty
            self.assertNotIn("prior_patterns_context", payload)


if __name__ == "__main__":
    unittest.main()
