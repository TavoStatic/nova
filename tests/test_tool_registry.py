import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nova_core
import nova_http
import tools.registry as registry_module

from services.nova_runtime_context import TOOL_EVENTS_FILE
from tools import ToolContext, build_default_registry
from tools.base_tool import ToolInvocationError
from tools.registry import build_core_tool_exports


class TestToolRegistry(unittest.TestCase):
    def test_build_core_tool_exports_returns_expected_runtime_tools(self):
        exports = build_core_tool_exports({"execute_registered_tool": lambda *_args, **_kwargs: "ok"})
        self.assertEqual(
            set(exports.keys()),
            {
                "tool_ls",
                "tool_read",
                "tool_find",
                "tool_health",
                "tool_system_check",
                "tool_queue_status",
                "tool_temporal_review",
                "tool_edfi_explore",
                "tool_pipeline",
                "tool_patch_preview_apply",
                "tool_patch_preview_approve",
                "tool_update_now",
                "tool_update_now_confirm",
                "tool_update_now_cancel",
                "tool_nova_pulse",
                "tool_nova_self_status",
                "tool_core_health_brief",
                "tool_core_thinning",
                "tool_search",
                "tool_web_fetch",
                "tool_wikipedia_lookup",
                "tool_stackexchange_search",
                "tool_web_search",
                "tool_web_gather",
                "tool_web_research",
                "tool_screen",
                "tool_camera",
            },
        )

    def test_default_tool_events_path_uses_runtime_context(self):
        self.assertEqual(registry_module.TOOL_EVENTS_PATH, TOOL_EVENTS_FILE)

    def test_manifest_lists_expected_tools(self):
        registry = build_default_registry()
        metadata = registry.list_metadata()
        names = {item["name"] for item in metadata}
        self.assertIn("codegen", names)
        self.assertIn("filesystem", names)
        self.assertIn("patch", names)
        self.assertIn("vision", names)
        self.assertIn("research", names)
        self.assertIn("system", names)
        self.assertIn("os_capability", names)
        self.assertIn("temporal_review", names)
        filesystem = next(item for item in metadata if item["name"] == "filesystem")
        self.assertEqual(filesystem["locality"], "local")
        self.assertEqual(filesystem["scope"], "user")
        self.assertTrue(filesystem["read_only"])
        patch_meta = next(item for item in metadata if item["name"] == "patch")
        self.assertTrue(patch_meta["requires_admin"])
        self.assertEqual(patch_meta["scope"], "system")
        self.assertFalse(patch_meta["read_only"])
        os_meta = next(item for item in metadata if item["name"] == "os_capability")
        self.assertEqual(os_meta["scope"], "system")
        temporal_meta = next(item for item in metadata if item["name"] == "temporal_review")
        self.assertTrue(temporal_meta["safe"])
        self.assertFalse(temporal_meta["mutating"])

    def test_temporal_review_tool_assesses_payload(self):
        registry = build_default_registry()
        ctx = ToolContext(
            user_id="tester",
            session_id="sess-temporal",
            policy={"tools_enabled": {"temporal_review": True}},
            allowed_root=".",
        )

        out = registry.run_tool(
            "temporal_review",
            {
                "action": "review",
                "payload": {
                    "title": "PEIMS deadline",
                    "start": "2026-06-10T09:00:00+00:00",
                    "importance": 1.0,
                    "dependency_risk": 0.7,
                    "stale_evidence": 0.4,
                    "operator_context": 0.2,
                },
            },
            ctx,
        )

        payload = json.loads(out)
        self.assertEqual(payload["tool"], "temporal_review")
        self.assertEqual(payload["status"], "ok")
        self.assertIn("pressure", payload)
        self.assertIn("decision", payload)

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

    def test_filesystem_find_defaults_to_live_workspace_scope(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "nova_core.py"
            archive = root / "runtime" / "exports" / "release" / "nova_core.py"
            quarantine = root / "runtime" / "recovery_quarantine" / "copy" / "nova_core.py"
            validation = root / "runtime" / "validation" / "case" / "nova_core.py"
            dependency = root / ".venv" / "Lib" / "site-packages" / "copy.py"
            for path in (live, archive, quarantine, validation, dependency):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("needle_symbol = True", encoding="utf-8")
            ctx = ToolContext(
                user_id="tester",
                session_id="sess-find",
                policy={"tools_enabled": {"files": True}},
                allowed_root=str(root),
            )

            out = registry.run_tool("filesystem", {"action": "find", "keyword": "needle_symbol"}, ctx)

            self.assertIn(str(live), out)
            self.assertNotIn(str(archive), out)
            self.assertNotIn(str(quarantine), out)
            self.assertNotIn(str(validation), out)
            self.assertNotIn(str(dependency), out)

    def test_filesystem_find_can_explicitly_search_archived_runtime_path(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "runtime" / "exports" / "release" / "nova_core.py"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text("needle_symbol = True", encoding="utf-8")
            ctx = ToolContext(
                user_id="tester",
                session_id="sess-find-archive",
                policy={"tools_enabled": {"files": True}},
                allowed_root=str(root),
            )

            out = registry.run_tool(
                "filesystem",
                {"action": "find", "keyword": "needle_symbol", "path": "runtime/exports"},
                ctx,
            )

            self.assertIn(str(archive), out)

    def test_filesystem_find_can_target_specific_file(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "subconscious_live_simulator.py"
            source.write_text("target_seam='fulfillment_bridge_entry_fallthrough'", encoding="utf-8")
            sibling = root / "runtime" / "subconscious_runs" / "latest.json"
            sibling.parent.mkdir(parents=True, exist_ok=True)
            sibling.write_text("fulfillment_bridge_entry_fallthrough", encoding="utf-8")
            ctx = ToolContext(
                user_id="tester",
                session_id="sess-find-file",
                policy={"tools_enabled": {"files": True}},
                allowed_root=str(root),
            )

            out = registry.run_tool(
                "filesystem",
                {"action": "find", "keyword": "fulfillment_bridge_entry_fallthrough", "path": "subconscious_live_simulator.py"},
                ctx,
            )

            self.assertIn(str(source), out)
            self.assertNotIn(str(sibling), out)

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

    def test_system_tool_system_check_alias_runs_health_check(self):
        registry = build_default_registry()
        ctx = ToolContext(
            user_id="tester",
            session_id="sess-system-check",
            policy={"tools_enabled": {"health": True}},
            allowed_root=".",
        )

        fake_completed = type("P", (), {"stdout": "{\"ok\": true}\n", "stderr": ""})()
        with patch("tools.system_tool.subprocess.run", return_value=fake_completed) as run_mock:
            out = registry.run_tool("system", {"action": "system_check"}, ctx)

        self.assertIn('"ok": true', out)
        called_cmd = run_mock.call_args[0][0]
        self.assertGreaterEqual(len(called_cmd), 3)
        self.assertIn("health.py", str(called_cmd[1]).lower())
        self.assertEqual(called_cmd[2], "check")

    def test_os_capability_tool_executes_through_controller_contract(self):
        registry = build_default_registry()
        calls = []

        class FakeController:
            def execute_capability(self, capability, args, **kwargs):
                calls.append((capability, args, kwargs))
                return {"ok": True, "status": "success", "reason": "", "executed": True}

        ctx = ToolContext(
            user_id="tester",
            session_id="sess-os-cap",
            policy={"tools_enabled": {}},
            allowed_root=".",
            extra={"os_script_controller": FakeController()},
        )

        raw = registry.run_tool(
            "os_capability",
            {"request": {"capability": "verify_ollama_model", "args": {"probe_chat": False}}},
            ctx,
        )

        payload = json.loads(raw)
        self.assertTrue(payload["ok"])
        self.assertEqual(calls[0][0], "verify_ollama_model")
        self.assertEqual(calls[0][1], {"probe_chat": False})
        self.assertIn("authority_context", calls[0][2])
        authority = calls[0][2]["authority_context"]
        self.assertIn("evidence_write", authority.get("allowed_authority_levels") or [])
        self.assertTrue(authority.get("allow_evidence_write"))

    def test_os_capability_tool_can_be_disabled_by_policy(self):
        registry = build_default_registry()
        ctx = ToolContext(
            user_id="tester",
            session_id="sess-os-cap-disabled",
            policy={"tools_enabled": {"os_capability": False}},
            allowed_root=".",
        )

        with self.assertRaises(ToolInvocationError) as err:
            registry.run_tool("os_capability", {"capability": "verify_ollama_model"}, ctx)

        self.assertEqual(str(err.exception), "os_capability_tool_disabled")

    def test_vision_tool_nonzero_helper_exit_is_recorded_as_error(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event_path = root / "tool_events.jsonl"
            ctx = ToolContext(
                user_id="tester",
                session_id="sess-vision-error",
                policy={"tools_enabled": {"screen": True}},
                allowed_root=str(root),
            )
            fake_completed = type("P", (), {"returncode": 1, "stdout": "", "stderr": "camera failed"})()
            with patch("tools.registry.TOOL_EVENTS_PATH", event_path), \
                 patch("tools.vision_tool.subprocess.run", return_value=fake_completed):
                with self.assertRaises(ToolInvocationError) as err:
                    registry.run_tool("vision", {"action": "screen"}, ctx)

            self.assertIn("vision_helper_failed:exit:1", str(err.exception))
            payload = json.loads(event_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["tool"], "vision")
            self.assertEqual(payload["status"], "error")
            self.assertIn("vision_helper_failed", payload["error"])

    def test_system_tool_nonzero_helper_exit_is_recorded_as_error(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event_path = root / "tool_events.jsonl"
            ctx = ToolContext(
                user_id="tester",
                session_id="sess-system-error",
                policy={"tools_enabled": {"health": True}},
                allowed_root=str(root),
            )
            fake_completed = type("P", (), {"returncode": 2, "stdout": "bad", "stderr": ""})()
            with patch("tools.registry.TOOL_EVENTS_PATH", event_path), \
                 patch("tools.system_tool.subprocess.run", return_value=fake_completed):
                with self.assertRaises(ToolInvocationError) as err:
                    registry.run_tool("system", {"action": "health_check"}, ctx)

            self.assertIn("system_helper_failed:exit:2", str(err.exception))
            payload = json.loads(event_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["tool"], "system")
            self.assertEqual(payload["status"], "error")
            self.assertIn("system_helper_failed", payload["error"])

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
                # Patch the service instance's events_log_path directly
                original_path = nova_core.TOOL_REGISTRY_SERVICE.events_log_path
                nova_core.TOOL_REGISTRY_SERVICE.events_log_path = event_path
                with patch("nova_http.TOOL_EVENTS_LOG", event_path), \
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
                    out = nova_core.execute_planned_action("ls", [])
                    self.assertIn("alpha.txt", out)
                    status = nova_http._control_status_payload()
                    self.assertTrue(status["tool_events_ok"])
                    self.assertEqual(status["tool_events_total"], 1)
                    self.assertEqual(status["tool_events_success_count"], 1)
                    self.assertEqual(status["last_tool_name"], "filesystem")
                    self.assertEqual(status["last_tool_status"], "ok")
            finally:
                nova_core.TOOL_REGISTRY_SERVICE.events_log_path = original_path
                nova_core.set_active_user(previous_user)


if __name__ == "__main__":
    unittest.main()
