from __future__ import annotations

import shutil
import unittest
import uuid
from unittest import mock
from pathlib import Path

import work_tree
from services.work_tree_signal_ingestion import WorkTreeSignalIngestionService, _branch_why_summary


WORK_TMP_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "pytest_temp"


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

    def test_repeated_signal_update_rebalances_stale_branch_tool(self) -> None:
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
        self.assertEqual(branch.preferred_tool, "find")
        self.assertEqual(branch.allowed_tools, ["find"])

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
            "alerts": ["error_spike on /api/control/status", "ollama_api unreachable"],
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
            "next_task": "check runtime heartbeat and queue status",
        }

        result = self.service.ingest_signal(signal)

        self.assertEqual(result.get("action"), "created")
        branch = self._signal_branches()[0]
        self.assertTrue(str(branch.preferred_tool or "").strip())
        self.assertEqual(branch.allowed_tools, [branch.preferred_tool])


if __name__ == "__main__":
    unittest.main()
