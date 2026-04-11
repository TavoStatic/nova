from __future__ import annotations

from contextlib import closing
import tempfile
import unittest
from pathlib import Path
import sqlite3

import work_tree
from work_tree_contracts import BranchStatus, ToolStatus, TreeStatus


class TestWorkTree(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        work_tree._set_db_path(Path(self._temp_dir.name) / "work_tree.sqlite3")

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

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

    def test_tree_becomes_complete_after_all_tasks_complete(self) -> None:
        tree = work_tree.initialize_tree("Close tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "Done")

        work_tree.mark_task_complete(task.task_id)

        self.assertTrue(work_tree.is_tree_complete(tree.tree_id))
        self.assertEqual(work_tree.get_tree(tree.tree_id).status, TreeStatus.COMPLETE)

    def test_run_autonomous_loop_completes_simple_tree(self) -> None:
        tree = work_tree.initialize_tree("Loop tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "Step one")
        work_tree.add_task_to_branch(root_branch.branch_id, "Step two")

        history = work_tree.run_autonomous_loop(tree.tree_id)

        self.assertEqual([step["action"] for step in history], ["execute", "execute"])
        self.assertTrue(work_tree.is_tree_complete(tree.tree_id))

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
        task = work_tree.add_task_to_branch(root_branch.branch_id, "search peims")
        work_tree.set_branch_tools(root_branch.branch_id, allowed_tools=["web_search"], preferred_tool="web_search")

        calls = []
        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: calls.append((tool, list(args or []))) or "search results",
        )

        self.assertEqual(step["action"], "executed")
        self.assertEqual(step["tool"], "web_search")
        self.assertEqual(step["tool_result"], "search results")
        self.assertEqual(calls, [("web_search", ["search peims"])])
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.COMPLETE)

    def test_execute_autonomous_step_marks_failed_tool_state(self) -> None:
        tree = work_tree.initialize_tree("Failure tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        task = work_tree.add_task_to_branch(root_branch.branch_id, "search peims")
        work_tree.set_branch_tools(root_branch.branch_id, required_tools=["web_search"], preferred_tool="web_search")

        step = work_tree.execute_autonomous_step(
            tree.tree_id,
            execute_planned_action_fn=lambda tool, args=None: {"ok": False, "error": "tool offline"},
        )

        self.assertEqual(step["action"], "tool_failed")
        self.assertEqual(step["tool"], "web_search")
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.ACTIVE)
        self.assertEqual(root_branch.tool_state["web_search"], ToolStatus.FAILED)

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
        self.assertEqual(work_tree._TASKS[task.task_id].status, work_tree.TaskStatus.ACTIVE)
        self.assertEqual(root_branch.tool_state["read"], ToolStatus.FAILED)

    def test_next_autonomous_step_blocks_when_tree_policy_disallows_tool(self) -> None:
        tree = work_tree.initialize_tree("Governed tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        work_tree.add_task_to_branch(root_branch.branch_id, "search peims")
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

    def test_sqlite_persistence_reloads_tree_branch_and_task_state(self) -> None:
        tree = work_tree.initialize_tree("Persistent tree")
        root_branch = work_tree._BRANCHES[tree.root_branch_id]
        child_branch = work_tree.add_branch_to_tree(tree.tree_id, "Persisted child", "child", root_branch.branch_id)
        work_tree.add_dependency(child_branch.branch_id, root_branch.branch_id)
        task = work_tree.add_task_to_branch(root_branch.branch_id, "Persisted task")
        work_tree.set_branch_tools(root_branch.branch_id, required_tools=["web_search"], preferred_tool="web_search")
        database_path = work_tree._DB_PATH

        work_tree._TREES.clear()
        work_tree._BRANCHES.clear()
        work_tree._TASKS.clear()
        work_tree._SCORES.clear()
        work_tree._set_db_path(database_path)

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

    def test_sqlite_sets_schema_version(self) -> None:
        with closing(sqlite3.connect(work_tree._DB_PATH)) as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])

        self.assertEqual(version, work_tree._DB_SCHEMA_VERSION)

    def test_sqlite_reload_skips_invalid_branch_rows(self) -> None:
        tree = work_tree.initialize_tree("Invalid rows")

        with closing(sqlite3.connect(work_tree._DB_PATH)) as connection:
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


if __name__ == "__main__":
    unittest.main()