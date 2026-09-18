"""White-box admission kernel tests. Not live Nova proof."""
from __future__ import annotations

import copy
import unittest

from research.work_admission.frozen_traces import (
    DEFAULT_POLICY,
    EXPECTED_EXPERIMENT,
    LABEL,
    experiment_cases,
    proposal_p_causal,
    proposal_p_cover,
    proposal_q,
    snapshot_for,
    FP_P_T0,
    T0_STAMP,
)
from research.work_admission.inspect_recorder import compare_decision, record_experiment
from research.work_admission.kernel import evaluate_admission


class TestWorkAdmissionKernelExperiment(unittest.TestCase):
    def test_label_is_white_box_not_live_proof(self) -> None:
        self.assertIn("white-box", LABEL)
        self.assertIn("not live", LABEL.lower())

    def test_kernel_does_not_mutate_inputs(self) -> None:
        name, proposal, snapshot, policy = experiment_cases()[1]
        p2, s2, pol2 = copy.deepcopy(proposal), copy.deepcopy(snapshot), copy.deepcopy(policy)
        evaluate_admission(proposal, snapshot, policy)
        self.assertEqual(proposal, p2)
        self.assertEqual(snapshot, s2)
        self.assertEqual(policy, pol2)

    def test_kernel_does_not_import_work_tree_or_runtime(self) -> None:
        import research.work_admission.kernel as kernel_mod
        with open(kernel_mod.__file__, encoding="utf-8") as handle:
            src = handle.read()
        self.assertNotIn("import work_tree", src)
        self.assertNotIn("from work_tree", src)
        self.assertNotIn("nova_runtime_context", src)
        self.assertNotIn("openai", src.lower())

    def test_frozen_experiment_table(self) -> None:
        failures = []
        for name, proposal, snapshot, policy in experiment_cases():
            actual = evaluate_admission(proposal, snapshot, policy)
            expected = EXPECTED_EXPERIMENT[name]
            cmp_ = compare_decision(actual, expected)
            if not cmp_["match"]:
                failures.append((name, cmp_["diffs"], actual.get("reason_codes"), actual.get("work_decision")))
        if failures:
            lines = [f"{n}: {d} actual_codes={c} work={w}" for n, d, c, w in failures]
            self.fail("frozen_table_mismatch (do not edit traces; preserve failure):\n" + "\n".join(lines))

    def test_inspect_recorder_does_not_change_decisions(self) -> None:
        report = record_experiment()
        self.assertTrue(report["not_live_nova_proof"])
        self.assertEqual(report["inspect_role"], "recorder_compare_only")
        self.assertEqual(report["failed_count"], 0, report["failed_cases"])


class TestWorkAdmissionSection13(unittest.TestCase):
    def test_unauthorized_tool_admits_work_denies_tool(self) -> None:
        proposal = proposal_p_causal(request_id="s13-tool-denied")
        snapshot = snapshot_for(FP_P_T0, current_time=T0_STAMP)
        policy = copy.deepcopy(DEFAULT_POLICY)
        policy["tool_policy"]["allowed_tools"] = ["read"]
        decision = evaluate_admission(proposal, snapshot, policy)
        self.assertEqual(decision["work_decision"], "admitted")
        self.assertEqual(decision["authority_decision"], "tool_denied")
        self.assertEqual(decision["execution_eligibility"], "not_executable")
        self.assertIn("TOOL_NOT_AUTHORIZED", decision["reason_codes"])
        self.assertTrue(decision["materialized"] is False)

    def test_ambiguous_target_needs_clarification(self) -> None:
        proposal = proposal_p_causal(request_id="s13-ambiguous")
        proposal["target"]["target_id"] = ""
        proposal["target"]["target_fingerprint"] = ""
        snapshot = snapshot_for(FP_P_T0, current_time=T0_STAMP)
        decision = evaluate_admission(proposal, snapshot, DEFAULT_POLICY)
        self.assertEqual(decision["work_decision"], "needs_clarification")
        self.assertIn("TARGET_NOT_IDENTIFIED", decision["reason_codes"])

    def test_unobservable_completion_needs_clarification(self) -> None:
        proposal = proposal_p_causal(request_id="s13-unobs")
        proposal["target"]["satisfaction_state"]["observable_checks"] = []
        snapshot = snapshot_for(FP_P_T0, current_time=T0_STAMP)
        decision = evaluate_admission(proposal, snapshot, DEFAULT_POLICY)
        self.assertEqual(decision["work_decision"], "needs_clarification")
        self.assertIn("COMPLETION_NOT_OBSERVABLE", decision["reason_codes"])

    def test_stale_evidence_needs_clarification(self) -> None:
        proposal = proposal_p_causal(request_id="s13-stale")
        snapshot = snapshot_for(FP_P_T0, current_time=T0_STAMP)
        snapshot["evidence"][0]["stale"] = True
        decision = evaluate_admission(proposal, snapshot, DEFAULT_POLICY)
        self.assertEqual(decision["work_decision"], "needs_clarification")
        self.assertIn("EVIDENCE_STALE", decision["reason_codes"])

    def test_actor_not_authorized(self) -> None:
        proposal = proposal_p_causal(request_id="s13-actor")
        snapshot = snapshot_for(FP_P_T0, current_time=T0_STAMP)
        policy = copy.deepcopy(DEFAULT_POLICY)
        policy["actor_authority"]["allowed_actor_ids"] = ["someone-else"]
        decision = evaluate_admission(proposal, snapshot, policy)
        self.assertEqual(decision["work_decision"], "admitted")
        self.assertEqual(decision["authority_decision"], "actor_denied")
        self.assertIn("ACTOR_NOT_AUTHORIZED", decision["reason_codes"])

    def test_empty_read_is_cover_not_tool_failed(self) -> None:
        proposal = proposal_p_cover(request_id="s13-cover")
        snapshot = snapshot_for(FP_P_T0, current_time=T0_STAMP)
        decision = evaluate_admission(proposal, snapshot, DEFAULT_POLICY)
        self.assertEqual(decision["work_decision"], "rejected")
        self.assertIn("COVER_OR_GOAL_SUBSTITUTION", decision["reason_codes"])
        self.assertNotEqual(decision["work_decision"], "tool_failed")

    def test_q_is_no_actionable_target_not_rejected(self) -> None:
        proposal = proposal_q(request_id="s13-q")
        snapshot = snapshot_for(FP_P_T0, current_time=T0_STAMP)
        decision = evaluate_admission(proposal, snapshot, DEFAULT_POLICY)
        self.assertEqual(decision["work_decision"], "no_actionable_target")
        self.assertIn("NO_ACTIONABLE_STEP", decision["reason_codes"])
