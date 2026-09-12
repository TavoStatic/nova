"""Frozen Work Tree mission loop — kernel scores, no Inspect UI required."""
from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path

from tests.inspect_live.nova_work_tree_loop import (
    run_close_when_thinning_changes_target,
    run_empty_read_refusal,
    run_refuse_close_on_unsatisfied_read,
)


def _tmp_root() -> Path:
    base = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "_test_tmp"
    path = base / f"inspect_loop_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestNovaWorkTreeLoopEval(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = _tmp_root()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_thinning_closes_only_when_target_changed(self) -> None:
        result = run_close_when_thinning_changes_target(self._tmp / "thin.sqlite3")
        self.assertEqual(result["raw"].get("action"), "executed")
        self.assertTrue(result["observed"]["executes_real_capability"])
        self.assertTrue(result["observed"]["produces_verifiable_evidence"])
        self.assertTrue(result["observed"]["closes_only_when_target_changed"])
        self.assertTrue(result["justified_loop"], result)

    def test_real_read_without_satisfaction_refuses_close(self) -> None:
        result = run_refuse_close_on_unsatisfied_read(
            self._tmp / "read.sqlite3",
            self._tmp / "marker.txt",
        )
        self.assertEqual(result["raw"].get("action"), "executed")
        self.assertTrue(result["observed"]["executes_real_capability"])
        self.assertTrue(result["observed"]["produces_verifiable_evidence"])
        self.assertTrue(result["observed"]["refuses_when_link_missing"])
        self.assertNotEqual(result["raw"].get("resolution"), "resolved")
        self.assertTrue(result["justified_loop"], result)

    def test_empty_read_cover_is_category_error_not_a_closed_finding(self) -> None:
        result = run_empty_read_refusal(self._tmp / "empty.sqlite3")
        self.assertTrue(result["observed"]["refuses_when_link_missing"])
        self.assertTrue(result["observed"]["closes_only_when_target_changed"])
        self.assertNotEqual(result["raw"].get("resolution"), "resolved")
        # Gloves: mill still files this as a failed read job.
        self.assertFalse(result["observed"]["admits_correctly"])
        self.assertFalse(result["justified_loop"])
