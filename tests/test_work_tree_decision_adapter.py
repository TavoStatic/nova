from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from services.work_tree_decision_adapter import WorkTreeDecisionAdapter


WORK_TMP_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "pytest_temp"


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


if __name__ == "__main__":
    unittest.main()
