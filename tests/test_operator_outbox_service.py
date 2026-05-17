import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import autonomy_maintenance
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE
from services.runtime_console_frontdoor import RUNTIME_CONSOLE_HTML


class TestOperatorOutboxService(unittest.TestCase):
    def test_append_notice_records_and_dedupes_pressure(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"

            first = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="autonomy_maintenance",
                severity="attention",
                title="Nova needs operator attention",
                message="I am stuck on active_work_tree_run_next.",
                dedupe_key="active_work_tree_run_next|blocked",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "aaa111",
            )
            second = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="autonomy_maintenance",
                severity="attention",
                title="Nova needs operator attention",
                message="I am stuck on active_work_tree_run_next.",
                dedupe_key="active_work_tree_run_next|blocked",
                now_fn=lambda: 1005.0,
                uuid_fn=lambda: "bbb222",
            )

            events = OPERATOR_OUTBOX_SERVICE.read_events(path)

        self.assertTrue(first.get("ok"))
        self.assertFalse(first.get("deduped"))
        self.assertTrue(second.get("ok"))
        self.assertTrue(second.get("deduped"))
        self.assertEqual(len(events), 1)
        self.assertIn("active_work_tree_run_next", events[0].get("message", ""))

    def test_notice_from_autonomy_uses_state_not_content_triggers(self):
        notice = OPERATOR_OUTBOX_SERVICE.notice_from_autonomy(
            {
                "decision": "recommend_action",
                "recommended_action": {
                    "action_type": "active_work_tree_run_next",
                    "requires_ack": False,
                },
                "reason": "Advance active Work Tree.",
            },
            {
                "action_type": "active_work_tree_run_next",
                "result": "blocked",
                "gate_reason": "operator_ack_required",
                "refusal_reasons": ["operator_ack_required"],
            },
        )

        self.assertEqual(notice.get("source"), "autonomy_maintenance")
        self.assertIn("I am stuck on active_work_tree_run_next.", notice.get("message", ""))
        self.assertIn("operator_ack_required", notice.get("message", ""))

    def test_work_tree_notice_names_missing_maintenance_tool_dispatch(self):
        notices = OPERATOR_OUTBOX_SERVICE.notices_from_work_tree_state(
            {
                "trees": [
                    {
                        "tree_id": "tree_tools",
                        "title": "Signal Intake",
                        "status": "active",
                        "next_step": {
                            "action": "execute",
                            "branch_id": "branch_tools",
                            "branch_title": "Probe local control endpoint",
                            "task_id": "task_tools",
                            "task_title": "Fetch http://127.0.0.1:8080/control",
                            "recommended_tool": "web_fetch",
                        },
                        "nodes": [],
                    }
                ]
            },
            executable_tools=["read", "find"],
        )

        self.assertEqual(len(notices), 1)
        self.assertIn("web_fetch", notices[0].get("title", ""))
        self.assertIn("web_fetch", notices[0].get("message", ""))
        self.assertIn("autonomy maintenance", notices[0].get("message", ""))

    def test_work_tree_notice_asks_for_operator_information_from_blocked_task(self):
        notices = OPERATOR_OUTBOX_SERVICE.notices_from_work_tree_state(
            {
                "trees": [
                    {
                        "tree_id": "tree_memory",
                        "title": "Signal Intake",
                        "status": "active",
                        "next_step": None,
                        "nodes": [
                            {
                                "id": "branch_memory",
                                "title": "Memory identity bootstrap",
                                "status": "blocked",
                                "source_type": "memory_health",
                                "work_class": "governance_pressure",
                                "actionability": "blocked",
                                "resolution_state": "observing",
                                "current_task": {
                                    "task_id": "task_memory",
                                    "title": "Wait for identity origin confirmation",
                                    "status": "blocked",
                                    "meta": {
                                        "blocked_reason": "pending_operator_confirmation",
                                    },
                                },
                            }
                        ],
                    }
                ]
            },
            executable_tools=["read", "find"],
        )

        self.assertEqual(len(notices), 1)
        self.assertIn("operator information", notices[0].get("message", ""))
        self.assertIn("pending_operator_confirmation", notices[0].get("message", ""))

    def test_work_tree_notice_names_internal_repair_hold(self):
        notices = OPERATOR_OUTBOX_SERVICE.notices_from_work_tree_state(
            {
                "trees": [
                    {
                        "tree_id": "tree_subconscious",
                        "title": "Signal Intake",
                        "status": "active",
                        "next_step": None,
                        "nodes": [
                            {
                                "id": "branch_subconscious",
                                "title": "Review subconscious priority",
                                "status": "blocked",
                                "source_type": "subconscious",
                                "work_class": "candidate_review",
                                "current_task": {
                                    "task_id": "task_subconscious",
                                    "title": "Hold owner-root repair lane for route_unclear",
                                    "status": "blocked",
                                    "meta": {
                                        "blocked_reason": "subconscious_pressure_owner_repair_required",
                                    },
                                },
                            }
                        ],
                    }
                ]
            },
            executable_tools=["read", "find"],
        )

        self.assertEqual(len(notices), 1)
        self.assertIn("internal repair lane", notices[0].get("message", ""))
        self.assertIn("subconscious_pressure_owner_repair_required", notices[0].get("message", ""))

    def test_autonomy_publish_writes_operator_notice(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            with mock.patch.object(autonomy_maintenance, "OPERATOR_OUTBOX", path):
                result = autonomy_maintenance._publish_operator_notice_from_autonomy(
                    {
                        "decision": "block_with_reason",
                        "recommended_action": {},
                        "reason": "Core steward posture is red.",
                        "rejection_reasons": ["posture_red"],
                    },
                    {
                        "result": "blocked",
                        "gate_reason": "Core steward posture is red.",
                        "refusal_reasons": ["posture_red"],
                    },
                )
                events = OPERATOR_OUTBOX_SERVICE.read_events(path)

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("published"))
        self.assertEqual(len(events), 1)
        self.assertIn("Core steward posture is red", events[0].get("message", ""))

    def test_autonomy_publish_writes_work_tree_operator_requests(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            with mock.patch.object(autonomy_maintenance, "OPERATOR_OUTBOX", path):
                result = autonomy_maintenance._publish_operator_notices_from_work_tree(
                    {
                        "trees": [
                            {
                                "tree_id": "tree_tools",
                                "title": "Signal Intake",
                                "status": "active",
                                "next_step": {
                                    "action": "execute",
                                    "branch_id": "branch_tools",
                                    "branch_title": "Probe local control endpoint",
                                    "task_id": "task_tools",
                                    "task_title": "Fetch http://127.0.0.1:8080/control",
                                    "recommended_tool": "web_fetch",
                                },
                                "nodes": [],
                            }
                        ]
                    }
                )
                events = OPERATOR_OUTBOX_SERVICE.read_events(path)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("published_count"), 1)
        self.assertEqual(len(events), 1)
        self.assertIn("web_fetch", events[0].get("message", ""))

    def test_runtime_console_polls_operator_outbox_from_health(self):
        self.assertIn("operator_outbox", RUNTIME_CONSOLE_HTML)
        self.assertIn("handleOperatorOutbox", RUNTIME_CONSOLE_HTML)
        self.assertIn("setInterval(health, 5000)", RUNTIME_CONSOLE_HTML)


if __name__ == "__main__":
    unittest.main()
