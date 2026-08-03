from __future__ import annotations

import os
import unittest
import uuid
from pathlib import Path

import work_tree
from services.solution_trail import (
    JUDGMENT_PREMATURE,
    JUDGMENT_PROVEN,
    JUDGMENT_REDUNDANT,
    action_suppressed_by_trail,
    align_branch_open_stem_to_trail,
    classify_attempt,
    preferred_tool_from_progress,
    record_attempt_on_branch,
)
from services.work_tree_signal_ingestion import advance_branch_sequence_after_task
from services.work_tree_task_progress import measure_solution_progress


def _validation_tmp_root() -> Path:
    return Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "_test_tmp"


class SolutionTrailTests(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._db_path = base_tmp / f"solution_trail_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(self._db_path)

    def tearDown(self) -> None:
        work_tree._clear_in_memory()
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

    def _release_branch(self):
        tree = work_tree.create_tree("Solution trail tree")
        work_tree._TREES[tree.tree_id] = tree
        root = work_tree.create_branch(tree.tree_id, "Root", "work")
        work_tree._BRANCHES[root.branch_id] = root
        tree.root_branch_id = root.branch_id
        branch = work_tree.create_branch(
            tree.tree_id,
            "Release package is stale behind live source",
            "work",
            root.branch_id,
        )
        branch.work_class = "release_readiness_gap"
        branch.source_type = "release"
        branch.source_payload = {
            "task_sequence": [
                {
                    "title": "Read release ledger for current package",
                    "allowed_tools": ["read"],
                    "preferred_tool": "read",
                },
                {
                    "title": "Read release validation seed for current package",
                    "allowed_tools": ["read"],
                    "preferred_tool": "read",
                },
                {
                    "title": "Rebuild and verify release package from current source",
                    "allowed_tools": ["release_rebuild_verify"],
                    "preferred_tool": "release_rebuild_verify",
                },
                {
                    "title": "Run release validation profile from current artifact",
                    "allowed_tools": ["release_validation_run"],
                    "preferred_tool": "release_validation_run",
                },
            ],
            "latest_artifact_name": "nova-rc.zip",
            "latest_version": "2026.07.20",
            "latest_verified_at": "2026-07-20T00:22:08",
            "latest_readiness_state": "source-changed-after-build",
            "surfaced_at": "2026-08-01T10:00:00",
        }
        work_tree._BRANCHES[branch.branch_id] = branch
        return branch

    def test_skips_sequence_stem_already_satisfied_by_evidence(self):
        branch = self._release_branch()
        done = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release ledger for current package",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=done.task_id,
            tool_name="read",
            tool_args=["ledger.jsonl"],
            result="ledger package seed artifact",
        )
        work_tree.mark_task_complete(done.task_id)
        stale = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release ledger for current package",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        result = align_branch_open_stem_to_trail(branch.branch_id)
        self.assertTrue(result.get("ok"))
        self.assertGreaterEqual(int(result.get("skipped") or 0), 1)
        open_tasks = [
            t
            for t in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(t.status, "value", t.status)) not in {"complete", "dropped"}
        ]
        self.assertEqual(len(open_tasks), 1)
        # Once early markers count, further read stems are obsolete — jump to rebuild.
        self.assertIn("rebuild", open_tasks[0].title.lower())
        self.assertEqual(str(getattr(stale.status, "value", stale.status)), "dropped")

    def test_does_not_touch_non_sequence_open_stem(self):
        branch = self._release_branch()
        custom = work_tree.add_task_to_branch(
            branch.branch_id,
            "Operator special investigation",
            meta={"expected_tool": "read"},
        )
        result = align_branch_open_stem_to_trail(branch.branch_id)
        self.assertEqual(result.get("reason"), "open_stem_not_in_sequence")
        self.assertEqual(int(result.get("skipped") or 0), 0)
        self.assertEqual(str(getattr(custom.status, "value", custom.status)), "open")

    def test_preferred_tool_from_next_marker_uses_ladder(self):
        progress = measure_solution_progress(
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            current_step_title="Rebuild package",
            solution_status="open",
            evidence=[
                {
                    "tool_name": "read",
                    "result_text": "ledger package seed source drift stale",
                    "created_at": "2026-08-01T12:00:00",
                },
                {
                    "tool_name": "read",
                    "result_text": "source changed after build",
                    "created_at": "2026-08-01T12:01:00",
                },
            ],
            context={"release_stale": True},
        )
        tool = preferred_tool_from_progress(
            progress,
            allowed_tools=["read", "release_rebuild_verify"],
            work_class="release_readiness_gap",
            source_type="release",
        )
        self.assertEqual(tool, "release_rebuild_verify")

    def test_skips_obsolete_read_stems_and_opens_rebuild(self):
        """After early markers hold, do not re-open more read — jump to rebuild."""
        branch = self._release_branch()
        ledger = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release ledger for current package",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=ledger.task_id,
            tool_name="read",
            tool_args=["ledger.jsonl"],
            result="ledger package seed source drift stale newest changed",
        )
        work_tree.mark_task_complete(ledger.task_id)
        # Never ran seed, but markers already hold — seed is still an obsolete read stem.
        work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release validation seed for current package",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
        result = align_branch_open_stem_to_trail(branch.branch_id)
        self.assertTrue(result.get("ok"))
        self.assertGreaterEqual(int(result.get("skipped") or 0), 1)
        open_tasks = [
            t
            for t in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(t.status, "value", t.status)) not in {"complete", "dropped"}
        ]
        self.assertEqual(len(open_tasks), 1)
        self.assertIn("rebuild", open_tasks[0].title.lower())
        preferred = str(
            (open_tasks[0].meta or {}).get("expected_tool")
            or (open_tasks[0].meta or {}).get("preferred_tool")
            or ""
        ).lower()
        if not preferred:
            preferred = str(getattr(branch, "preferred_tool", "") or "").lower()
        branch2 = work_tree.get_branch(branch.branch_id)
        preferred = preferred or str(getattr(branch2, "preferred_tool", "") or "").lower()
        self.assertEqual(preferred, "release_rebuild_verify")

    def test_validate_before_rebuild_is_premature_with_contract(self):
        before = measure_solution_progress(
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            solution_status="open",
            evidence=[
                {
                    "tool_name": "read",
                    "result_text": "ledger package seed source stale",
                    "created_at": "2026-08-01T12:00:00",
                }
            ],
            context={"release_stale": True},
        )
        # Validation tool run does not advance markers without rebuild.
        after = measure_solution_progress(
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            solution_status="open",
            evidence=[
                {
                    "tool_name": "read",
                    "result_text": "ledger package seed source stale",
                    "created_at": "2026-08-01T12:00:00",
                },
                {
                    "tool_name": "release_validation_run",
                    "result_text": "ok",
                    "created_at": "2026-08-01T12:05:00",
                },
            ],
            context={"release_stale": True},
        )
        classified = classify_attempt(
            tool_name="release_validation_run",
            task_title="Run release validation profile from current artifact",
            progress_before=before,
            progress_after=after,
            work_class="release_readiness_gap",
            source_type="release",
            branch_payload={
                "latest_artifact_name": "nova-rc.zip",
                "latest_version": "2026.07.20",
            },
        )
        self.assertEqual(classified.get("judgment"), JUDGMENT_PREMATURE)
        self.assertTrue(classified.get("retry_when"))
        self.assertTrue(
            any(
                c.get("marker_id") == "package_rebuilt"
                for c in list(classified.get("retry_when") or [])
                if isinstance(c, dict)
            )
        )
        # Still suppressed until package_rebuilt holds.
        self.assertIsNotNone(
            action_suppressed_by_trail(
                tool_name="release_validation_run",
                task_title="Run release validation profile from current artifact",
                judgments=[{**classified, "tool": "release_validation_run", "task_title": "Run release validation profile from current artifact"}],
                progress=after,
                branch_payload={"latest_artifact_name": "nova-rc.zip", "latest_version": "2026.07.20"},
            )
        )
        # After rebuild marker counts, contract lifts.
        rebuilt = measure_solution_progress(
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            solution_status="open",
            evidence=[
                {
                    "tool_name": "read",
                    "result_text": "ledger package seed source stale",
                    "created_at": "2026-08-01T12:00:00",
                },
                {
                    "tool_name": "read",
                    "result_text": "source drift newest",
                    "created_at": "2026-08-01T12:01:00",
                },
                {
                    "tool_name": "release_rebuild_verify",
                    "result_text": "ok",
                    "created_at": "2026-08-01T12:10:00",
                },
            ],
            context={"release_stale": True},
        )
        self.assertIsNone(
            action_suppressed_by_trail(
                tool_name="release_validation_run",
                task_title="Run release validation profile from current artifact",
                judgments=[{**classified, "tool": "release_validation_run", "task_title": "Run release validation profile from current artifact"}],
                progress=rebuilt,
                branch_payload={"latest_artifact_name": "nova-rc.zip", "latest_version": "2026.07.20"},
            )
        )

    def test_after_rebuild_nova_extends_sequence_into_validation(self):
        """Nova keeps fixing after rebuild — sequence must not die mid-solution."""
        branch = self._release_branch()
        # Simulate markers through rebuild so next is validation_recorded.
        for title, tool, result in (
            (
                "Read release ledger for current package",
                "read",
                "ledger package seed source drift stale",
            ),
            (
                "Rebuild and verify release package from current source",
                "release_rebuild_verify",
                "ok rebuilt package verified",
            ),
        ):
            task = work_tree.add_task_to_branch(
                branch.branch_id,
                title,
                meta={"expected_tool": tool, "allowed_tools": [tool]},
            )
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=tool,
                tool_args=[],
                result=result,
            )
            work_tree.mark_task_complete(task.task_id)
        # Truncated sequence ends at rebuild (legacy wiring).
        branch.source_payload = {
            **dict(branch.source_payload or {}),
            "task_sequence": [
                {
                    "title": "Read release ledger for current package",
                    "allowed_tools": ["read"],
                    "preferred_tool": "read",
                },
                {
                    "title": "Rebuild and verify release package from current source",
                    "allowed_tools": ["release_rebuild_verify"],
                    "preferred_tool": "release_rebuild_verify",
                },
            ],
        }
        work_tree._BRANCHES[branch.branch_id] = branch
        result = advance_branch_sequence_after_task(branch.branch_id)
        self.assertTrue(result.get("ok"), result)
        self.assertIn("validation", str(result.get("task_title") or "").lower())
        open_tasks = [
            t
            for t in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(t.status, "value", t.status)) not in {"complete", "dropped"}
        ]
        self.assertEqual(len(open_tasks), 1)
        self.assertEqual(
            str((open_tasks[0].meta or {}).get("expected_tool") or "").lower(),
            "release_validation_run",
        )

    def test_rebuild_that_advances_is_proven(self):
        before = measure_solution_progress(
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            solution_status="open",
            evidence=[
                {
                    "tool_name": "read",
                    "result_text": "ledger package seed",
                    "created_at": "2026-08-01T12:00:00",
                },
                {
                    "tool_name": "read",
                    "result_text": "source drift stale newest",
                    "created_at": "2026-08-01T12:01:00",
                },
            ],
            context={"release_stale": True},
        )
        after = measure_solution_progress(
            work_class="release_readiness_gap",
            source_type="release",
            branch_title="Release package is stale behind live source",
            solution_status="open",
            evidence=[
                {
                    "tool_name": "read",
                    "result_text": "ledger package seed",
                    "created_at": "2026-08-01T12:00:00",
                },
                {
                    "tool_name": "read",
                    "result_text": "source drift stale newest",
                    "created_at": "2026-08-01T12:01:00",
                },
                {
                    "tool_name": "release_rebuild_verify",
                    "result_text": "ok",
                    "created_at": "2026-08-01T12:10:00",
                },
            ],
            context={"release_stale": True},
        )
        classified = classify_attempt(
            tool_name="release_rebuild_verify",
            progress_before=before,
            progress_after=after,
            work_class="release_readiness_gap",
            source_type="release",
        )
        self.assertEqual(classified.get("judgment"), JUDGMENT_PROVEN)

    def test_record_and_skip_premature_validation_stem(self):
        branch = self._release_branch()
        # Establish early markers only.
        t1 = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release ledger for current package",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=t1.task_id,
            tool_name="read",
            tool_args=["ledger"],
            result="ledger package seed source stale",
        )
        work_tree.mark_task_complete(t1.task_id)
        before = work_tree._branch_progress_payload(branch)
        # Premature validation attempt.
        after = measure_solution_progress(
            work_class="release_readiness_gap",
            source_type="release",
            branch_title=branch.title,
            solution_status="open",
            evidence=work_tree.list_branch_evidence(branch.branch_id, limit=40)
            + [
                {
                    "tool_name": "release_validation_run",
                    "result_text": "ok",
                    "created_at": "2026-08-01T12:20:00",
                }
            ],
            context={"release_stale": True},
        )
        rec = record_attempt_on_branch(
            branch.branch_id,
            tool_name="release_validation_run",
            task_title="Run release validation profile from current artifact",
            progress_before=before,
            progress_after=after,
        )
        self.assertTrue(rec.get("ok"))
        self.assertEqual((rec.get("judgment") or {}).get("judgment"), JUDGMENT_PREMATURE)
        # Open a premature validation stem — trail should skip it.
        work_tree.add_task_to_branch(
            branch.branch_id,
            "Run release validation profile from current artifact",
            meta={
                "expected_tool": "release_validation_run",
                "allowed_tools": ["release_validation_run"],
            },
        )
        result = align_branch_open_stem_to_trail(branch.branch_id)
        self.assertTrue(result.get("ok"))
        self.assertGreaterEqual(int(result.get("skipped") or 0), 1)
        open_tasks = [
            t
            for t in work_tree.list_branch_tasks(branch.branch_id)
            if str(getattr(t.status, "value", t.status)) not in {"complete", "dropped"}
        ]
        # Should not leave validation as the open work while premature.
        for task in open_tasks:
            self.assertNotIn("validation profile", task.title.lower())


