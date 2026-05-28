from __future__ import annotations

import json
import os
import shutil
import unittest
import uuid
from unittest import mock
from pathlib import Path

import work_tree
from services.work_tree_signal_ingestion import WorkTreeSignalIngestionService, _branch_why_summary, _validation_artifact_truth_signal_from_status


WORK_TMP_ROOT = Path(os.environ.get("NOVA_VALIDATION_RUNTIME_DIR") or Path(__file__).resolve().parents[1] / "runtime" / "validation") / "pytest_temp"


def _workspace_case_dir(prefix: str) -> Path:
    WORK_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_TMP_ROOT / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestWorkTreeSignalIngestionService(unittest.TestCase):
    def setUp(self) -> None:
        work_tree._clear_in_memory()
        self._tmp = _workspace_case_dir("work_tree_signal_ingestion")
        self._persist_patcher = mock.patch.object(work_tree, "_persist_tree_state", return_value=None)
        self._persist_patcher.start()
        self.service = WorkTreeSignalIngestionService()

    def tearDown(self) -> None:
        self._persist_patcher.stop()
        work_tree._clear_in_memory()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _signal_branches(self):
        trees = [tree for tree in work_tree.list_trees() if str((tree.meta or {}).get("kind") or "") == "signal_ingestion"]
        if not trees:
            return []
        tree = trees[0]
        return [
            branch
            for branch in work_tree.list_tree_branches(tree.tree_id)
            if branch.tree_id == tree.tree_id and branch.branch_id != tree.root_branch_id
        ]

    def test_repeated_signal_updates_existing_branch_with_evidence(self) -> None:
        signal = {
            "source": "control_status",
            "signal_class": "code_defect",
            "title": "Fix NameError in control/status pulse path",
            "fingerprint": {
                "class": "code_defect",
                "surface": "control_status",
                "error": "NameError",
                "symbol": "PATCH_LOG",
            },
            "payload": {
                "error": "NameError",
                "symbol": "PATCH_LOG",
            },
            "severity": "high",
            "actionability": "safe_now",
            "next_task": "Inspect stack and patch the missing symbol reference",
        }

        first = self.service.ingest_signal(signal)
        second = self.service.ingest_signal(signal)

        self.assertEqual(first.get("action"), "created")
        self.assertEqual(second.get("action"), "updated")
        self.assertEqual(first.get("branch_id"), second.get("branch_id"))

        branches = self._signal_branches()
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.source_key, "code_defect:control_status:NameError:PATCH_LOG")
        self.assertEqual(branch.evidence_count, 2)
        self.assertEqual(str(branch.actionability or ""), "safe_now")

    def test_signal_tree_ingestion_archives_duplicate_signal_trees(self) -> None:
        canonical = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        duplicate = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={"kind": "signal_ingestion", "source": "runtime_signals", "signal_ingestion": True},
        )
        signal = {
            "source": "control_status",
            "signal_class": "code_defect",
            "title": "Fix duplicate Signal Intake routing",
            "fingerprint": {
                "class": "code_defect",
                "surface": "work_tree",
                "error": "duplicate_signal_tree",
                "symbol": "signal_ingestion",
            },
            "payload": {"symbol": "signal_ingestion"},
            "severity": "medium",
            "actionability": "safe_now",
            "next_task": "Inspect canonical Signal Intake routing",
        }

        result = self.service.ingest_signal(signal)

        self.assertEqual(result.get("tree_id"), canonical.tree_id)
        self.assertEqual(getattr(work_tree.get_tree(duplicate.tree_id).status, "value", ""), "archived")
        self.assertEqual(getattr(work_tree.get_tree(canonical.tree_id).status, "value", ""), "active")

    def test_signal_tree_repairs_legacy_policy_to_full_default_tools(self) -> None:
        tree = work_tree.initialize_tree(
            "Signal Intake: Runtime Governance",
            meta={
                "kind": "signal_ingestion",
                "source": "runtime_signals",
                "signal_ingestion": True,
                "execution_policy": {
                    "allowed_tools": ["read"],
                    "require_explicit_allow": True,
                },
            },
        )
        signal = {
            "source": "control_status",
            "signal_class": "code_defect",
            "title": "Fix legacy Signal Intake tool policy",
            "fingerprint": {
                "class": "code_defect",
                "surface": "work_tree",
                "error": "legacy_policy",
                "symbol": "signal_ingestion",
            },
            "payload": {"symbol": "signal_ingestion"},
            "severity": "medium",
            "actionability": "safe_now",
            "next_task": "Inspect Signal Intake policy",
        }

        self.service.ingest_signal(signal)

        policy = work_tree.get_tree(tree.tree_id).meta.get("execution_policy")
        allowed = policy.get("allowed_tools")
        self.assertIn("read", allowed)
        self.assertIn("source_root_judgment", allowed)
        self.assertIn("os_capability", allowed)
        self.assertIn("memory_bootstrap_confirm", allowed)

    def test_repeated_signal_update_clears_stale_branch_tool_without_explicit_tool(self) -> None:
        signal = {
            "source": "subconscious",
            "signal_class": "subconscious_candidate",
            "title": "Review subconscious priority with fulfillment/supervisor: subconscious_pressure_backlog_generation / route_fit_weak",
            "fingerprint": {
                "class": "subconscious_candidate",
                "surface": "subconscious_pressure_backlog_generation",
                "error": "route_fit_weak",
                "symbol": "test_route_probe_exposes_weak_fit_without_forcing_routing",
            },
            "payload": {
                "signal": "route_fit_weak",
                "target_seam": "subconscious_pressure_backlog_generation",
            },
            "severity": "medium",
            "actionability": "safe_now",
            "next_task": "Run or inspect test_route_probe_exposes_weak_fit_without_forcing_routing and confirm whether route_fit_weak is still active in subconscious_pressure_backlog_generation",
        }

        first = self.service.ingest_signal(signal)
        branch = next(branch for branch in self._signal_branches() if branch.branch_id == first.get("branch_id"))
        work_tree.set_branch_tools(branch.branch_id, allowed_tools=["queue_status"], preferred_tool="queue_status")

        second = self.service.ingest_signal(signal)

        self.assertEqual(second.get("action"), "updated")
        branch = next(branch for branch in self._signal_branches() if branch.branch_id == first.get("branch_id"))
        self.assertIsNone(branch.preferred_tool)
        self.assertEqual(branch.allowed_tools, [])

    def test_inactive_subconscious_candidate_retires_without_blocking_truth(self) -> None:
        signal = {
            "source": "subconscious",
            "signal_class": "subconscious_candidate",
            "title": "Review subconscious priority with supervisor: patch_routing_fallthrough / fallback_overuse",
            "fingerprint": {
                "class": "subconscious_candidate",
                "surface": "patch_routing_fallthrough",
                "error": "fallback_overuse",
                "symbol": "test_patch_routing_route",
            },
            "payload": {
                "signal": "fallback_overuse",
                "target_seam": "patch_routing_fallthrough",
            },
            "severity": "medium",
            "actionability": "safe_now",
            "allowed_tools": ["find"],
            "preferred_tool": "find",
            "next_task": "Find route evidence for patch_routing_fallthrough",
        }

        self.service.ingest_signal(signal)

        results = self.service.resolve_inactive_signal_branches(
            signal_class="subconscious_candidate",
            source="subconscious",
            active_source_keys=set(),
            reason="Latest subconscious report no longer carries this pressure as an active training priority.",
            resolution_mode="retire",
        )

        self.assertEqual([item.get("action") for item in results], ["retired"])
        branch = self._signal_branches()[0]
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)
        self.assertEqual(str(branch.resolution_state or ""), "retired")
        self.assertIn("Retired:", str(branch.notes or ""))
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks, [])

    def test_status_snapshot_ingests_autonomy_maintenance_last_error(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "autonomy_maintenance": {
                    "last_error": "subconscious_runner timed out after -11553 seconds",
                    "last_error_stale": False,
                    "last_generated_at": "2026-05-14 07:45:00",
                },
            }
        )

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "autonomy_maintenance")
        self.assertEqual(str(branch.work_class or ""), "maintenance_pressure")
        self.assertIn("-11553", str((branch.source_payload or {}).get("last_error") or ""))
        self.assertEqual(branch.preferred_tool, "read")

    def test_autonomy_maintenance_evidence_sequence_reaches_source_root_judgment(self) -> None:
        status_payload = {
            "autonomy_maintenance": {
                "last_error": "subconscious_runner timed out after -11553 seconds",
                "last_error_stale": False,
                "last_generated_at": "2026-05-14 07:45:00",
            },
            "runtime_worker_status": "failed",
            "runtime_worker_stale_identity": False,
        }

        self.service.sync_status_snapshot(status_payload)
        branch = self._signal_branches()[0]

        for _ in range(4):
            open_tasks = [
                task for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
            ]
            self.assertTrue(open_tasks)
            task = open_tasks[0]
            if task.title == "Synthesize source-root judgment from collected evidence":
                break
            expected_tool = str((task.meta or {}).get("expected_tool") or "read")
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=expected_tool,
                tool_args=list((task.meta or {}).get("tool_args") or []),
                result={"ok": True, "evidence": task.title},
            )
            work_tree.mark_task_complete(task.task_id)
            self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks[0].title, "Synthesize source-root judgment from collected evidence")
        self.assertEqual((open_tasks[0].meta or {}).get("expected_tool"), "source_root_judgment")

    def test_status_snapshot_ingests_runtime_restart_pressure(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "runtime_restart_analytics": {
                    "flap_level": "warn",
                    "flap_summary": "Runtime restart pressure is elevated.",
                    "recent_restart_count_15m": 3,
                    "consecutive_failures": 0,
                    "failure_count": 0,
                },
            }
        )

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "runtime_control")
        self.assertEqual(str(branch.work_class or ""), "runtime_failure")
        self.assertEqual(str(branch.source_key or ""), "runtime_failure:runtime_control:restart_pressure:guard_boot_history")

    def test_status_snapshot_does_not_treat_planned_restarts_as_pressure(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "runtime_restart_analytics": {
                    "flap_level": "good",
                    "flap_summary": "No failure-driven restart pressure is active.",
                    "recent_restart_count_15m": 4,
                    "pressure_restart_count_15m": 0,
                    "pressure_restart_count_1h": 0,
                    "planned_restart_count_1h": 4,
                    "restart_pressure_active": False,
                    "restart_provenance_status": "complete",
                    "restart_origin_gap_count_1h": 0,
                    "consecutive_failures": 0,
                    "failure_count": 0,
                },
            }
        )

        self.assertFalse(any(item.get("action") == "created" for item in results))
        self.assertEqual(self._signal_branches(), [])

    def test_status_snapshot_ingests_runtime_restart_provenance_gap(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "runtime_restart_analytics": {
                    "flap_level": "good",
                    "flap_summary": "No failure-driven restart pressure is active.",
                    "recent_restart_count_15m": 3,
                    "pressure_restart_count_15m": 0,
                    "pressure_restart_count_1h": 0,
                    "restart_pressure_active": False,
                    "restart_provenance_status": "incomplete",
                    "restart_origin_gap_count_1h": 3,
                    "consecutive_failures": 0,
                    "failure_count": 0,
                },
            }
        )

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "runtime_control")
        self.assertEqual(str(branch.work_class or ""), "governance_pressure")
        self.assertEqual(str(branch.source_key or ""), "governance_pressure:runtime_control:restart_provenance_gap:guard_boot_history")

    def test_status_snapshot_does_not_ingest_legacy_restart_provenance_gap(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "runtime_restart_analytics": {
                    "flap_level": "good",
                    "flap_summary": "No failure-driven restart pressure is active.",
                    "recent_restart_count_15m": 3,
                    "pressure_restart_count_15m": 0,
                    "pressure_restart_count_1h": 0,
                    "restart_pressure_active": False,
                    "restart_provenance_status": "legacy_incomplete",
                    "restart_origin_gap_count_1h": 3,
                    "restart_origin_active_gap_count_1h": 0,
                    "restart_origin_legacy_gap_count_1h": 3,
                    "consecutive_failures": 0,
                    "failure_count": 0,
                },
            }
        )

        self.assertFalse(any(item.get("action") == "created" for item in results))
        self.assertEqual(self._signal_branches(), [])

    def test_status_snapshot_ingests_storage_watch_pressure(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "storage_watch_status": "watch",
                "storage_watch_note": "archive growth is above threshold",
                "storage_watch_total_bytes": 99_000_000,
                "patch_snapshot_count": 12,
                "kidney_snapshot_count": 9,
                "release_validation_extract_count": 4,
                "release_validation_extract_bytes": 88_000_000,
                "release_stage_count": 2,
                "release_stage_bytes": 11_000_000,
                "release_zip_count": 7,
                "release_zip_bytes": 22_000_000,
            }
        )

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "storage_release_pressure")
        self.assertEqual(str(branch.work_class or ""), "maintenance_pressure")
        self.assertIn("archive growth", str((branch.source_payload or {}).get("storage_watch_note") or ""))
        self.assertEqual((branch.source_payload or {}).get("release_validation_extract_count"), 4)
        self.assertEqual((branch.source_payload or {}).get("release_stage_count"), 2)

    def test_status_snapshot_ingests_patch_pipeline_governance_gap(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "patch_enabled": True,
                "patch_status_ok": True,
                "patch_strict_manifest": False,
                "patch_behavioral_check": True,
                "patch_tests_available": True,
                "patch_pipeline_ready": True,
                "patch_cleanup_status": "ok",
            }
        )

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "patch_pipeline")
        self.assertEqual(str(branch.work_class or ""), "governance_pressure")
        self.assertIn("patch_strict_manifest_disabled", branch.source_payload.get("reasons") or [])

    def test_status_snapshot_ingests_autonomy_orchestrator_ack_hold(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "autonomy_orchestrator_decision": "defer_with_reason",
                "autonomy_orchestrator_decision_type": "Defer",
                "autonomy_orchestrator_action_type": "generated_queue_investigate",
                "autonomy_orchestrator_reason": "No candidate passed advisory preconditions.",
                "autonomy_orchestrator_ledger_status": "recorded",
                "autonomy_orchestrator_rejection_reasons": ["operator_ack_required"],
                "autonomy_orchestrator_summary": {
                    "rejection_reason_counts": {"operator_ack_required": 7},
                },
            }
        )

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "autonomy_orchestrator")
        self.assertEqual(str(branch.work_class or ""), "governance_pressure")
        self.assertIn("operator_ack_required", branch.source_payload.get("rejection_reasons") or [])

    def test_autonomy_orchestrator_evidence_sequence_reaches_source_root_judgment(self) -> None:
        status_payload = {
            "autonomy_orchestrator_decision": "defer_with_reason",
            "autonomy_orchestrator_decision_type": "Defer",
            "autonomy_orchestrator_action_type": "generated_queue_investigate",
            "autonomy_orchestrator_reason": "No candidate passed advisory preconditions.",
            "autonomy_orchestrator_ledger_status": "recorded",
            "autonomy_orchestrator_rejection_reasons": ["operator_ack_required"],
            "autonomy_orchestrator_summary": {
                "rejection_reason_counts": {"operator_ack_required": 7},
            },
        }

        self.service.sync_status_snapshot(status_payload)
        branch = self._signal_branches()[0]

        for _ in range(4):
            open_tasks = [
                task for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
            ]
            self.assertTrue(open_tasks)
            task = open_tasks[0]
            if task.title == "Synthesize source-root judgment from collected evidence":
                break
            expected_tool = str((task.meta or {}).get("expected_tool") or "read")
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=expected_tool,
                tool_args=list((task.meta or {}).get("tool_args") or []),
                result={"ok": True, "evidence": task.title},
            )
            work_tree.mark_task_complete(task.task_id)
            self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks[0].title, "Synthesize source-root judgment from collected evidence")
        self.assertEqual((open_tasks[0].meta or {}).get("expected_tool"), "source_root_judgment")

    def test_status_snapshot_ingests_subconscious_status_gap(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "subconscious_ok": False,
                "subconscious_generated_at": "",
                "subconscious_latest_report_path": "C:\\NOVA\\runtime\\subconscious_runs\\latest.json",
                "subconscious_training_priority_count": 0,
                "subconscious_live_summary": {"tracked_session_count": 0},
            }
        )

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "subconscious")
        self.assertEqual(str(branch.work_class or ""), "maintenance_pressure")
        self.assertFalse(branch.source_payload.get("subconscious_ok"))

    def test_status_snapshot_ingests_action_ledger_gap(self) -> None:
        results = self.service.ingest_status_snapshot(
            {
                "action_ledger_ok": False,
                "action_ledger_total": 0,
                "last_planner_decision": "llm_fallback",
                "last_route_summary": "llm_call:started -> finalize:error",
                "last_action_final_answer": "(error: LLM service unavailable)",
            }
        )

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "action_ledger")
        self.assertEqual(str(branch.work_class or ""), "maintenance_pressure")
        self.assertIn("what it ate", str((branch.source_payload or {}).get("rationale") or ""))

    def test_branch_why_summary_includes_rationale_owner_and_review_focus(self) -> None:
        summary = _branch_why_summary(
            {
                "signal_class": "subconscious_candidate",
                "source": "subconscious",
                "actionability": "safe_now",
                "severity": "medium",
                "payload": {
                    "target_seam": "patch_routing_fallthrough",
                    "signal": "fallback_overuse",
                    "suggested_test_name": "test_patch_routing_route",
                    "preferred_owner": "supervisor",
                    "route_hint": "supervisor_owned",
                    "rationale": "Patch routing slipped to fallback.",
                    "branch_note": "Patch-routing review: verify the exact patch lane and preserve rollback/apply governance.",
                },
            }
        )

        self.assertIn("seam=patch_routing_fallthrough", summary)
        self.assertIn("signal=fallback_overuse", summary)
        self.assertIn("test=test_patch_routing_route", summary)
        self.assertIn("owner=supervisor", summary)
        self.assertIn("route_hint=supervisor_owned", summary)
        self.assertIn("Rationale: Patch routing slipped to fallback.", summary)
        self.assertIn("Review focus: Patch-routing review", summary)

    def test_subconscious_signal_branch_notes_capture_review_focus(self) -> None:
        signal = {
            "source": "subconscious",
            "signal_class": "subconscious_candidate",
            "title": "Review subconscious priority with supervisor: patch_routing_fallthrough / fallback_overuse",
            "fingerprint": {
                "class": "subconscious_candidate",
                "surface": "patch_routing_fallthrough",
                "error": "fallback_overuse",
                "symbol": "test_patch_routing_route",
            },
            "payload": {
                "signal": "fallback_overuse",
                "target_seam": "patch_routing_fallthrough",
                "suggested_test_name": "test_patch_routing_route",
                "preferred_owner": "supervisor",
                "route_hint": "supervisor_owned",
                "rationale": "Patch routing slipped to fallback.",
                "branch_note": "Patch-routing review: verify the exact patch lane and preserve rollback/apply governance.",
            },
            "severity": "medium",
            "actionability": "safe_now",
            "next_task": "Run or inspect test_patch_routing_route and confirm whether patch routing still falls through",
        }

        result = self.service.ingest_signal(signal)

        self.assertEqual(result.get("action"), "created")
        branch = self._signal_branches()[0]
        self.assertIn("Patch routing slipped to fallback.", str(branch.notes or ""))
        self.assertIn("Patch-routing review", str(branch.notes or ""))

    def test_sequence_realigns_when_earlier_evidence_was_no_match(self) -> None:
        signal = {
            "source": "subconscious",
            "signal_class": "subconscious_candidate",
            "title": "Review subconscious priority with fulfillment: fulfillment_bridge_entry_fallthrough / fulfillment_missed",
            "fingerprint": {
                "class": "subconscious_candidate",
                "surface": "fulfillment_bridge_entry_fallthrough",
                "error": "fulfillment_missed",
                "symbol": "test_route_probe",
            },
            "payload": {
                "signal": "fulfillment_missed",
                "target_seam": "fulfillment_bridge_entry_fallthrough",
            },
            "severity": "high",
            "actionability": "safe_now",
            "allowed_tools": ["find", "read"],
            "preferred_tool": "find",
            "next_task": "Find route evidence for fulfillment_bridge_entry_fallthrough without running generated tests",
            "task_sequence": [
                {
                    "title": "Find pressure evidence for fulfillment_missed in fulfillment_bridge_entry_fallthrough",
                    "allowed_tools": ["find"],
                    "preferred_tool": "find",
                    "tool_args": ["fulfillment_missed", "tests"],
                },
                {
                    "title": "Read runtime/subconscious_runs/latest.json subconscious priority report",
                    "allowed_tools": ["read"],
                    "preferred_tool": "read",
                    "tool_args": ["runtime/subconscious_runs/latest.json"],
                },
            ],
        }
        self.service.ingest_signal(signal)
        branch = self._signal_branches()[0]
        first_task = work_tree.list_branch_tasks(branch.branch_id)[0]
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=first_task.task_id,
            tool_name="find",
            tool_args=["fulfillment_missed", "tests"],
            result="No matches found.",
        )
        work_tree.mark_task_complete(first_task.task_id)
        premature = work_tree.add_task_to_branch(
            branch.branch_id,
            "Read runtime/subconscious_runs/latest.json subconscious priority report",
            meta={"expected_tool": "read", "allowed_tools": ["read"]},
        )

        self.service.ingest_signal(signal)

        tasks = work_tree.list_branch_tasks(branch.branch_id)
        open_tasks = [task for task in tasks if getattr(task.status, "value", "") == "open"]
        dropped_tasks = [task for task in tasks if getattr(task.status, "value", "") == "dropped"]
        self.assertEqual(open_tasks[0].title, "Find pressure evidence for fulfillment_missed in fulfillment_bridge_entry_fallthrough")
        self.assertIn(premature.task_id, {task.task_id for task in dropped_tasks})

    def test_sequence_realigns_premature_blocked_task_to_judgment_step(self) -> None:
        signal = {
            "source": "subconscious",
            "signal_class": "subconscious_candidate",
            "title": "Review subconscious priority with fulfillment: fulfillment_bridge_entry_fallthrough / fulfillment_missed",
            "fingerprint": {
                "class": "subconscious_candidate",
                "surface": "fulfillment_bridge_entry_fallthrough",
                "error": "fulfillment_missed",
                "symbol": "test_route_probe",
            },
            "payload": {
                "signal": "fulfillment_missed",
                "target_seam": "fulfillment_bridge_entry_fallthrough",
            },
            "severity": "high",
            "actionability": "safe_now",
            "allowed_tools": ["find", "subconscious_review_judgment"],
            "preferred_tool": "find",
            "next_task": "Find route evidence for fulfillment_bridge_entry_fallthrough without running generated tests",
            "task_sequence": [
                {
                    "title": "Find route evidence for fulfillment_bridge_entry_fallthrough without running generated tests",
                    "allowed_tools": ["find"],
                    "preferred_tool": "find",
                    "tool_args": ["fulfillment_bridge_entry_fallthrough", "subconscious_live_simulator.py"],
                },
                {
                    "title": "Synthesize subconscious review judgment for fulfillment_bridge_entry_fallthrough / fulfillment_missed",
                    "allowed_tools": ["subconscious_review_judgment"],
                    "preferred_tool": "subconscious_review_judgment",
                },
            ],
            "blocked_task": "Hold owner-root repair lane for fulfillment_bridge_entry_fallthrough / fulfillment_missed using synthesized judgment instead of running generated tests as progress",
            "blocked_reason": "subconscious_pressure_owner_repair_required",
        }
        self.service.ingest_signal(signal)
        branch = self._signal_branches()[0]
        first_task = work_tree.list_branch_tasks(branch.branch_id)[0]
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=first_task.task_id,
            tool_name="find",
            tool_args=["fulfillment_bridge_entry_fallthrough", "subconscious_live_simulator.py"],
            result="subconscious_live_simulator.py:123: fulfillment_bridge_entry_fallthrough",
        )
        work_tree.mark_task_complete(first_task.task_id)
        premature_blocked = work_tree.add_task_to_branch(
            branch.branch_id,
            signal["blocked_task"],
            meta={"blocked_reason": "subconscious_pressure_owner_repair_required"},
        )
        work_tree.mark_task_blocked(premature_blocked.task_id, "subconscious_pressure_owner_repair_required")

        self.service.ingest_signal(signal)

        tasks = work_tree.list_branch_tasks(branch.branch_id)
        open_tasks = [task for task in tasks if getattr(task.status, "value", "") == "open"]
        dropped_tasks = [task for task in tasks if getattr(task.status, "value", "") == "dropped"]
        self.assertEqual(open_tasks[0].title, "Synthesize subconscious review judgment for fulfillment_bridge_entry_fallthrough / fulfillment_missed")
        self.assertEqual(open_tasks[0].meta.get("expected_tool"), "subconscious_review_judgment")
        self.assertIn(premature_blocked.task_id, {task.task_id for task in dropped_tasks})

    def test_ingested_branch_notes_include_signal_evidence_lines(self) -> None:
        signal = {
            "source": "subconscious",
            "signal_class": "subconscious_candidate",
            "title": "Review subconscious priority with supervisor: retrieval_followup_fallthrough / fallback_overuse",
            "fingerprint": {
                "class": "subconscious_candidate",
                "surface": "retrieval_followup_fallthrough",
                "error": "fallback_overuse",
                "symbol": "test_retrieval_followup_route",
            },
            "payload": {
                "signal": "fallback_overuse",
                "target_seam": "retrieval_followup_fallthrough",
                "suggested_test_name": "test_retrieval_followup_route",
                "preferred_owner": "supervisor",
                "route_hint": "supervisor_owned",
                "rationale": "Retrieval followup slipped into generic fallback.",
                "branch_note": "Retrieval review: inspect selected-result followup routing and preserve retrieval context.",
            },
            "severity": "medium",
            "actionability": "safe_now",
            "next_task": "Run or inspect test_retrieval_followup_route and confirm whether retrieval followup still falls through",
        }

        result = self.service.ingest_signal(signal)

        self.assertEqual(result.get("action"), "created")
        branch = self._signal_branches()[0]
        notes = str(branch.notes or "")
        self.assertIn("Signal evidence:", notes)
        self.assertIn("seam=retrieval_followup_fallthrough", notes)
        self.assertIn("signal=fallback_overuse", notes)
        self.assertIn("test=test_retrieval_followup_route", notes)
        self.assertIn("owner=supervisor", notes)
        self.assertIn("route_hint=supervisor_owned", notes)
        self.assertIn("Rationale: Retrieval followup slipped into generic fallback.", notes)
        self.assertIn("Review focus: Retrieval review:", notes)

    def test_dependency_unreachable_defaults_to_dead_end_bucket(self) -> None:
        signal = {
            "source": "control_status",
            "signal_class": "dependency_unreachable",
            "title": "Ollama API unreachable",
            "fingerprint": {
                "class": "dependency_unreachable",
                "surface": "control_status",
                "error": "dependency_unreachable",
                "symbol": "ollama_api",
            },
            "payload": {
                "alert": "ollama_api: reachability failed",
            },
            "severity": "medium",
        }

        result = self.service.ingest_signal(signal)

        self.assertEqual(result.get("action"), "created")
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.actionability or ""), "dead_end")
        self.assertEqual(str(branch.work_class or ""), "dependency_unreachable")

    def test_status_snapshot_ingests_first_wave_sources(self) -> None:
        status_payload = {
            "alerts": ["error_spike on /api/control/status", "ollama_api unreachable", "unowned_self_check_probe:failed"],
            "self_check_pass_ratio": 0.82,
            "autonomy_maintenance": {
                "last_regression_status": "failed: tests.test_runtime_recovery",
            },
        }

        results = self.service.ingest_status_snapshot(status_payload)

        self.assertGreaterEqual(len(results), 4)
        branches = self._signal_branches()
        self.assertGreaterEqual(len(branches), 4)

        classes = {str(branch.work_class or "") for branch in branches}
        self.assertIn("runtime_failure", classes)
        self.assertIn("dependency_unreachable", classes)
        self.assertIn("governance_pressure", classes)
        self.assertIn("regression_failure", classes)

        http_branch = [branch for branch in branches if str(branch.source_type or "") == "http_api_control"][0]
        self.assertEqual(str(http_branch.preferred_tool or ""), "read")
        self.assertIn("read", list(http_branch.allowed_tools or []))

    def test_sync_resolves_http_api_error_spike_when_alert_clears(self) -> None:
        self.service.sync_status_snapshot({"alerts": ["error_spike on /api/control/status"]})
        self.service.sync_status_snapshot({"alerts": []})

        branches = self._signal_branches()
        http_branch = [branch for branch in branches if str(branch.source_type or "") == "http_api_control"][0]
        self.assertEqual(getattr(http_branch.status, "value", http_branch.status), "complete")
        self.assertEqual(str(http_branch.resolution_state or ""), "resolved")

    def test_status_snapshot_does_not_duplicate_typed_test_profile_alert_as_self_check(self) -> None:
        status_payload = {
            "alerts": [
                "test_profile_inventory:drift=1;gaps=0;source_observed=1;inactive_install_profile=0",
                "work_tree_unresolved_truth:blocked=2;observing=1;latent_root=0;operator_hold=0",
            ],
            "self_check_pass_ratio": 0.91,
            "test_profile_inventory_ok": False,
            "test_profile_profile_gap_count": 0,
            "test_profile_profile_drift_count": 1,
            "test_profile_source_observed_count": 1,
            "test_profile_inventory": {
                "ok": False,
                "profile_drift_count": 1,
                "source_observed_count": 1,
                "profile_drift_tests": [
                    {
                        "path": "tests/test_evidence_validity.py",
                        "profile_class": "source_observed",
                    }
                ],
            },
        }

        self.service.sync_status_snapshot(status_payload)

        branches = self._signal_branches()
        titles = {branch.title for branch in branches}
        self.assertIn("Validation profile has source-observed tests outside compact lanes", titles)
        self.assertNotIn("Resolve self-check failures in control status", titles)

    def test_sync_resolves_stale_generic_self_check_when_typed_branch_owns_alert(self) -> None:
        self.service.ingest_signal(
            {
                "source": "self_check",
                "signal_class": "governance_pressure",
                "title": "Resolve self-check failures in control status",
                "fingerprint": {
                    "class": "governance_pressure",
                    "surface": "self_check",
                    "error": "self_check_failures",
                    "symbol": "control_status",
                },
                "payload": {
                    "pass_ratio": 0.91,
                    "alerts": ["test_profile_inventory:drift=1;gaps=0;source_observed=1;inactive_install_profile=0"],
                },
                "severity": "high",
                "actionability": "blocked",
                "next_task": "Confirm failing self-check probes and route each probe to root-cause branch",
            }
        )
        status_payload = {
            "alerts": ["test_profile_inventory:drift=1;gaps=0;source_observed=1;inactive_install_profile=0"],
            "self_check_pass_ratio": 0.91,
            "test_profile_inventory_ok": False,
            "test_profile_profile_gap_count": 0,
            "test_profile_profile_drift_count": 1,
            "test_profile_source_observed_count": 1,
            "test_profile_inventory": {
                "ok": False,
                "profile_drift_count": 1,
                "source_observed_count": 1,
                "profile_drift_tests": [
                    {
                        "path": "tests/test_evidence_validity.py",
                        "profile_class": "source_observed",
                    }
                ],
            },
        }

        self.service.sync_status_snapshot(status_payload)

        branches = self._signal_branches()
        self_check = [branch for branch in branches if str(branch.source_type or "") == "self_check"][0]
        self.assertEqual(getattr(self_check.status, "value", self_check.status), "complete")
        self.assertEqual(str(self_check.resolution_state or ""), "resolved")
        self.assertTrue(any(str(branch.source_type or "") == "test_ecosystem" for branch in branches))

    def test_status_snapshot_ingests_direct_control_runtime_fields(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "search_provider": "searxng",
            "searxng_ok": False,
            "searxng_note": "connection refused",
            "guard": {"running": False},
            "core": {"running": True},
            "webui": {"running": True},
            "core_heartbeat_age_sec": 42,
            "maintenance_scheduler_active": False,
            "maintenance_scheduler_mode": "inactive",
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertGreaterEqual(len([item for item in results if item.get("action") == "created"]), 4)
        branches = self._signal_branches()
        titles = {branch.title for branch in branches}
        self.assertIn("SearXNG search dependency unreachable", titles)
        self.assertIn("Guard process is not running", titles)
        self.assertIn("Core heartbeat is stale in control status", titles)
        self.assertIn("Maintenance scheduler is inactive", titles)
        by_title = {branch.title: branch for branch in branches}
        self.assertEqual(str(by_title["SearXNG search dependency unreachable"].source_type or ""), "web_search")
        self.assertEqual(by_title["SearXNG search dependency unreachable"].preferred_tool, "web_search")
        self.assertEqual(str(by_title["Guard process is not running"].source_type or ""), "runtime_core")
        self.assertEqual(by_title["Guard process is not running"].preferred_tool, "pulse")
        self.assertEqual(str(by_title["Core heartbeat is stale in control status"].source_type or ""), "runtime_core")
        self.assertEqual(str(by_title["Maintenance scheduler is inactive"].source_type or ""), "scheduler_registry")
        self.assertEqual(by_title["Maintenance scheduler is inactive"].preferred_tool, "queue_status")

    def test_status_snapshot_ingests_remaining_owned_source_root_surfaces(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "backend_commands": "unreadable",
            "backend_command_count": 0,
            "operator_outbox": {"ok": True, "open_count": 1},
            "operator_outbox_open_count": 1,
            "operator_outbox_latest_open_id": "outbox-1",
            "web_enabled": True,
            "allow_domains_count": 0,
            "patch_enabled": True,
            "patch_strict_manifest": False,
            "chat_login_enabled": True,
            "chat_users_count": 0,
            "chat_auth_source": "",
            "memory_enabled": True,
            "memory_health": {
                "status": "watch",
                "identity": {"exists": False},
                "learned_facts": {"exists": False},
            },
            "action_ledger_total": 1,
            "last_intent": "synthetic",
            "last_planner_decision": "fulfillment_plan",
            "last_route_summary": "",
            "last_route_grounded": False,
            "last_action_final_answer": "",
            "last_action_tool": "weather_current_location",
            "last_route_trace": [
                {"stage": "intent_router", "status": "failed", "detail": "synthetic route issue"},
                {"stage": "supervisor_fulfillment", "status": "failed", "detail": "synthetic handoff issue"},
                {"stage": "finalize_reply", "status": "failed", "detail": "synthetic reply issue"},
                {"stage": "weather_location", "status": "failed", "detail": "synthetic weather issue"},
            ],
            "retrieval_knowledge_status": "failed",
            "knowledge_used": True,
            "knowledge_chars": 0,
            "weather_source_host": "",
            "installer_packaging_status": "stale",
            "release_status": {
                "ok": True,
                "latest_readiness_state": "ready",
                "latest_ready_to_ship": True,
                "latest_artifact_name": "nova-rc.zip",
            },
            "tts_status": "missing",
            "voice_runtime_requested": True,
            "voice_runtime_ok": True,
            "safety_enabled": True,
            "pending_review_total": 1,
            "quarantine_total": 0,
            "requests_total": 1,
            "errors_total": 2,
            "health_score": 85,
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertGreaterEqual(len([item for item in results if item.get("action") == "created"]), 15)
        by_source = {str(branch.source_type or ""): branch for branch in self._signal_branches()}
        expected_sources = {
            "frontdoor_cli",
            "operator_control",
            "policy_gates",
            "session_identity_auth",
            "identity_profile_answers",
            "conversation_routing",
            "supervisor_fulfillment",
            "reply_quality_contracts",
            "retrieval_knowledge",
            "weather_location",
            "installer_packaging",
            "tts_audio_output",
            "safety_envelope",
            "metrics_ops_journal",
            "core_steward_reflection",
        }
        self.assertFalse(expected_sources - set(by_source))
        self.assertEqual(by_source["operator_control"].actionability, "blocked")
        identity_tasks = work_tree.list_branch_tasks(by_source["identity_profile_answers"].branch_id)
        self.assertIn("Read memory routing purpose controls", identity_tasks[0].title)
        self.assertEqual(by_source["safety_envelope"].preferred_tool, "phase2_audit")
        self.assertEqual(by_source["core_steward_reflection"].preferred_tool, "core_health")

    def test_installer_packaging_gap_routes_to_installer_validation_tool(self) -> None:
        status_payload = {
            "installer_release_status": {"latest_readiness_state": "no-builds", "latest_ready_to_ship": False},
            "release_status": {
                "ok": True,
                "latest_readiness_state": "ready-with-notes",
                "latest_ready_to_ship": True,
                "latest_artifact_name": "nova-rc.zip",
                "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
            },
        }

        self.service.sync_status_snapshot(status_payload)

        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "installer_packaging")
        installer_task = None
        for _ in range(5):
            open_tasks = [
                task for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
            ]
            self.assertEqual(len(open_tasks), 1)
            task = open_tasks[0]
            if task.title == "Run installer validation from current release package":
                installer_task = task
                break
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=str(task.meta.get("expected_tool") or "read"),
                tool_args=list(task.meta.get("tool_args") or []),
                result=f"{task.title} evidence",
            )
            work_tree.mark_task_complete(task.task_id)
            self.service.sync_status_snapshot(status_payload)
        self.assertIsNotNone(installer_task)
        self.assertEqual(installer_task.meta.get("expected_tool"), "installer_validation_run")
        branch = work_tree.get_branch(branch.branch_id)
        self.assertIn("installer_validation_run", branch.allowed_tools)

    def test_installer_packaging_ready_status_resolves_branch(self) -> None:
        open_payload = {
            "installer_release_status": {"latest_readiness_state": "no-builds", "latest_ready_to_ship": False},
            "release_status": {
                "ok": True,
                "latest_readiness_state": "ready",
                "latest_ready_to_ship": True,
                "latest_artifact_name": "nova-rc.zip",
            },
        }
        ready_payload = {
            "installer_release_status": {
                "latest_readiness_state": "ready-with-notes",
                "latest_ready_to_ship": True,
                "latest_source_package_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
            },
            "release_status": {
                "ok": True,
                "latest_readiness_state": "ready",
                "latest_ready_to_ship": True,
                "latest_artifact_name": "nova-rc.zip",
                "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
            },
        }

        self.service.sync_status_snapshot(open_payload)
        self.service.sync_status_snapshot(ready_payload)

        branch = self._signal_branches()[0]
        self.assertEqual(branch.resolution_state, "resolved")

    def test_installer_packaging_ready_status_reopens_when_built_from_previous_package(self) -> None:
        status_payload = {
            "installer_release_status": {
                "latest_readiness_state": "ready-with-notes",
                "latest_ready_to_ship": True,
                "latest_source_package_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc-old.zip",
            },
            "release_status": {
                "ok": True,
                "latest_readiness_state": "ready",
                "latest_ready_to_ship": True,
                "latest_artifact_name": "nova-rc-new.zip",
                "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc-new.zip",
            },
        }

        self.service.sync_status_snapshot(status_payload)

        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "installer_packaging")
        self.assertEqual(branch.resolution_state, "open")
        self.assertFalse(branch.source_payload.get("installer_matches_current_release"))
        self.assertEqual(
            branch.source_payload.get("installer_source_package_artifact_path"),
            "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc-old.zip",
        )

    def test_operator_outbox_open_work_uses_stable_blocked_branch(self) -> None:
        first = {
            "operator_outbox": {"ok": True, "open_count": 1},
            "operator_outbox_open_count": 1,
            "operator_outbox_latest_open_id": "outbox-1",
        }
        second = {
            "operator_outbox": {"ok": True, "open_count": 2},
            "operator_outbox_open_count": 2,
            "operator_outbox_latest_open_id": "outbox-2",
        }

        self.service.sync_status_snapshot(first)
        self.service.sync_status_snapshot(second)

        branches = self._signal_branches()
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.source_key, "operator_requested:operator_control:operator_outbox_open:operator_outbox")
        self.assertEqual(branch.status, work_tree.BranchStatus.BLOCKED)
        self.assertEqual(branch.allowed_tools, [])
        self.assertIsNone(branch.preferred_tool)
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(len(open_tasks), 1)
        self.assertEqual(open_tasks[0].status, work_tree.TaskStatus.BLOCKED)
        self.assertIn("Wait for operator response", open_tasks[0].title)
        self.assertNotIn("runtime/operator_outbox.jsonl", json.dumps(open_tasks[0].meta))

    def test_find_task_contracts_do_not_use_space_joined_paths(self) -> None:
        source = Path("services/work_tree_signal_ingestion.py").read_text(encoding="utf-8")

        self.assertNotIn('"services docs scripts"', source)
        self.assertNotIn('"services tools tests"', source)
        self.assertNotIn('"services work_tree.py"', source)

    def test_source_root_sequence_reaches_judgment_after_evidence_tasks(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "action_ledger_total": 1,
            "last_intent": "synthetic",
            "last_planner_decision": "",
            "last_route_summary": "",
            "last_route_trace": [
                {"stage": "intent_router", "status": "failed", "detail": "synthetic route issue"},
            ],
        }

        self.service.sync_status_snapshot(status_payload)
        branch = self._signal_branches()[0]

        for _ in range(6):
            open_tasks = [
                task for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
            ]
            self.assertTrue(open_tasks)
            task = open_tasks[0]
            if task.title == "Synthesize source-root judgment from collected evidence":
                break
            expected_tool = str((task.meta or {}).get("expected_tool") or "read")
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=expected_tool,
                tool_args=list((task.meta or {}).get("tool_args") or []),
                result={"ok": True, "evidence": task.title},
            )
            work_tree.mark_task_complete(task.task_id)
            self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks[0].title, "Synthesize source-root judgment from collected evidence")
        self.assertEqual((open_tasks[0].meta or {}).get("expected_tool"), "source_root_judgment")

    def test_active_source_signal_restarts_sequence_after_open_resolution_completion(self) -> None:
        status_payload = {
            "search_provider": "searxng",
            "searxng_ok": False,
            "search_api_endpoint": "http://127.0.0.1:8081/search",
            "searxng_note": "connection refused",
        }

        self.service.sync_status_snapshot(status_payload)
        branch = self._signal_branches()[0]
        completed_titles: list[str] = []

        for _ in range(8):
            open_tasks = [
                task for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
            ]
            self.assertTrue(open_tasks)
            task = open_tasks[0]
            expected_tool = str((task.meta or {}).get("expected_tool") or "read")
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=expected_tool,
                tool_args=list((task.meta or {}).get("tool_args") or []),
                result={"ok": True, "evidence": task.title},
            )
            work_tree.mark_task_complete(task.task_id)
            completed_titles.append(task.title)
            if task.title == "Synthesize source-root judgment from collected evidence":
                break
            self.service.sync_status_snapshot(status_payload)

        self.assertIn("Synthesize source-root judgment from collected evidence", completed_titles)
        self.assertEqual(work_tree.get_branch(branch.branch_id).resolution_state, "open")
        self.assertEqual(work_tree.get_branch(branch.branch_id).status, work_tree.BranchStatus.COMPLETE)

        self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks[0].title, "Probe configured web search route through web_search tool")
        self.assertEqual((open_tasks[0].meta or {}).get("expected_tool"), "web_search")
        self.assertEqual(work_tree.get_branch(branch.branch_id).status, work_tree.BranchStatus.READY)

    def test_source_root_sequence_routes_failed_evidence_to_judgment(self) -> None:
        status_payload = {
            "search_provider": "searxng",
            "searxng_ok": False,
            "search_api_endpoint": "http://127.0.0.1:8081/search",
            "searxng_note": "connection refused",
        }

        self.service.sync_status_snapshot(status_payload)
        branch = self._signal_branches()[0]
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks[0].title, "Probe configured web search route through web_search tool")
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=open_tasks[0].task_id,
            tool_name="web_search",
            tool_args=["nova runtime search dependency probe"],
            result="[FAIL] Local web search backend is unavailable.",
        )

        self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        dropped_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status == work_tree.TaskStatus.DROPPED
        ]
        self.assertEqual(open_tasks[0].title, "Synthesize source-root judgment from collected evidence")
        self.assertEqual((open_tasks[0].meta or {}).get("expected_tool"), "source_root_judgment")
        self.assertEqual(dropped_tasks[0].title, "Probe configured web search route through web_search tool")

        judgment_task = open_tasks[0]
        work_tree.record_task_evidence(
            branch_id=branch.branch_id,
            task_id=judgment_task.task_id,
            tool_name="source_root_judgment",
            tool_args=[branch.branch_id],
            result="Source Root Judgment\n- verdict: evidence_failed\n- operator_outbox: needed (failed_evidence)",
        )
        work_tree.mark_task_complete(judgment_task.task_id)

        self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks[0].title, "Hold source-root branch for operator/tool failure judgment")
        self.assertEqual(open_tasks[0].status, work_tree.TaskStatus.BLOCKED)

        self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(len(open_tasks), 1)
        self.assertEqual(open_tasks[0].title, "Hold source-root branch for operator/tool failure judgment")
        self.assertEqual(open_tasks[0].status, work_tree.TaskStatus.BLOCKED)
        self.assertEqual(
            (open_tasks[0].meta or {}).get("blocked_reason"),
            "source_root_failed_evidence_operator_judgment_required",
        )

    def test_self_repair_inventory_alias_reaches_source_root_judgment(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "self_repair_closure_inventory": {
                "gap_count": 1,
                "proof_scope": "source_contract",
                "roots": [
                    {
                        "root_id": "runtime_core",
                        "label": "Runtime core",
                        "ok": False,
                        "closure_depth": "execution_wired",
                        "gaps": ["missing_judgment_path"],
                        "source_files": ["nova_core.py"],
                        "missing_evidence_paths": [],
                        "missing_judgment_paths": ["source_root_judgment"],
                        "missing_closure_paths": [],
                        "missing_operator_outbox_paths": [],
                        "missing_owned_root_routes": [],
                    }
                ],
            },
        }

        self.service.sync_status_snapshot(status_payload)
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "self_repair_closure_inventory")

        for _ in range(5):
            open_tasks = [
                task for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
            ]
            self.assertTrue(open_tasks)
            task = open_tasks[0]
            if task.title == "Synthesize source-root judgment from collected evidence":
                break
            expected_tool = str((task.meta or {}).get("expected_tool") or "read")
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=expected_tool,
                tool_args=list((task.meta or {}).get("tool_args") or []),
                result={"ok": True, "evidence": task.title},
            )
            work_tree.mark_task_complete(task.task_id)
            self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks[0].title, "Synthesize source-root judgment from collected evidence")
        self.assertEqual((open_tasks[0].meta or {}).get("expected_tool"), "source_root_judgment")

    def test_source_wiring_probe_gap_becomes_work_tree_pressure(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "source_wiring_probe_ok": False,
            "source_wiring_probe_gap_count": 1,
            "source_wiring_probe": {
                "ok": False,
                "gap_count": 1,
                "missing_required_judgment_paths": ["source_root_judgment"],
            },
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "source_wiring_probe")
        self.assertEqual(str(branch.work_class or ""), "governance_pressure")
        self.assertEqual(str(branch.actionability or ""), "safe_now")
        self.assertIn("source_wiring_probe_gap", str(branch.source_key or ""))
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        self.assertEqual(tasks[0].meta.get("tool_args"), ["services/nova_wiring_inventory.py"])

    def test_source_wiring_probe_gap_resolves_when_probe_is_clean(self) -> None:
        failing = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "source_wiring_probe_ok": False,
            "source_wiring_probe_gap_count": 1,
            "source_wiring_probe": {
                "ok": False,
                "gap_count": 1,
                "missing_required_closure_paths": ["signal_branch_resolution"],
            },
        }
        clear = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "source_wiring_probe_ok": True,
            "source_wiring_probe_gap_count": 0,
            "source_wiring_probe": {"ok": True, "gap_count": 0},
        }

        self.service.sync_status_snapshot(failing)
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "source_wiring_probe")

        results = self.service.sync_status_snapshot(clear)

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.resolution_state or ""), "resolved")
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)

    def test_status_snapshot_ingests_blocked_generated_queue_pressure(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "generated_queue_status": "blocked",
            "queue_open_count": 2,
            "queue_actionable_count": 0,
            "queue_blocked_count": 2,
            "queue_blocked_reason_counts": {"parity_drift_locked": 2},
            "queue_blocked_files": ["drift_a.json", "drift_b.json"],
            "generated_work_queue": {
                "status": "blocked",
                "open_count": 2,
                "actionable_count": 0,
                "blocked_count": 2,
            },
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Generated Work Queue is blocked with no actionable session")
        self.assertEqual(str(branch.source_type or ""), "generated_queue")
        self.assertEqual(str(branch.work_class or ""), "maintenance_pressure")
        self.assertEqual(str(branch.source_key or ""), "maintenance_pressure:generated_queue:generated_queue_blocked:parity_drift_locked")
        self.assertEqual(branch.preferred_tool, "queue_status")
        self.assertEqual(branch.allowed_tools, ["queue_status", "read", "find"])
        self.assertEqual(branch.source_payload.get("queue_blocked_files"), ["drift_a.json", "drift_b.json"])

    def test_status_snapshot_resolves_blocked_generated_queue_pressure_when_actionable(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "generated_queue_status": "blocked",
                "queue_open_count": 1,
                "queue_actionable_count": 0,
                "queue_blocked_count": 1,
                "queue_blocked_reason_counts": {"parity_drift_locked": 1},
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "generated_queue_status": "actionable",
                "queue_open_count": 1,
                "queue_actionable_count": 1,
                "queue_blocked_count": 0,
                "queue_blocked_reason_counts": {},
            }
        )

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "generated_queue")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")

    def test_status_snapshot_ingests_current_tool_error(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "tool_events_error_count": 1,
            "tool_events_failure_count": 1,
            "last_tool_error_summary": "filesystem: Not a file: C:\\NOVA\\bad-task",
            "last_tool_error_ts": 123,
            "last_tool_error_age_sec": 4,
            "last_tool_error_stale": False,
            "last_tool_name": "filesystem",
            "last_tool_status": "error",
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Tool execution has a current error event")
        self.assertEqual(str(branch.source_type or ""), "tool_evidence")
        self.assertEqual(str(branch.work_class or ""), "runtime_failure")
        self.assertEqual(str(branch.source_key or ""), "runtime_failure:tool_evidence:tool_execution_error:filesystem")
        self.assertEqual(branch.preferred_tool, "read")
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        self.assertEqual(task.meta.get("tool_args"), ["runtime/tool_events.jsonl"])

    def test_status_snapshot_resolves_tool_error_when_stale(self) -> None:
        active_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "tool_events_error_count": 1,
            "tool_events_failure_count": 1,
            "last_tool_error_summary": "filesystem: old miss",
            "last_tool_error_ts": 10,
            "last_tool_error_stale": False,
            "last_tool_name": "filesystem",
            "last_tool_status": "error",
        }
        self.service.sync_status_snapshot(active_payload)

        stale_payload = dict(active_payload)
        stale_payload["last_tool_error_stale"] = True
        stale_payload["last_tool_status"] = "ok"
        results = self.service.sync_status_snapshot(stale_payload)

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "tool_evidence")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")

    def test_status_snapshot_ingests_os_capability_ledger_issue(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "os_capability_ledger_ok": False,
            "os_capability_ledger_readable_ok": True,
            "os_capability_ledger_total": 2,
            "os_capability_ledger_current_issue_count": 1,
            "os_capability_ledger_current_blocked_count": 1,
            "os_capability_ledger_current_failure_count": 0,
            "os_capability_ledger_current_timeout_count": 0,
            "os_capability_ledger_current_operator_outbox_count": 1,
            "os_capability_ledger_path": "C:\\NOVA\\runtime\\os_capability_ledger.jsonl",
            "last_os_capability_issue": {
                "capability": "verify_ollama_model",
                "status": "blocked",
                "reason": "contract_stale",
                "operator_outbox": True,
            },
            "os_capability_ledger": {
                "ok": False,
                "readable_ok": True,
                "count": 2,
                "current_issue_count": 1,
                "current_issue_rows": [
                    {
                        "capability": "verify_ollama_model",
                        "status": "blocked",
                        "reason": "contract_stale",
                        "operator_outbox": True,
                    }
                ],
            },
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "OS capability contract drift is blocking execution")
        self.assertEqual(str(branch.source_type or ""), "tool_registry_policy")
        self.assertEqual(str(branch.work_class or ""), "maintenance_pressure")
        self.assertEqual(str(branch.source_key or ""), "maintenance_pressure:tool_registry_policy:contract_stale:verify_ollama_model")
        self.assertEqual(branch.preferred_tool, "read")
        self.assertEqual(branch.allowed_tools, ["read"])
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        self.assertEqual(task.meta.get("tool_args"), ["runtime/os_capability_ledger.jsonl"])

    def test_status_snapshot_resolves_os_capability_ledger_issue_when_capability_runs_clean(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "os_capability_ledger_ok": False,
                "os_capability_ledger_readable_ok": True,
                "os_capability_ledger_current_issue_count": 1,
                "last_os_capability_issue": {
                    "capability": "verify_ollama_model",
                    "status": "blocked",
                    "reason": "contract_stale",
                },
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "os_capability_ledger_ok": True,
                "os_capability_ledger_readable_ok": True,
                "os_capability_ledger_total": 3,
                "os_capability_ledger_current_issue_count": 0,
                "os_capability_ledger": {
                    "ok": True,
                    "readable_ok": True,
                    "count": 3,
                    "current_issue_count": 0,
                    "current_issue_rows": [],
                },
            }
        )

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "tool_registry_policy")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")

    def test_status_snapshot_ingests_ollama_chat_route_gap(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "ollama_api_up": False,
            "ollama_tags_ok": True,
            "ollama_chat_route_ok": False,
            "ollama_version": "0.0.0-old",
            "ollama_version_ok": True,
            "ollama_api_contract_status": "chat_api_missing_or_incompatible",
            "ollama_health_status": "chat_route_unreachable",
            "ollama_health_info": "version=0.0.0-old;tags=200;chat_route=404",
            "ollama_health": {
                "ok": False,
                "status": "chat_route_unreachable",
                "tags_ok": True,
                "chat_route_ok": False,
                "tags_status": 200,
                "chat_route_status": 404,
                "version": "0.0.0-old",
                "version_ok": True,
                "api_contract_status": "chat_api_missing_or_incompatible",
            },
            "port_ownership": {
                "ok": True,
                "status": "ok",
                "ports": {
                    "11434": {
                        "service": "ollama",
                        "port": 11434,
                        "listening": True,
                        "listener_count": 1,
                        "expected_owner_present": True,
                        "owners": [{"pid": 123, "name": "ollama.exe"}],
                    }
                },
            },
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Ollama chat API/version contract unavailable while tags endpoint responds")
        self.assertEqual(str(branch.work_class or ""), "dependency_unreachable")
        self.assertEqual(str(branch.actionability or ""), "safe_now")
        self.assertEqual(str(branch.source_type or ""), "model_runtime")
        self.assertEqual(str(branch.source_key or ""), "dependency_unreachable:model_runtime:ollama_chat_route_unreachable:ollama")
        self.assertEqual(((branch.source_payload.get("ollama_port_ownership") or {}).get("listener_count")), 1)
        self.assertEqual(branch.source_payload.get("ollama_version"), "0.0.0-old")
        self.assertEqual(branch.source_payload.get("ollama_api_contract_status"), "chat_api_missing_or_incompatible")
        self.assertEqual(branch.preferred_tool, "os_capability")
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        self.assertEqual(task.meta.get("expected_tool"), "os_capability")
        request = json.loads(task.meta["tool_args"][0])
        self.assertEqual(request["capability"], "verify_ollama_model")
        self.assertTrue(request["args"]["probe_chat"])

    def test_status_snapshot_ingests_ollama_model_missing_gap(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "chat_model": "llama3.1:8b",
            "ollama_api_up": False,
            "ollama_tags_ok": True,
            "ollama_chat_route_ok": True,
            "ollama_model_available": False,
            "ollama_configured_model": "llama3.1:8b",
            "ollama_model_status": "missing",
            "ollama_available_models": ["llama3.2:3b", "qwen2.5vl:7b"],
            "ollama_health_status": "chat_model_missing",
            "ollama_health_info": "tags=200;chat_route=400;chat_model=llama3.1:8b;model_status=missing",
            "ollama_health": {
                "ok": False,
                "status": "chat_model_missing",
                "tags_ok": True,
                "chat_route_ok": True,
                "model_available": False,
                "model_status": "missing",
                "chat_model": "llama3.1:8b",
                "available_models": ["llama3.2:3b", "qwen2.5vl:7b"],
            },
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Ollama configured chat model is not installed")
        self.assertEqual(str(branch.work_class or ""), "dependency_unreachable")
        self.assertEqual(str(branch.source_type or ""), "model_runtime")
        self.assertEqual(str(branch.source_key or ""), "dependency_unreachable:model_runtime:ollama_chat_model_missing:ollama")
        self.assertEqual(branch.source_payload.get("ollama_configured_model"), "llama3.1:8b")
        self.assertFalse(branch.source_payload.get("ollama_model_available"))
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        request = json.loads(task.meta["tool_args"][0])
        self.assertEqual(request["capability"], "verify_ollama_model")
        self.assertEqual(request["args"]["model"], "llama3.1:8b")

    def test_status_snapshot_ingests_llm_reply_error_despite_green_ollama(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "ollama_api_up": True,
            "ollama_server_ok": True,
            "ollama_tags_ok": True,
            "ollama_chat_route_ok": True,
            "ollama_model_available": True,
            "ollama_chat_ready": True,
            "ollama_configured_model": "llama3.2:3b",
            "ollama_health": {
                "ok": True,
                "server_ok": True,
                "status": "ok",
                "chat_model": "llama3.2:3b",
                "model_available": True,
            },
            "last_planner_decision": "llm_fallback",
            "last_route_summary": "input:received -> llm_call:started -> finalize:llm_fallback",
            "last_action_final_answer": "(error: LLM service unavailable)",
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Last LLM reply failed despite healthy Ollama probes")
        self.assertEqual(str(branch.work_class or ""), "dependency_unreachable")
        self.assertEqual(str(branch.source_type or ""), "model_runtime")
        self.assertEqual(str(branch.source_key or ""), "dependency_unreachable:action_ledger:llm_reply_failed_after_healthy_probe:ollama")
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        request = json.loads(task.meta["tool_args"][0])
        self.assertEqual(request["capability"], "verify_ollama_model")
        self.assertTrue(request["args"]["probe_chat"])

    def test_status_snapshot_resolves_model_runtime_gap_when_ollama_contract_clears(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "chat_model": "llama3.2:3b",
                "ollama_api_up": False,
                "ollama_tags_ok": True,
                "ollama_chat_route_ok": True,
                "ollama_model_available": False,
                "ollama_configured_model": "llama3.2:3b",
                "ollama_health": {
                    "ok": False,
                    "tags_ok": True,
                    "chat_route_ok": True,
                    "model_available": False,
                    "chat_model": "llama3.2:3b",
                },
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "chat_model": "llama3.2:3b",
                "ollama_api_up": True,
                "ollama_server_ok": True,
                "ollama_tags_ok": True,
                "ollama_chat_route_ok": True,
                "ollama_model_available": True,
                "ollama_chat_ready": True,
                "ollama_configured_model": "llama3.2:3b",
                "ollama_health": {
                    "ok": True,
                    "server_ok": True,
                    "tags_ok": True,
                    "chat_route_ok": True,
                    "model_available": True,
                    "chat_model": "llama3.2:3b",
                },
            }
        )

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "model_runtime")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")

    def test_status_snapshot_ingests_validation_artifact_truth_gap(self) -> None:
        status_payload = {
            "alerts": [
                "validation_artifact_truth:llm_unavailable_in_green_regression;failures=2;llm_unavailable=2;hidden_by_green_regression=True"
            ],
            "self_check_pass_ratio": 0.97,
            "validation_artifact_truth": {
                "ok": False,
                "status": "llm_unavailable_in_green_regression",
                "action_dir": "runtime/validation/actions",
                "current_window_failure_count": 2,
                "current_window_llm_unavailable_count": 2,
                "hidden_by_green_regression": True,
                "latest_regression_status": "OK",
                "latest_regression_at": "2026-05-15 00:08:43",
                "latest_failure": {
                    "path": "runtime/validation/actions/2026-05-15_00-08-13_435_643dfb19.json",
                    "failure_kind": "llm_service_unavailable",
                    "final_answer": "(error: LLM service unavailable)",
                    "route_summary": "input:received -> llm_call:started -> finalize:llm_fallback",
                },
            },
            "validation_artifact_truth_ok": False,
            "validation_artifact_truth_status": "llm_unavailable_in_green_regression",
            "validation_artifact_failure_count": 2,
            "validation_artifact_llm_unavailable_count": 2,
            "validation_artifact_hidden_by_green_regression": True,
            "validation_artifact_latest_failure": {
                "path": "runtime/validation/actions/2026-05-15_00-08-13_435_643dfb19.json",
                "failure_kind": "llm_service_unavailable",
            },
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branches = self._signal_branches()
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Validation artifacts recorded LLM failure under green regression")
        self.assertEqual(str(branch.source_type or ""), "test_ecosystem")
        self.assertEqual(str(branch.work_class or ""), "regression_failure")
        self.assertEqual(
            str(branch.source_key or ""),
            "regression_failure:test_ecosystem:llm_unavailable_hidden_by_green_regression:llm_service_unavailable",
        )
        self.assertEqual(branch.source_payload.get("failure_count"), 2)
        signal = _validation_artifact_truth_signal_from_status(status_payload)
        read_steps = [
            item
            for item in list((signal or {}).get("task_sequence") or [])
            if item.get("preferred_tool") == "read"
        ]
        self.assertTrue(read_steps)
        self.assertTrue(all(len(item.get("tool_args") or []) == 1 for item in read_steps))
        self.assertEqual(
            (signal or {}).get("blocked_reason"),
            "validation_artifact_failure_requires_new_regression_evidence",
        )

    def test_status_snapshot_ingests_missing_validation_artifact_directory_as_missing_evidence(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 0.97,
            "validation_artifact_truth": {
                "ok": False,
                "status": "validation_actions_missing",
                "truth_state": "unknown",
                "missing_artifact": True,
                "action_dir": "runtime/validation/actions",
                "action_count": 0,
                "current_window_failure_count": 0,
                "current_window_llm_unavailable_count": 0,
                "hidden_by_green_regression": False,
                "latest_regression_status": "OK",
                "latest_regression_at": "2026-05-15 00:08:43",
            },
            "validation_artifact_truth_ok": False,
            "validation_artifact_truth_status": "validation_actions_missing",
            "validation_artifact_failure_count": 0,
            "validation_artifact_llm_unavailable_count": 0,
            "validation_artifact_hidden_by_green_regression": False,
            "validation_artifact_latest_failure": {},
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branches = self._signal_branches()
        self.assertEqual(len(branches), 1)
        branch = branches[0]
        self.assertEqual(branch.title, "Validation action artifact directory is missing")
        self.assertEqual(
            str(branch.source_key or ""),
            "regression_failure:test_ecosystem:validation_actions_missing:validation_actions",
        )
        self.assertTrue(branch.source_payload.get("missing_artifact"))
        signal = _validation_artifact_truth_signal_from_status(status_payload)
        self.assertEqual((signal or {}).get("blocked_reason"), "validation_action_evidence_missing")
        steps = list((signal or {}).get("task_sequence") or [])
        self.assertTrue(any(item.get("preferred_tool") == "ls" for item in steps))
        self.assertFalse(
            any(
                item.get("preferred_tool") == "find"
                and list(item.get("tool_args") or []) == ["runtime/validation/actions", "(error:"]
                for item in steps
            )
        )

    def test_sync_status_snapshot_resolves_validation_artifact_truth_gap_when_clear(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "validation_artifact_truth": {
                    "ok": False,
                    "status": "llm_unavailable_in_green_regression",
                    "current_window_failure_count": 1,
                    "current_window_llm_unavailable_count": 1,
                    "hidden_by_green_regression": True,
                    "latest_failure": {
                        "path": "runtime/validation/actions/bad.json",
                        "failure_kind": "llm_service_unavailable",
                    },
                },
                "validation_artifact_truth_ok": False,
                "validation_artifact_failure_count": 1,
                "validation_artifact_llm_unavailable_count": 1,
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "validation_artifact_truth": {
                    "ok": True,
                    "status": "ok",
                    "current_window_failure_count": 0,
                    "current_window_llm_unavailable_count": 0,
                },
                "validation_artifact_truth_ok": True,
                "validation_artifact_failure_count": 0,
                "validation_artifact_llm_unavailable_count": 0,
            }
        )

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "test_ecosystem")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")

    def test_status_snapshot_ingests_ollama_port_owner_mismatch(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "ollama_api_up": True,
            "ollama_tags_ok": True,
            "ollama_chat_route_ok": True,
            "port_ownership": {
                "ok": False,
                "status": "watch",
                "issue_count": 1,
                "ports": {
                    "11434": {
                        "service": "ollama",
                        "port": 11434,
                        "listening": True,
                        "listener_count": 1,
                        "expected_owner_present": False,
                        "owners": [{"pid": 456, "name": "python.exe", "cmdline": ["python", "other.py"]}],
                    }
                },
            },
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Ollama port is owned by an unexpected process")
        self.assertEqual(str(branch.source_type or ""), "model_runtime")
        self.assertEqual(str(branch.source_key or ""), "dependency_unreachable:model_runtime:ollama_port_owner_mismatch:ollama")
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        request = json.loads(task.meta["tool_args"][0])
        self.assertEqual(request["capability"], "inspect_ports")
        self.assertEqual(request["args"]["ports"], [11434])

    def test_status_snapshot_ingests_requested_voice_dependency_gap(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "voice_status": {
                "ok": False,
                "status": "disabled",
                "requested": True,
                "import_error": "No module named 'sounddevice'",
                "sounddevice_available": False,
                "wav_available": False,
                "whisper_available": False,
            },
            "voice_runtime_status": "disabled",
            "voice_runtime_requested": True,
            "voice_runtime_ok": False,
            "voice_import_error": "No module named 'sounddevice'",
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Voice runtime dependency unavailable after voice was requested")
        self.assertEqual(str(branch.source_type or ""), "voice")
        self.assertEqual(str(branch.work_class or ""), "dependency_unreachable")
        self.assertEqual(str(branch.actionability or ""), "safe_now")
        self.assertEqual(str(branch.source_key or ""), "dependency_unreachable:voice:voice_runtime_unavailable:voice_runtime")
        self.assertEqual(branch.preferred_tool, "read")
        task = work_tree.list_branch_tasks(branch.branch_id)[0]
        self.assertEqual(task.meta.get("tool_args"), ["services/nova_voice_runtime.py"])

    def test_status_snapshot_does_not_treat_unrequested_voice_as_failure_or_clearance(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "voice_status": {
                    "ok": False,
                    "status": "disabled",
                    "requested": True,
                    "import_error": "No module named 'sounddevice'",
                },
                "voice_runtime_status": "disabled",
                "voice_runtime_requested": True,
                "voice_runtime_ok": False,
            }
        )
        branch = self._signal_branches()[0]

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "voice_status": {
                    "ok": True,
                    "status": "not_initialized",
                    "requested": False,
                    "import_error": "",
                },
                "voice_runtime_status": "not_initialized",
                "voice_runtime_requested": False,
                "voice_runtime_ok": True,
            }
        )

        self.assertFalse(any(item.get("action") == "resolved" for item in results))
        branch = work_tree.get_branch(branch.branch_id)
        self.assertEqual(str(branch.source_type or ""), "voice")
        self.assertEqual(str(branch.resolution_state or ""), "open")

    def test_status_snapshot_resolves_voice_dependency_gap_when_requested_voice_loads(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "voice_status": {
                    "ok": False,
                    "status": "disabled",
                    "requested": True,
                    "import_error": "No module named 'sounddevice'",
                },
                "voice_runtime_status": "disabled",
                "voice_runtime_requested": True,
                "voice_runtime_ok": False,
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "voice_status": {
                    "ok": True,
                    "status": "ok",
                    "requested": True,
                    "import_error": "",
                    "sounddevice_available": True,
                    "wav_available": True,
                    "whisper_available": True,
                },
                "voice_runtime_status": "ok",
                "voice_runtime_requested": True,
                "voice_runtime_ok": True,
            }
        )

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "voice")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)

    def test_status_snapshot_ingests_vision_dependency_gap(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "vision_status": {
                "ok": False,
                "status": "missing_python_dependency",
                "requested": True,
                "screen_requested": True,
                "camera_requested": True,
                "missing_modules": ["mss", "pillow", "opencv"],
                "vision_model": "qwen2.5vl:7b",
                "vision_model_available": True,
            },
            "vision_runtime_status": "missing_python_dependency",
            "vision_runtime_requested": True,
            "vision_runtime_ok": False,
            "vision_missing_modules": ["mss", "pillow", "opencv"],
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Vision runtime dependency unavailable while vision tools are enabled")
        self.assertEqual(str(branch.source_type or ""), "vision")
        self.assertEqual(str(branch.work_class or ""), "dependency_unreachable")
        self.assertEqual(str(branch.source_key or ""), "dependency_unreachable:vision:vision_runtime_unavailable:vision_runtime")
        self.assertEqual(branch.source_payload.get("vision_missing_modules"), ["mss", "pillow", "opencv"])

    def test_status_snapshot_resolves_vision_dependency_gap_when_requested_vision_loads(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "vision_status": {
                    "ok": False,
                    "status": "missing_python_dependency",
                    "requested": True,
                    "missing_modules": ["mss"],
                },
                "vision_runtime_status": "missing_python_dependency",
                "vision_runtime_requested": True,
                "vision_runtime_ok": False,
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "vision_status": {
                    "ok": True,
                    "status": "ok",
                    "requested": True,
                    "missing_modules": [],
                    "vision_model_available": True,
                },
                "vision_runtime_status": "ok",
                "vision_runtime_requested": True,
                "vision_runtime_ok": True,
            }
        )

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "vision")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)

    def test_status_snapshot_ingests_release_readiness_gap(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "wiring_inventory": {"gap_count": 0},
            "release_status": {
                "ok": True,
                "ledger_path": "C:\\NOVA\\runtime\\exports\\release_packages\\release_ledger.jsonl",
                "latest_state": "built-only",
                "latest_readiness_state": "needs-promotion",
                "latest_ready_to_ship": False,
                "latest_readiness_note": "Latest build was verified, but no validation outcome is recorded yet.",
                "latest_artifact_name": "nova-rc.zip",
                "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
                "latest_verified_at": "2026-05-13T21:33:12-05:00",
                "latest_promoted_at": "",
                "latest_validation_seed_path": "C:\\NOVA\\runtime\\exports\\release_packages\\validation_records\\nova-rc.md",
            },
        }

        results = self.service.sync_status_snapshot(status_payload)

        self.assertTrue(any(item.get("action") == "created" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(branch.title, "Release package is verified but validation outcome is missing")
        self.assertEqual(str(branch.source_type or ""), "release")
        self.assertEqual(str(branch.work_class or ""), "release_readiness_gap")
        self.assertEqual(str(branch.actionability or ""), "safe_now")
        self.assertEqual(str(branch.source_key or ""), "release_readiness_gap:release:release_validation_outcome_missing:nova-rc.zip")
        self.assertEqual(branch.preferred_tool, "read")
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        self.assertEqual(len(tasks), 1)
        self.assertIn("release ledger", tasks[0].title)
        self.assertEqual(tasks[0].meta.get("tool_args"), ["C:\\NOVA\\runtime\\exports\\release_packages\\release_ledger.jsonl"])

    def test_release_readiness_gap_sequences_validation_before_outcome_recording(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "wiring_inventory": {"gap_count": 0},
            "release_status": {
                "ok": True,
                "ledger_path": "C:\\NOVA\\runtime\\exports\\release_packages\\release_ledger.jsonl",
                "latest_state": "built-only",
                "latest_readiness_state": "needs-promotion",
                "latest_ready_to_ship": False,
                "latest_artifact_name": "nova-rc.zip",
                "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
                "latest_validation_seed_path": "C:\\NOVA\\runtime\\exports\\release_packages\\validation_records\\nova-rc.md",
            },
        }

        self.service.sync_status_snapshot(status_payload)
        branch = self._signal_branches()[0]

        def complete_open(tool_name: str) -> None:
            open_tasks = [
                task for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.status != work_tree.TaskStatus.COMPLETE
            ]
            self.assertEqual(len(open_tasks), 1)
            task = open_tasks[0]
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=tool_name,
                tool_args=list(task.meta.get("tool_args") or []),
                result=f"{tool_name} result",
            )
            work_tree.mark_task_complete(task.task_id)

        complete_open("read")
        self.service.sync_status_snapshot(status_payload)
        complete_open("read")
        self.service.sync_status_snapshot(status_payload)
        complete_open("release_validation_run")
        self.service.sync_status_snapshot(status_payload)
        complete_open("release_promotion_judgment")
        self.service.sync_status_snapshot(status_payload)
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(len(open_tasks), 1)
        self.assertIn("Record completed validation outcome", open_tasks[0].title)
        self.assertEqual(open_tasks[0].meta.get("expected_tool"), "release_record_validation_outcome")

        complete_open("release_record_validation_outcome")
        self.service.sync_status_snapshot(status_payload)
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(open_tasks, [])

    def test_release_source_changed_sequences_to_rebuild_verify(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "release_status": {
                "ok": True,
                "ledger_path": "C:\\NOVA\\runtime\\exports\\release_packages\\release_ledger.jsonl",
                "latest_state": "promoted-pass-with-notes",
                "latest_readiness_state": "source-changed-after-build",
                "latest_ready_to_ship": False,
                "latest_readiness_note": "Live source changed after the latest release build.",
                "latest_artifact_name": "nova-rc.zip",
                "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
                "latest_validation_seed_path": "C:\\NOVA\\runtime\\exports\\release_packages\\validation_records\\nova-rc.md",
                "latest_artifact_stale": True,
                "latest_source_status": "changed-after-build",
                "latest_source_changed_after_build": True,
                "latest_source_changed_after_build_count": 3,
                "latest_source_newest_path": "services\\work_tree_signal_ingestion.py",
            },
        }

        self.service.sync_status_snapshot(status_payload)
        branch = self._signal_branches()[0]

        def complete_open(tool_name: str) -> None:
            open_tasks = [
                task for task in work_tree.list_branch_tasks(branch.branch_id)
                if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
            ]
            self.assertEqual(len(open_tasks), 1)
            task = open_tasks[0]
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=tool_name,
                tool_args=list(task.meta.get("tool_args") or []),
                result=f"{tool_name} result",
            )
            work_tree.mark_task_complete(task.task_id)

        complete_open("read")
        self.service.sync_status_snapshot(status_payload)
        complete_open("read")
        self.service.sync_status_snapshot(status_payload)
        complete_open("read")
        self.service.sync_status_snapshot(status_payload)

        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(len(open_tasks), 1)
        self.assertIn("Rebuild and verify release package", open_tasks[0].title)
        self.assertEqual(open_tasks[0].meta.get("expected_tool"), "release_rebuild_verify")
        self.assertEqual(open_tasks[0].meta.get("allowed_tools"), ["release_rebuild_verify"])
        branch = self._signal_branches()[0]
        self.assertEqual(branch.preferred_tool, "release_rebuild_verify")
        self.assertEqual(branch.allowed_tools, ["release_rebuild_verify"])
        self.assertEqual(str(branch.resolution_state or ""), "open")
        self.assertNotEqual(branch.status, work_tree.BranchStatus.COMPLETE)

    def test_status_snapshot_resolves_direct_control_runtime_fields_when_clear(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "search_provider": "searxng",
                "searxng_ok": False,
                "guard": {"running": False},
                "core": {"running": True},
                "webui": {"running": True},
                "maintenance_scheduler_active": False,
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "search_provider": "searxng",
                "searxng_ok": True,
                "guard": {"running": True},
                "core": {"running": True},
                "webui": {"running": True},
                "core_heartbeat_age_sec": 0,
                "maintenance_scheduler_active": True,
            }
        )

        self.assertTrue(any(item.get("action") == "resolved" for item in results))
        self.assertTrue(all(str(branch.resolution_state or "") in {"resolved", "retired"} for branch in self._signal_branches()))

    def test_status_snapshot_ignores_stale_regression_failure(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "autonomy_maintenance": {
                "last_regression_status": "FAILED",
                "last_regression_stale": True,
            },
        }

        results = self.service.ingest_status_snapshot(status_payload)

        classes = {str(branch.work_class or "") for branch in self._signal_branches()}
        self.assertEqual(results, [])
        self.assertNotIn("regression_failure", classes)

    def test_status_snapshot_ingests_memory_health_bootstrap_gap(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "memory_enabled": True,
            "memory_health_status": "watch",
            "memory_health_issue_count": 2,
            "memory_health_issues": [
                {"code": "learned_facts_missing", "detail": "missing learned facts"},
                {"code": "identity_missing", "detail": "missing identity"},
            ],
            "memory_health": {
                "status": "watch",
                "issue_count": 2,
                "bootstrap": {
                    "memory_enabled": True,
                    "status": "incomplete",
                    "missing": ["learned_facts", "identity"],
                },
            },
        }

        results = self.service.ingest_status_snapshot(status_payload)

        created = [item for item in results if str(item.get("action") or "") == "created"]
        self.assertEqual(len(created), 1)
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "memory_identity")
        self.assertEqual(str(branch.source_key or ""), "governance_pressure:memory_identity:memory_bootstrap_incomplete:identity_memory")
        self.assertEqual(str(branch.work_class or ""), "governance_pressure")
        self.assertEqual(str(branch.actionability or ""), "safe_now")
        self.assertEqual(branch.preferred_tool, "pulse")
        self.assertEqual(branch.allowed_tools, ["pulse"])
        self.assertEqual(len(work_tree.list_branch_tasks(branch.branch_id)), 1)
        self.assertIn("learned_facts_missing", branch.source_payload.get("memory_health_issue_codes") or [])

    def test_memory_health_signal_advances_finite_evidence_sequence(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "memory_enabled": True,
            "memory_health_status": "watch",
            "memory_health_issue_count": 1,
            "memory_health_issues": [{"code": "identity_missing", "detail": "missing identity"}],
            "memory_health": {
                "status": "watch",
                "issue_count": 1,
                "bootstrap": {"memory_enabled": True, "status": "incomplete", "missing": ["identity"]},
            },
        }

        self.service.ingest_status_snapshot(status_payload)
        branch = self._signal_branches()[0]
        first_tasks = work_tree.list_branch_tasks(branch.branch_id)
        self.assertEqual(len(first_tasks), 1)
        self.assertIn("Pulse current memory bootstrap evidence", first_tasks[0].title)
        self.assertEqual(branch.preferred_tool, "pulse")

        def complete_with_evidence(task, tool_name: str) -> None:
            work_tree.record_task_evidence(
                branch_id=branch.branch_id,
                task_id=task.task_id,
                tool_name=tool_name,
                tool_args=[],
                result=f"{tool_name} result",
            )
            work_tree.mark_task_complete(task.task_id)

        complete_with_evidence(first_tasks[0], "pulse")
        self.service.ingest_status_snapshot(status_payload)

        branch = self._signal_branches()[0]
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        open_tasks = [task for task in tasks if task.status != work_tree.TaskStatus.COMPLETE]
        self.assertEqual(len(tasks), 2)
        self.assertEqual(len(open_tasks), 1)
        self.assertIn("Find memory_health_payload", open_tasks[0].title)
        self.assertEqual(branch.preferred_tool, "find")

        complete_with_evidence(open_tasks[0], "find")
        self.service.ingest_status_snapshot(status_payload)

        branch = self._signal_branches()[0]
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        open_tasks = [task for task in tasks if task.status != work_tree.TaskStatus.COMPLETE]
        self.assertEqual(len(tasks), 3)
        self.assertEqual(len(open_tasks), 1)
        self.assertIn("Find append_memory_event", open_tasks[0].title)
        self.assertEqual(branch.preferred_tool, "find")

        complete_with_evidence(open_tasks[0], "find")
        self.service.ingest_status_snapshot(status_payload)

        branch = self._signal_branches()[0]
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        open_tasks = [task for task in tasks if task.status != work_tree.TaskStatus.COMPLETE]
        self.assertEqual(len(tasks), 4)
        self.assertEqual(len(open_tasks), 1)
        self.assertIn("Read memory/bootstrap_origin.json", open_tasks[0].title)
        self.assertEqual(branch.preferred_tool, "read")

        complete_with_evidence(open_tasks[0], "read")
        self.service.ingest_status_snapshot(status_payload)

        branch = self._signal_branches()[0]
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        open_tasks = [task for task in tasks if task.status != work_tree.TaskStatus.COMPLETE]
        self.assertEqual(len(tasks), 5)
        self.assertEqual(len(open_tasks), 1)
        self.assertIn("Synthesize memory bootstrap judgment", open_tasks[0].title)
        self.assertEqual(branch.preferred_tool, "memory_bootstrap_judgment")

        complete_with_evidence(open_tasks[0], "memory_bootstrap_judgment")
        self.service.ingest_status_snapshot(status_payload)

        branch = self._signal_branches()[0]
        tasks = work_tree.list_branch_tasks(branch.branch_id)
        open_tasks = [task for task in tasks if task.status != work_tree.TaskStatus.COMPLETE]
        self.assertEqual(len(tasks), 6)
        self.assertEqual(len(open_tasks), 1)
        self.assertEqual(open_tasks[0].status, work_tree.TaskStatus.BLOCKED)
        self.assertIn("memory bootstrap origin contract", open_tasks[0].title)
        self.assertEqual(branch.status, work_tree.BranchStatus.BLOCKED)
        self.assertIsNone(branch.preferred_tool)
        self.assertEqual(branch.allowed_tools, [])

    def test_memory_health_updates_stale_blocked_origin_reason(self) -> None:
        status_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "memory_enabled": True,
            "memory_health_status": "watch",
            "memory_health_issue_count": 1,
            "memory_health_issues": [{"code": "identity_missing", "detail": "missing identity"}],
            "memory_health": {
                "status": "watch",
                "issue_count": 1,
                "bootstrap": {"memory_enabled": True, "status": "incomplete", "missing": ["identity"]},
            },
        }

        self.service.ingest_status_snapshot(status_payload)
        branch = self._signal_branches()[0]
        for task in work_tree.list_branch_tasks(branch.branch_id):
            work_tree.mark_task_complete(task.task_id)
        stale = work_tree.add_task_to_branch(
            branch.branch_id,
            "Await operator-confirmed memory bootstrap origin contract before writing identity facts",
            meta={"blocked_reason": "memory_bootstrap_origin_contract_required"},
        )
        work_tree.mark_task_blocked(stale.task_id, "memory_bootstrap_origin_contract_required")

        pending_origin_payload = dict(status_payload)
        pending_origin_payload["memory_health"] = {
            "status": "watch",
            "issue_count": 3,
            "bootstrap": {
                "memory_enabled": True,
                "status": "waiting_for_origin_confirmation",
                "missing": ["identity"],
                "origin_status": "pending_operator_confirmation",
            },
            "bootstrap_origin": {
                "status": "pending_operator_confirmation",
                "authority": "pending_operator_confirmation",
                "pending_slots": ["assistant_name"],
                "path": "C:\\NOVA\\memory\\bootstrap_origin.json",
                "exists": True,
                "valid": True,
            },
        }

        self.service.ingest_status_snapshot(pending_origin_payload)

        blocked = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status == work_tree.TaskStatus.BLOCKED
        ]
        self.assertEqual(len(blocked), 1)
        self.assertIn("operator confirmation of memory bootstrap origin", blocked[0].title)
        self.assertEqual(blocked[0].meta.get("blocked_reason"), "memory_bootstrap_origin_confirmation_pending")

    def test_memory_health_ready_origin_releases_identity_bootstrap_task(self) -> None:
        pending_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "memory_enabled": True,
            "memory_health_status": "watch",
            "memory_health_issue_count": 1,
            "memory_health_issues": [{"code": "identity_missing", "detail": "missing identity"}],
            "memory_health": {
                "status": "watch",
                "issue_count": 1,
                "bootstrap": {
                    "memory_enabled": True,
                    "status": "waiting_for_origin_confirmation",
                    "missing": ["identity", "learned_facts"],
                    "origin_status": "pending_operator_confirmation",
                },
                "bootstrap_origin": {
                    "status": "pending_operator_confirmation",
                    "authority": "pending_operator_confirmation",
                    "pending_slots": ["assistant_name"],
                    "path": "C:\\NOVA\\memory\\bootstrap_origin.json",
                    "exists": True,
                    "valid": True,
                },
            },
        }
        self.service.ingest_status_snapshot(pending_payload)
        branch = self._signal_branches()[0]
        for task in work_tree.list_branch_tasks(branch.branch_id):
            work_tree.mark_task_complete(task.task_id)
        blocked_task = work_tree.add_task_to_branch(
            branch.branch_id,
            "Await operator confirmation of memory bootstrap origin before writing identity facts",
            meta={"blocked_reason": "memory_bootstrap_origin_confirmation_pending"},
        )
        work_tree.mark_task_blocked(blocked_task.task_id, "memory_bootstrap_origin_confirmation_pending")

        ready_payload = dict(pending_payload)
        ready_payload["memory_health"] = {
            "status": "watch",
            "issue_count": 2,
            "bootstrap": {
                "memory_enabled": True,
                "status": "incomplete",
                "missing": ["identity", "learned_facts"],
                "origin_status": "ready",
            },
            "bootstrap_origin": {
                "status": "ready",
                "authority": "operator_confirmed",
                "pending_slots": [],
                "may_seed_identity_facts": True,
                "path": "C:\\NOVA\\memory\\bootstrap_origin.json",
                "exists": True,
                "valid": True,
            },
        }
        self.service.ingest_status_snapshot(ready_payload)

        branch = self._signal_branches()[0]
        open_tasks = [
            task for task in work_tree.list_branch_tasks(branch.branch_id)
            if task.status not in {work_tree.TaskStatus.COMPLETE, work_tree.TaskStatus.DROPPED}
        ]
        self.assertEqual(len(open_tasks), 1)
        self.assertEqual(open_tasks[0].status, work_tree.TaskStatus.OPEN)
        self.assertIn("Apply operator-confirmed memory identity bootstrap", open_tasks[0].title)
        self.assertEqual(branch.preferred_tool, "memory_identity_bootstrap")
        self.assertEqual(branch.allowed_tools, ["memory_identity_bootstrap"])

    def test_status_snapshot_uses_stable_regression_branch_identity(self) -> None:
        first = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "autonomy_maintenance": {
                    "last_regression_status": "FAILED",
                    "last_regression_stale": False,
                },
            }
        )
        second = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "autonomy_maintenance": {
                    "last_regression_status": "failed: tests.test_runtime_recovery",
                    "last_regression_stale": False,
                },
            }
        )

        created = [item for item in first if str(item.get("action") or "") == "created"]
        updated = [item for item in second if str(item.get("action") or "") == "updated"]
        self.assertEqual(len(created), 1)
        self.assertEqual(len(updated), 1)
        self.assertEqual(created[0].get("branch_id"), updated[0].get("branch_id"))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_key or ""), "regression_failure:test_ecosystem:regression_failure:daily_regression")
        self.assertEqual(str((branch.source_payload or {}).get("last_regression_status") or ""), "failed: tests.test_runtime_recovery")

    def test_sync_status_snapshot_resolves_release_readiness_branch_when_ready(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "release_status": {
                    "ok": True,
                    "latest_state": "built-only",
                    "latest_readiness_state": "needs-promotion",
                    "latest_ready_to_ship": False,
                    "latest_artifact_name": "nova-rc.zip",
                    "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
                },
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "release_status": {
                    "ok": True,
                    "latest_state": "promoted-pass",
                    "latest_readiness_state": "ready",
                    "latest_ready_to_ship": True,
                    "latest_artifact_name": "nova-rc.zip",
                    "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
                },
            }
        )

        resolved = [item for item in results if str(item.get("action") or "") == "resolved"]
        self.assertEqual(len(resolved), 1)
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "release")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)

    def test_reopened_blocked_release_signal_restores_observing_resolution(self) -> None:
        blocked_payload = {
            "alerts": [],
            "self_check_pass_ratio": 1.0,
            "release_status": {
                "ok": True,
                "latest_state": "built-only",
                "latest_readiness_state": "needs-promotion",
                "latest_ready_to_ship": False,
                "latest_artifact_name": "nova-rc.zip",
                "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
            },
        }
        self.service.sync_status_snapshot(blocked_payload)
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "release_status": {
                    "ok": True,
                    "latest_state": "promoted-pass",
                    "latest_readiness_state": "ready",
                    "latest_ready_to_ship": True,
                    "latest_artifact_name": "nova-rc.zip",
                    "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
                },
            }
        )

        results = self.service.sync_status_snapshot(blocked_payload)

        self.assertTrue(any(item.get("action") == "reopened" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.actionability or ""), "safe_now")
        self.assertEqual(str(branch.resolution_state or ""), "open")
        self.assertNotIn("Resolution:", str(branch.notes or ""))

    def test_partial_status_snapshot_does_not_resolve_absent_surfaces(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "release_status": {
                    "ok": True,
                    "latest_state": "built-only",
                    "latest_readiness_state": "needs-promotion",
                    "latest_ready_to_ship": False,
                    "latest_artifact_name": "nova-rc.zip",
                    "latest_artifact_path": "C:\\NOVA\\runtime\\exports\\release_packages\\nova-rc.zip",
                },
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "autonomy_maintenance": {
                    "last_regression_status": "OK",
                    "last_regression_stale": False,
                },
            }
        )

        self.assertFalse(any(item.get("action") == "resolved" for item in results))
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "release")
        self.assertNotEqual(str(branch.resolution_state or ""), "resolved")

    def test_sync_status_snapshot_resolves_regression_branch_when_stale(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "autonomy_maintenance": {
                    "last_regression_status": "FAILED",
                    "last_regression_stale": False,
                },
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "autonomy_maintenance": {
                    "last_regression_status": "FAILED",
                    "last_regression_stale": True,
                },
            }
        )

        resolved = [item for item in results if str(item.get("action") or "") == "resolved"]
        self.assertEqual(len(resolved), 1)
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.work_class or ""), "regression_failure")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)
        self.assertIn("Regression failure aged stale", str(branch.notes or ""))

    def test_sync_status_snapshot_resolves_memory_health_branch_when_ready(self) -> None:
        self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "memory_enabled": True,
                "memory_health_status": "watch",
                "memory_health_issue_count": 1,
                "memory_health_issues": [{"code": "identity_missing", "detail": "missing identity"}],
                "memory_health": {
                    "status": "watch",
                    "issue_count": 1,
                    "bootstrap": {"memory_enabled": True, "status": "incomplete", "missing": ["identity"]},
                },
            }
        )

        results = self.service.sync_status_snapshot(
            {
                "alerts": [],
                "self_check_pass_ratio": 1.0,
                "memory_enabled": True,
                "memory_health_status": "ok",
                "memory_health_issue_count": 0,
                "memory_health_issues": [],
                "memory_health": {
                    "status": "ok",
                    "issue_count": 0,
                    "bootstrap": {"memory_enabled": True, "status": "ready", "missing": []},
                },
            }
        )

        resolved = [item for item in results if str(item.get("action") or "") == "resolved"]
        self.assertEqual(len(resolved), 1)
        branch = self._signal_branches()[0]
        self.assertEqual(str(branch.source_type or ""), "memory_identity")
        self.assertEqual(str(branch.resolution_state or ""), "resolved")
        self.assertEqual(branch.status, work_tree.BranchStatus.COMPLETE)

    def test_created_signal_branch_gets_explicit_tool_assignment(self) -> None:
        signal = {
            "source": "control_status",
            "signal_class": "runtime_failure",
            "title": "Inspect runtime heartbeat drift",
            "fingerprint": {
                "class": "runtime_failure",
                "surface": "control_status",
                "error": "heartbeat_drift",
                "symbol": "core_heartbeat",
            },
            "payload": {"alert": "heartbeat drift"},
            "severity": "high",
            "actionability": "safe_now",
            "allowed_tools": ["pulse"],
            "preferred_tool": "pulse",
            "next_task": "check runtime heartbeat and queue status",
        }

        result = self.service.ingest_signal(signal)

        self.assertEqual(result.get("action"), "created")
        branch = self._signal_branches()[0]
        self.assertTrue(str(branch.preferred_tool or "").strip())
        self.assertEqual(branch.allowed_tools, [branch.preferred_tool])


if __name__ == "__main__":
    unittest.main()
