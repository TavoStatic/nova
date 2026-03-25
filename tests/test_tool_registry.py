import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nova_core
import nova_http

from tools import ToolContext, build_default_registry
from tools.base_tool import ToolInvocationError


class TestToolRegistry(unittest.TestCase):
    def test_manifest_lists_expected_tools(self):
        registry = build_default_registry()
        metadata = registry.list_metadata()
        names = {item["name"] for item in metadata}
        self.assertIn("filesystem", names)
        self.assertIn("patch", names)
        self.assertIn("vision", names)
        self.assertIn("research", names)
        self.assertIn("system", names)
        filesystem = next(item for item in metadata if item["name"] == "filesystem")
        self.assertEqual(filesystem["locality"], "local")
        self.assertEqual(filesystem["scope"], "user")
        self.assertTrue(filesystem["read_only"])
        patch_meta = next(item for item in metadata if item["name"] == "patch")
        self.assertTrue(patch_meta["requires_admin"])
        self.assertEqual(patch_meta["scope"], "system")
        self.assertFalse(patch_meta["read_only"])

    def test_filesystem_ls_uses_allowed_root(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha.txt").write_text("hello", encoding="utf-8")
            (root / "nested").mkdir()
            ctx = ToolContext(
                user_id="tester",
                session_id="sess-1",
                policy={"tools_enabled": {"files": True}},
                allowed_root=str(root),
            )
            out = registry.run_tool("filesystem", {"action": "ls"}, ctx)
            self.assertIn("FILE  alpha.txt", out)
            self.assertIn("DIR   nested", out)

    def test_filesystem_denies_path_escape(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root.parent / "outside.txt"
            outside.write_text("nope", encoding="utf-8")
            ctx = ToolContext(
                user_id="tester",
                session_id="sess-2",
                policy={"tools_enabled": {"files": True}},
                allowed_root=str(root),
            )
            with self.assertRaises(ToolInvocationError):
                registry.run_tool("filesystem", {"action": "read", "path": str(outside)}, ctx)

    def test_disabled_tool_is_denied(self):
        registry = build_default_registry()
        ctx = ToolContext(
            user_id="tester",
            session_id="sess-3",
            policy={"tools_enabled": {"files": False}},
            allowed_root=".",
        )
        with self.assertRaises(ToolInvocationError) as err:
            registry.run_tool("filesystem", {"action": "ls"}, ctx)
        self.assertEqual(str(err.exception), "files_tool_disabled")

    def test_tool_event_written_for_success(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event_path = root / "tool_events.jsonl"
            ctx = ToolContext(
                user_id="tester",
                session_id="sess-4",
                policy={"tools_enabled": {"files": True}},
                allowed_root=str(root),
            )
            with patch("tools.registry.TOOL_EVENTS_PATH", event_path):
                registry.run_tool("filesystem", {"action": "ls"}, ctx)
            lines = event_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["tool"], "filesystem")
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["locality"], "local")
            self.assertEqual(payload["scope"], "user")
            self.assertFalse(payload["mutating"])

    def test_patch_tool_requires_admin(self):
        registry = build_default_registry()
        ctx = ToolContext(
            user_id="tester",
            session_id="sess-5",
            policy={"patch": {"enabled": True, "allow_force": False}},
            allowed_root=".",
            is_admin=False,
            extra={"patch_handlers": {"preview": lambda value: f"preview:{value}"}},
        )
        with self.assertRaises(ToolInvocationError) as err:
            registry.run_tool("patch", {"action": "preview", "value": "demo.zip"}, ctx)
        self.assertEqual(str(err.exception), "admin_required")

    def test_system_tool_queue_status_formats_generated_queue(self):
        registry = build_default_registry()
        ctx = ToolContext(
            user_id="tester",
            session_id="sess-queue",
            policy={"tools_enabled": {"health": True}},
            allowed_root=".",
        )
        queue_payload = {
            "count": 4,
            "open_count": 2,
            "green_count": 2,
            "drift_count": 2,
            "warning_count": 0,
            "never_run_count": 0,
            "next_item": {
                "file": "next_generated.json",
                "family_id": "demo-family",
                "latest_status": "drift",
                "opportunity_reason": "parity_drift",
                "latest_report_path": "C:/Nova/runtime/test_sessions/next_generated/result.json",
            },
            "items": [
                {
                    "file": "next_generated.json",
                    "open": True,
                    "latest_status": "drift",
                    "opportunity_reason": "parity_drift",
                    "highest_priority": {"signal": "fallback_overuse", "urgency": "high", "seam": "demo_seam"},
                }
            ],
        }
        with patch("nova_http._generated_work_queue", return_value=queue_payload):
            out = registry.run_tool("system", {"action": "queue_status"}, ctx)
        self.assertIn("Standing work queue", out)
        self.assertIn("open: 2 of 4", out)
        self.assertIn("Next item: next_generated.json", out)
        self.assertIn("fallback_overuse", out)

    def test_core_keyword_to_status_event_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha.txt").write_text("hello", encoding="utf-8")
            event_path = root / "tool_events.jsonl"
            policy = {
                "allowed_root": str(root),
                "tools_enabled": {"files": True, "screen": False, "camera": False, "health": False, "web": False},
                "web": {"enabled": False, "search_provider": "html", "search_api_endpoint": "", "allow_domains": []},
                "memory": {"enabled": False, "scope": "private"},
                "models": {"chat": "test-model"},
            }
            previous_user = nova_core.get_active_user()
            try:
                nova_core.set_active_user("tester")
                with patch("tools.registry.TOOL_EVENTS_PATH", event_path), \
                     patch("nova_http.TOOL_EVENTS_LOG", event_path), \
                     patch("nova_core.load_policy", return_value=policy), \
                     patch("nova_http.nova_core.load_policy", return_value=policy), \
                     patch("nova_http.nova_core.ollama_api_up", return_value=False), \
                     patch("nova_http.nova_core.chat_model", return_value="test-model"), \
                     patch("nova_http.nova_core.mem_enabled", return_value=False), \
                     patch("nova_http._chat_login_enabled", return_value=False), \
                     patch("nova_http._chat_auth_source", return_value="disabled"), \
                     patch("nova_http._chat_users", return_value={}), \
                     patch("nova_http._guard_status_payload", return_value={}), \
                     patch("nova_http._core_status_payload", return_value={"running": False, "pid": None, "heartbeat_age_sec": None}), \
                     patch("nova_http._append_metrics_snapshot", return_value=None), \
                     patch("nova_http._metrics_payload", return_value={"ok": True, "points": []}):
                    kind, tool_name, out = nova_core.handle_keywords("ls")
                    self.assertEqual(kind, "tool")
                    self.assertEqual(tool_name, "ls")
                    self.assertIn("alpha.txt", out)
                    status = nova_http._control_status_payload()
                    self.assertTrue(status["tool_events_ok"])
                    self.assertEqual(status["tool_events_total"], 1)
                    self.assertEqual(status["tool_events_success_count"], 1)
                    self.assertEqual(status["last_tool_name"], "filesystem")
                    self.assertEqual(status["last_tool_status"], "ok")
            finally:
                nova_core.set_active_user(previous_user)


if __name__ == "__main__":
    unittest.main()