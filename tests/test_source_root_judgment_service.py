from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import work_tree
from services.operator_outbox import OPERATOR_OUTBOX_SERVICE
from services.source_root_judgment import build_source_root_judgment
from services.source_root_judgment import publish_source_root_operator_notice
from services.source_root_judgment import render_source_root_judgment


class SourceRootJudgmentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        work_tree._clear_in_memory()
        self._persist_patcher = mock.patch.object(work_tree, "_persist_tree_state", return_value=None)
        self._persist_patcher.start()
        self._reload_patcher = mock.patch.object(work_tree, "reload_persisted_state", return_value=None)
        self._reload_patcher.start()

    def tearDown(self) -> None:
        self._reload_patcher.stop()
        self._persist_patcher.stop()
        work_tree._clear_in_memory()

    def _branch_with_task(self):
        tree = work_tree.initialize_tree("Signal Intake: Runtime Governance", meta={"kind": "signal_ingestion"})
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Conversation routing evidence is incomplete", "governance")
        branch.source_type = "conversation_routing"
        branch.work_class = "governance_pressure"
        branch.actionability = "safe_now"
        branch.source_payload = {"issue_steps": [{"stage": "intent_router", "outcome": "failed"}]}
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
        task = work_tree.add_task_to_branch(branch.branch_id, "Read routing evidence", meta={"allowed_tools": ["read"]})
        return branch, task

    def test_build_source_root_judgment_uses_work_tree_evidence(self) -> None:
        branch, task = self._branch_with_task()
        evidence_id = work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=task.task_id,
            tool_name="read",
            tool_args=["services/nova_routing_support.py"],
            result="routing evidence",
        )
        work_tree.mark_task_complete(task.task_id)

        judgment = build_source_root_judgment(branch.branch_id, work_tree_module=work_tree)

        self.assertEqual(judgment["verdict"], "evidence_review_needed")
        self.assertEqual(judgment["evidence_count"], 1)
        self.assertEqual(judgment["evidence_tools"], ["read"])
        self.assertFalse(judgment["operator_outbox"])
        self.assertIn("Source Root Judgment", render_source_root_judgment(judgment))
        self.assertTrue(evidence_id)

    def test_build_source_root_judgment_treats_fail_marker_as_failed_evidence(self) -> None:
        branch, task = self._branch_with_task()
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=task.task_id,
            tool_name="web_search",
            tool_args=["nova runtime search dependency probe"],
            result="[FAIL] Local web search backend is unavailable.",
        )
        work_tree.mark_task_complete(task.task_id)

        judgment = build_source_root_judgment(branch.branch_id, work_tree_module=work_tree)

        self.assertEqual(judgment["verdict"], "evidence_failed")
        self.assertEqual(judgment["failed_evidence_count"], 1)
        self.assertFalse(judgment["ok"])
        self.assertTrue(judgment["operator_outbox"])
        self.assertEqual(judgment["operator_reason"], "failed_evidence")

    def test_restart_provenance_gap_requires_operator_attribution(self) -> None:
        branch, task = self._branch_with_task()
        branch.source_type = "runtime_control"
        branch.work_class = "governance_pressure"
        branch.source_payload = {
            "runtime_restart_analytics": {
                "restart_provenance_status": "incomplete",
                "restart_origin_active_gap_count_1h": 1,
            }
        }
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=task.task_id,
            tool_name="read",
            tool_args=["runtime/guard_boot_history.json"],
            result='[{"restart_origin":"unattributed_guard_start","provenance_complete":false}]',
        )
        work_tree.mark_task_complete(task.task_id)

        judgment = build_source_root_judgment(branch.branch_id, work_tree_module=work_tree)

        self.assertEqual(judgment["verdict"], "operator_or_authority_needed")
        self.assertFalse(judgment["ok"])
        self.assertTrue(judgment["operator_outbox"])
        self.assertEqual(judgment["operator_reason"], "restart_provenance_operator_attribution_required")

    def test_blocked_source_root_judgment_publishes_operator_notice(self) -> None:
        branch, task = self._branch_with_task()
        work_tree.mark_task_blocked(task.task_id, "operator_authority_required")
        branch.actionability = "blocked"

        judgment = build_source_root_judgment(branch.branch_id, work_tree_module=work_tree)

        self.assertEqual(judgment["verdict"], "operator_or_authority_needed")
        self.assertTrue(judgment["operator_outbox"])

        with tempfile.TemporaryDirectory() as temp_dir:
            outbox_path = Path(temp_dir) / "operator_outbox.jsonl"
            result = publish_source_root_operator_notice(judgment, outbox_path=outbox_path)
            events = OPERATOR_OUTBOX_SERVICE.read_events(outbox_path, limit=5)

        self.assertTrue(result["published"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source"], "source_root_judgment")
        self.assertEqual((events[0]["payload"]["tree"] or {})["branch_id"], branch.branch_id)


if __name__ == "__main__":
    unittest.main()
