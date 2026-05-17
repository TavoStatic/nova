from __future__ import annotations

import os

import shutil
import unittest
import uuid
from pathlib import Path

from services.nova_runtime_context import WORK_DECISION_LEARNING_FILE
from services.work_tree_decision_adapter import WorkTreeDecisionAdapter


WORK_TMP_ROOT = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestWorkTreeDecisionAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = _workspace_case_dir("work_tree_decision_adapter")
        self.state_path = self._tmp / "decision_state.json"
        self.adapter = WorkTreeDecisionAdapter(state_path=self.state_path)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_default_state_path_uses_runtime_context(self) -> None:
        adapter = WorkTreeDecisionAdapter()

        self.assertEqual(adapter._state_path, WORK_DECISION_LEARNING_FILE)

    def test_score_update_success_and_failure(self) -> None:
        key = "work:test|terms:test"
        self.adapter.record_decision(decision_type="continue", work_identity_key=key, branch_id="branch_a")
        self.adapter.record_outcome(work_identity_key=key, decision_type="continue", outcome="success")
        self.adapter.record_decision(decision_type="continue", work_identity_key=key, branch_id="branch_a")
        self.adapter.record_outcome(work_identity_key=key, decision_type="continue", outcome="failure")

        scores = self.adapter.get_scores_for_identity(work_identity_key=key)
        self.assertIsNotNone(scores)
        self.assertEqual(float((scores or {}).get("continue_score") or 0.0), 0.0)

    def test_decision_bias_uses_highest_score(self) -> None:
        key = "work:bias|terms:bias"
        self.adapter.record_decision(decision_type="branch", work_identity_key=key, branch_id="branch_1")
        self.adapter.record_outcome(work_identity_key=key, decision_type="branch", outcome="success")
        self.adapter.record_decision(decision_type="branch", work_identity_key=key, branch_id="branch_2")
        self.adapter.record_outcome(work_identity_key=key, decision_type="branch", outcome="success")

        self.assertEqual(self.adapter.get_bias_for_identity(work_identity_key=key), "branch")

    def test_state_persists_across_instances(self) -> None:
        key = "work:persist|terms:persist"
        self.adapter.record_decision(decision_type="new", work_identity_key=key, branch_id="")
        self.adapter.record_outcome(work_identity_key=key, decision_type="new", outcome="success")

        second = WorkTreeDecisionAdapter(state_path=self.state_path)
        scores = second.get_scores_for_identity(work_identity_key=key)
        self.assertIsNotNone(scores)
        self.assertEqual(float((scores or {}).get("new_tree_score") or 0.0), 1.0)

    def test_stale_blank_decision_closes_success_across_instances(self) -> None:
        key = "work:cross-process|terms:cross|process"
        first = WorkTreeDecisionAdapter(state_path=self.state_path, stale_success_seconds=300)
        first.record_decision(
            decision_type="continue",
            work_identity_key=key,
            branch_id="branch_a",
            timestamp=1_000.0,
        )

        second = WorkTreeDecisionAdapter(state_path=self.state_path, stale_success_seconds=300)
        second.record_decision(
            decision_type="continue",
            work_identity_key=key,
            branch_id="branch_a",
            timestamp=1_301.0,
        )

        rows = second.get_recent_decisions(limit=2, work_identity_key=key)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].get("outcome"), "success")
        self.assertGreater(float(rows[0].get("outcome_timestamp") or 0.0), 0.0)
        self.assertEqual(rows[1].get("outcome"), "")

        scores = second.get_scores_for_identity(work_identity_key=key)
        self.assertIsNotNone(scores)
        self.assertEqual(float((scores or {}).get("continue_score") or 0.0), 1.0)
        self.assertEqual(int((scores or {}).get("decision_count") or 0), 1)

    def test_explicit_flush_closes_stale_pending_successes(self) -> None:
        key = "work:flush|terms:flush"
        self.adapter = WorkTreeDecisionAdapter(state_path=self.state_path, stale_success_seconds=300)
        self.adapter.record_decision(
            decision_type="new",
            work_identity_key=key,
            branch_id="branch_a",
            timestamp=2_000.0,
        )

        self.assertEqual(self.adapter.flush_stale_pending_successes(now_ts=2_299.0), 0)
        self.assertEqual(self.adapter.flush_stale_pending_successes(now_ts=2_300.0), 1)

        scores = self.adapter.get_scores_for_identity(work_identity_key=key)
        self.assertIsNotNone(scores)
        self.assertEqual(float((scores or {}).get("new_tree_score") or 0.0), 1.0)


if __name__ == "__main__":
    unittest.main()
