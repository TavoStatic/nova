"""Observation spine: Phase 1 repeat/ineligible path, Phase 2 competing pickup offers."""
from __future__ import annotations

import os
import unittest
import uuid
from pathlib import Path
from unittest import mock

import work_tree
from services.autonomy_execution_gate import AUTONOMY_EXECUTION_GATE_SERVICE
from services.observation_spine import (
    ALTER_EXISTING_SELECTION,
    COMPETING_INTERPRETATIONS,
    NO_META_INTERVENTION,
    PICKUP_PATH_GAP,
    REPEATED_UNCHANGED_PATH,
    REVISE_EXISTING_SELECTION,
    SELF_PREDICTION_MISS,
    apply_repeated_path_to_trail,
    apply_self_prediction_miss_to_trail,
    build_observation_spine_payload,
    meta_check,
    observe,
    recent_observations,
    reset_memory_only,
    reset_observations,
    trailing_mill_skip_loop,
)
from services.solution_trail import action_suppressed_by_trail


def _validation_tmp_root() -> Path:
    return Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "_test_tmp"


class ObservationSpineTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_observations()
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._db_path = base_tmp / f"observation_spine_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(self._db_path)

    def tearDown(self) -> None:
        work_tree._clear_in_memory()
        reset_observations()
        try:
            if self._db_path.exists():
                self._db_path.unlink()
        except Exception:
            pass

    def test_payload_empty_window_is_watching_nothing(self):
        payload = build_observation_spine_payload()
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("status"), "empty")
        self.assertFalse(payload.get("intervening"))
        self.assertEqual(payload.get("finding_code"), NO_META_INTERVENTION)
        self.assertEqual(payload.get("window_count"), 0)
        self.assertEqual(payload.get("observations"), [])

    def test_payload_repeated_path_is_intervening(self):
        for _ in range(3):
            observe(
                source="executor",
                operation="invoke",
                subject="core_thinning",
                input_ref="core_thinning|",
                outcome="success",
            )
        payload = build_observation_spine_payload()
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("status"), "intervening")
        self.assertTrue(payload.get("intervening"))
        self.assertEqual(payload.get("finding_code"), REPEATED_UNCHANGED_PATH)
        self.assertEqual(payload.get("subject"), "core_thinning")
        self.assertEqual(payload.get("window_count"), 3)
        self.assertEqual(len(payload.get("observations") or []), 3)
        self.assertEqual((payload.get("last_invoke") or {}).get("subject"), "core_thinning")

    def test_mill_skip_counts_as_loop_and_stop_runs_mill(self):
        from autonomy_maintenance import (
            _active_work_tree_cycle_for_execution_mode,
            _skipped_maintenance_execution_payload,
        )

        state = {}
        for _ in range(3):
            _skipped_maintenance_execution_payload(
                state,
                "last_active_work_tree_cycle",
                "orchestrator_owns_execution",
            )
        finding = meta_check()
        self.assertEqual(finding.finding_code, REPEATED_UNCHANGED_PATH)
        self.assertEqual(finding.subject, "active_work_tree_cycle")
        self.assertTrue(trailing_mill_skip_loop())
        rows = recent_observations()
        self.assertTrue(any(row.source == "mill" and row.outcome == "skipped" for row in rows))
        with mock.patch(
            "autonomy_maintenance._run_active_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 1, "tree_count": 1},
        ) as run_mill:
            out = _active_work_tree_cycle_for_execution_mode(
                state,
                mission_snapshot=None,
                policy_snapshot=None,
                autonomy_orchestrator={},
                legacy_execution_enabled=False,
            )
        run_mill.assert_called_once()
        self.assertEqual(out.get("executed_count"), 1)
        self.assertEqual(out.get("status"), "ok")
        self.assertFalse(trailing_mill_skip_loop())
        skip_rows = [
            row
            for row in recent_observations()
            if row.source == "mill" and row.subject == "active_work_tree_cycle" and row.outcome == "skipped"
        ]
        self.assertEqual(len(skip_rows), 3)
        self.assertTrue(
            any(row.source == "mill" and row.reason_code == "mill_skip_stop_run" for row in recent_observations())
        )
        with mock.patch(
            "autonomy_maintenance._run_active_work_tree_cycle",
            return_value={"status": "ok", "executed_count": 1, "tree_count": 1},
        ) as run_again:
            later = _active_work_tree_cycle_for_execution_mode(
                {},
                mission_snapshot=None,
                policy_snapshot=None,
                autonomy_orchestrator={},
                legacy_execution_enabled=False,
            )
        run_again.assert_not_called()
        self.assertEqual(later.get("status"), "skipped")
        self.assertFalse(trailing_mill_skip_loop())

    def test_payload_projects_observations_into_linked_cognitive_events(self):
        first = observe(
            source="pickup",
            operation="select_next_action",
            subject="read",
            input_ref="branch-1",
            outcome="selected",
        )
        second = observe(
            source="executor",
            operation="invoke",
            subject="read",
            input_ref="branch-1",
            outcome="success",
        )

        payload = build_observation_spine_payload()
        events = payload.get("cognitive_events") or []
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_id"], f"observation-{first.seq}")
        self.assertEqual(events[0]["event_type"], "action_selected")
        self.assertEqual(events[1]["event_type"], "action_invoked")
        self.assertEqual(events[1]["parent_events"], [f"observation-{first.seq}"])
        self.assertEqual(events[1]["content"]["outcome"], second.outcome)
        self.assertEqual(events[1]["origin"], "observation_spine")

    def test_repeated_path_projects_a_self_question(self):
        for _ in range(3):
            observe(
                source="executor",
                operation="invoke",
                subject="core_thinning",
                input_ref="same-input",
                outcome="success",
            )

        payload = build_observation_spine_payload()
        self.assertIn("What changed since the last attempt on this path?", payload.get("self_questions") or [])

    def test_payload_projects_grounded_dynamic_self_model(self):
        observe(
            source="pickup",
            operation="offer",
            subject="phase2_audit",
            input_ref="branch-envelope",
            outcome="offered",
            reason_code="review_required",
        )

        payload = build_observation_spine_payload()
        model = payload.get("self_model") or {}
        self.assertEqual(model.get("identity"), "Nova operational self-model")
        self.assertIn("phase2_audit", model.get("observed_capabilities") or [])
        self.assertEqual(model.get("active_constraints"), ["review_required"])
        self.assertEqual((model.get("current_internal_condition") or {}).get("observation_count"), 1)
        self.assertEqual(model.get("source_observation_seqs"), [1])

    def test_competing_offers_remain_visible_as_internal_positions(self):
        first = observe(
            source="pickup",
            operation="offer",
            subject="phase2_audit",
            input_ref="branch-envelope",
            outcome="offered",
        )
        second = observe(
            source="pickup",
            operation="offer",
            subject="release_rebuild_verify",
            input_ref="branch-release",
            outcome="offered",
        )

        payload = build_observation_spine_payload()
        positions = payload.get("internal_positions") or []
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0]["supporting_evidence"], [first.seq])
        self.assertEqual(positions[1]["supporting_evidence"], [second.seq])
        self.assertEqual([position["confidence"] for position in positions], [0.5, 0.5])
        self.assertIn("test:phase2_audit", positions[0]["action_implications"])

    def test_internal_positions_update_after_selection_and_invocation(self):
        first = observe(
            source="pickup",
            operation="offer",
            subject="phase2_audit",
            input_ref="branch-envelope",
            outcome="offered",
        )
        second = observe(
            source="pickup",
            operation="offer",
            subject="release_rebuild_verify",
            input_ref="branch-release",
            outcome="offered",
        )
        selected = observe(
            source="pickup",
            operation="select_next_action",
            subject="phase2_audit",
            input_ref="branch-envelope",
            outcome="selected",
        )
        invoked = observe(
            source="executor",
            operation="invoke",
            subject="phase2_audit",
            input_ref="branch-envelope",
            outcome="success",
        )

        positions = build_observation_spine_payload().get("internal_positions") or []
        self.assertEqual(positions[0]["supporting_evidence"], [first.seq, selected.seq, invoked.seq])
        self.assertEqual(positions[0]["confidence"], 0.9)
        self.assertEqual(positions[0]["status"], "supported")
        self.assertEqual(positions[1]["supporting_evidence"], [second.seq])
        self.assertEqual(positions[1]["opposing_evidence"], [selected.seq, invoked.seq])
        self.assertEqual(positions[1]["status"], "deprioritized")

    def test_three_unchanged_invokes_stop_the_path(self):
        for _ in range(3):
            observe(
                source="executor",
                operation="invoke",
                subject="core_thinning",
                input_ref="core_thinning|",
                outcome="success",
            )
        finding = meta_check()
        self.assertEqual(finding.finding_code, REPEATED_UNCHANGED_PATH)
        self.assertEqual(finding.subject, "core_thinning")
        self.assertEqual(finding.effect, "stop_repeated_path")

    def test_persisted_repeats_survive_a_new_once_process(self):
        for _ in range(2):
            observe(
                source="planner",
                operation="select_next_action",
                subject="pulse_status",
                input_ref="pulse",
                outcome="selected",
                reason_code="seam_pressure_elevated",
            )
        reset_memory_only()
        observe(
            source="planner",
            operation="select_next_action",
            subject="pulse_status",
            input_ref="pulse",
            outcome="selected",
            reason_code="seam_pressure_elevated",
        )
        finding = meta_check()
        self.assertEqual(finding.finding_code, REPEATED_UNCHANGED_PATH)
        self.assertEqual(finding.subject, "pulse_status")

    def test_two_invokes_do_not_fire(self):
        for _ in range(2):
            observe(
                source="executor",
                operation="invoke",
                subject="core_thinning",
                input_ref="core_thinning|",
                outcome="success",
            )
        self.assertEqual(meta_check().finding_code, NO_META_INTERVENTION)

    def test_changed_input_ref_is_not_a_repeat(self):
        observe(source="executor", operation="invoke", subject="core_thinning", input_ref="a", outcome="success")
        observe(source="executor", operation="invoke", subject="core_thinning", input_ref="a", outcome="success")
        observe(source="executor", operation="invoke", subject="core_thinning", input_ref="b", outcome="success")
        self.assertEqual(meta_check().finding_code, NO_META_INTERVENTION)

    def test_two_pickup_offers_are_competing_interpretations(self):
        observe(
            source="pickup",
            operation="offer",
            subject="phase2_audit",
            input_ref="branch_envelope",
            outcome="offered",
        )
        observe(
            source="pickup",
            operation="offer",
            subject="release_record_validation_outcome",
            input_ref="branch_release",
            outcome="offered",
        )
        finding = meta_check()
        self.assertEqual(finding.finding_code, COMPETING_INTERPRETATIONS)
        self.assertEqual(finding.effect, ALTER_EXISTING_SELECTION)

    def test_pickup_select_then_other_invoke_is_prediction_miss(self):
        observe(
            source="pickup",
            operation="select_next_action",
            subject="release_record_validation_outcome",
            input_ref="branch_release",
            outcome="selected",
        )
        observe(
            source="executor",
            operation="invoke",
            subject="phase2_audit",
            input_ref="branch_envelope",
            outcome="success",
        )
        finding = meta_check()
        self.assertEqual(finding.finding_code, SELF_PREDICTION_MISS)
        self.assertEqual(finding.effect, REVISE_EXISTING_SELECTION)
        self.assertEqual(finding.subject, "release_record_validation_outcome")

    def test_pickup_select_then_matching_invoke_is_not_a_miss(self):
        observe(
            source="pickup",
            operation="select_next_action",
            subject="release_record_validation_outcome",
            input_ref="branch_release",
            outcome="selected",
        )
        observe(
            source="executor",
            operation="invoke",
            subject="release_record_validation_outcome",
            input_ref="branch_release",
            outcome="success",
        )
        self.assertEqual(meta_check().finding_code, NO_META_INTERVENTION)

    def test_prediction_miss_makes_invoked_path_ineligible(self):
        tree = work_tree.initialize_tree("Prediction miss tree")
        root = work_tree._BRANCHES[tree.root_branch_id]
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Safety envelope", "work", root.branch_id)
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["phase2_audit"], require_explicit_allow=True)
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["phase2_audit"], preferred_tool="phase2_audit")
        work_tree.add_task_to_branch(
            branch.branch_id,
            "Run safety-envelope audit",
            meta={"expected_tool": "phase2_audit", "allowed_tools": ["phase2_audit"]},
        )
        before = work_tree.list_autonomous_options(tree.tree_id)
        self.assertEqual(len(before), 1)
        applied = apply_self_prediction_miss_to_trail(
            branch_id=branch.branch_id,
            tool_name="phase2_audit",
            task_title="Run safety-envelope audit",
            input_ref=branch.branch_id,
            predicted_subject="release_record_validation_outcome",
            predicted_ref="branch_release",
        )
        self.assertTrue(applied.get("ok"))
        self.assertEqual(work_tree.list_autonomous_options(tree.tree_id), [])
        from services.solution_trail import trail_world_holds
        from services.work_tree_signal_ingestion import advance_branch_sequence_after_task

        held = trail_world_holds(work_tree.get_branch(branch.branch_id), has_open_stem=True)
        self.assertIsNotNone(held)
        self.assertEqual((held or {}).get("class"), "redundant")
        work_tree._TASKS[before[0]["task_id"]].status = work_tree.TaskStatus.ATTEMPTED
        branch.source_payload = {
            **dict(branch.source_payload or {}),
            "task_sequence": [
                {
                    "title": "Run safety-envelope audit",
                    "allowed_tools": ["phase2_audit"],
                    "preferred_tool": "phase2_audit",
                },
                {
                    "title": "Run safety-envelope audit",
                    "allowed_tools": ["phase2_audit"],
                    "preferred_tool": "phase2_audit",
                },
            ],
        }
        result = advance_branch_sequence_after_task(branch.branch_id)
        self.assertEqual(result.get("reason"), "trail_world_holds")

    def test_one_pickup_offer_is_not_competing(self):
        observe(
            source="pickup",
            operation="offer",
            subject="phase2_audit",
            input_ref="branch_envelope",
            outcome="offered",
        )
        self.assertEqual(meta_check().finding_code, NO_META_INTERVENTION)

    def test_planner_selected_but_gate_denied_is_pickup_gap(self):
        observe(
            source="planner",
            operation="select_next_action",
            subject="release_rebuild_verify",
            input_ref="release",
            outcome="selected",
        )
        observe(
            source="execution_gate",
            operation="evaluate",
            subject="release_rebuild_verify",
            input_ref="release",
            outcome="blocked",
            reason_code="action_not_execute_allowed",
        )
        finding = meta_check()
        self.assertEqual(finding.finding_code, PICKUP_PATH_GAP)
        self.assertEqual(finding.subject, "release_rebuild_verify")

    def test_execution_gate_emits_raw_observation(self):
        AUTONOMY_EXECUTION_GATE_SERVICE.evaluate(
            {
                "decision_type": "RecommendAction",
                "recommended_action": {
                    "action_type": "pulse_status",
                    "target_id": "runtime",
                    "reason_code": "seam_pressure_elevated",
                },
                "confidence": 0.9,
                "refusal_reasons": [],
            },
            {
                "mode": "canary",
                "execute_enabled": True,
                "execute_allowed_actions": ["generated_queue_run_next"],
            },
        )
        rows = recent_observations()
        self.assertTrue(rows)
        last = rows[-1]
        self.assertEqual(last.source, "execution_gate")
        self.assertEqual(last.operation, "evaluate")
        self.assertEqual(last.subject, "pulse_status")
        self.assertEqual(last.outcome, "blocked")

    def test_repeated_path_makes_existing_trail_ineligible(self):
        tree = work_tree.initialize_tree("Observation spine tree")
        root = work_tree._BRANCHES[tree.root_branch_id]
        branch = work_tree.add_branch_to_tree(
            tree.tree_id,
            "Map HTTP extraction boundary: chat_sessions",
            "core_thinning",
            root.branch_id,
        )
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["core_thinning"], require_explicit_allow=True)
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["core_thinning"], preferred_tool="core_thinning")
        work_tree.add_task_to_branch(branch.branch_id, "Map HTTP extraction boundary: chat_sessions")

        before = work_tree.list_autonomous_options(tree.tree_id)
        self.assertEqual(len(before), 1)
        self.assertEqual(before[0]["recommended_tool"], "core_thinning")

        applied = apply_repeated_path_to_trail(
            branch_id=branch.branch_id,
            tool_name="core_thinning",
            task_title="Map HTTP extraction boundary: chat_sessions",
            input_ref="core_thinning|",
        )
        self.assertTrue(applied.get("ok"))
        payload = dict(branch.source_payload or {})
        suppressed = action_suppressed_by_trail(
            tool_name="core_thinning",
            judgments=list(payload.get("attempt_judgments") or []),
            progress=work_tree._branch_progress_payload(branch) or {},
            branch_payload=payload,
        )
        self.assertIsNotNone(suppressed)
        self.assertEqual(work_tree.list_autonomous_options(tree.tree_id), [])
        preview = work_tree._preview_next_autonomous_step(tree.tree_id)
        self.assertTrue(preview is None or str(preview.get("branch_id") or "") != branch.branch_id)

    def test_minted_reexamine_is_dropped_from_pickup(self):
        tree = work_tree.initialize_tree("Re-examine leftover")
        root = work_tree._BRANCHES[tree.root_branch_id]
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Review wrapper shim leftover", "core_thinning", root.branch_id)
        work_tree.set_tree_execution_policy(tree.tree_id, allowed_tools=["core_thinning"], require_explicit_allow=True)
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["core_thinning"], preferred_tool="core_thinning")
        work_tree.add_task_to_branch(branch.branch_id, work_tree.SIGNAL_STILL_PRESENT_REEXAMINE_TITLE)

        options = work_tree.list_autonomous_options(tree.tree_id)
        self.assertEqual(options, [])
        open_titles = [
            task.title
            for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertNotIn(work_tree.SIGNAL_STILL_PRESENT_REEXAMINE_TITLE, open_titles)


class ObservationSpineCirculationTests(unittest.TestCase):
    """Blind organs pulse the existing spine. No new store."""

    def setUp(self) -> None:
        reset_observations()
        base_tmp = _validation_tmp_root()
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._db_path = base_tmp / f"spine_circ_{uuid.uuid4().hex}.sqlite3"
        work_tree._set_db_path(self._db_path)

    def tearDown(self) -> None:
        work_tree._clear_in_memory()
        reset_observations()
        try:
            if self._db_path.exists():
                self._db_path.unlink()
        except Exception:
            pass

    def test_ingest_create_and_refuse_are_visible_on_spine(self) -> None:
        from services.work_tree_signal_ingestion import WorkTreeSignalIngestionService

        svc = WorkTreeSignalIngestionService()
        created = svc.ingest_signal(
            {
                "source": "capability_manifest",
                "signal_class": "declared_capability_absent",
                "title": "Declared capability gap",
                "fingerprint": {
                    "class": "declared_capability_absent",
                    "surface": "capability_manifest",
                    "error": "gap",
                    "symbol": "circ_gap",
                },
                "severity": "medium",
                "actionability": "safe_now",
                "allowed_tools": ["read"],
                "preferred_tool": "read",
            }
        )
        self.assertEqual(created.get("action"), "created")
        rows = recent_observations()
        self.assertTrue(any(row.source == "ingest" and row.operation == "create" for row in rows))

        reset_observations()
        branch = work_tree.get_branch(str(created.get("branch_id") or ""))
        self.assertIsNotNone(branch)
        for task in work_tree.list_branch_tasks(branch.branch_id):
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}:
                work_tree.mark_task_dropped(task.task_id, reason="circulation_test")
        refused = svc.teach_unclaimable_refusals(active_source_keys=set())
        self.assertTrue(any(item.get("branch_id") == branch.branch_id for item in refused))
        rows = recent_observations()
        self.assertTrue(
            any(row.source == "ingest" and row.operation == "refuse" and row.input_ref == branch.branch_id for row in rows)
        )

    def test_sequence_advance_mint_is_visible_on_spine(self) -> None:
        from services.work_tree_signal_ingestion import advance_branch_sequence_after_task

        tree = work_tree.initialize_tree("Circulation sequence")
        root = work_tree._BRANCHES[tree.root_branch_id]
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Release package has failing validation", "work", root.branch_id)
        branch.source_payload = {
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
            ]
        }
        done = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read release ledger for current package",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )
        work_tree.mark_task_complete(done.task_id)
        result = advance_branch_sequence_after_task(branch.branch_id)
        self.assertEqual(result.get("reason"), "next_sequence_task_created")
        rows = recent_observations()
        self.assertTrue(
            any(row.source == "sequence" and row.operation == "mint" and row.input_ref == branch.branch_id for row in rows)
        )

    def test_sanitize_resolve_is_visible_on_spine(self) -> None:
        from services.backpack_host.sanitize import _sanitize_work_tree

        tree = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        root = work_tree._BRANCHES[tree.root_branch_id]
        branch = work_tree.add_branch_to_tree(tree.tree_id, "Saved data connector capability profile is missing", "work", root.branch_id)
        branch.source_type = "edfi_capability_profile"
        branch.source_key = "governance_pressure:edfi_capability_profile:edfi_profile_missing:district-main"
        branch.resolution_state = "open"
        with mock.patch.object(work_tree, "reload_persisted_state", return_value=True):
            results = _sanitize_work_tree(
                "edfi",
                points={"signal_sources": ["edfi_capability_profile"], "pipeline_ids": ["edfi"]},
                reason="edfi backpack was uninstalled; leftover pressure is residue, not live work.",
            )
        self.assertTrue(any(item.get("branch_id") == branch.branch_id and item.get("action") == "resolved" for item in results))
        rows = recent_observations()
        self.assertTrue(
            any(row.source == "sanitize" and row.operation == "resolve" and row.input_ref == branch.branch_id for row in rows)
        )
