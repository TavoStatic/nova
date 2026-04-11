from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import work_tree
from services.work_tree_seeding import WORK_TREE_SEEDING_SERVICE, WorkTreeSeedingService


class TestWorkTreeSeedingService(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        work_tree._set_db_path(Path(self._temp_dir.name) / "work_tree.sqlite3")

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_create_seeded_tree_builds_child_branches_with_tools(self) -> None:
        tree_id = WORK_TREE_SEEDING_SERVICE.create_seeded_tree(
            work_tree_module=work_tree,
            title_seed="check runtime pulse then verify Ollama system status",
            source="operator",
            user_id="operator",
        )

        tree = work_tree.get_tree(tree_id)
        self.assertIsNotNone(tree)
        root = work_tree._BRANCHES[(tree or work_tree.get_tree(tree_id)).root_branch_id]
        self.assertGreaterEqual(len(root.children), 2)

        for child_id in root.children:
            child = work_tree._BRANCHES[child_id]
            child_tasks = [task for task in work_tree._TASKS.values() if task.branch_id == child.branch_id]
            self.assertGreaterEqual(len(child_tasks), 1)
            self.assertTrue(str(child.preferred_tool or "").strip())
            self.assertGreaterEqual(len(child.allowed_tools), 1)

    def test_seeded_tree_executes_from_child_branch(self) -> None:
        tree_id = WORK_TREE_SEEDING_SERVICE.create_seeded_tree(
            work_tree_module=work_tree,
            title_seed="runtime health check",
            source="chat",
            user_id="",
        )

        tree = work_tree.get_tree(tree_id)
        self.assertIsNotNone(tree)
        root = work_tree._BRANCHES[(tree or work_tree.get_tree(tree_id)).root_branch_id]
        root_tasks = [task for task in work_tree._TASKS.values() if task.branch_id == root.branch_id]
        self.assertEqual(root_tasks, [])

        step = work_tree.next_autonomous_step(tree_id)
        self.assertIsNotNone(step)
        self.assertEqual((step or {}).get("action"), "execute")
        self.assertIn((step or {}).get("branch_id"), root.children)

    # ------------------------------------------------------------------
    # LLM decomposer tests
    # ------------------------------------------------------------------

    def test_llm_decompose_success_uses_llm_steps(self) -> None:
        """When Ollama returns valid JSON with system tools, branches are built from LLM output."""
        llm_steps = [
            {"title": "check runtime pulse", "tool": "pulse"},
            {"title": "verify queue backlog status", "tool": "queue_status"},
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": json.dumps(llm_steps)}}
        mock_response.raise_for_status = lambda: None

        svc = WorkTreeSeedingService()
        import services.work_tree_seeding as _mod

        with patch.object(_mod, "_requests") as mock_req:
            mock_req.post.return_value = mock_response
            tree_id = svc.create_seeded_tree(
                work_tree_module=work_tree,
                title_seed="check runtime pulse then verify queue backlog",
                source="operator",
                user_id="test",
            )

        tree = work_tree.get_tree(tree_id)
        self.assertIsNotNone(tree)
        root = work_tree._BRANCHES[tree.root_branch_id]
        # Exactly 2 children from LLM output
        self.assertEqual(len(root.children), 2)
        title_fragments = [work_tree._BRANCHES[c].title for c in root.children]
        self.assertTrue(any("pulse" in t.lower() for t in title_fragments))

    def test_llm_decompose_fallback_on_failure(self) -> None:
        """When Ollama is unreachable, rule-based splitter is used instead."""
        svc = WorkTreeSeedingService()
        import services.work_tree_seeding as _mod

        with patch.object(_mod, "_requests") as mock_req:
            mock_req.post.side_effect = ConnectionError("Ollama offline")
            tree_id = svc.create_seeded_tree(
                work_tree_module=work_tree,
                title_seed="check runtime health then verify system queue status",
                source="chat",
                user_id="",
            )

        tree = work_tree.get_tree(tree_id)
        self.assertIsNotNone(tree)
        root = work_tree._BRANCHES[tree.root_branch_id]
        # Rule-based splitter splits on "then" → 2 branches
        self.assertGreaterEqual(len(root.children), 2)

    def test_llm_decompose_non_system_tool_falls_back_to_inferred(self) -> None:
        """LLM returning a non-system tool (e.g. web_search) is silently replaced by inferred tool."""
        llm_steps = [
            {"title": "check runtime pulse", "tool": "web_search"},  # invalid for system tree
            {"title": "verify system health", "tool": "web_fetch"},   # invalid for system tree
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": json.dumps(llm_steps)}}
        mock_response.raise_for_status = lambda: None

        svc = WorkTreeSeedingService()
        import services.work_tree_seeding as _mod

        with patch.object(_mod, "_requests") as mock_req:
            mock_req.post.return_value = mock_response
            tree_id = svc.create_seeded_tree(
                work_tree_module=work_tree,
                title_seed="check runtime pulse then verify system health",
                source="operator",
                user_id="test",
            )

        tree = work_tree.get_tree(tree_id)
        self.assertIsNotNone(tree)
        root = work_tree._BRANCHES[tree.root_branch_id]
        for child_id in root.children:
            child = work_tree._BRANCHES[child_id]
            # preferred_tool must be a system tool, never web_search or web_fetch
            self.assertNotIn(child.preferred_tool, ("web_search", "web_fetch", "heartbeat"))

    def test_seeded_tree_tagged_as_system_kind(self) -> None:
        """Trees created by the seeding service must carry kind='system' in their meta."""
        tree_id = WORK_TREE_SEEDING_SERVICE.create_seeded_tree(
            work_tree_module=work_tree,
            title_seed="verify runtime heartbeat",
            source="health",
            user_id="",
        )
        tree = work_tree.get_tree(tree_id)
        self.assertIsNotNone(tree)
        self.assertIsInstance(tree.meta, dict)
        self.assertEqual(tree.meta.get("kind"), "system")

    def test_visual_payload_includes_kind_and_source(self) -> None:
        """get_visual_tree_data exposes kind and source from meta."""
        tree_id = WORK_TREE_SEEDING_SERVICE.create_seeded_tree(
            work_tree_module=work_tree,
            title_seed="check system health",
            source="maintenance",
            user_id="",
        )
        data = work_tree.get_visual_tree_data(tree_id)
        self.assertIsNotNone(data)
        self.assertEqual(data["kind"], "system")
        self.assertEqual(data["source"], "maintenance")


if __name__ == "__main__":
    unittest.main()
