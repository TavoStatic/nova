from __future__ import annotations

import os
import unittest
from pathlib import Path
import uuid

import work_tree
from services.subconscious_review_judgment import (
    build_subconscious_review_judgment,
    is_no_owner_root_repair_judgment,
    render_subconscious_review_judgment,
)


def _validation_tmp_root() -> Path:
    return Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "_test_tmp"


class FakeReviewAuthority:
    def __init__(self, verdict: dict | None = None) -> None:
        self.verdict = verdict or {
            "approved": True,
            "authority_owner": "fulfillment",
            "authority_status": "approved",
            "authority_reason": "confirmed owner route from branch evidence",
        }
        self.signal = {}
        self.gate = {}

    def review_candidate(self, signal, gate, **kwargs):
        self.signal = dict(signal or {})
        self.gate = dict(gate or {})
        return dict(self.verdict)


class TestSubconsciousReviewJudgmentService(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._db_path = base_tmp / f"subconscious_review_judgment_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(self._db_path)

    def tearDown(self) -> None:
        work_tree._clear_in_memory()
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                path = Path(f"{self._db_path}{suffix}")
                if path.exists():
                    path.unlink()
            except Exception:
                pass

    def _subconscious_branch(self):
        tree = work_tree.initialize_tree("Signal Intake: Runtime Governance")
        branch = work_tree._BRANCHES[tree.root_branch_id]
        branch.source_type = "subconscious"
        branch.source_payload = {
            "target_seam": "fulfillment_bridge_entry_fallthrough",
            "signal": "fulfillment_missed",
            "preferred_owner": "fulfillment",
            "route_hint": "fulfillment_applicable",
            "review_contract": "subconscious.review.fulfillment",
            "review_gate": {
                "approved": True,
                "status": "approved_priority_review",
                "reason": "high urgency robustness 0.97 meets threshold",
                "preferred_owner": "fulfillment",
                "route_hint": "fulfillment_applicable",
                "review_contract": "subconscious.review.fulfillment",
            },
        }
        return branch

    def _record_evidence(self, branch, title: str, tool_name: str, args: list[str], result: str) -> None:
        task = work_tree.add_task_to_branch(branch.branch_id, title)
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=task.task_id,
            tool_name=tool_name,
            tool_args=args,
            result=result,
        )
        work_tree.mark_task_complete(task.task_id)

    def test_judgment_confirms_owner_root_repair_after_required_evidence(self) -> None:
        branch = self._subconscious_branch()
        self._record_evidence(
            branch,
            "Find route evidence for fulfillment_bridge_entry_fallthrough without running generated tests",
            "find",
            ["fulfillment_bridge_entry_fallthrough", "subconscious_live_simulator.py"],
            "subconscious_live_simulator.py:42: fulfillment_bridge_entry_fallthrough",
        )
        self._record_evidence(
            branch,
            "Find pressure evidence for fulfillment_missed in fulfillment_bridge_entry_fallthrough",
            "find",
            ["fulfillment_missed", "tests"],
            "tests/test_fulfillment.py:55: fulfillment_missed",
        )
        self._record_evidence(
            branch,
            "Read runtime/subconscious_runs/latest.json subconscious priority report",
            "read",
            ["runtime/subconscious_runs/latest.json"],
            '{"families": [{"family_id": "fulfillment-fallthrough-family"}]}',
        )
        self._record_evidence(
            branch,
            "Queue status after subconscious pressure ingestion",
            "queue_status",
            [],
            "generated queue clear",
        )
        authority = FakeReviewAuthority()

        judgment = build_subconscious_review_judgment(
            branch_id=branch.branch_id,
            work_tree_module=work_tree,
            review_authority_service=authority,
        )

        self.assertTrue(judgment.get("ok"))
        self.assertEqual(judgment.get("verdict"), "owner_root_repair_required")
        self.assertEqual(judgment.get("classification"), "authority_confirmed_owner_root")
        self.assertTrue((judgment.get("evidence") or {}).get("complete"))
        self.assertTrue(authority.gate.get("approved"))
        self.assertEqual((authority.signal.get("payload") or {}).get("target_seam"), "fulfillment_bridge_entry_fallthrough")
        rendered = render_subconscious_review_judgment(judgment)
        self.assertIn("do_not_run_generated_tests_as_progress", rendered)

    def test_judgment_retires_pressure_when_authority_finds_no_owner_root(self) -> None:
        branch = self._subconscious_branch()
        self._record_evidence(
            branch,
            "Find route evidence for fulfillment_bridge_entry_fallthrough without running generated tests",
            "find",
            ["fulfillment_bridge_entry_fallthrough", "subconscious_live_simulator.py"],
            "subconscious_live_simulator.py:42: fulfillment_bridge_entry_fallthrough",
        )
        self._record_evidence(
            branch,
            "Find pressure evidence for fulfillment_missed in fulfillment_bridge_entry_fallthrough",
            "find",
            ["fulfillment_missed", "tests"],
            "tests/test_fulfillment.py:55: fulfillment_missed",
        )
        self._record_evidence(
            branch,
            "Read runtime/subconscious_runs/latest.json subconscious priority report",
            "read",
            ["runtime/subconscious_runs/latest.json"],
            '{"families": [{"family_id": "fulfillment-fallthrough-family"}]}',
        )
        self._record_evidence(
            branch,
            "Queue status after subconscious pressure ingestion",
            "queue_status",
            [],
            "generated queue clear",
        )
        authority = FakeReviewAuthority(
            {
                "approved": False,
                "authority_owner": "fulfillment",
                "authority_status": "rejected",
                "authority_reason": "probe fulfillment_viable=False",
            }
        )

        judgment = build_subconscious_review_judgment(
            branch_id=branch.branch_id,
            work_tree_module=work_tree,
            review_authority_service=authority,
        )

        self.assertEqual(judgment.get("verdict"), "no_owner_root_repair")
        self.assertEqual(judgment.get("classification"), "authority_rejected")
        self.assertTrue(is_no_owner_root_repair_judgment(judgment))
        rendered = render_subconscious_review_judgment(judgment)
        self.assertIn("Retire this candidate", rendered)

    def test_judgment_blocks_when_required_evidence_is_missing(self) -> None:
        branch = self._subconscious_branch()
        self._record_evidence(
            branch,
            "Find route evidence for fulfillment_bridge_entry_fallthrough without running generated tests",
            "find",
            ["fulfillment_bridge_entry_fallthrough", "subconscious_live_simulator.py"],
            "subconscious_live_simulator.py:42: fulfillment_bridge_entry_fallthrough",
        )

        judgment = build_subconscious_review_judgment(
            branch_id=branch.branch_id,
            work_tree_module=work_tree,
            review_authority_service=FakeReviewAuthority(),
        )

        self.assertEqual(judgment.get("classification"), "evidence_incomplete")
        self.assertIn("pressure_evidence", (judgment.get("evidence") or {}).get("missing") or [])
