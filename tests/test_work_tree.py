from __future__ import annotations

from contextlib import closing
import json
import os
import unittest
from pathlib import Path
import sqlite3
from unittest import mock
import uuid

import work_tree
from work_tree_contracts import BranchStatus, ToolStatus, TreeStatus


def _validation_tmp_root() -> Path:
    return Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "_test_tmp"


class TestWorkTree(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._db_path = base_tmp / f"work_tree_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(self._db_path)

    def tearDown(self) -> None:
        try:
            if self._db_path.exists():
                self._db_path.unlink()
        except Exception:
            pass
        try:
            journal_path = self._db_path.with_name(f"{self._db_path.name}-journal")
            if journal_path.exists():
                journal_path.unlink()
        except Exception:
            pass

    def test_next_open_branch_prefers_nearest_eligible_branch(self) -> None:
        tree = work_tree.initialize_tree("Build runtime")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(tree.tree_id, "Deep child", "child", root_branch.branch_id)
        child_branch.priority = 100

        work_tree.add_task_to_branch(root_branch.branch_id, "Root task")
        work_tree.add_task_to_branch(child_branch.branch_id, "Child task")

        selected = work_tree.next_open_branch(tree.tree_id)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.branch_id, root_branch.branch_id)
        self.assertEqual(root_branch.status, BranchStatus.ACTIVE)
        self.assertEqual(child_branch.status, BranchStatus.READY)

    def test_default_tree_allowed_tools_returns_full_copy(self) -> None:
        tools = work_tree.default_tree_allowed_tools()
        tools.append("local_mutation")

        self.assertIn("source_root_judgment", work_tree.default_tree_allowed_tools())
        self.assertIn("os_capability", work_tree.default_tree_allowed_tools())
        self.assertIn("memory_bootstrap_confirm", work_tree.default_tree_allowed_tools())
        self.assertNotIn("local_mutation", work_tree.default_tree_allowed_tools())

    def test_inspect_tree_does_not_persist_snapshot_reads(self) -> None:
        tree = work_tree.initialize_tree("Inspect tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "Inspect queue")

        with mock.patch.object(work_tree, "_persist_tree_state") as persist_mock:
            payload = work_tree.inspect_tree(tree.tree_id)

        self.assertIsNotNone(payload)
        persist_mock.assert_not_called()

    def test_touch_branch_persists_resolution_state_without_status_change(self) -> None:
        tree = work_tree.initialize_tree("Persist resolution")
        branch = work_tree._BRANCHES[tree.root_branch_id]
        branch.status = BranchStatus.COMPLETE
        branch.resolution_state = "open"
        work_tree._persist_tree_state(tree.tree_id)

        branch.resolution_state = "resolved"
        work_tree.touch_branch(branch.branch_id)

        work_tree._clear_in_memory()
        self.assertTrue(work_tree.reload_persisted_state())
        restored = work_tree._BRANCHES[branch.branch_id]
        self.assertEqual(restored.status, BranchStatus.COMPLETE)
        self.assertEqual(restored.resolution_state, "resolved")

    def test_db_transaction_retries_retryable_operational_error(self) -> None:
        calls = []

        class FakeConnection:
            def __init__(self) -> None:
                self.begin_calls = 0
                self.closed = False

            def execute(self, sql: str):
                if sql == "BEGIN IMMEDIATE":
                    self.begin_calls += 1
                    if len(calls) < 2:
                        calls.append("retry")
                        raise sqlite3.OperationalError("disk I/O error")
                    calls.append("success")
                return None

            def commit(self) -> None:
                return None

            def rollback(self) -> None:
                return None

            def close(self) -> None:
                self.closed = True

        with mock.patch.object(work_tree, "_db_connect", side_effect=lambda: FakeConnection()), \
             mock.patch.object(work_tree.time, "sleep", return_value=None):
            with work_tree._db_transaction() as connection:
                self.assertIsNotNone(connection)

        self.assertEqual(calls, ["retry", "retry", "success"])

    def test_dependency_blocks_branch_until_parent_branch_completes(self) -> None:
        tree = work_tree.initialize_tree("Dependency tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(tree.tree_id, "Blocked child", "child", root_branch.branch_id)
        work_tree.add_dependency(child_branch.branch_id, root_branch.branch_id)

        root_task = work_tree.add_task_to_branch(root_branch.branch_id, "Finish root")
        work_tree.add_task_to_branch(child_branch.branch_id, "Finish child")

        self.assertFalse(work_tree.is_branch_ready(child_branch.branch_id))
        self.assertEqual(child_branch.status, BranchStatus.BLOCKED)

        work_tree.mark_task_complete(root_task.task_id)

        self.assertTrue(work_tree.is_branch_ready(child_branch.branch_id))
        self.assertEqual(root_branch.status, BranchStatus.COMPLETE)
        self.assertEqual(child_branch.status, BranchStatus.READY)

    def test_next_autonomous_step_waits_for_missing_tools(self) -> None:
        tree = work_tree.initialize_tree("Tool wait")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "Need tool")
        work_tree.set_branch_tools(
            root_branch.branch_id,
            required_tools=["web_search"],
            allowed_tools=["web_search", "web_fetch"],
            preferred_tool="web_search",
        )
        root_branch.tool_state["web_search"] = ToolStatus.BLOCKED

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "wait_for_tools")
        self.assertEqual(step["branch_id"], root_branch.branch_id)
        self.assertEqual(step["missing_tools"], ["web_search"])

    def test_next_autonomous_step_recommends_preferred_tool_when_ready(self) -> None:
        tree = work_tree.initialize_tree("Tool ready")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "Use tool")
        work_tree.set_branch_tools(
            root_branch.branch_id,
            required_tools=["web_search"],
            allowed_tools=["web_search", "web_fetch"],
            preferred_tool="web_search",
        )

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["branch_id"], root_branch.branch_id)
        self.assertEqual(step["recommended_tool"], "web_search")
        self.assertEqual(step["required_tools"], ["web_search"])
        self.assertEqual(step["allowed_tools"], ["web_search", "web_fetch"])

    def test_next_autonomous_step_reports_missing_tool_when_branch_has_none(self) -> None:
        tree = work_tree.initialize_tree("Missing assignment")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "collect student_data attendance guidance")

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "missing_tool_assignment")
        self.assertEqual(str(root_branch.preferred_tool or ""), "")
        self.assertEqual(root_branch.allowed_tools, [])

    def test_next_autonomous_step_prefers_patch_rollback_for_rollback_task(self) -> None:
        tree = work_tree.initialize_tree("Patch rollback tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(
            root_branch.branch_id,
            "patch rollback",
            meta={"expected_tool": "patch_rollback", "allowed_tools": ["patch_rollback"]},
        )
        work_tree.set_tree_policy(
            tree.tree_id,
            allowed_tools=["patch_apply", "patch_rollback"],
            require_explicit_allow=True,
        )

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["recommended_tool"], "patch_rollback")
        self.assertEqual(root_branch.preferred_tool, "patch_rollback")
        self.assertEqual(root_branch.allowed_tools, ["patch_rollback"])

    def test_next_autonomous_step_prefers_patch_preview_apply_for_approved_preview_task(self) -> None:
        tree = work_tree.initialize_tree("Patch preview apply tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(
            root_branch.branch_id,
            "apply approved preview preview_queue_item.txt",
            meta={
                "patch_preview": "preview_queue_item.txt",
                "expected_tool": "patch_preview_apply",
                "allowed_tools": ["patch_preview_apply"],
            },
        )
        work_tree.set_tree_policy(
            tree.tree_id,
            allowed_tools=["patch_preview_apply", "patch_apply", "patch_rollback"],
            require_explicit_allow=True,
        )

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["recommended_tool"], "patch_preview_apply")
        self.assertEqual(root_branch.preferred_tool, "patch_preview_apply")
        self.assertEqual(root_branch.allowed_tools, ["patch_preview_apply"])

    def test_next_autonomous_step_prefers_patch_preview_approve_for_pending_preview_task(self) -> None:
        tree = work_tree.initialize_tree("Patch preview approve tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(
            root_branch.branch_id,
            "approve pending preview preview_queue_item.txt",
            meta={
                "patch_preview": "preview_queue_item.txt",
                "expected_tool": "patch_preview_approve",
                "allowed_tools": ["patch_preview_approve"],
            },
        )
        work_tree.set_tree_policy(
            tree.tree_id,
            allowed_tools=["patch_preview_approve", "patch_preview_apply", "patch_rollback"],
            require_explicit_allow=True,
        )

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["recommended_tool"], "patch_preview_approve")
        self.assertEqual(root_branch.preferred_tool, "patch_preview_approve")
        self.assertEqual(root_branch.allowed_tools, ["patch_preview_approve"])

    def test_next_autonomous_step_prefers_generated_queue_run_for_generated_session_task(self) -> None:
        tree = work_tree.initialize_tree("Generated queue tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(
            root_branch.branch_id,
            "run generated session subconscious_demo_family_turn.json",
            meta={
                "session_file": "subconscious_demo_family_turn.json",
                "expected_tool": "generated_queue_run",
                "allowed_tools": ["generated_queue_run"],
            },
        )
        work_tree.set_tree_policy(
            tree.tree_id,
            allowed_tools=["generated_queue_run", "read", "find"],
            require_explicit_allow=True,
        )

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["recommended_tool"], "generated_queue_run")
        self.assertEqual(root_branch.preferred_tool, "generated_queue_run")
        self.assertEqual(root_branch.allowed_tools, ["generated_queue_run"])

    def test_execute_autonomous_step_passes_generated_session_file_arg(self) -> None:
        tree = work_tree.initialize_tree("Generated queue execute")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "run generated session subconscious_demo_family_turn.json",
            meta={"session_file": "subconscious_demo_family_turn.json"},
        )
        work_tree.set_tree_policy(
            tree.tree_id,
            allowed_tools=["generated_queue_run", "read", "find"],
            require_explicit_allow=True,
        )
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["generated_queue_run"], preferred_tool="generated_queue_run")

        calls = []
        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: calls.append((tool, list(args or []))) or {"ok": True, "report_status": "green"},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "generated_queue_run")
        self.assertEqual(calls, [("generated_queue_run", ["subconscious_demo_family_turn.json"])])
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_os_capability_task_uses_structured_capability_request_args(self) -> None:
        tree = work_tree.initialize_tree("OS capability route")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.set_tree_policy(tree.tree_id, allowed_tools=["os_capability"])
        work_tree.set_branch_tools(
            root_branch.branch_id,
            required_tools=["os_capability"],
            allowed_tools=["os_capability"],
            preferred_tool="os_capability",
        )
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Verify local Ollama model",
            meta={
                "capability_request": {
                    "capability": "verify_ollama_model",
                    "args": {"probe_chat": False},
                }
            },
        )
        calls = []

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: calls.append((tool, list(args or []))) or {"ok": True, "status": "success"},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(calls[0][0], "os_capability")
        self.assertEqual(
            json.loads(calls[0][1][0]),
            {"capability": "verify_ollama_model", "args": {"probe_chat": False}},
        )
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_execute_autonomous_step_stops_when_branch_has_no_tool_assignment(self) -> None:
        tree = work_tree.initialize_tree("Missing assignment boundary")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "collect runtime diagnostics")

        called = []
        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: called.append((tool, list(args or []))) or "ok",
        )

        self.assertEqual(step["action"], "missing_tool_assignment")
        self.assertEqual(step["task_id"], task.task_id)
        self.assertEqual(called, [])
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_next_autonomous_step_does_not_wait_when_required_tool_failed(self) -> None:
        tree = work_tree.initialize_tree("Retry failed tool")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "search student_data")
        work_tree.set_branch_tools(root_branch.branch_id, required_tools=["web_search"], preferred_tool="web_search")
        root_branch.tool_state["web_search"] = ToolStatus.FAILED

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["recommended_tool"], "web_search")

    def test_tree_becomes_complete_after_all_tasks_complete(self) -> None:
        tree = work_tree.initialize_tree("Close tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "Done")

        work_tree.mark_task_complete(task.task_id)

        self.assertTrue(work_tree.is_tree_complete(tree.tree_id))
        self.assertEqual(work_tree.get_tree(tree.tree_id).status, TreeStatus.COMPLETE)

    def test_run_autonomous_loop_without_executor_is_planning_only(self) -> None:
        tree = work_tree.initialize_tree("Loop tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "Step one")
        work_tree.add_task_to_branch(root_branch.branch_id, "Step two")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")

        history = work_tree.run_autonomous_loop(tree.tree_id)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["action"], "execute")
        self.assertFalse(work_tree.is_tree_complete(tree.tree_id))

    def test_run_autonomous_loop_stops_when_tools_are_blocked(self) -> None:
        tree = work_tree.initialize_tree("Blocked loop")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "Need tools")
        work_tree.set_branch_tools(root_branch.branch_id, required_tools=["web_search"])
        root_branch.tool_state["web_search"] = ToolStatus.BLOCKED

        history = work_tree.run_autonomous_loop(tree.tree_id)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["action"], "wait_for_tools")
        self.assertFalse(work_tree.is_tree_complete(tree.tree_id))

    def test_execute_autonomous_step_runs_real_tool_and_completes_task(self) -> None:
        tree = work_tree.initialize_tree("Execute tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "search student_data")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")

        calls = []
        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: calls.append((tool, list(args or []))) or "search results",
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "web_search")
        self.assertEqual(step["tool_result"], "search results")
        self.assertTrue(str(step.get("evidence_id") or "").startswith("evidence_"))
        self.assertEqual(calls, [("web_search", ["search student_data"])])
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)
        evidence = work_tree.list_branch_evidence(root_branch.branch_id)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["task_id"], task.task_id)
        self.assertEqual(evidence[0]["tool_name"], "web_search")
        self.assertEqual(evidence[0]["tool_args"], ["search student_data"])
        self.assertEqual(evidence[0]["result_text"], "search results")

    def test_execute_autonomous_step_marks_failed_tool_state(self) -> None:
        tree = work_tree.initialize_tree("Failure tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "search student_data")
        work_tree.set_branch_tools(root_branch.branch_id, required_tools=["web_search"], preferred_tool="web_search")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"ok": False, "error": "tool offline"},
        )

        self.assertEqual(step["action"], "tool_failed")
        self.assertEqual(step["tool"], "web_search")
        self.assertTrue(str(step.get("failure_evidence_id") or "").startswith("evidence_"))
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)
        self.assertEqual(root_branch.tool_state["web_search"], ToolStatus.FAILED)
        evidence = work_tree.list_branch_evidence(root_branch.branch_id)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["task_id"], task.task_id)
        self.assertEqual(evidence[0]["tool_name"], "web_search")
        self.assertIn("tool offline", evidence[0]["result_text"])
        visual = work_tree.get_visual_tree_data(tree.tree_id)
        node = (visual or {}).get("nodes", [])[0]
        self.assertEqual((node.get("tool_state") or {}).get("web_search"), "failed")

    def test_blocked_task_blocks_branch_without_becoming_executable(self) -> None:
        tree = work_tree.initialize_tree("Blocked task tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "await operator contract")

        work_tree.mark_task_blocked(task.task_id, "needs_operator_origin")

        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.BLOCKED)
        self.assertEqual(root_branch.status, BranchStatus.BLOCKED)
        self.assertFalse(work_tree.is_tree_complete(tree.tree_id))
        self.assertIsNone(work_tree.next_autonomous_step(tree.tree_id))

    def test_visual_tree_exposes_current_task_meta_for_blocked_requests(self) -> None:
        tree = work_tree.initialize_tree("Blocked task metadata")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "await operator contract")

        work_tree.mark_task_blocked(task.task_id, "needs_operator_origin")

        visual = work_tree.get_visual_tree_data(tree.tree_id)
        node = (visual or {}).get("nodes", [])[0]

        self.assertEqual(node["current_task"]["meta"]["blocked_reason"], "needs_operator_origin")
        self.assertEqual(node["current_task"]["meta"]["block_reason"], "needs_operator_origin")

    def test_execute_autonomous_step_patch_preview_apply_uses_preview_meta(self) -> None:
        tree = work_tree.initialize_tree("Patch preview execution")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "apply approved preview preview_queue_item.txt",
            meta={"patch_preview": "preview_queue_item.txt"},
        )
        work_tree.set_tree_execution_policy(
            tree.tree_id,
            allowed_tools=["patch_preview_apply"],
            require_explicit_allow=True,
        )
        work_tree.set_branch_tools(
            root_branch.branch_id,
            allowed_tools=["patch_preview_apply"],
            preferred_tool="patch_preview_apply",
        )

        calls = []
        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: calls.append((tool, list(args or []))) or {"ok": True, "preview": "preview_queue_item.txt"},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "patch_preview_apply")
        self.assertEqual(calls, [("patch_preview_apply", ["preview_queue_item.txt"])])
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_execute_autonomous_step_patch_preview_approve_uses_preview_meta(self) -> None:
        tree = work_tree.initialize_tree("Patch preview approval execution")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "approve pending preview preview_queue_item.txt",
            meta={"patch_preview": "preview_queue_item.txt"},
        )
        work_tree.set_tree_execution_policy(
            tree.tree_id,
            allowed_tools=["patch_preview_approve"],
            require_explicit_allow=True,
        )
        work_tree.set_branch_tools(
            root_branch.branch_id,
            allowed_tools=["patch_preview_approve"],
            preferred_tool="patch_preview_approve",
        )

        calls = []
        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: calls.append((tool, list(args or []))) or {"ok": True, "preview": "preview_queue_item.txt"},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "patch_preview_approve")
        self.assertEqual(calls, [("patch_preview_approve", ["preview_queue_item.txt"])])
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_execute_autonomous_step_read_not_a_file_marks_failed(self) -> None:
        tree = work_tree.initialize_tree("Read failure tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "Map run_loop, hard_answer, patch_apply seams")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["read"], preferred_tool="read")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: "Not a file: C:\\Nova\\Map run_loop, hard_answer, patch_apply seams",
        )

        self.assertEqual(step["action"], "tool_failed")
        self.assertEqual(step["tool"], "read")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_execute_autonomous_step_fail_marker_marks_failed(self) -> None:
        tree = work_tree.initialize_tree("Web search failure tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "Probe configured web search route")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: "[FAIL] Local web search backend is unavailable.",
        )

        self.assertEqual(step["action"], "tool_failed")
        self.assertEqual(step["tool"], "web_search")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_execute_autonomous_step_records_structured_judgment_false_ok(self) -> None:
        tree = work_tree.initialize_tree("Judgment tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Synthesize source-root judgment from collected evidence",
            meta={"expected_tool": "source_root_judgment", "allowed_tools": ["source_root_judgment"]},
        )
        work_tree.set_branch_tools(
            root_branch.branch_id,
            allowed_tools=["source_root_judgment"],
            preferred_tool="source_root_judgment",
        )

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {
                "ok": False,
                "schema": "nova.source_root_judgment.v1",
                "verdict": "evidence_failed",
                "reason": "evidence_failed",
            },
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "source_root_judgment")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_execute_autonomous_step_read_preserves_relative_path(self) -> None:
        tree = work_tree.initialize_tree("Read relative path tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "Read services/memory_health.py bootstrap state")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["read"], preferred_tool="read")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"tool": tool, "args": list(args or [])},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool_result"], {"tool": "read", "args": ["services/memory_health.py"]})

    def test_execute_autonomous_step_ls_not_a_folder_marks_failed(self) -> None:
        tree = work_tree.initialize_tree("Ls failure tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "retrieve recent logs")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["ls"], preferred_tool="ls")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: "Not a folder: C:\\Nova\\retrieve recent logs",
        )

        self.assertEqual(step["action"], "tool_failed")
        self.assertEqual(step["tool"], "ls")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_execute_autonomous_step_ls_log_review_targets_runtime_dir(self) -> None:
        tree = work_tree.initialize_tree("Ls log tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "retrieve recent logs")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["ls"], preferred_tool="ls")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"tool": tool, "args": list(args or [])},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "ls")
        self.assertEqual(step["tool_result"], {"tool": "ls", "args": ["runtime"]})
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_execute_autonomous_step_patch_apply_not_a_file_marks_failed(self) -> None:
        tree = work_tree.initialize_tree("Patch apply failure tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "patch preview teach.zip")
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["patch_apply"], require_explicit_allow=True)
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["patch_apply"], preferred_tool="patch_apply")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: "Not a file: C:\\Nova\\patch preview teach.zip",
        )

        self.assertEqual(step["action"], "tool_failed")
        self.assertEqual(step["tool"], "patch_apply")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_execute_autonomous_step_test_review_prefers_find_and_uses_test_symbol(self) -> None:
        tree = work_tree.initialize_tree("Test review tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Run or inspect test_generic_fallback_does_not_hide_viable_specific_route and confirm whether fallback_overuse is still active",
            meta={
                "expected_tool": "find",
                "allowed_tools": ["find"],
                "tool_args": ["test_generic_fallback_does_not_hide_viable_specific_route"],
            },
        )

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"tool": tool, "args": list(args or [])},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "find")
        self.assertEqual(step["tool_result"], {"tool": "find", "args": ["test_generic_fallback_does_not_hide_viable_specific_route"]})
        self.assertEqual(root_branch.preferred_tool, "find")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_execute_autonomous_step_uses_explicit_task_tool_args(self) -> None:
        tree = work_tree.initialize_tree("Scoped evidence tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Find route evidence for fulfillment_bridge_entry_fallthrough without running generated tests",
            meta={
                "expected_tool": "find",
                "allowed_tools": ["find"],
                "tool_args": ["fulfillment_bridge_entry_fallthrough", "subconscious_live_simulator.py"],
            },
        )
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["find"], preferred_tool="find")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"tool": tool, "args": list(args or [])},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "find")
        self.assertEqual(
            step["tool_result"],
            {
                "tool": "find",
                "args": ["fulfillment_bridge_entry_fallthrough", "subconscious_live_simulator.py"],
            },
        )

    def test_subconscious_review_judgment_uses_current_branch_id(self) -> None:
        tree = work_tree.initialize_tree("Subconscious judgment tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Synthesize subconscious review judgment for fulfillment_bridge_entry_fallthrough / fulfillment_missed",
            meta={
                "expected_tool": "subconscious_review_judgment",
                "allowed_tools": ["subconscious_review_judgment"],
            },
        )
        work_tree.set_branch_tools(
            root_branch.branch_id,
            allowed_tools=["subconscious_review_judgment"],
            preferred_tool="subconscious_review_judgment",
        )

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"tool": tool, "args": list(args or [])},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "subconscious_review_judgment")
        self.assertEqual(step["tool_result"], {"tool": "subconscious_review_judgment", "args": [root_branch.branch_id]})

    def test_execute_autonomous_step_find_no_matches_keeps_task_open(self) -> None:
        tree = work_tree.initialize_tree("Find miss tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Find pressure evidence for fulfillment_missed in fulfillment_bridge_entry_fallthrough",
            meta={"expected_tool": "find", "allowed_tools": ["find"], "tool_args": ["fulfillment_missed", "subconscious_live_simulator.py"]},
        )
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["find"], preferred_tool="find")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: "No matches found.",
        )

        self.assertEqual(step["action"], "tool_failed")
        self.assertEqual(step["error"], "No matches found.")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_next_autonomous_step_blocks_when_tree_policy_disallows_tool(self) -> None:
        tree = work_tree.initialize_tree("Governed tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "search student_data")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["queue_status"], require_explicit_allow=True)

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "governance_blocked")
        self.assertEqual(step["recommended_tool"], "web_search")
        self.assertEqual(step["reason"], "tree_policy_blocked")
        self.assertIn("queue_status", step["tree_allowed_tools"])

    def test_format_tree_snapshot_reports_next_step_and_policy(self) -> None:
        tree = work_tree.initialize_tree("Inspect tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "inspect runtime")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["queue_status"], preferred_tool="queue_status")

        text = work_tree.format_tree_snapshot(tree.tree_id)

        self.assertIn("Active work tree: Inspect tree", text)
        self.assertIn("Recommended tool: queue_status", text)
        self.assertIn("Tree policy allows:", text)

    def test_run_autonomous_loop_executes_tools_when_callback_provided(self) -> None:
        tree = work_tree.initialize_tree("Execute loop")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "query one")
        work_tree.add_task_to_branch(root_branch.branch_id, "query two")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")

        history = work_tree.run_autonomous_loop(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: f"ok:{args[0] if args else tool}",
        )

        self.assertEqual([step["action"] for step in history], ["executed", "executed"])
        self.assertTrue(work_tree.is_tree_complete(tree.tree_id))

    def test_visual_tree_preserves_selected_active_branch_without_running_task(self) -> None:
        tree = work_tree.initialize_tree("Visual active branch")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(tree.tree_id, "Inspect queue", "planned", root_branch.branch_id)
        work_tree.add_task_to_branch(child_branch.branch_id, "inspect queue")
        work_tree.set_branch_tools(child_branch.branch_id, allowed_tools=["queue_status"], preferred_tool="queue_status")

        selected = work_tree.next_open_branch(tree.tree_id)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.branch_id, child_branch.branch_id)

        payload = work_tree.get_visual_tree_data(tree.tree_id)
        self.assertIsNotNone(payload)
        nodes = {node["id"]: node for node in payload["nodes"]}
        self.assertEqual(nodes[child_branch.branch_id]["status"], "active")

    def test_visual_tree_honors_explicit_task_tool_before_text_guess(self) -> None:
        tree = work_tree.initialize_tree("Visual task tool")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            "Review subconscious generated pressure",
            "planned",
            root_branch.branch_id,
        )
        work_tree.add_task_to_branch(
            child_branch.branch_id,
            "Queue status after generated pressure report",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        work_tree.set_branch_tools(child_branch.branch_id, allowed_tools=["read"], preferred_tool="read")

        visual = work_tree.get_visual_tree_data(tree.tree_id)
        self.assertIsNotNone(visual)
        visual_nodes = {node["id"]: node for node in visual["nodes"]}
        self.assertEqual(visual_nodes[child_branch.branch_id]["preferred_tool"], "read")

        inspected = work_tree.inspect_tree(tree.tree_id)
        self.assertIsNotNone(inspected)
        ready = {branch["branch_id"]: branch for branch in inspected["ready_branches"]}
        self.assertEqual(ready[child_branch.branch_id]["preferred_tool"], "read")
        self.assertEqual(ready[child_branch.branch_id]["allowed_tools"], ["read"])

    def test_selected_active_branch_persists_across_reload(self) -> None:
        tree = work_tree.initialize_tree("Persist selected active branch")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(tree.tree_id, "Hold operator step", "planned", root_branch.branch_id)
        work_tree.add_task_to_branch(child_branch.branch_id, "hold operator step")
        work_tree.set_branch_tools(child_branch.branch_id, allowed_tools=["patch_rollback"], preferred_tool="patch_rollback")
        selected = work_tree.next_open_branch(tree.tree_id)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.branch_id, child_branch.branch_id)

        work_tree._TREES.clear()
        work_tree._BRANCHES.clear()
        work_tree._TASKS.clear()
        work_tree._SCORES.clear()
        self.assertTrue(work_tree.reload_persisted_state())

        payload = work_tree.get_visual_tree_data(tree.tree_id)
        self.assertIsNotNone(payload)
        nodes = {node["id"]: node for node in payload["nodes"]}
        self.assertEqual(nodes[child_branch.branch_id]["status"], "active")

    def test_visual_tree_does_not_preserve_failed_active_branch(self) -> None:
        tree = work_tree.initialize_tree("Visual failed branch")
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["read"], require_explicit_allow=True)
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(tree.tree_id, "Inspect missing file", "planned", root_branch.branch_id)
        work_tree.add_task_to_branch(child_branch.branch_id, "inspect missing file")
        work_tree.set_branch_tools(child_branch.branch_id, allowed_tools=["read"], preferred_tool="read")

        result = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: "Not a file: C:\\Nova\\inspect missing file",
        )
        self.assertEqual(result["action"], "tool_failed")

        payload = work_tree.get_visual_tree_data(tree.tree_id)
        self.assertIsNotNone(payload)
        nodes = {node["id"]: node for node in payload["nodes"]}
        self.assertEqual(nodes[child_branch.branch_id]["status"], "ready")

    def test_next_autonomous_step_uses_decision_callback_selection(self) -> None:
        tree = work_tree.initialize_tree("Decision callback")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(tree.tree_id, "Child", "planned", root_branch.branch_id)
        work_tree.add_task_to_branch(root_branch.branch_id, "root task")
        work_tree.add_task_to_branch(child_branch.branch_id, "child task")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")
        work_tree.set_branch_tools(child_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")

        step = work_tree.next_autonomous_step(
            tree.tree_id,
            decide_next_step_fn=lambda tree_id, options: {"branch_id": child_branch.branch_id, "recommended_tool": "web_search"},
        )

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["branch_id"], child_branch.branch_id)

    def test_next_autonomous_step_rejects_invalid_decision_branch(self) -> None:
        tree = work_tree.initialize_tree("Invalid decision")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "root task")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")

        step = work_tree.next_autonomous_step(
            tree.tree_id,
            decide_next_step_fn=lambda tree_id, options: {"branch_id": "missing", "recommended_tool": "web_search"},
        )

        self.assertEqual(step["action"], "invalid_decision")
        self.assertEqual(step["reason"], "unknown_branch")

    def test_next_autonomous_step_rejects_decision_task_mismatch(self) -> None:
        tree = work_tree.initialize_tree("Invalid task decision")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "root task")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")

        step = work_tree.next_autonomous_step(
            tree.tree_id,
            decide_next_step_fn=lambda tree_id, options: {
                "branch_id": root_branch.branch_id,
                "task_id": "task_missing",
                "recommended_tool": "web_search",
            },
        )

        self.assertEqual(step["action"], "invalid_decision")
        self.assertEqual(step["reason"], "task_mismatch")
        self.assertEqual(step["branch_id"], root_branch.branch_id)
        self.assertEqual(step["task_id"], "task_missing")
        self.assertEqual(step["available_task_id"], task.task_id)

    def test_sqlite_persistence_reloads_tree_branch_and_task_state(self) -> None:
        tree = work_tree.initialize_tree("Persistent tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(tree.tree_id, "Persisted child", "child", root_branch.branch_id)
        work_tree.add_dependency(child_branch.branch_id, root_branch.branch_id)
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Persisted task",
            meta={
                "target": {
                    "file": "nova_http.py",
                    "function": "process_chat",
                    "block": "routing_supervisor_intent",
                    "start_line": 3200,
                    "end_line": 3350,
                },
                "scope": "single_block_only",
                "verification": {"required": True},
            },
        )
        work_tree.set_branch_tools(root_branch.branch_id, required_tools=["web_search"], preferred_tool="web_search")
        work_tree._TREES.clear()
        work_tree._BRANCHES.clear()
        work_tree._TASKS.clear()
        work_tree._SCORES.clear()
        self.assertTrue(work_tree.reload_persisted_state())

        restored_tree = work_tree.get_tree(tree.tree_id)
        restored_root = work_tree._BRANCHES[root_branch.branch_id]
        restored_child = work_tree._BRANCHES[child_branch.branch_id]
        restored_task = work_tree._TASKS[task.task_id]

        self.assertIsNotNone(restored_tree)
        self.assertEqual(restored_tree.root_branch_id, root_branch.branch_id)
        self.assertEqual(restored_root.required_tools, ["web_search"])
        self.assertEqual(restored_root.preferred_tool, "web_search")
        self.assertEqual(restored_child.depends_on, [root_branch.branch_id])
        self.assertEqual(restored_task.title, "Persisted task")
        self.assertEqual(restored_task.meta["target"]["file"], "nova_http.py")
        self.assertEqual(restored_task.meta["target"]["function"], "process_chat")
        self.assertEqual(restored_task.meta["target"]["block"], "routing_supervisor_intent")
        self.assertEqual(restored_task.meta["target"]["start_line"], 3200)
        self.assertEqual(restored_task.meta["target"]["end_line"], 3350)

    def test_next_autonomous_step_carries_single_block_target_metadata(self) -> None:
        tree = work_tree.initialize_tree("Stabilize one block")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["patch_apply"], require_explicit_allow=True)
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["patch_apply"], preferred_tool="patch_apply")
        work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Stabilize routing_supervisor_intent only",
            meta={
                "target": {
                    "file": "nova_http.py",
                    "function": "process_chat",
                    "block": "routing_supervisor_intent",
                    "start_line": 3200,
                    "end_line": 3350,
                },
                "scope": "single_block_only",
                "verification": {"required": True},
            },
        )

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["recommended_tool"], "patch_apply")
        self.assertEqual(step["task_target"]["file"], "nova_http.py")
        self.assertEqual(step["task_target"]["function"], "process_chat")
        self.assertEqual(step["task_target"]["block"], "routing_supervisor_intent")
        self.assertEqual(step["task_target"]["start_line"], 3200)
        self.assertEqual(step["task_target"]["end_line"], 3350)

    def test_execute_autonomous_step_blocks_scoped_task_without_verification_payload(self) -> None:
        tree = work_tree.initialize_tree("Scoped task verify")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Stabilize routing_supervisor_intent only",
            meta={
                "target": {
                    "file": "nova_http.py",
                    "function": "process_chat",
                    "block": "routing_supervisor_intent",
                    "start_line": 3200,
                    "end_line": 3350,
                },
                "scope": "single_block_only",
                "verification": {"required": True},
            },
        )
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["patch_apply"], require_explicit_allow=True)
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["patch_apply"], preferred_tool="patch_apply")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: "ok",
        )

        self.assertEqual(step["action"], "verification_failed")
        self.assertEqual(step["reason"], "verification_result_required")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_execute_autonomous_step_blocks_scope_expansion_for_scoped_task(self) -> None:
        tree = work_tree.initialize_tree("Scoped task scope")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Stabilize routing_supervisor_intent only",
            meta={
                "target": {
                    "file": "nova_http.py",
                    "function": "process_chat",
                    "block": "routing_supervisor_intent",
                    "start_line": 3200,
                    "end_line": 3350,
                },
                "scope": "single_block_only",
                "verification": {"required": True},
            },
        )
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["patch_apply"], require_explicit_allow=True)
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["patch_apply"], preferred_tool="patch_apply")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"ok": True, "scope_ok": False, "verified": False, "reason": "scope_expanded"},
        )

        self.assertEqual(step["action"], "scope_blocked")
        self.assertEqual(step["reason"], "scope_expanded")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.OPEN)

    def test_execute_autonomous_step_completes_verified_scoped_task(self) -> None:
        tree = work_tree.initialize_tree("Scoped task success")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(
            root_branch.branch_id,
            "Stabilize routing_supervisor_intent only",
            meta={
                "target": {
                    "file": "nova_http.py",
                    "function": "process_chat",
                    "block": "routing_supervisor_intent",
                    "start_line": 3200,
                    "end_line": 3350,
                },
                "scope": "single_block_only",
                "verification": {"required": True},
            },
        )
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["patch_apply"], require_explicit_allow=True)
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["patch_apply"], preferred_tool="patch_apply")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"ok": True, "scope_ok": True, "verified": True, "message": "block stabilized"},
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["task_target"]["file"], "nova_http.py")
        self.assertEqual(step["task_target"]["function"], "process_chat")
        self.assertEqual(step["task_target"]["block"], "routing_supervisor_intent")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_sqlite_sets_schema_version(self) -> None:
        with closing(work_tree._db_connect()) as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])

        self.assertEqual(version, work_tree._DB_SCHEMA_VERSION)

    def test_sqlite_reload_skips_invalid_branch_rows(self) -> None:
        tree = work_tree.initialize_tree("Invalid rows")

        with closing(work_tree._db_connect()) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO work_tree_branches (
                    branch_id, tree_id, parent_branch_id, title, bucket, status, created_at, updated_at,
                    priority, score, depth, depends_on_json, blocked_by_json, children_json, open_stem_count,
                    required_tools_json, allowed_tools_json, preferred_tool, tool_state_json, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "branch_invalid",
                    tree.tree_id,
                    None,
                    "Broken",
                    "broken",
                    "not_a_real_status",
                    "2026-04-09T00:00:00",
                    "2026-04-09T00:00:00",
                    50,
                    50.0,
                    0,
                    "[]",
                    "[]",
                    "[]",
                    0,
                    "[]",
                    "[]",
                    None,
                    "{}",
                    None,
                ),
            )
            connection.commit()

        work_tree._set_db_path(work_tree._DB_PATH)

        self.assertNotIn("branch_invalid", work_tree._BRANCHES)

    def test_list_visual_trees_prefers_trees_with_branch_history(self) -> None:
        rich_tree = work_tree.initialize_tree("Rich tree")
        rich_root = work_tree._BRANCHES[rich_tree.root_branch_id]
        work_tree.add_task_to_branch(rich_root.branch_id, "Inspect queue")

        shell_tree = work_tree.create_tree("Shell tree")
        work_tree._TREES[shell_tree.tree_id] = shell_tree
        work_tree.save_tree(shell_tree)
        work_tree._persist_tree_state(shell_tree.tree_id)

        payloads = work_tree.list_visual_trees(limit=2)

        self.assertGreaterEqual(len(payloads), 2)
        self.assertEqual(payloads[0]["tree_id"], rich_tree.tree_id)
        self.assertGreaterEqual(len(payloads[0]["nodes"]), 1)
        self.assertEqual(payloads[1]["tree_id"], shell_tree.tree_id)
        self.assertEqual(payloads[1]["nodes"], [])

    def test_list_visual_trees_omits_archived_trees(self) -> None:
        visible_tree = work_tree.initialize_tree("Visible tree")
        visible_root = work_tree._BRANCHES[visible_tree.root_branch_id]
        work_tree.add_task_to_branch(visible_root.branch_id, "Inspect queue")

        archived_tree = work_tree.initialize_tree("Archived tree")
        archived_root = work_tree._BRANCHES[archived_tree.root_branch_id]
        work_tree.add_task_to_branch(archived_root.branch_id, "Already done")
        archived_task = work_tree.list_branch_tasks(archived_root.branch_id)[0]
        work_tree.mark_task_complete(archived_task.task_id)
        work_tree.archive_tree(archived_tree.tree_id, reason="stale")

        payloads = work_tree.list_visual_trees(limit=None)
        payload_ids = [payload.get("tree_id") for payload in payloads]

        self.assertIn(visible_tree.tree_id, payload_ids)
        self.assertNotIn(archived_tree.tree_id, payload_ids)
        self.assertEqual(work_tree.get_tree(archived_tree.tree_id).status, TreeStatus.ARCHIVED)


