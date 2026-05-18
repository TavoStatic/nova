import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import nova_core
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE
from services.os_capability_operator_outbox import build_os_capability_notice, publish_os_capability_notice
from tools import ToolContext, build_default_registry


def _blocked_result(capability: str = "inspect_ports", reason: str = "missing_capability") -> dict:
    return {
        "ok": False,
        "status": "blocked",
        "reason": reason,
        "operator_outbox": True,
        "executed": False,
        "ledger": {
            "status": "recorded",
            "path": f"C:/NOVA/runtime/os_capability_ledger.jsonl",
        },
        "row": {
            "schema": "nova.os_capability_ledger.v1",
            "request_id": "oscap_1000000000000_test",
            "status": "blocked",
            "reason": reason,
            "capability": capability,
            "contract_version": "0.1.0",
            "authority_level": "read_only",
            "mutating": False,
            "locality": "local",
            "registry_path": "C:/NOVA/tools/os_capabilities/os_capabilities.json",
            "script_path": "",
            "script_sha256": "",
            "args": {},
            "prepare": {
                "ok": False,
                "reason": reason,
                "operator_outbox": True,
                "errors": [f"{reason}:{capability}"],
                "execution_hash": {},
            },
            "errors": [f"{reason}:{capability}"],
        },
    }


class TestOsCapabilityOperatorOutboxService(unittest.TestCase):
    def test_build_notice_from_controller_result_state(self):
        notice = build_os_capability_notice(
            _blocked_result("inspect_processes", "missing_capability"),
            context={"tree_id": "tree-a", "branch_id": "branch-a", "task_id": "task-a"},
        )

        self.assertEqual(notice.get("source"), "os_capability")
        self.assertIn("inspect_processes", notice.get("title", ""))
        self.assertIn("inspect_processes", notice.get("message", ""))
        payload = notice.get("payload") or {}
        self.assertEqual(payload.get("request_kind"), "os_capability_contract")
        self.assertEqual(payload.get("blocked_reason"), "missing_capability")
        self.assertEqual((payload.get("context") or {}).get("task_id"), "task-a")

    def test_publish_notice_dedupes_repeated_contract_gap(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "operator_outbox.jsonl"
            result = _blocked_result("verify_ollama_model", "contract_stale")

            first = publish_os_capability_notice(
                result,
                outbox_path=path,
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "noticeaaa",
            )
            second = publish_os_capability_notice(
                result,
                outbox_path=path,
                now_fn=lambda: 1005.0,
                uuid_fn=lambda: "noticebbb",
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(first.get("published"))
        self.assertFalse(first.get("deduped"))
        self.assertTrue(second.get("deduped"))
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].get("payload") or {}).get("blocked_reason"), "contract_stale")

    def test_registered_tool_publishes_operator_notice_when_controller_marks_outbox(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "operator_outbox.jsonl"
            registry = build_default_registry()

            class FakeController:
                def execute_capability(self, capability, args, **kwargs):
                    result = _blocked_result(capability, "invalid_args")
                    result["row"]["args"] = args
                    result["ledger"]["path"] = str(path.with_name("os_capability_ledger.jsonl"))
                    return result

            ctx = ToolContext(
                user_id="tester",
                session_id="sess-os-outbox",
                policy={"tools_enabled": {}},
                allowed_root=".",
                extra={
                    "os_script_controller": FakeController(),
                    "operator_outbox_path": str(path),
                    "work_tree_target": {
                        "tree_id": "tree-os",
                        "branch_id": "branch-os",
                        "task_id": "task-os",
                    },
                },
            )

            raw = registry.run_tool(
                "os_capability",
                {"capability": "verify_ollama_model", "args": {"probe_chat": "bad"}},
                ctx,
            )
            payload = json.loads(raw)
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["operator_notice"]["published"])
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].get("payload") or {}).get("capability"), "verify_ollama_model")
        self.assertEqual(((events[0].get("payload") or {}).get("context") or {}).get("task_id"), "task-os")

    def test_core_tool_publishes_operator_notice_when_controller_marks_outbox(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "operator_outbox.jsonl"
            result = _blocked_result("inspect_processes", "authority_blocked")
            result["ledger"]["path"] = str(path.with_name("os_capability_ledger.jsonl"))

            with mock.patch("services.os_capability_operator_outbox.OPERATOR_OUTBOX_FILE", path), mock.patch(
                "services.os_script_controller.OS_SCRIPT_CONTROLLER_SERVICE.execute_capability",
                return_value=result,
            ):
                payload = nova_core.tool_os_capability(capability="inspect_processes")
                events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["operator_notice"]["published"])
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].get("payload") or {}).get("blocked_reason"), "authority_blocked")


if __name__ == "__main__":
    unittest.main()
