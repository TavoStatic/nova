from __future__ import annotations

import json
import os
import unittest
import uuid
from pathlib import Path

import work_tree
from services.solution_trail import (
    JUDGMENT_PREMATURE,
    JUDGMENT_PROVEN,
    JUDGMENT_REDUNDANT,
    JUDGMENT_REFUSED,
    PRESSURE_EMPTY_CLAIM,
    PRESSURE_INHERITED,
    _prune_expired_judgments,
    action_suppressed_by_trail,
    align_branch_open_stem_to_trail,
    branch_has_active_refuse,
    classify_attempt,
    derive_branch_memory_kind,
    mill_judgment_signal,
    trail_world_holds,
    preferred_tool_from_progress,
    record_attempt_on_branch,
    record_refuse_on_branch,
    record_world_hold_on_branch,
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

    def test_release_sequence_keeps_promotion_step_after_validation_marker_advances(self):
        branch = self._release_branch()
        branch.source_payload = {
            **dict(branch.source_payload or {}),
            "task_sequence": [
                {
                    "title": "Run release validation profile from current artifact",
                    "allowed_tools": ["release_validation_run"],
                    "preferred_tool": "release_validation_run",
                },
                {
                    "title": "Run release promotion judgment from validation evidence",
                    "allowed_tools": ["release_promotion_judgment"],
                    "preferred_tool": "release_promotion_judgment",
                },
                {
                    "title": "Record completed validation outcome in release ledger",
                    "allowed_tools": ["release_record_validation_outcome"],
                    "preferred_tool": "release_record_validation_outcome",
                },
            ],
        }
        work_tree._BRANCHES[branch.branch_id] = branch

        task = work_tree.add_task_to_branch(
            branch.branch_id,
            "Run release validation profile from current artifact",
            meta={"expected_tool": "release_validation_run", "allowed_tools": ["release_validation_run"]},
        )
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=task.task_id,
            tool_name="release_validation_run",
            tool_args=[],
            result="validation ok",
        )
        work_tree.mark_task_complete(task.task_id)
        work_tree.stamp_branch_progress(branch.branch_id, persist=False)

        result = advance_branch_sequence_after_task(branch.branch_id)
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("task_title"), "Run release promotion judgment from validation evidence")

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

    def test_refuse_without_invoke_changes_pickup_until_source_key_is_active(self) -> None:
        tree = work_tree.initialize_tree("Signal Intake", meta={"kind": "signal_ingestion", "last_active_source_keys": []})
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Declared capability gap", "work", tree.root_branch_id)
        branch.source_key = "declared_capability_absent:capability_manifest:gap"
        branch.work_class = "capability_gap"
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
        work_tree.add_task_to_branch(
            branch.branch_id,
            "Read capabilities roadmap manifest",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        before = work_tree.list_autonomous_options(tree.tree_id)
        self.assertTrue(any(str(item.get("branch_id")) == branch.branch_id for item in before))

        rec = record_refuse_on_branch(
            branch.branch_id,
            reason="not_in_active_ingest",
            retry_when=[{"type": "source_key_in_active_set", "value": branch.source_key}],
            do_not_retry_while=[{"type": "no_open_stem"}],
            tool_name="read",
        )
        self.assertTrue(rec.get("ok"))
        self.assertFalse(rec.get("already"))
        self.assertEqual((rec.get("judgment") or {}).get("judgment"), JUDGMENT_REFUSED)
        pressure = ((rec.get("judgment") or {}).get("pressure") or {})
        self.assertEqual(pressure.get("event"), PRESSURE_EMPTY_CLAIM)
        self.assertEqual(pressure.get("note"), PRESSURE_EMPTY_CLAIM)
        self.assertFalse(pressure.get("invoke"))
        self.assertNotIn("evidence_count", pressure)

        after = work_tree.list_autonomous_options(tree.tree_id)
        self.assertFalse(any(str(item.get("branch_id")) == branch.branch_id for item in after))
        live = work_tree.get_branch(branch.branch_id)
        self.assertIsNotNone(live)
        self.assertNotEqual(str(live.resolution_state or "").strip().lower(), "resolved")
        self.assertTrue(
            any(t.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED} for t in work_tree.list_branch_tasks(branch.branch_id))
        )

        again = record_refuse_on_branch(
            branch.branch_id,
            reason="not_in_active_ingest",
            retry_when=[{"type": "source_key_in_active_set", "value": branch.source_key}],
        )
        self.assertTrue(again.get("already"))

        tree.meta = dict(tree.meta or {})
        tree.meta["last_active_source_keys"] = [branch.source_key]
        work_tree.save_tree(tree)
        self.assertIsNone(
            branch_has_active_refuse(
                work_tree.get_branch(branch.branch_id),
                has_open_stem=True,
                active_source_keys={branch.source_key},
            )
        )
        released = work_tree.list_autonomous_options(tree.tree_id)
        self.assertTrue(any(str(item.get("branch_id")) == branch.branch_id for item in released))

    def test_refuse_inherits_pressure_from_prior_attempt(self) -> None:
        branch = self._release_branch()
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
        rec_attempt = record_attempt_on_branch(
            branch.branch_id,
            tool_name="read",
            task_title="Read release ledger for current package",
            progress_before={"markers": []},
            progress_after={"markers": []},
        )
        prior_id = str((rec_attempt.get("judgment") or {}).get("attempt_id") or "")
        self.assertTrue(prior_id)
        refused = record_refuse_on_branch(
            branch.branch_id,
            reason="no_stem_sequence_exhausted",
            retry_when=[{"type": "has_open_stem"}],
            do_not_retry_while=[{"type": "no_open_stem"}],
            tool_name="read",
        )
        pressure = ((refused.get("judgment") or {}).get("pressure") or {})
        self.assertEqual(pressure.get("event"), PRESSURE_INHERITED)
        self.assertEqual(pressure.get("inherited_from"), prior_id)
        self.assertFalse(pressure.get("invoke"))
        self.assertNotIn("evidence_count", pressure)
        self.assertNotEqual(pressure.get("note"), PRESSURE_EMPTY_CLAIM)
        self.assertIsNotNone(
            branch_has_active_refuse(work_tree.get_branch(branch.branch_id), has_open_stem=False)
        )
        self.assertIsNone(
            branch_has_active_refuse(work_tree.get_branch(branch.branch_id), has_open_stem=True)
        )

    def test_record_refuse_carries_causal_facts_through_persistence_and_contract(self) -> None:
        tree = work_tree.initialize_tree("Causal refusal tree")
        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            "Worker timeout from unset max-lane-seconds",
            "work",
            tree.root_branch_id,
        )
        branch.work_class = "regression_failure"
        branch.source_type = "test_ecosystem"
        branch.source_key = "regression_failure:test_ecosystem:regression_failure:daily_regression"
        branch.resolution_state = "open"
        condition_bugged = "regression_lane_worker/max_lane_seconds/env_unset/v1"
        condition_fixed = "regression_lane_worker/max_lane_seconds/default_14400/v1"
        branch.source_payload = {
            "source_key": branch.source_key,
            "observation_input_ref": condition_bugged,
        }

        causal = {
            "causal_condition": "NOVA_REGRESSION_MAX_LANE_SECONDS unset",
            "causal_observed_failure": "worker recorded TIMED_OUT after ~1.5s",
            "causal_verified_cause": "unset env resolved to max_lane_seconds() == 1",
            "causal_change_made": "default parsing corrected",
            "causal_observed_result": "default resolves to 14400s; worker proceeds normally",
            "causal_scope": "regression_lane_worker / lane execution",
        }

        rec = record_refuse_on_branch(
            branch.branch_id,
            reason="worker_timed_out_1.5s_env_unset",
            retry_when=[{"type": "input_ref_changed", "from": condition_bugged}],
            do_not_retry_while=[{"type": "same_input_ref", "value": condition_bugged}],
            tool_name="run",
            task_title="launch regression unit lane via worker",
            causal=causal,
        )
        self.assertTrue(rec.get("ok"))
        self.assertFalse(rec.get("already"))
        self.assertEqual((rec.get("judgment") or {}).get("judgment"), JUDGMENT_REFUSED)
        for key, value in causal.items():
            self.assertEqual((rec.get("judgment") or {}).get(key), value)

        # True SQLite round-trip on the public seam.
        work_tree._BRANCHES.clear()
        work_tree._TASKS.clear()
        work_tree._SCORES.clear()
        self.assertTrue(work_tree.reload_persisted_state())
        live = work_tree.get_branch(branch.branch_id)
        self.assertIsNotNone(live)
        payload = dict(live.source_payload or {})
        rows = [dict(r) for r in payload.get("attempt_judgments") or [] if isinstance(r, dict)]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.get("judgment"), JUDGMENT_REFUSED)
        for key, value in causal.items():
            self.assertEqual(row.get(key), value)

        # Same causal condition -> identical failed attempt suppressed.
        same_ctx = dict(payload)
        same_ctx["observation_input_ref"] = condition_bugged
        self.assertIsNotNone(
            action_suppressed_by_trail(
                tool_name="run",
                task_title="launch regression unit lane via worker",
                judgments=[row],
                branch_payload=same_ctx,
                source_key=branch.source_key,
            )
        )

        # Changed causal condition -> refusal expires, attempt eligible again.
        changed_ctx = dict(payload)
        changed_ctx["observation_input_ref"] = condition_fixed
        self.assertIsNone(
            action_suppressed_by_trail(
                tool_name="run",
                task_title="launch regression unit lane via worker",
                judgments=[row],
                branch_payload=changed_ctx,
                source_key=branch.source_key,
            )
        )

        # Expired judgment pruned when the condition changes.
        self.assertEqual(
            _prune_expired_judgments([row], branch_payload=changed_ctx, progress={}),
            [],
        )

    def test_teach_unclaimable_refusals_writes_without_minting(self) -> None:
        from services.work_tree_signal_ingestion import WorkTreeSignalIngestionService

        tree = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Declared capability gap", "work", tree.root_branch_id)
        branch.source_key = "declared_capability_absent:capability_manifest:gap"
        branch.source_type = "capability_manifest"
        branch.work_class = "capability_gap"
        branch.resolution_state = "open"
        svc = WorkTreeSignalIngestionService()
        results = svc.teach_unclaimable_refusals(active_source_keys=set())
        self.assertTrue(any(item.get("action") == "refused" and item.get("branch_id") == branch.branch_id for item in results))
        self.assertEqual(work_tree.list_branch_tasks(branch.branch_id), [])
        live = work_tree.get_branch(branch.branch_id)
        self.assertEqual(str(live.resolution_state or ""), "open")
        self.assertIsNotNone(branch_has_active_refuse(live, has_open_stem=False, active_source_keys=set()))
        self.assertIsNone(branch_has_active_refuse(live, has_open_stem=False, active_source_keys={branch.source_key}))

    def test_empty_claim_pressure_ignores_evidence_count(self) -> None:
        tree = work_tree.initialize_tree("Empty claim pressure")
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Pre-meta leftover", "work", tree.root_branch_id)
        branch.evidence_count = 12
        rec = record_refuse_on_branch(
            branch.branch_id,
            reason="not_in_active_ingest",
            retry_when=[{"type": "source_key_in_active_set", "value": "k"}],
        )
        pressure = ((rec.get("judgment") or {}).get("pressure") or {})
        self.assertEqual(pressure.get("event"), PRESSURE_EMPTY_CLAIM)
        self.assertNotIn("evidence_count", pressure)
        self.assertEqual(int(work_tree.get_branch(branch.branch_id).evidence_count or 0), 12)

    def test_derive_kind_shared_by_pickup_and_visual(self) -> None:
        tree = work_tree.initialize_tree(
            "Shared kind",
            meta={"kind": "signal_ingestion", "last_active_source_keys": []},
        )
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Declared capability gap", "work", tree.root_branch_id)
        branch.source_key = "declared_capability_absent:capability_manifest:gap"
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
        work_tree.add_task_to_branch(
            branch.branch_id,
            "Read capabilities roadmap manifest",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        record_refuse_on_branch(
            branch.branch_id,
            reason="not_in_active_ingest",
            retry_when=[{"type": "source_key_in_active_set", "value": branch.source_key}],
        )
        derived = derive_branch_memory_kind(
            work_tree.get_branch(branch.branch_id),
            has_open_stem=True,
            active_source_keys=set(),
        )
        self.assertEqual(derived.get("kind"), JUDGMENT_REFUSED)
        self.assertTrue(derived.get("controlling"))
        visual = work_tree.get_visual_tree_data(tree.tree_id)
        node = next(item for item in (visual.get("nodes") or []) if item.get("id") == branch.branch_id)
        self.assertEqual(node.get("branch_memory_kind"), derived)
        inspected = work_tree.inspect_tree(tree.tree_id)
        ready = {row.get("branch_id"): row for row in list(inspected.get("ready_branches") or [])}
        if branch.branch_id in ready:
            self.assertEqual((ready[branch.branch_id].get("branch_memory_kind") or {}).get("kind"), JUDGMENT_REFUSED)
        self.assertFalse(any(str(item.get("branch_id")) == branch.branch_id for item in work_tree.list_autonomous_options(tree.tree_id)))

    def test_same_world_refuse_changes_only_that_branch_pickup(self) -> None:
        tree = work_tree.initialize_tree(
            "Same-world pickup",
            meta={"kind": "signal_ingestion", "last_active_source_keys": []},
        )
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["read"], require_explicit_allow=True)
        refused = work_tree.add_branch_to_tree(tree.tree_id, "Unclaimable leftover", "work", tree.root_branch_id)
        kept = work_tree.add_branch_to_tree(tree.tree_id, "Claimable stem", "work", tree.root_branch_id)
        for branch, key in ((refused, "leftover:gap"), (kept, "live:gap")):
            branch.source_key = key
            work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
            work_tree.add_task_to_branch(
                branch.branch_id,
                "Read current source",
                meta={"expected_tool": "read", "allowed_tools": ["read"]},
            )
        before_ids = {str(item.get("branch_id")) for item in work_tree.list_autonomous_options(tree.tree_id)}
        self.assertIn(refused.branch_id, before_ids)
        self.assertIn(kept.branch_id, before_ids)

        rec = record_refuse_on_branch(
            refused.branch_id,
            reason="not_in_active_ingest",
            retry_when=[{"type": "source_key_in_active_set", "value": refused.source_key}],
        )
        self.assertTrue(rec.get("ok"))
        after_ids = {str(item.get("branch_id")) for item in work_tree.list_autonomous_options(tree.tree_id)}
        self.assertNotIn(refused.branch_id, after_ids)
        self.assertIn(kept.branch_id, after_ids)

        visual = work_tree.get_visual_tree_data(tree.tree_id)
        node_ids = {item.get("id") for item in (visual.get("nodes") or [])}
        self.assertIn(refused.branch_id, node_ids)
        self.assertIn(kept.branch_id, node_ids)
        live = work_tree.get_branch(refused.branch_id)
        self.assertNotEqual(str(live.resolution_state or "").strip().lower(), "resolved")
        self.assertNotEqual(str(getattr(live.status, "value", live.status) or "").lower(), "archived")

        tree.meta = dict(tree.meta or {})
        tree.meta["last_active_source_keys"] = [refused.source_key]
        work_tree.save_tree(tree)
        restored_ids = {str(item.get("branch_id")) for item in work_tree.list_autonomous_options(tree.tree_id)}
        self.assertIn(refused.branch_id, restored_ids)
        self.assertIn(kept.branch_id, restored_ids)
        released = derive_branch_memory_kind(
            work_tree.get_branch(refused.branch_id),
            has_open_stem=True,
            active_source_keys={refused.source_key},
        )
        self.assertEqual(released.get("kind"), JUDGMENT_REFUSED)
        self.assertFalse(released.get("controlling"))

    def test_mill_judgment_signal_names_no_model(self) -> None:
        tree = work_tree.initialize_tree(
            "Mill signal",
            meta={"kind": "signal_ingestion", "last_active_source_keys": []},
        )
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Uninstalled leftover", "work", tree.root_branch_id)
        branch.source_key = "declared_capability_absent:edfi"
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["read"], preferred_tool="read")
        work_tree.add_task_to_branch(
            branch.branch_id,
            "Read leftover",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        record_refuse_on_branch(
            branch.branch_id,
            reason="not_in_active_ingest",
            retry_when=[{"type": "source_key_in_active_set", "value": branch.source_key}],
        )
        derived = derive_branch_memory_kind(
            work_tree.get_branch(branch.branch_id),
            has_open_stem=True,
            active_source_keys=set(),
        )
        signal = mill_judgment_signal(derived)
        self.assertEqual(signal.get("class"), JUDGMENT_REFUSED)
        self.assertTrue(signal.get("controlling"))
        self.assertNotIn("model", signal)
        blob = json.dumps(signal)
        self.assertNotIn("qwen", blob.lower())
        self.assertNotIn("llama", blob.lower())
        stuffed = mill_judgment_signal({**derived, "model": "qwen2.5:14b", "chat": "qwen3.5:9b"})
        self.assertNotIn("model", stuffed)
        self.assertNotIn("chat", stuffed)
        self.assertEqual(stuffed.get("class"), JUDGMENT_REFUSED)

    def test_paid_trail_holds_world_and_blocks_sequence_remint(self) -> None:
        from services.solution_trail import record_attempt_on_branch
        from services.work_tree_signal_ingestion import advance_branch_sequence_after_task

        tree = work_tree.initialize_tree("Compact paid trail")
        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            "Validation profile has source-observed tests outside compact lanes",
            "work",
            tree.root_branch_id,
        )
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["source_root_judgment"], preferred_tool="source_root_judgment")
        first = work_tree.add_task_to_branch(
            branch.branch_id,
            "Synthesize source-root judgment from collected evidence",
            meta={"expected_tool": "source_root_judgment", "allowed_tools": ["source_root_judgment"]},
        )
        branch.source_payload = {
            "task_sequence": [
                {
                    "title": "Synthesize source-root judgment from collected evidence",
                    "allowed_tools": ["source_root_judgment"],
                    "preferred_tool": "source_root_judgment",
                },
                {
                    "title": "Synthesize source-root judgment from collected evidence",
                    "allowed_tools": ["source_root_judgment"],
                    "preferred_tool": "source_root_judgment",
                },
            ]
        }
        work_tree._TASKS[first.task_id].status = work_tree.TaskStatus.ATTEMPTED
        record_attempt_on_branch(
            branch.branch_id,
            tool_name="source_root_judgment",
            task_title=first.title,
            progress_before={"markers": []},
            progress_after={"markers": []},
        )
        held = trail_world_holds(work_tree.get_branch(branch.branch_id), has_open_stem=True)
        self.assertIsNotNone(held)
        self.assertEqual((held or {}).get("class"), JUDGMENT_REDUNDANT)
        result = advance_branch_sequence_after_task(branch.branch_id)
        self.assertEqual(result.get("reason"), "trail_world_holds")
        titles = [
            item.title
            for item in work_tree.list_branch_tasks(branch.branch_id)
            if item.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(titles.count("Synthesize source-root judgment from collected evidence"), 1)

    def test_sip_skip_world_hold_blocks_sequence_remint(self) -> None:
        from services.work_tree_signal_ingestion import advance_branch_sequence_after_task

        tree = work_tree.initialize_tree("Sip world hold")
        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            "Validation profile has source-observed tests outside compact lanes",
            "work",
            tree.root_branch_id,
        )
        first = work_tree.add_task_to_branch(
            branch.branch_id,
            "Synthesize source-root judgment from collected evidence",
            meta={"expected_tool": "source_root_judgment", "allowed_tools": ["source_root_judgment"]},
        )
        branch.source_payload = {
            "task_sequence": [
                {
                    "title": "Synthesize source-root judgment from collected evidence",
                    "allowed_tools": ["source_root_judgment"],
                    "preferred_tool": "source_root_judgment",
                },
                {
                    "title": "Synthesize source-root judgment from collected evidence",
                    "allowed_tools": ["source_root_judgment"],
                    "preferred_tool": "source_root_judgment",
                },
            ]
        }
        record_world_hold_on_branch(
            branch.branch_id,
            tool_name="source_root_judgment",
            task_title=first.title,
            reason="skip_until_world_changes",
            input_ref="source_root_judgment",
        )
        work_tree._TASKS[first.task_id].status = work_tree.TaskStatus.ATTEMPTED
        held = trail_world_holds(work_tree.get_branch(branch.branch_id), has_open_stem=True)
        self.assertIsNotNone(held)
        result = advance_branch_sequence_after_task(branch.branch_id)
        self.assertEqual(result.get("reason"), "trail_world_holds")
        open_titles = [
            item.title
            for item in work_tree.list_branch_tasks(branch.branch_id)
            if item.status in {work_tree.TaskStatus.OPEN, work_tree.TaskStatus.ACTIVE}
        ]
        self.assertEqual(open_titles, [])


class SolutionProgressStampHonestyTests(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._db_path = base_tmp / f"solution_stamp_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(self._db_path)

    def tearDown(self) -> None:
        work_tree._clear_in_memory()
        try:
            if self._db_path.exists():
                self._db_path.unlink()
        except Exception:
            pass

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
