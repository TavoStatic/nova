import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import autonomy_maintenance
import work_tree
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE
from services.runtime_console_frontdoor import RUNTIME_CONSOLE_HTML
from work_tree_contracts import TaskStatus


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
        self.assertEqual(events[0].get("status"), "new")
        self.assertIn("active_work_tree_run_next", events[0].get("message", ""))

    def test_append_notice_updates_existing_open_pressure_instead_of_repeating(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"

            first = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Nova needs a tool assignment",
                message="First evidence.",
                dedupe_key="work_tree|missing_tool_assignment|tree-a|branch-a|task-a",
                payload={"request_kind": "tool_assignment", "task_id": "task-a"},
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "firstone",
            )
            second = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Nova needs a tool assignment",
                message="Updated evidence.",
                dedupe_key="work_tree|missing_tool_assignment|tree-a|branch-a|task-a",
                payload={"request_kind": "tool_assignment", "task_id": "task-a", "branch_id": "branch-a"},
                now_fn=lambda: 5000.0,
                uuid_fn=lambda: "secondone",
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(first.get("ok"))
        self.assertTrue(second.get("deduped"))
        self.assertTrue(second.get("updated"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get("message"), "Updated evidence.")
        self.assertEqual(events[0].get("updated_ts_epoch"), 5000.0)
        self.assertEqual(events[0].get("repeat_count"), 1)
        self.assertEqual((events[0].get("payload") or {}).get("branch_id"), "branch-a")

    def test_closed_notice_does_not_dedupe_new_pressure(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            first = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Need operator information",
                message="I need an origin answer.",
                dedupe_key="work_tree|blocked_task|branch-a|task-a|origin",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "aaa111",
            )
            event_id = str((first.get("event") or {}).get("id") or "")
            closed = OPERATOR_OUTBOX_SERVICE.set_notice_status(
                path,
                event_id=event_id,
                status="resolved",
                now_fn=lambda: 1001.0,
            )
            second = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Need operator information",
                message="I need an origin answer again.",
                dedupe_key="work_tree|blocked_task|branch-a|task-a|origin",
                now_fn=lambda: 1005.0,
                uuid_fn=lambda: "bbb222",
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(closed.get("ok"))
        self.assertFalse(second.get("deduped"))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].get("status"), "resolved")
        self.assertEqual(events[1].get("status"), "new")

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

    def test_notice_from_autonomy_ignores_internal_cooldown_wait(self):
        notice = OPERATOR_OUTBOX_SERVICE.notice_from_autonomy(
            {
                "decision": "defer_with_reason",
                "recommended_action": {},
                "reason": "Waiting for cooldown before the next action.",
                "rejection_reasons": ["cooldown_active"],
            },
            {
                "result": "blocked",
                "gate_reason": "decision_not_recommend_action",
                "refusal_reasons": ["cooldown_active"],
            },
        )

        self.assertEqual(notice, {})

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
                            "task_title": "Run operator-only probe",
                            "recommended_tool": "operator_only_probe",
                        },
                        "nodes": [],
                    }
                ]
            },
            executable_tools=["read", "find"],
        )

        self.assertEqual(len(notices), 1)
        self.assertIn("operator_only_probe", notices[0].get("title", ""))
        self.assertIn("operator_only_probe", notices[0].get("message", ""))
        self.assertIn("autonomy maintenance", notices[0].get("message", ""))

    def test_work_tree_notice_payload_keeps_target_without_full_tree_snapshot(self):
        notices = OPERATOR_OUTBOX_SERVICE.notices_from_work_tree_state(
            {
                "trees": [
                    {
                        "tree_id": "tree_big",
                        "title": "Signal Intake",
                        "status": "active",
                        "next_step": {
                            "action": "missing_tool_assignment",
                            "branch_id": "branch_big",
                            "branch_title": "Investigate control status size",
                            "task_id": "task_big",
                            "task_title": "Assign bounded status probe",
                            "suggested_tools": ["read", "find"],
                        },
                        "nodes": [
                            {
                                "id": f"branch_{index}",
                                "title": "Historical branch",
                                "source_payload": {"large": "x" * 4000},
                            }
                            for index in range(20)
                        ],
                    }
                ]
            },
            executable_tools=["read", "find"],
        )

        self.assertEqual(len(notices), 1)
        payload = notices[0].get("payload") or {}
        self.assertNotIn("tree", payload)
        self.assertEqual(payload.get("tree_id"), "tree_big")
        self.assertEqual(payload.get("branch_id"), "branch_big")
        self.assertEqual(payload.get("task_id"), "task_big")
        self.assertEqual(payload.get("request_kind"), "tool_assignment")
        self.assertEqual(payload.get("suggested_tools"), ["read", "find"])

    def test_work_tree_notice_names_failed_tool_judgment(self):
        notices = OPERATOR_OUTBOX_SERVICE.notices_from_work_tree_state(
            {
                "trees": [
                    {
                        "tree_id": "tree_failed_tool",
                        "title": "Signal Intake",
                        "status": "active",
                        "next_step": {
                            "action": "execute",
                            "branch_id": "branch_failed_tool",
                            "branch_title": "Probe local runtime",
                            "task_id": "task_failed_tool",
                            "task_title": "Run runtime probe",
                            "recommended_tool": "system_check",
                        },
                        "nodes": [
                            {
                                "id": "branch_failed_tool",
                                "title": "Probe local runtime",
                                "status": "ready",
                                "tool_state": {"system_check": "failed"},
                                "current_task": {
                                    "task_id": "task_failed_tool",
                                    "title": "Run runtime probe",
                                    "status": "open",
                                    "meta": {},
                                },
                            }
                        ],
                    }
                ]
            },
            executable_tools=["system_check"],
        )

        self.assertEqual(len(notices), 1)
        self.assertEqual((notices[0].get("payload") or {}).get("request_kind"), "tool_failure_judgment")
        self.assertIn("system_check", notices[0].get("title", ""))
        self.assertIn("judgment", notices[0].get("message", ""))

    def test_work_tree_failed_tool_history_without_current_task_is_not_live_pressure(self):
        notices = OPERATOR_OUTBOX_SERVICE.notices_from_work_tree_state(
            {
                "trees": [
                    {
                        "tree_id": "tree_failed_history",
                        "title": "Signal Intake",
                        "status": "active",
                        "next_step": {},
                        "nodes": [
                            {
                                "id": "branch_failed_history",
                                "title": "Resolved routing root",
                                "status": "complete",
                                "resolution_state": "resolved",
                                "tool_state": {"read": "failed"},
                                "current_task": None,
                            }
                        ],
                    }
                ]
            },
            executable_tools=["read"],
        )

        self.assertEqual(notices, [])

    def test_reconcile_work_tree_notices_stales_cleared_pressure(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            stale = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Old Work Tree pressure",
                message="This pressure is gone.",
                dedupe_key="work_tree|missing_tool_assignment|tree-a|branch-a|task-a|tool-a",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "oldnotice",
            )
            kept = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Current Work Tree pressure",
                message="This pressure is still active.",
                dedupe_key="work_tree|missing_tool_assignment|tree-a|branch-b|task-b|tool-b",
                now_fn=lambda: 1001.0,
                uuid_fn=lambda: "keepnotice",
            )

            result = OPERATOR_OUTBOX_SERVICE.reconcile_work_tree_notices(
                path,
                active_notices=[
                    {
                        "dedupe_key": "work_tree|missing_tool_assignment|tree-a|branch-b|task-b|tool-b",
                    }
                ],
                now_fn=lambda: 1010.0,
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(stale.get("ok"))
        self.assertTrue(kept.get("ok"))
        self.assertEqual(result.get("staled_count"), 1)
        by_key = {event.get("dedupe_key"): event for event in events}
        self.assertEqual(
            by_key["work_tree|missing_tool_assignment|tree-a|branch-a|task-a|tool-a"].get("status"),
            "stale",
        )
        self.assertEqual(
            by_key["work_tree|missing_tool_assignment|tree-a|branch-b|task-b|tool-b"].get("status"),
            "new",
        )

    def test_reconcile_work_tree_notices_stales_older_open_duplicates(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            key = "work_tree|missing_tool_assignment|tree-a|branch-a|task-a"
            OPERATOR_OUTBOX_SERVICE._write_events(
                path,
                [
                    {
                        "id": "001-old",
                        "ts_epoch": 1000.0,
                        "ts": "old",
                        "source": "work_tree",
                        "severity": "attention",
                        "title": "Old duplicate",
                        "message": "Old duplicate",
                        "dedupe_key": key,
                        "status": "new",
                        "payload": {"request_kind": "tool_assignment"},
                    },
                    {
                        "id": "002-new",
                        "ts_epoch": 2000.0,
                        "ts": "new",
                        "source": "work_tree",
                        "severity": "attention",
                        "title": "Current duplicate",
                        "message": "Current duplicate",
                        "dedupe_key": key,
                        "status": "new",
                        "payload": {"request_kind": "tool_assignment"},
                    },
                ],
            )

            result = OPERATOR_OUTBOX_SERVICE.reconcile_work_tree_notices(
                path,
                active_notices=[{"dedupe_key": key}],
                now_fn=lambda: 3000.0,
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertEqual(result.get("staled_count"), 1)
        self.assertEqual(events[0].get("status"), "stale")
        self.assertEqual(events[0].get("status_note"), "work_tree_pressure_superseded")
        self.assertEqual(events[1].get("status"), "new")

    def test_reconcile_source_root_judgment_notices_stales_closed_branch_pressure(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            cleared = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="source_root_judgment",
                severity="attention",
                title="Source root needs operator judgment: installer_packaging",
                message="Installer evidence failed.",
                dedupe_key="source_root_judgment|installer_packaging|failed_evidence|aaa",
                payload={
                    "request_kind": "source_root_judgment",
                    "tree": {
                        "branch_id": "branch_installer",
                        "branch_title": "Installer package readiness",
                        "task_id": "task_installer",
                        "task_title": "Synthesize source-root judgment",
                    },
                },
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "oldsrc",
            )
            kept = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="source_root_judgment",
                severity="attention",
                title="Source root needs operator judgment: web_search",
                message="Search evidence failed.",
                dedupe_key="source_root_judgment|web_search|failed_evidence|bbb",
                payload={
                    "request_kind": "source_root_judgment",
                    "tree": {
                        "branch_id": "branch_search",
                        "branch_title": "SearXNG search dependency",
                    },
                },
                now_fn=lambda: 1001.0,
                uuid_fn=lambda: "keepsrc",
            )

            result = OPERATOR_OUTBOX_SERVICE.reconcile_source_root_judgment_notices(
                path,
                work_tree_state={
                    "trees": [
                        {
                            "tree_id": "tree_signal",
                            "nodes": [
                                {
                                    "id": "branch_installer",
                                    "status": "complete",
                                    "resolution_state": "resolved",
                                },
                                {
                                    "id": "branch_search",
                                    "status": "blocked",
                                    "resolution_state": "open",
                                },
                            ],
                        }
                    ]
                },
                now_fn=lambda: 1010.0,
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(cleared.get("ok"))
        self.assertTrue(kept.get("ok"))
        self.assertEqual(result.get("staled_count"), 1)
        by_key = {event.get("dedupe_key"): event for event in events}
        self.assertEqual(
            by_key["source_root_judgment|installer_packaging|failed_evidence|aaa"].get("status"),
            "stale",
        )
        self.assertEqual(
            by_key["source_root_judgment|installer_packaging|failed_evidence|aaa"].get("status_note"),
            "source_root_pressure_cleared",
        )
        self.assertEqual(
            by_key["source_root_judgment|web_search|failed_evidence|bbb"].get("status"),
            "new",
        )

    def test_reconcile_autonomy_notices_stales_cleared_pressure(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            stale = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="autonomy_maintenance",
                severity="attention",
                title="Old autonomy pressure",
                message="This pressure cleared.",
                dedupe_key="block_with_reason|block_with_reason|blocked|old_reason|posture_red",
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "oldauto",
            )
            kept = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="autonomy_maintenance",
                severity="attention",
                title="Current autonomy pressure",
                message="This pressure is still active.",
                dedupe_key="block_with_reason|block_with_reason|blocked|current_reason|runtime_evidence_stale",
                now_fn=lambda: 1001.0,
                uuid_fn=lambda: "keepauto",
            )

            result = OPERATOR_OUTBOX_SERVICE.reconcile_autonomy_notices(
                path,
                active_notices=[
                    {
                        "dedupe_key": "block_with_reason|block_with_reason|blocked|current_reason|runtime_evidence_stale",
                    }
                ],
                now_fn=lambda: 1010.0,
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(stale.get("ok"))
        self.assertTrue(kept.get("ok"))
        self.assertEqual(result.get("staled_count"), 1)
        by_key = {event.get("dedupe_key"): event for event in events}
        self.assertEqual(
            by_key["block_with_reason|block_with_reason|blocked|old_reason|posture_red"].get("status"),
            "stale",
        )
        self.assertEqual(
            by_key["block_with_reason|block_with_reason|blocked|current_reason|runtime_evidence_stale"].get("status"),
            "new",
        )

    def test_reconcile_os_capability_notices_stales_restored_contract_pressure(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            stale = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="os_capability",
                severity="attention",
                title="OS capability contract stale: verify_ollama_model",
                message="hash mismatch",
                dedupe_key="os_capability|verify_ollama_model|contract_stale|aaa",
                payload={
                    "capability": "verify_ollama_model",
                    "blocked_reason": "contract_stale",
                },
                now_fn=lambda: 1000.0,
                uuid_fn=lambda: "oldoscap",
            )
            kept = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="os_capability",
                severity="attention",
                title="OS capability request invalid: verify_ollama_model",
                message="bad args",
                dedupe_key="os_capability|verify_ollama_model|invalid_args|bbb",
                payload={
                    "capability": "verify_ollama_model",
                    "blocked_reason": "invalid_args",
                },
                now_fn=lambda: 1001.0,
                uuid_fn=lambda: "keepargs",
            )

            result = OPERATOR_OUTBOX_SERVICE.reconcile_os_capability_notices(
                path,
                capability="verify_ollama_model",
                cleared_reasons={"contract_stale"},
                now_fn=lambda: 1010.0,
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(stale.get("ok"))
        self.assertTrue(kept.get("ok"))
        self.assertEqual(result.get("staled_count"), 1)
        by_key = {event.get("dedupe_key"): event for event in events}
        self.assertEqual(
            by_key["os_capability|verify_ollama_model|contract_stale|aaa"].get("status"),
            "stale",
        )
        self.assertEqual(
            by_key["os_capability|verify_ollama_model|invalid_args|bbb"].get("status"),
            "new",
        )

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

    def test_operator_response_records_work_tree_evidence_and_resolves_task(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "work_tree.sqlite3"
            work_tree._set_db_path(db_path)
            tree = work_tree.initialize_tree("Operator help loop")
            branch = work_tree._BRANCHES[tree.root_branch_id]
            task = work_tree.add_task_to_branch(branch.branch_id, "Wait for operator origin")
            work_tree.mark_task_blocked(task.task_id, "pending_operator_confirmation")
            path = Path(temp_dir) / "operator_outbox.jsonl"
            notice = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Nova needs operator information",
                message="I need operator information for identity bootstrap.",
                dedupe_key=f"work_tree|blocked_task|{branch.branch_id}|{task.task_id}|pending_operator_confirmation",
                payload={
                    "tree_id": tree.tree_id,
                    "tree_title": tree.title,
                    "branch_id": branch.branch_id,
                    "branch_title": branch.title,
                    "task": {
                        "task_id": task.task_id,
                        "title": task.title,
                        "status": "blocked",
                    },
                    "request_kind": "operator_information",
                    "blocked_reason": "pending_operator_confirmation",
                },
                now_fn=lambda: 2000.0,
                uuid_fn=lambda: "noticeaaa",
            )
            event_id = str((notice.get("event") or {}).get("id") or "")

            response = OPERATOR_OUTBOX_SERVICE.respond_to_notice(
                path,
                event_id=event_id,
                message="Identity origin is confirmed by Gus.",
                responder="operator",
                resolution="task_resolved",
                work_tree_module=work_tree,
                now_fn=lambda: 2005.0,
                uuid_fn=lambda: "responseaa",
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path)
            evidence = work_tree.list_branch_evidence(branch.branch_id)

        self.assertTrue(response.get("ok"))
        self.assertEqual((response.get("event") or {}).get("status"), "resolved")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get("response_count"), 1)
        self.assertEqual(work_tree._TASKS[task.task_id].status, TaskStatus.COMPLETE)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["tool_name"], "operator_response")
        self.assertEqual(evidence[0]["task_id"], task.task_id)
        self.assertEqual(work_tree._BRANCHES[branch.branch_id].evidence_count, 1)

    def test_continue_work_response_satisfies_blocked_operator_wait(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "work_tree.sqlite3"
            work_tree._set_db_path(db_path)
            tree = work_tree.initialize_tree("Operator continuation loop")
            branch = work_tree._BRANCHES[tree.root_branch_id]
            wait_task = work_tree.add_task_to_branch(branch.branch_id, "Wait for operator context")
            work_tree.mark_task_blocked(wait_task.task_id, "pending_operator_context")
            next_task = work_tree.add_task_to_branch(
                branch.branch_id,
                "Synthesize memory bootstrap judgment from collected evidence",
                meta={
                    "allowed_tools": ["memory_bootstrap_judgment"],
                    "expected_tool": "memory_bootstrap_judgment",
                },
            )
            work_tree.set_branch_tools(
                branch.branch_id,
                allowed_tools=["memory_bootstrap_judgment"],
                preferred_tool="memory_bootstrap_judgment",
            )
            path = Path(temp_dir) / "operator_outbox.jsonl"
            notice = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Nova needs operator information",
                message="I need operator context before continuing.",
                dedupe_key=f"work_tree|blocked_task|{branch.branch_id}|{wait_task.task_id}|pending_operator_context",
                payload={
                    "tree_id": tree.tree_id,
                    "tree_title": tree.title,
                    "branch_id": branch.branch_id,
                    "branch_title": branch.title,
                    "task": {
                        "task_id": wait_task.task_id,
                        "title": wait_task.title,
                        "status": "blocked",
                    },
                    "request_kind": "operator_information",
                    "blocked_reason": "pending_operator_context",
                },
                now_fn=lambda: 2020.0,
                uuid_fn=lambda: "noticecont",
            )
            event_id = str((notice.get("event") or {}).get("id") or "")

            response = OPERATOR_OUTBOX_SERVICE.respond_to_notice(
                path,
                event_id=event_id,
                message="Use the operator context as evidence and continue the branch.",
                responder="operator",
                resolution="continue_work",
                work_tree_module=work_tree,
                now_fn=lambda: 2025.0,
                uuid_fn=lambda: "responsect",
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path)
            next_step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertTrue(response.get("ok"))
        self.assertEqual((response.get("event") or {}).get("status"), "resolved")
        self.assertEqual(events[0].get("status"), "resolved")
        self.assertEqual(work_tree._TASKS[wait_task.task_id].status, TaskStatus.COMPLETE)
        self.assertEqual(work_tree._TASKS[next_task.task_id].status, TaskStatus.OPEN)
        self.assertEqual((response.get("work_tree") or {}).get("task_completed"), True)
        self.assertEqual((next_step or {}).get("task_id"), next_task.task_id)
        self.assertEqual((next_step or {}).get("recommended_tool"), "memory_bootstrap_judgment")

    def test_task_resolved_response_requires_work_tree_target(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            notice = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Nova needs operator information",
                message="I need operator information without a target.",
                payload={},
                now_fn=lambda: 2100.0,
                uuid_fn=lambda: "noticebbb",
            )
            event_id = str((notice.get("event") or {}).get("id") or "")

            response = OPERATOR_OUTBOX_SERVICE.respond_to_notice(
                path,
                event_id=event_id,
                message="Trying to resolve without a target.",
                responder="operator",
                resolution="task_resolved",
                work_tree_module=work_tree,
                now_fn=lambda: 2105.0,
                uuid_fn=lambda: "responsebb",
            )
            events = OPERATOR_OUTBOX_SERVICE.read_events(path)

        self.assertFalse(response.get("ok"))
        self.assertEqual((response.get("event") or {}).get("status"), "answered")
        self.assertEqual((response.get("work_tree") or {}).get("reason"), "task_resolved_requires_work_tree_target")
        self.assertEqual(events[0].get("response_count"), 1)
        self.assertEqual(events[0].get("status"), "answered")

    def test_continue_work_response_requires_work_tree_target(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            notice = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Nova needs operator information",
                message="I need operator information without a target.",
                payload={},
                now_fn=lambda: 2120.0,
                uuid_fn=lambda: "noticeccc",
            )
            event_id = str((notice.get("event") or {}).get("id") or "")

            response = OPERATOR_OUTBOX_SERVICE.respond_to_notice(
                path,
                event_id=event_id,
                message="Trying to continue without a target.",
                responder="operator",
                resolution="continue_work",
                work_tree_module=work_tree,
                now_fn=lambda: 2125.0,
                uuid_fn=lambda: "responsecc",
            )

        self.assertFalse(response.get("ok"))
        self.assertEqual((response.get("event") or {}).get("status"), "answered")
        self.assertEqual((response.get("work_tree") or {}).get("reason"), "continue_work_requires_work_tree_target")

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
                                    "task_title": "Run operator-only probe",
                                    "recommended_tool": "operator_only_probe",
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
        self.assertIn("operator_only_probe", events[0].get("message", ""))

    def test_autonomy_publish_stales_old_work_tree_requests_when_pressure_clears(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Old Work Tree pressure",
                message="This pressure cleared.",
                dedupe_key="work_tree|missing_tool_assignment|tree-clear|branch-clear|task-clear|tool-clear",
                now_fn=lambda: 3000.0,
                uuid_fn=lambda: "oldclear",
            )

            with mock.patch.object(autonomy_maintenance, "OPERATOR_OUTBOX", path):
                result = autonomy_maintenance._publish_operator_notices_from_work_tree(
                    {
                        "trees": [
                            {
                                "tree_id": "tree-clear",
                                "title": "Signal Intake",
                                "status": "active",
                                "next_step": None,
                                "nodes": [],
                            }
                        ]
                    }
                )
                events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("published_count"), 0)
        self.assertEqual(result.get("staled_count"), 1)
        self.assertEqual(events[0].get("status"), "stale")

    def test_autonomy_publish_stales_old_autonomy_request_when_pressure_clears(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="autonomy_maintenance",
                severity="attention",
                title="Nova needs operator attention: block_with_reason",
                message="I am stuck on block_with_reason. decision_not_recommend_action; rejections: posture_red",
                dedupe_key="block_with_reason|block_with_reason|blocked|decision_not_recommend_action|posture_red",
                now_fn=lambda: 3000.0,
                uuid_fn=lambda: "oldauto",
            )

            with mock.patch.object(autonomy_maintenance, "OPERATOR_OUTBOX", path):
                result = autonomy_maintenance._publish_operator_notice_from_autonomy(
                    {
                        "decision": "recommend_action",
                        "recommended_action": {
                            "action_type": "pulse_status",
                            "requires_ack": False,
                        },
                    },
                    {
                        "action_type": "pulse_status",
                        "result": "success",
                        "gate_reason": "execution_allowed",
                        "refusal_reasons": [],
                    },
                )
                events = OPERATOR_OUTBOX_SERVICE.read_events(path, limit=10)

        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("published"))
        self.assertEqual(result.get("staled_count"), 1)
        self.assertEqual(events[0].get("status"), "stale")
        self.assertEqual(events[0].get("status_note"), "autonomy_pressure_cleared")

    def test_summary_keeps_open_notices_visible_when_latest_event_is_closed(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            first = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Nova needs operator information",
                message="Open notice should stay visible.",
                now_fn=lambda: 4000.0,
                uuid_fn=lambda: "open0001",
            )
            second = OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Closed newer notice",
                message="This newer notice is already resolved.",
                now_fn=lambda: 4001.0,
                uuid_fn=lambda: "closed01",
            )
            first_id = str((first.get("event") or {}).get("id") or "")
            second_id = str((second.get("event") or {}).get("id") or "")
            OPERATOR_OUTBOX_SERVICE.set_notice_status(
                path,
                event_id=second_id,
                status="resolved",
                now_fn=lambda: 4002.0,
            )

            summary = OPERATOR_OUTBOX_SERVICE.summary(path, limit=1)

        self.assertEqual(summary.get("count"), 1)
        self.assertEqual(summary.get("latest_id"), second_id)
        self.assertEqual(summary.get("open_count"), 1)
        self.assertEqual(summary.get("latest_open_id"), first_id)
        self.assertEqual([event.get("id") for event in summary.get("open_events") or []], [first_id])

    def test_summary_projects_legacy_tree_payload_without_carrying_snapshot(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "operator_outbox.jsonl"
            OPERATOR_OUTBOX_SERVICE.append_notice(
                path,
                source="work_tree",
                severity="attention",
                title="Nova needs a tool assignment",
                message="A legacy notice has a full Work Tree payload.",
                payload={
                    "tree": {
                        "tree_id": "tree_legacy",
                        "title": "Signal Intake",
                        "next_step": {
                            "action": "missing_tool_assignment",
                            "branch_id": "branch_legacy",
                            "branch_title": "Legacy branch",
                            "task_id": "task_legacy",
                            "task_title": "Legacy task",
                            "suggested_tools": ["read", "find"],
                        },
                        "nodes": [{"payload": "x" * 5000} for _ in range(12)],
                    },
                    "request_kind": "tool_assignment",
                },
                now_fn=lambda: 4100.0,
                uuid_fn=lambda: "legacy01",
            )

            summary = OPERATOR_OUTBOX_SERVICE.summary(path, limit=1)

        latest = summary.get("latest") or {}
        payload = latest.get("payload") or {}
        self.assertNotIn("tree", payload)
        self.assertNotIn("nodes", str(payload))
        self.assertEqual(payload.get("tree_id"), "tree_legacy")
        self.assertEqual(payload.get("branch_id"), "branch_legacy")
        self.assertEqual(payload.get("task_id"), "task_legacy")
        self.assertEqual(payload.get("request_kind"), "tool_assignment")
        self.assertEqual((latest.get("work_tree_target") or {}).get("task_id"), "task_legacy")

    def test_runtime_console_polls_operator_outbox_from_health(self):
        self.assertIn("operator_outbox", RUNTIME_CONSOLE_HTML)
        self.assertIn("handleOperatorOutbox", RUNTIME_CONSOLE_HTML)
        self.assertIn("open_events", RUNTIME_CONSOLE_HTML)
        self.assertIn("setInterval(health, 5000)", RUNTIME_CONSOLE_HTML)


if __name__ == "__main__":
    unittest.main()
