"""
Authoritative behavior tests — Work Tree ingestion and missing_tool_assignment behavior.

Tests Work Tree runtime behavior at the public API level.
Does NOT inspect source code or depend on internal call patterns.
"""
from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import work_tree
from work_tree_contracts import BranchStatus, TaskStatus, ToolStatus


WORK_TMP_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestWorkTreeIngestion(unittest.TestCase):
    """Tests that trees and branches can be created and queried correctly."""

    def setUp(self) -> None:
        self._tmp = _workspace_case_dir("authoritative_work_tree_ingestion")
        work_tree._set_db_path(self._tmp / "wt_test.sqlite3")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_create_tree_produces_active_tree_with_root_branch(self):
        tree = work_tree.initialize_tree("Test tree")
        self.assertIsNotNone(tree)
        self.assertEqual(tree.status.value, "active")
        self.assertIn(tree.root_branch_id, work_tree._BRANCHES)

    def test_add_branch_creates_child_under_root(self):
        tree = work_tree.initialize_tree("Branch test")
        root = work_tree._BRANCHES[tree.root_branch_id]
        child = work_tree.add_branch_to_tree(tree.tree_id, "Child branch", "child", root.branch_id)
        self.assertIsNotNone(child)
        self.assertEqual(child.parent_branch_id, root.branch_id)
        self.assertIn(child.branch_id, root.children)

    def test_add_task_makes_branch_have_open_tasks(self):
        tree = work_tree.initialize_tree("Task test")
        root = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root.branch_id, "Do something")
        self.assertIsNotNone(task)
        self.assertEqual(task.status, TaskStatus.OPEN)
        self.assertGreater(root.open_stem_count, 0)

    def test_mark_task_complete_finalizes_branch_when_sole_task(self):
        tree = work_tree.initialize_tree("Completion test")
        root = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root.branch_id, "Single task")
        work_tree.mark_task_complete(task.task_id)
        self.assertEqual(task.status, TaskStatus.COMPLETE)
        self.assertEqual(root.status, BranchStatus.COMPLETE)

    def test_tree_persists_and_reloads_correctly(self):
        db_path = self._tmp / "persist_test.sqlite3"
        work_tree._set_db_path(db_path)
        tree = work_tree.initialize_tree("Persist test")
        root = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root.branch_id, "Persist me")

        # Reload state from disk
        work_tree._load_persisted_state()

        reloaded_tree = work_tree._TREES.get(tree.tree_id)
        self.assertIsNotNone(reloaded_tree)
        self.assertEqual(reloaded_tree.title, "Persist test")

        reloaded_branch = work_tree._BRANCHES.get(root.branch_id)
        self.assertIsNotNone(reloaded_branch)
        self.assertGreater(reloaded_branch.open_stem_count, 0)


class TestMissingToolAssignment(unittest.TestCase):
    """Tests deterministic tool handoff for undeclared branches in governed trees."""

    def setUp(self) -> None:
        self._tmp = _workspace_case_dir("authoritative_work_tree_assignment")
        work_tree._set_db_path(self._tmp / "mta_test.sqlite3")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_branch_with_no_tools_gets_deterministic_assignment(self):
        tree = work_tree.initialize_tree("No tools tree")
        root = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root.branch_id, "Do task without tools")

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertTrue(str(step.get("recommended_tool") or "").strip())
        self.assertEqual(root.preferred_tool, step["recommended_tool"])

    def test_deterministic_assignment_is_explicit_on_branch(self):
        tree = work_tree.initialize_tree("Suggestions tree")
        root = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root.branch_id, "research attendance web data")

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        selected = str(step.get("recommended_tool") or "").strip()
        self.assertTrue(selected)
        self.assertEqual(root.allowed_tools, [selected])
        self.assertEqual(root.preferred_tool, selected)

    def test_execute_calls_executor_after_deterministic_assignment(self):
        tree = work_tree.initialize_tree("No exec tree")
        root = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root.branch_id, "task without tools")

        executor_calls = []
        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: executor_calls.append(tool) or "ran",
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["task_id"], task.task_id)
        self.assertEqual(len(executor_calls), 1)

    def test_task_completes_after_deterministic_assignment(self):
        tree = work_tree.initialize_tree("Task open tree")
        root = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root.branch_id, "undeclared task")

        work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: "ok",
        )

        reloaded_task = work_tree._TASKS.get(task.task_id)
        self.assertIsNotNone(reloaded_task)
        self.assertEqual(reloaded_task.status, TaskStatus.COMPLETE)

    def test_branch_with_declared_tool_proceeds_to_execute(self):
        tree = work_tree.initialize_tree("With tools tree")
        root = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root.branch_id, "search for data")
        work_tree.set_branch_tools(
            root.branch_id,
            required_tools=["web_search"],
            allowed_tools=["web_search", "web_fetch"],
            preferred_tool="web_search",
        )

        step = work_tree.next_autonomous_step(tree.tree_id)

        self.assertEqual(step["action"], "execute")
        self.assertEqual(step["recommended_tool"], "web_search")

    def test_blocked_tool_returns_wait_not_missing_assignment(self):
        tree = work_tree.initialize_tree("Blocked tool tree")
        root = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root.branch_id, "search task")
        work_tree.set_branch_tools(root.branch_id, required_tools=["web_search"], preferred_tool="web_search")
        root.tool_state["web_search"] = ToolStatus.BLOCKED

        step = work_tree.next_autonomous_step(tree.tree_id)

        # Blocked tool → wait, not missing_tool_assignment
        self.assertEqual(step["action"], "wait_for_tools")
        self.assertIn("web_search", step.get("missing_tools", []))


if __name__ == "__main__":
    unittest.main()