class SolutionProgressStampHonestyTests(unittest.TestCase):
    def setUp(self) -> None:
        work_tree._clear_in_memory()

    def tearDown(self) -> None:
        work_tree._clear_in_memory()

    def test_closed_finding_without_effort_is_not_100_percent(self):
        from services.work_tree_task_progress import measure_solution_progress

        progress = measure_solution_progress(
            work_class="candidate_review",
            source_type="subconscious",
            branch_title="Review subconscious priority with supervisor: weather",
            solution_status="retired",
            evidence=[],
        )
        self.assertEqual(int(progress.get("percent")), 0)
        self.assertEqual(str(progress.get("motion") or ""), "done")
        self.assertTrue(progress.get("closed_without_effort"))
        self.assertEqual(int(progress.get("effort_count")), 0)
        self.assertIn("without recorded tool effort", str(progress.get("operator_summary") or ""))
        for marker in list(progress.get("markers") or []):
            self.assertFalse(bool(marker.get("counts")), marker)

    def test_stamp_never_persists_done_while_open_stem_exists(self):
        tree = work_tree.create_tree("Stamp honesty")
        work_tree._TREES[tree.tree_id] = tree
        root = work_tree.create_branch(tree.tree_id, "Root", "work")
        work_tree._BRANCHES[root.branch_id] = root
        tree.root_branch_id = root.branch_id
        branch = work_tree.create_branch(
            tree.tree_id,
            "Release package is verified but validation outcome is missing",
            "work",
            root.branch_id,
        )
        branch.work_class = "release_readiness_gap"
        branch.source_type = "release"
        branch.resolution_state = "resolved"  # dirty satisfaction-like state
        branch.source_payload = {
            "solution_progress": {
                "percent": 100,
                "motion": "done",
                "solution_status": "complete",
                "operator_summary": "100% · done · 4/4 markers counting",
                "effort": [],
                "effort_count": 0,
            },
            "recurring_finding_satisfaction_status": "satisfied",
        }
        work_tree._BRANCHES[branch.branch_id] = branch
        task = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release ledger for current package",
            meta={"expected_tool": "read"},
        )
        # Poison meta with old false complete.
        task.meta = {
            **dict(task.meta or {}),
            "progress": {
                "percent": 100,
                "motion": "done",
                "solution_status": "complete",
                "effort": [],
            },
        }
        live = work_tree._branch_progress_payload(branch)
        self.assertEqual(live.get("solution_status"), "open")
        self.assertNotEqual(str(live.get("motion") or "").lower(), "done")
        stamped = work_tree.stamp_branch_progress(branch.branch_id, persist=False)
        self.assertEqual(stamped.get("solution_status"), "open")
        cached = (branch.source_payload or {}).get("solution_progress") or {}
        self.assertLess(int(cached.get("percent") or 0), 100)
        self.assertNotEqual(str(cached.get("motion") or "").lower(), "done")
        # Compact stamp must carry effort list field (may be empty honestly).
        self.assertIn("effort", cached)
        self.assertIn("markers", cached)
        meta_p = (task.meta or {}).get("progress") or {}
        self.assertLess(int(meta_p.get("percent") or 0), 100)


if __name__ == "__main__":
    unittest.main()