class TestWorkTreeNotesPayload(unittest.TestCase):
    def setUp(self) -> None:
        work_tree._clear_in_memory()
        self._persist_patcher = mock.patch.object(work_tree, "_persist_tree_state", return_value=None)
        self._persist_patcher.start()

    def tearDown(self) -> None:
        self._persist_patcher.stop()
        work_tree._clear_in_memory()

    def test_inspect_tree_includes_branch_notes(self) -> None:
        tree = work_tree.initialize_tree("Inspect notes")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        root_branch.notes = "Review focus: patch lane drift"
        work_tree.add_task_to_branch(root_branch.branch_id, "Inspect queue")

        payload = work_tree.inspect_tree(tree.tree_id)

        self.assertIsNotNone(payload)
        ready_branches = payload.get("ready_branches") or []
        self.assertTrue(ready_branches)
        self.assertEqual(ready_branches[0].get("notes"), "Review focus: patch lane drift")

    def test_get_visual_tree_data_includes_branch_notes(self) -> None:
        tree = work_tree.initialize_tree("Visual notes")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        root_branch.notes = "Signal evidence: source=subconscious"
        work_tree.add_task_to_branch(root_branch.branch_id, "Inspect queue")

        payload = work_tree.get_visual_tree_data(tree.tree_id)

        self.assertIsNotNone(payload)
        nodes = payload.get("nodes") or []
        self.assertTrue(nodes)
        self.assertEqual(nodes[0].get("notes"), "Signal evidence: source=subconscious")


if __name__ == "__main__":
    unittest.main()

